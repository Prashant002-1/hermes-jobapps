from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes_jobapps import intake, sources
from hermes_jobapps.workspace import AmbiguousReference, Workspace, section


GREENHOUSE_URL = "https://boards.greenhouse.io/northstar/jobs/123"
ENV = {"EXA_API_KEY": "test-key"}

POSTING = """About the role
Northstar builds scheduling tools for field teams. This is a hybrid role with three days per week in the office.

What you'll do
- Build and maintain the APIs that power dispatch planning.
- Work with designers to ship features end to end.

Requirements
- 3+ years of experience building production web services.
- Proficiency in Python and SQL.
- Clear written communication.

Benefits
- Health coverage and a learning budget.

The salary range for this role is $120,000 - $150,000 per year.
"""

GREENHOUSE_CONTENT = (
    "<p>Northstar builds scheduling tools for field teams across three regions.</p>"
    "<h3>What you'll do</h3><ul><li>Build and maintain the APIs that power dispatch planning.</li></ul>"
    "<h3>Requirements</h3><ul><li>3+ years of experience building production web services.</li>"
    "<li>Proficiency in Python and SQL.</li></ul>"
    "<p>We are unable to sponsor visas for this role.</p>"
)


def setUpModule() -> None:
    for name in ("urlopen", "_run_command"):
        patcher = mock.patch.object(sources, name, side_effect=AssertionError(f"tests must not reach {name}"))
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


def greenhouse_fetch(url: str) -> dict:
    return {
        "title": "Applied AI Engineer",
        "location": {"name": "Denver, CO"},
        "absolute_url": GREENHOUSE_URL,
        "content": GREENHOUSE_CONTENT,
        "questions": [
            {"label": "Will you require sponsorship?", "required": True, "fields": [{"type": "boolean"}]},
            {"label": "Portfolio link", "required": False, "fields": [{"type": "input_text"}]},
        ],
        "pay_input_ranges": [{"title": "Base salary", "min_cents": 10000000, "max_cents": 14000000, "currency_type": "USD"}],
    }


def no_fetch(url: str) -> dict:
    raise AssertionError(f"unexpected fetch: {url}")


def settings_with(*, needs_sponsorship=None, blockers=None, intent="apply") -> dict:
    return {
        "rules": {"needs_sponsorship": needs_sponsorship, "pasted_job_intent": intent},
        "criteria": {"blockers": list(blockers or [])},
    }


def job(description: str, *, title: str = "Software Engineer", location: str = "") -> dict:
    return {"title": title, "company": "Northstar", "location": location, "description": description}


class PreflightTests(unittest.TestCase):
    def test_sponsorship_is_tri_state(self) -> None:
        posting = job("Build internal tools. We are unable to sponsor visas for this role. Join a small team.")

        needed = intake.preflight(posting, settings_with(needs_sponsorship=True))
        self.assertEqual(needed["decision"], "skip")
        self.assertEqual(
            needed["blockers"],
            [
                {
                    "area": "sponsorship",
                    "severity": "blocker",
                    "evidence": "We are unable to sponsor visas for this role.",
                    "action": intake.SPONSORSHIP_ACTION,
                }
            ],
        )
        self.assertEqual(needed["facts"]["sponsorship"], "denied")

        unknown = intake.preflight(posting, settings_with(needs_sponsorship=None))
        self.assertEqual((unknown["decision"], unknown["blockers"], unknown["clear"]), ("apply", [], []))
        self.assertEqual(unknown["facts"]["sponsorship"], "denied")

        ignored = intake.preflight(posting, settings_with(needs_sponsorship=False))
        self.assertEqual((ignored["decision"], ignored["blockers"], ignored["clear"]), ("apply", [], []))
        self.assertNotIn("sponsorship", ignored["facts"])

    def test_sponsorship_offer_is_clear_and_silence_is_unstated(self) -> None:
        offered = intake.preflight(
            job("Build internal tools. Visa sponsorship is available for this role."),
            settings_with(needs_sponsorship=True),
        )
        self.assertEqual(offered["decision"], "apply")
        self.assertEqual(offered["blockers"], [])
        self.assertEqual(
            offered["clear"],
            [{"area": "sponsorship", "evidence": "Visa sponsorship is available for this role."}],
        )
        self.assertEqual(offered["facts"]["sponsorship"], "offered")

        silent = intake.preflight(job("Build internal tools for dispatch."), settings_with(needs_sponsorship=True))
        self.assertEqual((silent["decision"], silent["facts"]["sponsorship"]), ("apply", "unstated"))

    def test_built_in_sponsorship_phrases(self) -> None:
        denied = (
            "No visa sponsorship for this position.",
            "We are unable to sponsor candidates.",
            "We are not able to sponsor work visas.",
            "We cannot sponsor visas.",
            "The company will not sponsor applicants.",
            "Must be authorized to work in the U.S. without sponsorship now or in the future.",
            "You must be a U.S. citizen.",
            "US citizenship required.",
            "An active security clearance is needed.",
            "We do not offer sponsorship.",
            "Sponsorship is not available.",
            "We can’t provide visa sponsorship.",
            "No visa\n  sponsorship is offered.",
        )
        offered = (
            "Visa sponsorship available.",
            "We will sponsor the right candidate.",
            "Sponsorship is available.",
            "We are open to sponsorship.",
        )
        unstated = (
            "No security clearance required.",
            "Our sponsors fund community events.",
            "Will you now or in the future require sponsorship?",
        )
        for expected, phrases in (("denied", denied), ("offered", offered), ("unstated", unstated)):
            for phrase in phrases:
                with self.subTest(phrase=phrase):
                    result = intake.preflight(job(f"Build tools. {phrase} Join us."), settings_with(needs_sponsorship=True))
                    self.assertEqual(result["facts"]["sponsorship"], expected)
                    self.assertEqual(result["decision"], "skip" if expected == "denied" else "apply")

    def test_denial_wins_over_offer_and_evidence_keeps_the_sentence(self) -> None:
        result = intake.preflight(
            job("Sponsorship is available for some teams. Must be authorized to work in the U.S. without sponsorship."),
            settings_with(needs_sponsorship=True),
        )
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["clear"], [])
        self.assertEqual(
            result["blockers"][0]["evidence"],
            "Must be authorized to work in the U.S. without sponsorship.",
        )

    def test_pattern_criteria_match_title_location_and_description(self) -> None:
        blockers = [
            {
                "area": "location",
                "type": "pattern",
                "patterns": ["relocation required", "on-site only"],
                "severity": "flag",
                "action": "Ask whether relocating is acceptable.",
            },
            {"area": "location", "type": "pattern", "patterns": ["denver"], "severity": "clear"},
            {"area": "domain", "type": "pattern", "patterns": ["DEFENSE"], "severity": "blocker", "action": "Skip."},
        ]
        result = intake.preflight(
            job("Build planning tools.\nThis role is On-Site   Only at our office. Relocation required.", location="Denver, CO"),
            settings_with(blockers=blockers),
        )
        self.assertEqual(result["decision"], "pending")
        self.assertEqual(
            result["blockers"],
            [
                {
                    "area": "location",
                    "severity": "flag",
                    "evidence": "Relocation required.",
                    "action": "Ask whether relocating is acceptable.",
                }
            ],
        )
        self.assertEqual(result["clear"], [{"area": "location", "evidence": "Denver, CO"}])

        blocked = intake.preflight(job("Build tools.", title="Defense Systems Engineer"), settings_with(blockers=blockers))
        self.assertEqual(blocked["decision"], "skip")
        self.assertEqual(blocked["blockers"][0]["evidence"], "Defense Systems Engineer")
        self.assertEqual(blocked["blockers"][0]["action"], "Skip.")

    def test_title_criteria_only_read_the_title(self) -> None:
        blockers = [{"area": "seniority", "type": "title", "patterns": ["staff", "principal"], "severity": "blocker", "action": "Reach role."}]
        hit = intake.preflight(job("Build tools.", title="Principal Engineer"), settings_with(blockers=blockers))
        self.assertEqual(hit["decision"], "skip")
        self.assertEqual(hit["blockers"][0]["evidence"], "Principal Engineer")
        miss = intake.preflight(
            job("You will work with staff engineers and report to a principal engineer."),
            settings_with(blockers=blockers),
        )
        self.assertEqual((miss["decision"], miss["blockers"]), ("apply", []))

    def test_years_criteria_use_the_threshold(self) -> None:
        blockers = [{"area": "seniority", "type": "years", "threshold": 5, "severity": "blocker", "action": "Too senior."}]
        cases = (
            ("We were founded 12 years ago. You have 5+ years of experience shipping software.", 5, "skip"),
            ("Requires 3-5 years of experience. 2 years with Python.", 3, "apply"),
            ("At least 7 yrs building APIs.", 7, "skip"),
            ("Over the past 10 years we grew quickly. No minimum experience.", None, "apply"),
        )
        for description, years, decision in cases:
            with self.subTest(description=description):
                result = intake.preflight(job(description), settings_with(blockers=blockers))
                self.assertEqual(result["facts"].get("years_required"), years)
                self.assertEqual(result["decision"], decision)
        blocked = intake.preflight(job(cases[0][0]), settings_with(blockers=blockers))
        self.assertEqual(
            blocked["blockers"],
            [
                {
                    "area": "seniority",
                    "severity": "blocker",
                    "evidence": "You have 5+ years of experience shipping software.",
                    "action": "Too senior.",
                }
            ],
        )
        flagged = intake.preflight(job(cases[0][0]), settings_with(blockers=[{**blockers[0], "severity": "flag"}]))
        self.assertEqual(flagged["decision"], "pending")

    def test_decision_rules(self) -> None:
        flag = {"area": "effort", "type": "pattern", "patterns": ["take-home"], "severity": "flag"}
        blocker = {"area": "domain", "type": "pattern", "patterns": ["gambling"], "severity": "blocker"}
        clear = {"area": "level", "type": "pattern", "patterns": ["early career"], "severity": "clear"}
        text = "An early career role at a gambling company with a take-home exercise."
        self.assertEqual(intake.preflight(job(text), settings_with(blockers=[flag, blocker, clear]))["decision"], "skip")
        self.assertEqual(intake.preflight(job(text), settings_with(blockers=[flag, clear]))["decision"], "pending")
        self.assertEqual(intake.preflight(job(text), settings_with(blockers=[clear]))["decision"], "apply")
        self.assertEqual(intake.preflight(job(text), settings_with(blockers=[clear], intent="review"))["decision"], "pending")
        self.assertEqual(intake.preflight(job(text), {})["decision"], "apply")
        only_clear = intake.preflight(job(text), settings_with(blockers=[clear]))
        self.assertEqual(only_clear["clear"], [{"area": "level", "evidence": text}])

    def test_invalid_criteria_fail_visibly(self) -> None:
        cases = (
            [{"area": "x", "type": "regex", "patterns": ["a"]}],
            [{"area": "x", "type": "pattern", "patterns": ["a"], "severity": "fatal"}],
            [{"area": "x", "type": "years", "threshold": "five"}],
            [{"area": "x", "type": "pattern", "patterns": []}],
            ["remote"],
        )
        for blockers in cases:
            with self.subTest(blockers=blockers):
                with self.assertRaisesRegex(ValueError, r"criteria\.blockers\[0\]"):
                    intake.preflight(job("Build tools."), settings_with(blockers=blockers))

    def test_facts(self) -> None:
        result = intake.preflight(job(POSTING), settings_with())
        self.assertEqual(
            result["facts"],
            {
                "years_required": 3,
                "workplace": "hybrid",
                "salary": "$120,000 - $150,000 per year",
                "sponsorship": "unstated",
            },
        )
        remote = intake.preflight(
            job("This is a full-time position. We raised $20M last year. Pay: $55 - $70 per hour.", location="Remote (US)"),
            settings_with(needs_sponsorship=False),
        )
        self.assertEqual(remote["facts"], {"workplace": "remote", "employment_type": "full-time", "salary": "$55 - $70 per hour"})
        intern = intake.preflight(
            job("Join the team on-site.", title="Software Engineering Intern", location="On-site, Austin"),
            settings_with(needs_sponsorship=False),
        )
        self.assertEqual(intern["facts"], {"workplace": "onsite", "employment_type": "internship"})
        hinted = intake.preflight(
            {**job("Work remotely on anything."), "workplace": "onsite", "employment_type": "contract", "salary": "$90K"},
            settings_with(needs_sponsorship=False),
        )
        self.assertEqual(hinted["facts"], {"workplace": "onsite", "employment_type": "contract", "salary": "$90K"})
        self.assertEqual(intake.preflight(job("Build tools."), settings_with(needs_sponsorship=False))["facts"], {})

    def test_salary_extraction(self) -> None:
        cases = (
            ("Comp: $120k-$160k plus equity.", "$120k-$160k"),
            ("We raised $500K last spring. Base salary $95,000.", "$95,000"),
            ("Earn from $90K to $110K a year.", "$90K to $110K a year"),
            ("OTE $200K–$250K.", "$200K–$250K"),
            ("Contract pay is $60/hr.", "$60/hr"),
            ("We raised $20M and manage $1,000,000,000.", None),
            ("Everyone gets a $50 - $75 gift card.", None),
        )
        for description, expected in cases:
            with self.subTest(description=description):
                facts = intake.preflight(job(description), settings_with(needs_sponsorship=False))["facts"]
                self.assertEqual(facts.get("salary"), expected)

    def test_requirements_come_from_headed_sections(self) -> None:
        result = intake.preflight(job(POSTING), settings_with())
        self.assertEqual(
            result["requirements"],
            [
                "3+ years of experience building production web services.",
                "Proficiency in Python and SQL.",
                "Clear written communication.",
                "Build and maintain the APIs that power dispatch planning.",
                "Work with designers to ship features end to end.",
            ],
        )

    def test_requirement_heading_shapes(self) -> None:
        text = (
            "## What You’ll Do\n"
            "1. Design the ingestion service for partner data.\n"
            "**Minimum Qualifications:**\n"
            "• Experience with PostgreSQL at scale.\n"
            "• Experience with PostgreSQL at scale.\n"
            "• Bonus points:\n"
            "You have: A habit of writing things down. Comfort with ambiguity!\n"
            "About Northstar\n"
            "We must mention that experience here is not a requirement line.\n"
        )
        self.assertEqual(
            intake.extract_requirements(text),
            [
                "Experience with PostgreSQL at scale.",
                "A habit of writing things down.",
                "Comfort with ambiguity!",
                "Design the ingestion service for partner data.",
            ],
        )

    def test_requirements_fall_back_to_keyword_sentences(self) -> None:
        text = (
            "Northstar builds scheduling tools. You must enjoy working with customers. "
            "Experience building production APIs is required. We have snacks. "
            "Proficiency in Python matters. You must enjoy working with customers."
        )
        self.assertEqual(
            intake.extract_requirements(text),
            [
                "You must enjoy working with customers.",
                "Experience building production APIs is required.",
                "Proficiency in Python matters.",
            ],
        )
        self.assertEqual(intake.extract_requirements("We have snacks. Join us."), [])
        self.assertEqual(
            intake.extract_requirements("We build agents. Requirements: Experience building production APIs. We have snacks."),
            ["Experience building production APIs."],
        )

    def test_requirements_are_bounded_and_clipped(self) -> None:
        bullets = "\n".join(f"- Requirement number {index} with experience in area {index}." for index in range(14))
        long_bullet = "- " + "Experience with very long descriptions " * 12
        found = intake.preflight(job(f"Requirements\n{long_bullet}\n{bullets}"), settings_with())["requirements"]
        self.assertEqual(len(found), 10)
        self.assertLessEqual(len(found[0]), 300)
        self.assertGreater(len(found[0]), 290)
        self.assertTrue(found[0].endswith("…"))


class WorkspaceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmp.name) / "ws")
        self.ws.init(name="Jordan Example")

    def tearDown(self) -> None:
        self.tmp.cleanup()


class AddJobTests(WorkspaceCase):
    def test_pasted_text_creates_a_job_with_rendered_sections(self) -> None:
        self.ws.save_settings(
            {
                "rules": {"needs_sponsorship": True},
                "criteria": {
                    "blockers": [
                        {"area": "location", "type": "pattern", "patterns": ["hybrid"], "severity": "flag", "action": "Confirm the commute."},
                        {"area": "stack", "type": "pattern", "patterns": ["python"], "severity": "clear"},
                    ]
                },
            }
        )
        text = POSTING + "\nWe will sponsor visas for this role.\n"
        result = intake.add_job(
            self.ws,
            text=text,
            company="Northstar",
            title="Software Engineer",
            location="Denver, CO",
            url="https://northstar.example/careers/42?utm_source=feed",
            notes="Referred by a friend.",
            today="2026-11-10",
        )
        self.assertTrue(result["ok"])
        job_id = "2026-11-northstar-software-engineer"
        folder = self.ws.jobs_dir / job_id
        self.assertEqual(
            result["job"],
            {
                "job": job_id,
                "company": "Northstar",
                "title": "Software Engineer",
                "location": "Denver, CO",
                "stage": "new",
                "folder": str(folder),
                "path": str(folder / "job.md"),
            },
        )
        self.assertEqual(result["preflight"]["decision"], "pending")
        self.assertEqual([item["area"] for item in result["preflight"]["blockers"]], ["location"])
        self.assertEqual(result["preflight"]["facts"]["years_required"], 3)
        self.assertEqual(result["preflight"]["requirements_count"], 5)
        self.assertNotIn("requirements", result["preflight"])
        self.assertEqual(result["next"], "Call jobapps_brief for this job, then write the requested document.")

        doc = self.ws.job_doc(job_id)
        self.assertEqual(doc.meta["decision"], "pending")
        self.assertEqual(doc.meta["source"], "pasted")
        self.assertEqual(doc.meta["status"], "new")
        self.assertEqual(doc.meta["url"], "https://northstar.example/careers/42?utm_source=feed")
        self.assertEqual(doc.meta["created_on"], "2026-11-10")
        self.assertEqual(section(doc.body, "Posting"), text.strip())
        self.assertEqual(
            section(doc.body, "Assessment").splitlines(),
            [
                "- Decision: pending",
                "- Flag (location): This is a hybrid role with three days per week in the office. Action: Confirm the commute.",
                "- Clear (sponsorship): We will sponsor visas for this role.",
                "- Clear (stack): Proficiency in Python and SQL.",
                "- Years required: 3",
                "- Workplace: hybrid",
                "- Salary: $120,000 - $150,000 per year",
                "- Sponsorship: offered",
            ],
        )
        self.assertEqual(
            section(doc.body, "Requirements").splitlines(),
            [
                "- 3+ years of experience building production web services.",
                "- Proficiency in Python and SQL.",
                "- Clear written communication.",
                "- Build and maintain the APIs that power dispatch planning.",
                "- Work with designers to ship features end to end.",
            ],
        )
        self.assertEqual(section(doc.body, "Notes"), "Referred by a friend.")
        self.assertIn("2026-11-10: Added.", section(doc.body, "Log"))
        self.assertNotIn("## Application questions", doc.body)

    def test_blocker_skips_and_empty_sections_are_omitted(self) -> None:
        self.ws.save_settings({"rules": {"needs_sponsorship": True}})
        text = "Northstar is hiring. " * 12 + "We cannot sponsor visas."
        result = intake.add_job(self.ws, text=text, company="Northstar", title="Analyst")
        self.assertEqual(result["preflight"]["decision"], "skip")
        self.assertEqual(result["preflight"]["requirements_count"], 0)
        self.assertEqual(result["next"], "A configured blocker matched. Tell the user and ask whether to skip or proceed.")
        doc = self.ws.job_doc(result["job"]["job"])
        self.assertEqual(doc.meta["decision"], "skip")
        self.assertEqual(doc.meta["status"], "new")
        self.assertNotIn("## Requirements", doc.body)
        self.assertEqual(
            section(doc.body, "Assessment").splitlines(),
            [
                "- Decision: skip",
                f"- Blocker (sponsorship): We cannot sponsor visas. Action: {intake.SPONSORSHIP_ACTION}",
                "- Sponsorship: denied",
            ],
        )

    def test_url_is_hydrated_and_arguments_override(self) -> None:
        calls = []

        def fetch(url: str) -> dict:
            calls.append(url)
            return greenhouse_fetch(url)

        result = intake.add_job(
            self.ws,
            url=GREENHOUSE_URL + "?gh_src=feed",
            title="AI Engineer (Platform)",
            fetch_json=fetch,
            today="2026-11-10",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertIn("boards-api.greenhouse.io/v1/boards/northstar/jobs/123", calls[0])
        self.assertEqual(result["job"]["company"], "Northstar")
        self.assertEqual(result["job"]["title"], "AI Engineer (Platform)")
        self.assertEqual(result["job"]["location"], "Denver, CO")
        self.assertEqual(result["preflight"]["decision"], "apply")
        self.assertEqual(result["preflight"]["facts"]["sponsorship"], "denied")
        self.assertEqual(result["preflight"]["facts"]["salary"], "Base salary: 100,000 - 140,000 USD")
        doc = self.ws.job_doc(result["job"]["job"])
        self.assertEqual(doc.meta["source"], "greenhouse")
        self.assertEqual(doc.meta["url"], GREENHOUSE_URL)
        posting = section(doc.body, "Posting")
        self.assertTrue(posting.startswith("Northstar builds scheduling tools"))
        self.assertNotIn("<", posting)
        self.assertEqual(
            section(doc.body, "Requirements").splitlines(),
            [
                "- 3+ years of experience building production web services.",
                "- Proficiency in Python and SQL.",
                "- Build and maintain the APIs that power dispatch planning.",
            ],
        )
        self.assertEqual(
            section(doc.body, "Application questions").splitlines(),
            ["- Will you require sponsorship? (required, boolean)", "- Portfolio link (optional, input_text)"],
        )

        again = intake.add_job(self.ws, url=GREENHOUSE_URL + "/", fetch_json=no_fetch)
        self.assertEqual(
            again,
            {"ok": True, "duplicate": True, "job": result["job"], "hint": "This job already exists. Continue with it."},
        )
        self.assertEqual(len(self.ws.jobs()), 1)

    def test_unsupported_url_asks_for_the_posting_text(self) -> None:
        result = intake.add_job(self.ws, url="https://northstar.example/careers/42", fetch_json=no_fetch)
        self.assertEqual(
            result,
            {
                "ok": False,
                "needs": "posting_text",
                "hint": "This URL is not a supported ATS page. Fetch the posting with your web tool, then call again with text, company and title (keep url).",
            },
        )
        self.assertEqual(self.ws.jobs(), [])

    def test_failed_hydration_asks_for_the_posting_text(self) -> None:
        def fetch(url: str) -> dict:
            raise RuntimeError("HTTP 404")

        result = intake.add_job(self.ws, url=GREENHOUSE_URL, fetch_json=fetch)
        self.assertEqual((result["ok"], result["needs"]), (False, "posting_text"))
        self.assertIn("HTTP 404", result["error"])
        self.ws.save_settings({"discovery": {"hydrators": ["lever"]}})
        result = intake.add_job(self.ws, url=GREENHOUSE_URL, fetch_json=no_fetch)
        self.assertEqual((result["ok"], result["needs"]), (False, "posting_text"))
        self.assertEqual(self.ws.jobs(), [])

    def test_text_needs_company_and_title(self) -> None:
        expected = {"ok": False, "needs": ["company", "title"], "hint": "Read them from the posting and call again."}
        self.assertEqual(intake.add_job(self.ws, text=POSTING, title="Software Engineer"), expected)
        self.assertEqual(intake.add_job(self.ws, text=POSTING, company="Northstar"), expected)
        self.assertEqual(intake.add_job(self.ws, text=POSTING, company="  ", title="Software Engineer"), expected)
        self.assertEqual(self.ws.jobs(), [])

    def test_short_posting_and_missing_source(self) -> None:
        self.assertEqual(
            intake.add_job(self.ws, text="Build things at Northstar.", company="Northstar", title="Engineer"),
            {"ok": False, "needs": "posting_text", "hint": "Provide the full job description."},
        )
        short = intake.add_job(
            self.ws,
            url=GREENHOUSE_URL,
            fetch_json=lambda url: {"title": "Engineer", "content": "<p>Short.</p>"},
        )
        self.assertEqual(short, {"ok": False, "needs": "posting_text", "hint": "Provide the full job description."})
        empty = intake.add_job(self.ws)
        self.assertEqual((empty["ok"], empty["needs"]), (False, "posting_text"))
        self.assertEqual(self.ws.jobs(), [])

    def test_duplicates_by_url_and_by_company_and_title(self) -> None:
        first = intake.add_job(
            self.ws,
            text=POSTING,
            company="Northstar",
            title="Software Engineer",
            url="https://www.northstar.example/careers/42/",
        )
        by_url = intake.add_job(
            self.ws,
            text=POSTING,
            company="Northstar Labs",
            title="Engineer II",
            url="http://northstar.example/careers/42?utm_campaign=x",
        )
        self.assertEqual(
            by_url,
            {"ok": True, "duplicate": True, "job": first["job"], "hint": "This job already exists. Continue with it."},
        )
        url_only = intake.add_job(self.ws, url="https://northstar.example/careers/42", fetch_json=no_fetch)
        self.assertTrue(url_only["duplicate"])
        by_name = intake.add_job(self.ws, text="Too short to matter.", company=" northstar ", title="SOFTWARE  engineer")
        self.assertTrue(by_name["duplicate"])
        self.assertEqual(by_name["job"]["job"], first["job"]["job"])
        self.assertEqual(len(self.ws.jobs()), 1)

        different = intake.add_job(self.ws, text=POSTING, company="Northstar", title="Data Engineer")
        self.assertNotIn("duplicate", different)
        self.assertEqual(len(self.ws.jobs()), 2)

    def test_inactive_jobs_only_block_by_url(self) -> None:
        first = intake.add_job(self.ws, text=POSTING, company="Northstar", title="Software Engineer", url="https://northstar.example/a")
        for status in ("rejected", "closed", "skipped"):
            with self.subTest(status=status):
                self.ws.update_job(first["job"]["job"], {"status": status})
                same_url = intake.add_job(self.ws, text=POSTING, company="Other", title="Other", url="https://northstar.example/a")
                self.assertTrue(same_url.get("duplicate"))
                self.assertEqual(same_url["job"]["stage"], status)
        reopened = intake.add_job(self.ws, text=POSTING, company="Northstar", title="Software Engineer", url="https://northstar.example/b")
        self.assertNotIn("duplicate", reopened)
        self.assertNotEqual(reopened["job"]["job"], first["job"]["job"])

    def test_lead_promotion(self) -> None:
        lead = self.ws.create_lead(
            company="Fieldwork",
            title="Data Engineer",
            url="https://fieldwork.example/jobs/9",
            location="Remote",
            posting=POSTING,
            source="exa",
        )
        result = intake.add_job(self.ws, lead=lead["id"], notes="From the weekly search.", fetch_json=no_fetch, today="2026-11-10")
        self.assertTrue(result["ok"])
        self.assertEqual(result["job"]["job"], "2026-11-fieldwork-data-engineer")
        self.assertEqual((result["job"]["company"], result["job"]["title"], result["job"]["location"]), ("Fieldwork", "Data Engineer", "Remote"))
        doc = self.ws.job_doc(result["job"]["job"])
        self.assertEqual(doc.meta["source"], "lead")
        self.assertEqual(doc.meta["url"], "https://fieldwork.example/jobs/9")
        self.assertEqual(section(doc.body, "Posting"), POSTING.strip())
        self.assertEqual(section(doc.body, "Notes"), "From the weekly search.")
        promoted = self.ws.resolve_lead(lead["id"])
        self.assertEqual(promoted["status"], "promoted")
        self.assertEqual(promoted["job"], result["job"]["job"])

        again = intake.add_job(self.ws, lead=lead["id"], fetch_json=no_fetch)
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["job"]["job"], result["job"]["job"])
        self.assertEqual(len(self.ws.jobs()), 1)

    def test_lead_with_a_snippet_is_hydrated_or_needs_text(self) -> None:
        thin = self.ws.create_lead(company="Northstar", title="Applied AI Engineer", url=GREENHOUSE_URL, posting="Build agents.")
        other = self.ws.create_lead(company="Fieldwork", title="Analyst", url="https://fieldwork.example/jobs/3", posting="Analyze.")

        needs = intake.add_job(self.ws, lead=other["id"], fetch_json=no_fetch)
        self.assertEqual(needs, {"ok": False, "needs": "posting_text", "hint": "Provide the full job description."})
        self.assertEqual(self.ws.resolve_lead(other["id"])["status"], "new")

        result = intake.add_job(self.ws, lead=thin["id"], fetch_json=greenhouse_fetch)
        self.assertTrue(result["ok"])
        doc = self.ws.job_doc(result["job"]["job"])
        self.assertEqual(doc.meta["source"], "lead")
        self.assertIn("unable to sponsor visas", section(doc.body, "Posting"))
        self.assertEqual(self.ws.resolve_lead(thin["id"])["status"], "promoted")

    def test_lead_errors(self) -> None:
        self.ws.create_lead(company="Northstar", title="Engineer", url="https://northstar.example/1", posting=POSTING)
        self.ws.create_lead(company="Northstar", title="Designer", url="https://northstar.example/2", posting=POSTING)
        with self.assertRaises(KeyError):
            intake.add_job(self.ws, lead="nobody")
        with self.assertRaises(AmbiguousReference):
            intake.add_job(self.ws, lead="northstar")
        with self.assertRaises(ValueError):
            intake.add_job(self.ws, lead="northstar-engineer", url="https://northstar.example/1")
        self.assertEqual(self.ws.jobs(), [])

    def test_adding_a_posting_closes_the_matching_lead(self) -> None:
        lead = self.ws.create_lead(company="Fieldwork", title="Analyst", url="https://fieldwork.example/jobs/3/", posting="Analyze.")
        keep = self.ws.create_lead(company="Fieldwork", title="Designer", url="https://fieldwork.example/jobs/4", posting="Design.")
        result = intake.add_job(self.ws, text=POSTING, company="Fieldwork", title="Analyst", url="https://fieldwork.example/jobs/3")
        closed = self.ws.resolve_lead(lead["id"])
        self.assertEqual((closed["status"], closed["job"]), ("promoted", result["job"]["job"]))
        self.assertEqual(self.ws.resolve_lead(keep["id"])["status"], "new")


def exa_post(results: list[dict]):
    calls = []

    def post(url: str, payload: dict, headers: dict) -> dict:
        calls.append((url, payload, headers))
        return {"results": results}

    post.calls = calls
    return post


class FindJobsTests(WorkspaceCase):
    def results(self) -> list[dict]:
        return [
            {"title": "Job Application for Applied AI Engineer at Northstar", "url": GREENHOUSE_URL + "?gh_src=feed"},
            {
                "title": "Fieldwork | Data Engineer",
                "url": "https://fieldwork.example/jobs/9",
                "highlights": ["Own the pipelines.", "We are unable to sponsor visas."],
            },
            {"title": "Tracked Role - Meridian", "url": "https://meridian.example/jobs/1/"},
            {"title": "Saved Lead - Orbital", "url": "https://orbital.example/jobs/2?utm_source=x"},
        ]

    def test_search_results_become_leads(self) -> None:
        self.ws.save_settings({"rules": {"needs_sponsorship": True}})
        intake.add_job(self.ws, text=POSTING, company="Meridian", title="Tracked Role", url="https://meridian.example/jobs/1")
        self.ws.create_lead(company="Orbital", title="Saved Lead", url="https://orbital.example/jobs/2")
        post = exa_post(self.results())
        fetched = []

        def fetch(url: str) -> dict:
            fetched.append(url)
            return greenhouse_fetch(url)

        result = intake.find_jobs(self.ws, " ai  engineer ", limit=4, post_json=post, fetch_json=fetch, env=ENV, today="2026-11-10")
        self.assertEqual(post.calls[0][1]["numResults"], 4)
        self.assertEqual(len(fetched), 1)
        self.assertEqual(
            result,
            {
                "ok": True,
                "query": "ai engineer",
                "found": 4,
                "new": 2,
                "known": 2,
                "leads": [
                    {
                        "lead": "northstar-applied-ai-engineer",
                        "company": "Northstar",
                        "title": "Applied AI Engineer",
                        "location": "Denver, CO",
                        "url": GREENHOUSE_URL,
                        "preflight": "skip",
                        "blockers": ["sponsorship"],
                    },
                    {
                        "lead": "fieldwork-data-engineer",
                        "company": "Fieldwork",
                        "title": "Data Engineer",
                        "url": "https://fieldwork.example/jobs/9",
                        "preflight": "skip",
                        "blockers": ["sponsorship"],
                    },
                ],
            },
        )
        hydrated = self.ws.resolve_lead("northstar-applied-ai-engineer")
        self.assertEqual(hydrated["status"], "new")
        self.assertEqual(hydrated["source"], "greenhouse")
        self.assertEqual(hydrated["found_on"], "2026-11-10")
        self.assertEqual(hydrated["preflight"], "skip")
        self.assertEqual(hydrated["blockers"], ["sponsorship"])
        self.assertIn("Proficiency in Python and SQL.", section(self.ws.read(Path(hydrated["path"])).body, "Posting"))
        snippet = self.ws.resolve_lead("fieldwork-data-engineer")
        self.assertEqual(snippet["source"], "exa")
        self.assertEqual(
            section(self.ws.read(Path(snippet["path"])).body, "Posting"),
            "Own the pipelines. We are unable to sponsor visas.",
        )
        self.assertEqual(len(self.ws.leads()), 3)
        self.assertEqual(len(self.ws.jobs()), 1)

        again = intake.find_jobs(self.ws, "ai engineer", post_json=post, fetch_json=no_fetch, env=ENV)
        self.assertEqual((again["found"], again["new"], again["known"], again["leads"]), (4, 0, 4, []))
        self.assertEqual(len(self.ws.leads()), 3)

    def test_clear_leads_omit_empty_fields(self) -> None:
        post = exa_post([{"title": "Fieldwork | Data Engineer", "url": "https://fieldwork.example/jobs/9", "text": "Own the pipelines."}])
        result = intake.find_jobs(self.ws, "data engineer", post_json=post, fetch_json=no_fetch, env=ENV)
        self.assertEqual(
            result["leads"],
            [
                {
                    "lead": "fieldwork-data-engineer",
                    "company": "Fieldwork",
                    "title": "Data Engineer",
                    "url": "https://fieldwork.example/jobs/9",
                    "preflight": "apply",
                }
            ],
        )
        self.assertEqual(self.ws.resolve_lead("fieldwork-data-engineer")["blockers"], [])

    def test_canonical_url_of_a_hydrated_result_can_be_known(self) -> None:
        intake.add_job(self.ws, url=GREENHOUSE_URL, fetch_json=greenhouse_fetch)
        post = exa_post([{"title": "Applied AI Engineer", "url": "https://job-boards.greenhouse.io/northstar/jobs/123"}])
        result = intake.find_jobs(self.ws, "ai engineer", post_json=post, fetch_json=greenhouse_fetch, env=ENV)
        self.assertEqual((result["found"], result["new"], result["known"]), (1, 0, 1))
        self.assertEqual(self.ws.leads(), [])

    def test_failed_hydration_keeps_the_snippet(self) -> None:
        def fetch(url: str) -> dict:
            raise RuntimeError("HTTP 500")

        post = exa_post([{"title": "Job Application for Applied AI Engineer at Northstar", "url": GREENHOUSE_URL, "highlights": ["Build agents."]}])
        result = intake.find_jobs(self.ws, "ai engineer", post_json=post, fetch_json=fetch, env=ENV)
        self.assertEqual(result["new"], 1)
        lead = self.ws.resolve_lead(result["leads"][0]["lead"])
        self.assertEqual((lead["company"], lead["title"], lead["source"]), ("Northstar", "Applied AI Engineer", "exa"))
        self.assertEqual(section(self.ws.read(Path(lead["path"])).body, "Posting"), "Build agents.")

    def test_missing_api_key_and_provider_errors(self) -> None:
        hint = "Search with your web tool instead and add postings with jobapps_add_job."
        missing = intake.find_jobs(self.ws, "ai engineer", post_json=exa_post([]), env={})
        self.assertEqual(
            missing,
            {"ok": False, "error": "EXA_API_KEY is not set. Add it to the environment to use Exa search.", "hint": hint},
        )

        def down(url: str, payload: dict, headers: dict) -> dict:
            raise RuntimeError("provider down")

        failed = intake.find_jobs(self.ws, "ai engineer", post_json=down, env=ENV)
        self.assertEqual((failed["ok"], failed["hint"]), (False, hint))
        self.assertIn("provider down", failed["error"])
        self.assertEqual(self.ws.leads(), [])


class LeadStatusTests(WorkspaceCase):
    def test_status_changes_and_validation(self) -> None:
        lead = self.ws.create_lead(company="Fieldwork", title="Data Engineer", url="https://fieldwork.example/jobs/9")
        for status in ("shortlisted", "dismissed", "new"):
            with self.subTest(status=status):
                self.assertEqual(
                    intake.set_lead_status(self.ws, "fieldwork data", status),
                    {"ok": True, "lead": lead["id"], "status": status},
                )
                self.assertEqual(self.ws.resolve_lead(lead["id"])["status"], status)
        self.assertEqual(intake.set_lead_status(self.ws, lead["id"], " Shortlisted ")["status"], "shortlisted")
        for status in ("promoted", "archived", ""):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    intake.set_lead_status(self.ws, lead["id"], status)
        self.assertEqual(self.ws.resolve_lead(lead["id"])["status"], "shortlisted")
        with self.assertRaises(KeyError):
            intake.set_lead_status(self.ws, "nobody", "dismissed")


class FindPeopleTests(WorkspaceCase):
    def people_post(self):
        return exa_post(
            [
                {
                    "title": "Riley Sample - Recruiter - Northstar | LinkedIn",
                    "url": "https://www.linkedin.com/in/riley-sample",
                    "highlights": ["Hires engineers at Northstar."],
                }
            ]
        )

    def test_returns_tracked_and_found_people_without_saving(self) -> None:
        self.ws.create_person(name="Jordan Example", company="Northstar Labs", role="Engineering Manager", status="contacted")
        self.ws.create_person(name="Casey Placeholder", company="Fieldwork")
        post = self.people_post()
        result = intake.find_people(self.ws, company="Northstar", limit=3, post_json=post, env=ENV)
        self.assertEqual(post.calls[0][1]["category"], "people")
        self.assertEqual(post.calls[0][1]["numResults"], 3)
        self.assertEqual(
            result,
            {
                "ok": True,
                "company": "Northstar",
                "tracked": [{"person": "jordan-example", "name": "Jordan Example", "role": "Engineering Manager", "status": "contacted"}],
                "found": [
                    {
                        "name": "Riley Sample",
                        "role": "Recruiter",
                        "company": "Northstar",
                        "linkedin": "https://www.linkedin.com/in/riley-sample",
                        "source_url": "https://www.linkedin.com/in/riley-sample",
                        "snippet": "Hires engineers at Northstar.",
                    }
                ],
                "note": "Nothing was saved. Save a person only when the user asks, with jobapps_person. Verify identity and never guess an email address.",
            },
        )
        self.assertEqual(len(self.ws.people()), 2)

    def test_job_reference_supplies_the_company(self) -> None:
        added = intake.add_job(self.ws, text=POSTING, company="Northstar", title="Software Engineer")
        post = self.people_post()
        result = intake.find_people(self.ws, job=added["job"]["job"], post_json=post, env=ENV)
        self.assertEqual(result["company"], "Northstar")
        self.assertIn("Northstar", post.calls[0][1]["query"])
        self.assertEqual(result["tracked"], [])
        with self.assertRaises(KeyError):
            intake.find_people(self.ws, job="nobody", post_json=post, env=ENV)

    def test_query_only_and_errors(self) -> None:
        post = self.people_post()
        result = intake.find_people(self.ws, query="platform recruiters in Denver", post_json=post, env=ENV)
        self.assertEqual((result["ok"], result["company"], result["tracked"]), (True, "", []))
        self.assertEqual(post.calls[0][1]["query"], "platform recruiters in Denver")
        hint = "Use your web search tool to find people instead."
        missing_key = intake.find_people(self.ws, company="Northstar", post_json=post, env={})
        self.assertEqual((missing_key["ok"], missing_key["hint"]), (False, hint))
        self.assertIn("EXA_API_KEY", missing_key["error"])
        nothing = intake.find_people(self.ws, post_json=post, env=ENV)
        self.assertEqual((nothing["ok"], nothing["hint"]), (False, hint))


class GmailDraftTests(WorkspaceCase):
    def setUp(self) -> None:
        super().setUp()
        self.calls: list[tuple[list[str], str, float]] = []

    def run_ok(self, command: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, stdin, timeout))
        return subprocess.CompletedProcess(command, 0, '{"draftId":"draft_123"}', "")

    def test_draft_for_a_tracked_person_is_logged(self) -> None:
        person = self.ws.create_person(name="Jordan Example", company="Northstar", email="jordan@northstar.example")
        subject = "Question about the platform team " + "and more " * 12
        result = intake.gmail_draft(self.ws, subject=subject, body="Hi Jordan,\n\nA short note.", person="jordan", run=self.run_ok)
        self.assertEqual(
            result,
            {"ok": True, "draft_id": "draft_123", "to": "jordan@northstar.example", "note": "Draft only. Nothing was sent."},
        )
        command, stdin, _ = self.calls[0]
        self.assertIn("--gmail-no-send", command)
        self.assertEqual(command[command.index("gmail") : command.index("gmail") + 3], ["gmail", "drafts", "create"])
        self.assertEqual(command[command.index("--to") + 1], "jordan@northstar.example")
        self.assertNotIn("send", command)
        self.assertEqual(stdin, "Hi Jordan,\n\nA short note.")
        log = section(self.ws.read(Path(person["path"])).body, "Log").splitlines()
        self.assertEqual(len(log), 2)
        entry = log[-1].split(": ", 1)[1]
        self.assertTrue(entry.startswith("Gmail draft created: Question about the platform team"))
        self.assertEqual(len(entry), len("Gmail draft created: ") + 80)

    def test_explicit_recipient_and_account(self) -> None:
        person = self.ws.create_person(name="Jordan Example", company="Northstar")
        result = intake.gmail_draft(
            self.ws,
            to="jordan@other.example",
            subject="Hello",
            body="Body",
            account="me@example.com",
            person=person["id"],
            run=self.run_ok,
        )
        self.assertEqual(result["to"], "jordan@other.example")
        self.assertEqual(self.calls[0][0][1:3], ["--account", "me@example.com"])
        self.assertIn("Gmail draft created: Hello", self.ws.read(Path(person["path"])).body)

        unaddressed = intake.gmail_draft(self.ws, subject="Hello", body="Body", run=self.run_ok)
        self.assertEqual((unaddressed["ok"], unaddressed["to"]), (True, ""))
        self.assertNotIn("--to", self.calls[1][0])

    def test_person_without_email_is_never_guessed(self) -> None:
        person = self.ws.create_person(name="Jordan Example", company="Northstar")
        result = intake.gmail_draft(self.ws, subject="Hello", body="Body", person=person["id"], run=self.run_ok)
        self.assertEqual(result, {"ok": False, "error": "No email on file for Jordan Example. Ask the user; never guess."})
        self.assertEqual(self.calls, [])
        self.assertNotIn("Gmail draft", self.ws.read(Path(person["path"])).body)
        with self.assertRaises(KeyError):
            intake.gmail_draft(self.ws, subject="Hello", body="Body", person="nobody", run=self.run_ok)

    def test_subject_and_body_are_required(self) -> None:
        for kwargs in ({"subject": "", "body": "Body"}, {"subject": "Hello", "body": "  "}, {}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(
                    intake.gmail_draft(self.ws, run=self.run_ok, **kwargs),
                    {"ok": False, "error": "A draft needs a subject and a body."},
                )
        self.assertEqual(self.calls, [])

    def test_source_errors_are_reported_and_not_logged(self) -> None:
        person = self.ws.create_person(name="Jordan Example", company="Northstar", email="jordan@northstar.example")
        bad = intake.gmail_draft(self.ws, to="jordan-at-example", subject="Hello", body="Body", run=self.run_ok)
        self.assertEqual(bad, {"ok": False, "error": "Not a valid email address: jordan-at-example"})
        self.assertEqual(self.calls, [])

        self.ws.save_settings({"networking": {"gog_path": "/nonexistent/jobapps-test-gog"}})
        missing = intake.gmail_draft(self.ws, subject="Hello", body="Body", person=person["id"])
        self.assertEqual(missing, {"ok": False, "error": "gog command not found: /nonexistent/jobapps-test-gog"})

        def failing(command: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, "", "auth required")

        failed = intake.gmail_draft(self.ws, subject="Hello", body="Body", person=person["id"], run=failing)
        self.assertEqual(failed, {"ok": False, "error": "gog draft creation failed: auth required"})
        self.assertNotIn("Gmail draft", self.ws.read(Path(person["path"])).body)


if __name__ == "__main__":
    unittest.main()
