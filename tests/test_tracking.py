from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from hermes_jobapps.tracking import brief, job_header, overview, save_person, track_job
from hermes_jobapps.workspace import STAGES, Workspace, section, sha256_file


TODAY = date(2027, 3, 16)


def iso(offset: int = 0) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


class TrackingCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmp.name) / "ws")
        self.ws.init(name="Jordan Example")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def job(self, company: str, title: str = "AI Engineer", *, status: str = "new", updated: int = -1, **meta) -> str:
        record = self.ws.create_job(
            company=company,
            title=title,
            status=status,
            created_on=iso(updated),
            posting=meta.pop("posting", ""),
            location=meta.pop("location", ""),
            url=meta.pop("url", ""),
            body_sections=meta.pop("body_sections", None),
            extra_meta=meta,
        )
        return record["id"]

    def meta(self, job_id: str) -> dict:
        return self.ws.job_doc(job_id).meta

    def log(self, job_id: str) -> str:
        return section(self.ws.job_doc(job_id).body, "Log")

    def material(self, job_id: str, name: str, qa: str = "") -> Path:
        path = self.ws.job_dir(job_id) / name
        path.write_text("source", encoding="utf-8")
        if qa in ("pass", "review", "fail", "stale"):
            report = {
                "status": "pass" if qa == "stale" else qa,
                "source_sha256": "0" * 64 if qa == "stale" else sha256_file(path),
                "checked_at": iso(),
            }
            (path.parent / "qa").mkdir(exist_ok=True)
            (path.parent / "qa" / f"{name}.json").write_text(json.dumps(report), encoding="utf-8")
        return path

    def evidence(self, name: str, body: str, **meta) -> None:
        self.ws.write(self.ws.evidence_dir / f"{name}.md", {"title": name.title(), "status": "active", **meta}, body)

    def playbook(self, text: str) -> None:
        (self.ws.profile_dir / "playbook.md").write_text(text, encoding="utf-8")


class JobHeaderTests(unittest.TestCase):
    def test_shape_and_omissions(self) -> None:
        header = job_header(
            {
                "id": "2026-11-northstar-ai-engineer",
                "company": "Northstar",
                "title": "AI Engineer",
                "stage": "applied",
                "location": "",
                "url": None,
                "applied_on": "2026-11-02T09:30:00",
                "next_action": "x" * 400,
                "next_action_due": "2026-11-12",
                "updated_on": "2026-11-02",
                "path": "/somewhere/job.md",
                "source": "pasted",
            }
        )
        self.assertEqual(
            list(header), ["job", "company", "title", "stage", "applied_on", "next_action", "due", "updated_on"]
        )
        self.assertEqual(header["applied_on"], "2026-11-02")
        self.assertEqual(header["due"], "2026-11-12")
        self.assertEqual(len(header["next_action"]), 160)

    def test_stage_falls_back_to_status(self) -> None:
        self.assertEqual(job_header({"id": "a", "status": "submitted"})["stage"], "applied")
        self.assertEqual(job_header({"id": 7, "company": 1848})["company"], "1848")


class OverviewTests(TrackingCase):
    def test_rejects_unknown_view_and_stage(self) -> None:
        with self.assertRaisesRegex(ValueError, "today, jobs, people, leads"):
            overview(self.ws, view="board", today=TODAY)
        with self.assertRaisesRegex(ValueError, ", ".join(STAGES)):
            overview(self.ws, view="jobs", stage="pending", today=TODAY)
        with self.assertRaisesRegex(ValueError, ", ".join(STAGES)):
            overview(self.ws, stage="bogus", today=TODAY)

    def test_empty_workspace_reports_setup(self) -> None:
        result = overview(self.ws, today=TODAY)
        self.assertEqual(result["as_of"], "2027-03-16")
        self.assertEqual(result["workspace"], str(self.ws.root))
        self.assertEqual(result["counts"], {**{stage: 0 for stage in STAGES}, "total": 0, "people": 0, "leads": 0})
        self.assertEqual(result["attention"], {})
        self.assertEqual(len(result["setup"]), 2)
        self.assertTrue(any("evidence" in line for line in result["setup"]))
        self.assertTrue(any("jobs" in line.lower() for line in result["setup"]))

    def test_setup_names_missing_profile_and_clears_when_ready(self) -> None:
        bare = Workspace(Path(self.tmp.name) / "bare")
        bare.init()
        self.assertTrue(any("profile.md" in line for line in overview(bare, today=TODAY)["setup"]))

        self.evidence("review-only", "Facts", status="needs_review")
        self.job("Northstar")
        self.assertEqual(len(overview(self.ws, today=TODAY)["setup"]), 1)
        self.evidence("atlas", "Facts")
        self.assertNotIn("setup", overview(self.ws, today=TODAY))

    def test_counts_cover_stages_people_and_open_leads(self) -> None:
        self.job("Northstar", status="applied")
        self.job("Fieldwork", status="submitted")
        self.job("Meridian", status="skipped")
        self.ws.create_person(name="Jamie Chen", why="Former teammate.")
        self.ws.create_lead(company="Harbor", title="ML Engineer", status="new", found_on=iso(-1))
        self.ws.create_lead(company="Quill", title="ML Engineer", status="shortlisted", found_on=iso(-90))
        self.ws.create_lead(company="Tern", title="ML Engineer", status="dismissed", found_on=iso(-1))
        self.ws.create_lead(company="Vale", title="ML Engineer", status="promoted", found_on=iso(-1))
        counts = overview(self.ws, today=TODAY)["counts"]
        self.assertEqual(counts["applied"], 2)
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["new"], 0)
        self.assertEqual(counts["total"], 3)
        self.assertEqual(counts["people"], 1)
        self.assertEqual(counts["leads"], 2)

    def test_due_lists_open_jobs_inside_the_horizon(self) -> None:
        overdue = self.job("Northstar", next_action="Send the follow-up", next_action_due=iso(-2))
        soon = self.job("Fieldwork", status="applied", next_action_due=iso(3))
        now = self.job("Meridian", status="interviewing", next_action_due=iso())
        self.job("Harbor", next_action_due=iso(4))
        self.job("Quill", status="rejected", next_action_due=iso(-1))
        self.job("Tern", next_action="No date")
        self.job("Vale", next_action_due="2026-13-45")
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual([item["job"] for item in attention["due"]], [overdue, now, soon])
        self.assertEqual([item["days_overdue"] for item in attention["due"]], [2, 0, -3])
        self.assertEqual(attention["due_total"], 3)
        self.assertEqual(attention["due"][0]["next_action"], "Send the follow-up")
        self.assertEqual(attention["due"][0]["due"], iso(-2))

    def test_applied_quiet_uses_the_configured_wait(self) -> None:
        at_threshold = self.job("Northstar", status="applied", applied_on=iso(-10))
        self.job("Fieldwork", status="applied", applied_on=iso(-9))
        self.job("Meridian", status="applied", applied_on=iso(-20), next_action_due=iso(2))
        self.job("Harbor", status="applied", applied_on=iso(-20), next_action_due=iso())
        stale_due = self.job("Quill", status="applied", applied_on=iso(-20), next_action_due=iso(-1))
        self.job("Tern", status="interviewing", applied_on=iso(-30))
        self.job("Vale", status="applied")
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual(
            attention["applied_quiet"],
            [
                {"job": at_threshold, "company": "Northstar", "title": "AI Engineer", "applied_on": iso(-10), "days": 10},
                {"job": stale_due, "company": "Quill", "title": "AI Engineer", "applied_on": iso(-20), "days": 20},
            ],
        )
        self.assertEqual(attention["applied_quiet_total"], 2)

        self.ws.save_settings({"followups": {"application_check_after_days": 9}})
        quiet = overview(self.ws, today=TODAY)["attention"]["applied_quiet"]
        self.assertEqual([item["company"] for item in quiet], ["Fieldwork", "Northstar", "Quill"])

    def test_ready_carries_materials_with_their_check_state(self) -> None:
        ready = self.job("Northstar", status="ready")
        self.material(ready, "Jordan Example - Resume - Northstar.typ", "pass")
        self.material(ready, "Jordan Example - Cover Letter - Northstar.typ")
        (self.ws.job_dir(ready) / "offer-scan.pdf").write_bytes(b"%PDF")
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual(attention["ready_total"], 1)
        item = attention["ready"][0]
        self.assertEqual(item["job"], ready)
        self.assertEqual(
            item["materials"],
            [
                {"name": "Jordan Example - Cover Letter - Northstar.typ", "kind": "cover_letter", "qa": "none"},
                {"name": "Jordan Example - Resume - Northstar.typ", "kind": "resume", "qa": "pass"},
                {"name": "offer-scan.pdf", "kind": "other"},
            ],
        )

        empty = self.job("Fieldwork", status="ready")
        by_job = {item["job"]: item for item in overview(self.ws, today=TODAY)["attention"]["ready"]}
        self.assertNotIn("materials", by_job[empty])

    def test_ready_bounds_materials_per_job(self) -> None:
        ready = self.job("Northstar", status="ready")
        for index in range(9):
            self.material(ready, f"notes-{index}.md")
        item = overview(self.ws, today=TODAY)["attention"]["ready"][0]
        self.assertEqual(len(item["materials"]), 6)
        self.assertEqual(item["materials_total"], 9)

    def test_interviewing_includes_offers(self) -> None:
        interviewing = self.job("Northstar", status="phone_screen")
        offer = self.job("Fieldwork", status="offer")
        self.job("Meridian", status="applied")
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual({item["job"] for item in attention["interviewing"]}, {interviewing, offer})
        self.assertEqual({item["stage"] for item in attention["interviewing"]}, {"interviewing", "offer"})
        self.assertEqual(attention["interviewing_total"], 2)

    def test_in_progress_is_recent_new_work_that_was_not_skipped(self) -> None:
        newest = self.job("Northstar", updated=-1)
        edge = self.job("Fieldwork", updated=-21)
        self.job("Meridian", updated=-22)
        self.job("Harbor", updated=-2, decision="skip")
        pending = self.job("Quill", updated=-3, decision="pending")
        self.job("Tern", updated=-1, status="applied")
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual([item["job"] for item in attention["in_progress"]], [newest, pending, edge])
        self.assertEqual(attention["in_progress_total"], 3)

    def test_people_needing_a_touch_are_ordered(self) -> None:
        self.ws.create_person(name="Zed Follow", why="x", status="follow_up")
        self.ws.create_person(name="Amy Follow", why="x", status="follow_up", next_touch=iso(9))
        self.ws.create_person(name="Bea Soon", company="Northstar", role="Recruiter", why="x", status="contacted", next_touch=iso(3))
        self.ws.create_person(name="Cal Overdue", why="x", status="contacted", next_touch=iso(-4))
        self.ws.create_person(name="Dee Later", why="x", status="contacted", next_touch=iso(4))
        self.ws.create_person(name="Eli Fresh", why="x", status="to_contact")
        self.ws.create_person(name="Abe Fresh", why="x", status="to_contact")
        self.ws.create_person(name="Fay Replied", why="x", status="replied")
        self.ws.create_person(name="Gus Paused", why="x", status="paused", email="gus@example.com")
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual(
            [item["name"] for item in attention["people"]],
            ["Amy Follow", "Zed Follow", "Cal Overdue", "Bea Soon", "Abe Fresh", "Eli Fresh"],
        )
        self.assertEqual(attention["people_total"], 6)
        self.assertEqual(
            attention["people"][3],
            {
                "person": "bea-soon",
                "name": "Bea Soon",
                "company": "Northstar",
                "role": "Recruiter",
                "status": "contacted",
                "next_touch": iso(3),
            },
        )
        self.assertEqual(attention["people"][1], {"person": "zed-follow", "name": "Zed Follow", "status": "follow_up"})

    def test_fresh_leads_put_shortlisted_first(self) -> None:
        self.ws.create_lead(company="Harbor", title="ML Engineer", found_on=iso(-1), url="https://jobs.example.com/harbor")
        self.ws.create_lead(company="Quill", title="Data Engineer", found_on=iso(-5), status="shortlisted", location="Remote")
        self.ws.create_lead(company="Tern", title="AI Engineer", found_on=iso(-30), extra_meta={"preflight": "p" * 400})
        self.ws.create_lead(company="Vale", title="AI Engineer", found_on=iso(-31))
        self.ws.create_lead(company="Wren", title="AI Engineer", found_on=iso(-1), status="dismissed")
        self.ws.create_lead(company="Yarrow", title="AI Engineer", found_on=iso(-1), status="promoted")
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual([item["company"] for item in attention["leads"]], ["Quill", "Harbor", "Tern"])
        self.assertEqual(attention["leads_total"], 3)
        self.assertEqual(
            attention["leads"][0],
            {
                "lead": "quill-data-engineer",
                "company": "Quill",
                "title": "Data Engineer",
                "location": "Remote",
                "found_on": iso(-5),
                "status": "shortlisted",
            },
        )
        self.assertEqual(attention["leads"][1]["url"], "https://jobs.example.com/harbor")
        self.assertEqual(len(attention["leads"][2]["preflight"]), 160)

        self.ws.save_settings({"followups": {"lead_fresh_days": 3}})
        self.assertEqual([item["company"] for item in overview(self.ws, today=TODAY)["attention"]["leads"]], ["Harbor"])

    def test_attention_lists_are_bounded_with_true_totals(self) -> None:
        for index in range(5):
            self.job(f"Company {index}", next_action_due=iso(-index))
        result = overview(self.ws, limit=2, today=TODAY)
        self.assertEqual(len(result["attention"]["due"]), 2)
        self.assertEqual(result["attention"]["due_total"], 5)
        self.assertEqual(len(result["attention"]["in_progress"]), 2)
        self.assertEqual(result["attention"]["in_progress_total"], 5)
        self.assertEqual(len(overview(self.ws, limit=0, today=TODAY)["attention"]["due"]), 1)
        self.assertEqual(len(overview(self.ws, limit=-4, view="jobs", today=TODAY)["jobs"]), 1)

    def test_limit_is_capped_at_fifty(self) -> None:
        for index in range(55):
            self.job(f"Company {index:02d}")
        result = overview(self.ws, view="jobs", limit=999, today=TODAY)
        self.assertEqual(len(result["jobs"]), 50)
        self.assertEqual(result["jobs_total"], 55)

    def test_jobs_view_filters_by_stage_and_query(self) -> None:
        older = self.job("Northstar Labs", "AI Engineer", status="applied", updated=-9)
        newer = self.job("Northstar Labs", "Data Engineer", status="applied", updated=-2)
        other = self.job("Fieldwork", "AI Engineer", updated=-1)

        everything = overview(self.ws, view="jobs", today=TODAY)
        self.assertEqual([item["job"] for item in everything["jobs"]], [other, newer, older])
        self.assertEqual(everything["jobs_total"], 3)
        self.assertEqual(everything["filter"], {})
        self.assertNotIn("attention", everything)
        self.assertIn("counts", everything)

        applied = overview(self.ws, view="jobs", stage="Applied", today=TODAY)
        self.assertEqual([item["job"] for item in applied["jobs"]], [newer, older])
        self.assertEqual(applied["filter"], {"stage": "applied"})

        words = overview(self.ws, view="jobs", query="ENGINEER northstar ai", today=TODAY)
        self.assertEqual([item["job"] for item in words["jobs"]], [older])
        self.assertEqual(words["filter"], {"query": "ENGINEER northstar ai"})

        nothing = overview(self.ws, view="jobs", stage="offer", query="northstar", today=TODAY)
        self.assertEqual(nothing["jobs"], [])
        self.assertEqual(nothing["jobs_total"], 0)

    def test_today_with_a_filter_behaves_as_jobs(self) -> None:
        self.job("Northstar", status="applied")
        self.job("Fieldwork")
        by_query = overview(self.ws, query="fieldwork", today=TODAY)
        self.assertEqual([item["company"] for item in by_query["jobs"]], ["Fieldwork"])
        self.assertNotIn("attention", by_query)
        by_stage = overview(self.ws, stage="applied", today=TODAY)
        self.assertEqual([item["company"] for item in by_stage["jobs"]], ["Northstar"])

    def test_people_view_lists_everyone(self) -> None:
        job_id = self.job("Northstar")
        self.ws.create_person(
            name="Jamie Chen",
            company="Northstar",
            role="Engineering Manager",
            email="jamie@example.com",
            linkedin="https://linkedin.example.com/in/jamie",
            why="x",
            status="replied",
            jobs=[job_id],
        )
        self.ws.create_person(name="Priya Raman", company="Fieldwork", role="Recruiter", why="x", status="paused")
        result = overview(self.ws, view="people", today=TODAY)
        self.assertEqual(result["people_total"], 2)
        self.assertEqual(
            result["people"][0],
            {
                "person": "jamie-chen",
                "name": "Jamie Chen",
                "company": "Northstar",
                "role": "Engineering Manager",
                "email": "jamie@example.com",
                "linkedin": "https://linkedin.example.com/in/jamie",
                "status": "replied",
                "jobs": [job_id],
            },
        )
        by_role = overview(self.ws, view="people", query="recruiter fieldwork", today=TODAY)
        self.assertEqual([item["name"] for item in by_role["people"]], ["Priya Raman"])
        self.assertEqual(by_role["people_total"], 1)
        self.assertEqual(overview(self.ws, view="people", query="nobody", today=TODAY)["people"], [])

    def test_leads_view_lists_open_leads_of_any_age(self) -> None:
        self.ws.create_lead(company="Harbor", title="ML Engineer", found_on=iso(-200))
        self.ws.create_lead(company="Quill", title="Data Engineer", found_on=iso(-300), status="shortlisted")
        self.ws.create_lead(company="Wren", title="AI Engineer", found_on=iso(-1), status="dismissed")
        result = overview(self.ws, view="leads", today=TODAY)
        self.assertEqual([item["company"] for item in result["leads"]], ["Quill", "Harbor"])
        self.assertEqual(result["leads_total"], 2)
        self.assertNotIn("leads", overview(self.ws, today=TODAY)["attention"])
        self.assertEqual(
            [item["lead"] for item in overview(self.ws, view="leads", query="harbor ml", today=TODAY)["leads"]],
            ["harbor-ml-engineer"],
        )

    def test_overview_stays_small_with_many_jobs(self) -> None:
        for index in range(80):
            self.job(
                f"Company {index:02d}",
                "Machine Learning Engineer",
                updated=-(index % 15),
                location="Remote",
                url=f"https://jobs.example.com/{index}",
                next_action="Follow up with the recruiter. " * 10,
            )
        result = overview(self.ws, today=TODAY)
        self.assertEqual(result["counts"]["total"], 80)
        self.assertEqual(result["attention"]["in_progress_total"], 80)
        self.assertEqual(len(result["attention"]["in_progress"]), 12)
        self.assertTrue(all(len(item["next_action"]) <= 160 for item in result["attention"]["in_progress"]))
        self.assertLess(len(json.dumps(result)), 9000)


class BriefTests(TrackingCase):
    def test_rejects_unknown_purpose_and_unknown_job(self) -> None:
        self.job("Northstar")
        with self.assertRaisesRegex(ValueError, "application_answers"):
            brief(self.ws, "northstar", purpose="essay")
        with self.assertRaises(KeyError):
            brief(self.ws, "nobody")

    def test_ambiguous_reference_lists_matches(self) -> None:
        for title in ("AI Engineer", "Data Engineer"):
            self.job("Northstar", title)
        result = brief(self.ws, "northstar")
        self.assertEqual(set(result), {"ambiguous", "matches", "matches_total", "hint"})
        self.assertTrue(result["ambiguous"])
        self.assertEqual({item["title"] for item in result["matches"]}, {"AI Engineer", "Data Engineer"})
        self.assertEqual(result["hint"], "Call again with the exact job id.")

        for index in range(6):
            self.job("Fieldwork", f"Engineer {index}")
        many = brief(self.ws, "fieldwork")
        self.assertEqual(len(many["matches"]), 5)
        self.assertEqual(many["matches_total"], 6)

    def test_packet_carries_the_job_sections_and_destination(self) -> None:
        job_id = self.job(
            "Northstar",
            location="Remote",
            url="https://jobs.example.com/northstar",
            posting="Build agents.\n\nShip evaluations.",
            decision="apply",
            body_sections={
                "Assessment": "No blockers.\n- Sponsorship: not needed.",
                "Requirements": "- Python\n- Evaluation design",
                "Research": "Series B, forty people.",
                "Notes": "Referred by Jamie.",
            },
        )
        folder = os.path.abspath(self.ws.job_dir(job_id))
        result = brief(self.ws, job_id)
        self.assertEqual(result["job"]["job"], job_id)
        self.assertEqual(result["job"]["folder"], folder)
        self.assertEqual(result["job"]["decision"], "apply")
        self.assertEqual(result["job"]["location"], "Remote")
        self.assertEqual(result["posting"], "Build agents.\n\nShip evaluations.")
        self.assertEqual(result["assessment"], "No blockers.\n- Sponsorship: not needed.")
        self.assertEqual(result["requirements"], "- Python\n- Evaluation design")
        self.assertEqual(result["notes"], "Referred by Jamie.")
        self.assertNotIn("research", result)
        self.assertEqual(result["write_to"], folder)
        self.assertIn("Strategy section", result["next"])
        self.assertIn("run jobapps_check", result["next"])
        self.assertEqual(result["profile"]["contact"], {"name": "Jordan Example"})
        self.assertIn("## Target direction", result["profile"]["text"])
        self.assertIn("## Sounds like me", result["voice"])
        for absent in ("materials", "evidence", "evidence_note", "people", "playbook"):
            self.assertNotIn(absent, result)

    def test_research_only_for_purposes_that_use_it(self) -> None:
        job_id = self.job("Northstar", body_sections={"Research": "Series B, forty people."})
        for purpose in ("cover_letter", "outreach", "interview", "general"):
            self.assertEqual(brief(self.ws, job_id, purpose=purpose)["research"], "Series B, forty people.")
        for purpose in ("resume", "application_answers"):
            self.assertNotIn("research", brief(self.ws, job_id, purpose=purpose))

    def test_long_sections_are_cut_with_a_marker(self) -> None:
        posting = "\n".join(f"Line {index:05d} of the posting." for index in range(700))
        job_id = self.job(
            "Northstar",
            posting=posting,
            body_sections={"Requirements": "r" * 4000, "Notes": "n" * 2500, "Assessment": "Short."},
        )
        result = brief(self.ws, job_id)
        marker = "\n[posting truncated: read job.md for the rest]"
        self.assertTrue(result["posting"].endswith(marker))
        self.assertLessEqual(len(result["posting"]), 14000 + len(marker))
        self.assertTrue(result["posting"].startswith("Line 00000 of the posting.\nLine 00001"))
        self.assertTrue(result["requirements"].endswith("[truncated: read job.md for the rest]"))
        self.assertTrue(result["requirements"].startswith("r" * 3000 + "\n["))
        self.assertTrue(result["notes"].startswith("n" * 2000 + "\n["))
        self.assertEqual(result["assessment"], "Short.")

        short = self.job("Fieldwork", posting="p" * 14000)
        self.assertEqual(brief(self.ws, short)["posting"], "p" * 14000)

    def test_materials_people_and_contact(self) -> None:
        job_id = self.job("Northstar")
        other = self.job("Fieldwork")
        resume = self.material(job_id, "Jordan Example - Resume - Northstar.typ", "review")
        self.ws.set_meta(self.ws.profile_dir / "profile.md", {"email": "jordan@example.com", "location": "Denver, CO"})
        self.ws.create_person(name="Jamie Chen", company="NORTHSTAR", role="Engineering Manager", why="x", email="jamie@example.com")
        self.ws.create_person(name="Priya Raman", company="Talent Partners", why="x", status="contacted", jobs=[job_id])
        self.ws.create_person(name="Sam Ortiz", company="Fieldwork", why="x", jobs=[other])
        result = brief(self.ws, job_id, purpose="outreach")
        self.assertEqual(
            result["materials"],
            [{"name": resume.name, "kind": "resume", "qa": "review", "path": str(resume)}],
        )
        self.assertEqual(
            result["profile"]["contact"],
            {"name": "Jordan Example", "email": "jordan@example.com", "location": "Denver, CO"},
        )
        self.assertEqual(
            result["people"],
            [
                {
                    "person": "jamie-chen",
                    "name": "Jamie Chen",
                    "role": "Engineering Manager",
                    "status": "to_contact",
                    "email": "jamie@example.com",
                },
                {"person": "priya-raman", "name": "Priya Raman", "status": "contacted"},
            ],
        )
        self.assertNotIn("people_total", result)

    def test_playbook_selects_shared_and_purpose_sections(self) -> None:
        job_id = self.job("Northstar")
        self.assertNotIn("playbook", brief(self.ws, job_id, purpose="general"))
        self.playbook(
            "# Playbook\n\nRules learned from your corrections.\n\n"
            "## All documents\n\n- No em dashes.\n\n"
            "## Resume\n\n- One page.\n- Mechanism before result.\n\n"
            "## Cover letter\n\n_Nothing yet._\n\n"
            "## Application answers\n\n\n"
            "## Outreach\n\n- Under 90 words.\n\n"
            "## Interview\n\n   \n_Add stories here._\n\n"
            "## Workflow\n\n- Ask before sending.\n"
        )
        self.assertEqual(
            brief(self.ws, job_id, purpose="resume")["playbook"],
            "## All documents\n\n- No em dashes.\n\n## Resume\n\n- One page.\n- Mechanism before result.",
        )
        self.assertEqual(
            brief(self.ws, job_id, purpose="outreach")["playbook"],
            "## All documents\n\n- No em dashes.\n\n## Outreach\n\n- Under 90 words.",
        )
        for purpose in ("cover_letter", "application_answers", "interview"):
            self.assertEqual(brief(self.ws, job_id, purpose=purpose)["playbook"], "## All documents\n\n- No em dashes.")
        general = brief(self.ws, job_id, purpose="general")["playbook"]
        self.assertEqual(
            [line for line in general.splitlines() if line.startswith("## ")],
            ["## All documents", "## Resume", "## Outreach", "## Workflow"],
        )
        self.assertNotIn("Nothing yet", general)
        self.assertNotIn("Add stories", general)

    def test_playbook_without_shared_rules_or_headings(self) -> None:
        job_id = self.job("Northstar")
        self.playbook("# Playbook\n\n## All documents\n\n_None._\n\n## Resume\n\n- One page.\n")
        self.assertEqual(brief(self.ws, job_id)["playbook"], "## Resume\n\n- One page.")
        self.assertNotIn("playbook", brief(self.ws, job_id, purpose="interview"))
        self.playbook("# Playbook\n\n- Never use the word passionate.\n")
        self.assertEqual(brief(self.ws, job_id, purpose="interview")["playbook"], "- Never use the word passionate.")

    def test_evidence_is_whole_when_it_fits(self) -> None:
        job_id = self.job("Northstar", posting="Build retrieval pipelines.")
        self.evidence("atlas", "# Atlas\n\n## Facts\n\n- Built the retrieval pipeline.", organization="Atlas Co", start="2024-01", tags=["rag"])
        self.evidence("beacon", "Unconfirmed latency number.", status="needs_review")
        self.evidence("cobalt", "Old project.", status="retired")
        result = brief(self.ws, job_id)
        evidence = result["evidence"]
        self.assertEqual(evidence["mode"], "full")
        self.assertNotIn("omitted", evidence)
        self.assertNotIn("evidence_note", result)
        self.assertEqual([item["id"] for item in evidence["files"]], ["atlas", "beacon"])
        atlas, beacon = evidence["files"]
        self.assertEqual(atlas["title"], "Atlas")
        self.assertEqual(atlas["text"], "# Atlas\n\n## Facts\n\n- Built the retrieval pipeline.")
        self.assertEqual(atlas["path"], str(self.ws.evidence_dir / "atlas.md"))
        self.assertEqual(atlas["meta"], {"organization": "Atlas Co", "start": "2024-01"})
        self.assertNotIn("status", atlas)
        self.assertEqual(beacon["status"], "needs_review")
        self.assertNotIn("cobalt", json.dumps(result))
        self.assertNotIn("Old project", json.dumps(result))

    def test_evidence_is_ranked_when_over_budget(self) -> None:
        job_id = self.job(
            "Northstar",
            "Retrieval Engineer",
            posting="Design retrieval pipelines with embeddings and reranking.",
            body_sections={"Requirements": "- Kubernetes operators\n- Evaluation harness"},
        )
        filler = " Zzz." * 100
        self.evidence("alpha", "Managed a bakery schedule." + filler, tags=["bakery"])
        self.evidence("bravo", "Built retrieval pipelines with embeddings, reranking and an evaluation harness." + filler)
        self.evidence("charlie", "Wrote Kubernetes operators." + filler, status="needs_review")
        self.evidence("delta", "Tuned embeddings for retrieval pipelines." + filler)
        self.evidence("echo", "Coached a chess club." + filler, tags=["chess", "coaching"])
        self.evidence("foxtrot", "Outdated retrieval embeddings reranking evaluation kubernetes.", status="retired")

        full = brief(self.ws, job_id)
        self.assertEqual(full["evidence"]["mode"], "full")
        self.assertEqual([item["id"] for item in full["evidence"]["files"]], ["alpha", "bravo", "charlie", "delta", "echo"])

        ranked = brief(self.ws, job_id, max_chars=1700)
        evidence = ranked["evidence"]
        self.assertEqual(evidence["mode"], "ranked")
        self.assertEqual([item["id"] for item in evidence["files"]], ["bravo", "delta", "charlie"])
        self.assertEqual(evidence["files"][2]["status"], "needs_review")
        self.assertTrue(evidence["files"][0]["text"].startswith("Built retrieval pipelines"))
        self.assertEqual(
            evidence["omitted"],
            [
                {"id": "alpha", "title": "Alpha", "tags": ["bakery"], "path": str(self.ws.evidence_dir / "alpha.md")},
                {"id": "echo", "title": "Echo", "tags": ["chess", "coaching"], "path": str(self.ws.evidence_dir / "echo.md")},
            ],
        )
        self.assertIn("Absence here does not mean absence of experience", ranked["evidence_note"])
        self.assertNotIn("foxtrot", json.dumps(ranked))

    def test_ranked_evidence_keeps_at_least_three_files(self) -> None:
        job_id = self.job("Northstar", posting="Design retrieval pipelines.")
        for name in ("alpha", "bravo", "charlie", "delta"):
            self.evidence(name, f"{name} work." + " Zzz." * 100)
        self.evidence("echo", "Retrieval pipelines." + " Zzz." * 100)
        evidence = brief(self.ws, job_id, max_chars=10)["evidence"]
        self.assertEqual(evidence["mode"], "ranked")
        self.assertEqual([item["id"] for item in evidence["files"]], ["echo", "alpha", "bravo"])
        self.assertEqual([item["id"] for item in evidence["omitted"]], ["charlie", "delta"])

    def test_budget_defaults_to_settings(self) -> None:
        job_id = self.job("Northstar", posting="Design retrieval pipelines.")
        for name in ("alpha", "bravo", "charlie", "delta"):
            self.evidence(name, f"{name} work." + " Zzz." * 100)
        self.assertEqual(brief(self.ws, job_id)["evidence"]["mode"], "full")
        self.ws.save_settings({"brief": {"max_chars": 1200}})
        self.assertEqual(brief(self.ws, job_id)["evidence"]["mode"], "ranked")
        self.assertEqual(brief(self.ws, job_id, max_chars=50000)["evidence"]["mode"], "full")


class TrackJobTests(TrackingCase):
    def test_rejects_unknown_status_and_bad_dates(self) -> None:
        job_id = self.job("Northstar")
        with self.assertRaisesRegex(ValueError, ", ".join(STAGES)):
            track_job(self.ws, job_id, status="hired", today=TODAY)
        for bad in ("tomorrow", "11/20/2026", "2026-02-30", "20261120"):
            with self.subTest(due=bad), self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                track_job(self.ws, job_id, next_action="Call", due=bad, today=TODAY)
        with self.assertRaisesRegex(ValueError, "applied_on"):
            track_job(self.ws, job_id, applied_on="last week", today=TODAY)
        with self.assertRaises(ValueError):
            track_job(self.ws, job_id, next_action="", due=iso(2), today=TODAY)
        with self.assertRaises(KeyError):
            track_job(self.ws, "nobody", status="applied", today=TODAY)
        self.assertEqual(self.meta(job_id)["status"], "new")
        self.assertEqual(self.log(job_id).count("\n- "), 0)

    def test_accepts_stages_and_known_aliases(self) -> None:
        job_id = self.job("Northstar")
        self.assertEqual(track_job(self.ws, job_id, status="Phone Screen", today=TODAY)["job"]["stage"], "interviewing")
        self.assertEqual(track_job(self.ws, job_id, status="OFFER", today=TODAY)["job"]["stage"], "offer")
        self.assertEqual(track_job(self.ws, job_id, status="withdrawn", today=TODAY)["job"]["stage"], "closed")
        self.assertEqual(track_job(self.ws, job_id, status="new", today=TODAY)["job"]["stage"], "new")
        self.assertEqual(self.meta(job_id)["status"], "new")

    def test_ambiguous_reference_changes_nothing(self) -> None:
        first = self.job("Northstar", "AI Engineer")
        self.job("Northstar", "Data Engineer")
        result = track_job(self.ws, "northstar", status="applied", today=TODAY)
        self.assertTrue(result["ambiguous"])
        self.assertEqual(len(result["matches"]), 2)
        self.assertEqual(result["hint"], "Call again with the exact job id.")
        self.assertEqual(self.meta(first)["status"], "new")

    def test_applying_sets_the_date_and_a_check(self) -> None:
        job_id = self.job("Northstar", next_action="Submit the form", next_action_due=iso(-1))
        result = track_job(self.ws, "northstar", status="applied", note="Sent through the careers page.", today=TODAY)
        self.assertTrue(result["ok"])
        self.assertEqual(result["changed"], ["status", "next_action", "next_action_due", "applied_on"])
        self.assertEqual(result["job"]["stage"], "applied")
        self.assertEqual(result["job"]["applied_on"], iso())
        self.assertEqual(result["job"]["next_action"], "Check on the application")
        self.assertEqual(result["job"]["due"], iso(10))
        meta = self.meta(job_id)
        self.assertEqual(
            (meta["status"], meta["applied_on"], meta["next_action"], meta["next_action_due"]),
            ("applied", iso(), "Check on the application", iso(10)),
        )
        self.assertIn("Status: new -> applied. Sent through the careers page.", self.log(job_id))

    def test_applying_respects_what_is_already_planned(self) -> None:
        self.ws.save_settings({"followups": {"application_check_after_days": 4}})
        planned = self.job("Northstar", next_action="Ask Jamie for a referral", next_action_due=iso(2))
        result = track_job(self.ws, planned, status="submitted", applied_on=iso(-3), today=TODAY)
        self.assertEqual(result["changed"], ["status", "applied_on"])
        self.assertEqual(result["job"]["applied_on"], iso(-3))
        self.assertEqual(result["job"]["next_action"], "Ask Jamie for a referral")
        self.assertEqual(result["job"]["due"], iso(2))

        given = self.job("Fieldwork")
        result = track_job(self.ws, given, status="applied", next_action="Email the recruiter", due=iso(1), today=TODAY)
        self.assertEqual(result["job"]["next_action"], "Email the recruiter")
        self.assertEqual(result["job"]["due"], iso(1))

        cleared = self.job("Meridian", next_action="Submit", next_action_due=iso(-2))
        result = track_job(self.ws, cleared, status="applied", next_action="", today=TODAY)
        self.assertNotIn("next_action", result["job"])
        self.assertNotIn("due", result["job"])

        default = self.job("Harbor", applied_on=iso(-8))
        result = track_job(self.ws, default, status="applied", today=TODAY)
        self.assertEqual(result["job"]["applied_on"], iso(-8))
        self.assertEqual(result["job"]["due"], iso(4))

    def test_ready_is_blocked_until_the_resume_check_passes(self) -> None:
        job_id = self.job("Northstar", next_action="Finish the resume")
        self.material(job_id, "Jordan Example - Resume - Northstar.typ")
        self.material(job_id, "Jordan Example - Resume - Northstar - Alt.tex", "fail")
        self.material(job_id, "Jordan Example - Cover Letter - Northstar.typ")
        self.material(job_id, "resume-notes.md")
        before = (self.ws.job_dir(job_id) / "job.md").read_text(encoding="utf-8")

        result = track_job(self.ws, job_id, status="ready", note="Done.", next_action="Apply", today=TODAY)
        self.assertEqual(
            result,
            {
                "ok": False,
                "blocked": [
                    {"name": "Jordan Example - Resume - Northstar - Alt.tex", "qa": "fail"},
                    {"name": "Jordan Example - Resume - Northstar.typ", "qa": "none"},
                ],
                "hint": "Run jobapps_check on these files, fix what it reports, then mark ready. "
                "Use force only when the user explicitly accepts the risk.",
            },
        )
        self.assertEqual((self.ws.job_dir(job_id) / "job.md").read_text(encoding="utf-8"), before)

    def test_ready_blocks_stale_checks_and_allows_pass_or_review(self) -> None:
        job_id = self.job("Northstar")
        name = "Jordan Example - Resume - Northstar.typ"
        self.material(job_id, name, "stale")
        self.assertEqual(track_job(self.ws, job_id, status="ready", today=TODAY)["blocked"], [{"name": name, "qa": "stale"}])
        self.material(job_id, name, "review")
        result = track_job(self.ws, job_id, status="materials_ready", today=TODAY)
        self.assertEqual((result["ok"], result["job"]["stage"], result["changed"]), (True, "ready", ["status"]))

        passing = self.job("Fieldwork")
        self.material(passing, "Jordan Example - Resume - Fieldwork.tex", "pass")
        self.assertEqual(track_job(self.ws, passing, status="ready", today=TODAY)["job"]["stage"], "ready")

    def test_ready_can_be_forced_and_is_free_without_resume_sources(self) -> None:
        forced = self.job("Northstar")
        self.material(forced, "Jordan Example - Resume - Northstar.typ", "fail")
        result = track_job(self.ws, forced, status="ready", force=True, note="User accepted the overflow.", today=TODAY)
        self.assertEqual(result["job"]["stage"], "ready")
        log = self.log(forced)
        self.assertIn("Status: new -> ready.", log)
        self.assertIn("Jordan Example - Resume - Northstar.typ (fail)", log)
        self.assertIn("User accepted the overflow.", log)

        free = self.job("Fieldwork")
        self.material(free, "Jordan Example - Cover Letter - Fieldwork.typ")
        self.material(free, "Jordan Example - Resume - Fieldwork.docx")
        (self.ws.job_dir(free) / "Jordan Example - Resume - Fieldwork - Final.pdf").write_bytes(b"%PDF")
        self.assertEqual(track_job(self.ws, free, status="ready", today=TODAY)["job"]["stage"], "ready")

        already = self.job("Meridian", status="ready")
        self.material(already, "Jordan Example - Resume - Meridian.typ")
        result = track_job(self.ws, already, status="ready", next_action="Apply tonight", today=TODAY)
        self.assertEqual(result["changed"], ["next_action"])

    def test_closing_a_job_clears_the_next_action(self) -> None:
        for status in ("rejected", "closed", "skipped"):
            with self.subTest(status=status):
                job_id = self.job(f"Company {status}", status="applied", next_action="Check in", next_action_due=iso(2), applied_on=iso(-5))
                result = track_job(self.ws, job_id, status=status, today=TODAY)
                self.assertEqual(result["changed"], ["status", "next_action", "next_action_due"])
                self.assertEqual(result["job"]["stage"], status)
                self.assertNotIn("next_action", result["job"])
                self.assertNotIn("due", result["job"])
                self.assertEqual(result["job"]["applied_on"], iso(-5))
                self.assertEqual(self.meta(job_id)["next_action"], "")
                self.assertEqual(self.meta(job_id)["next_action_due"], "")
                self.assertIn(f"Status: applied -> {status}.", self.log(job_id))

    def test_closing_keeps_an_action_given_in_the_same_call(self) -> None:
        job_id = self.job("Northstar", status="interviewing", next_action="Prepare", next_action_due=iso(1))
        result = track_job(self.ws, job_id, status="rejected", next_action="Ask for feedback", due=iso(5), today=TODAY)
        self.assertEqual(result["job"]["next_action"], "Ask for feedback")
        self.assertEqual(result["job"]["due"], iso(5))

    def test_next_action_updates_and_clears(self) -> None:
        job_id = self.job("Northstar", status="applied", applied_on=iso(-2))
        result = track_job(self.ws, job_id, next_action="  Email the\n recruiter ", due=iso(4), today=TODAY)
        self.assertEqual(result["changed"], ["next_action", "next_action_due"])
        self.assertEqual(result["job"]["next_action"], "Email the recruiter")
        self.assertEqual(result["job"]["stage"], "applied")
        self.assertIn(f"Next: Email the recruiter (due {iso(4)}).", self.log(job_id))

        result = track_job(self.ws, job_id, next_action="Call the recruiter", today=TODAY)
        self.assertEqual(result["changed"], ["next_action"])
        self.assertEqual(result["job"]["due"], iso(4))

        result = track_job(self.ws, job_id, due=iso(6), today=TODAY)
        self.assertEqual(result["changed"], ["next_action_due"])
        self.assertIn(f"Next: Call the recruiter (due {iso(6)}).", self.log(job_id))

        result = track_job(self.ws, job_id, next_action="", today=TODAY)
        self.assertEqual(result["changed"], ["next_action", "next_action_due"])
        self.assertNotIn("next_action", result["job"])
        self.assertNotIn("due", result["job"])
        self.assertEqual(self.meta(job_id)["next_action_due"], "")
        self.assertIn("Next action cleared.", self.log(job_id))

        result = track_job(self.ws, job_id, next_action="Wait", today=TODAY)
        self.assertIn("Next: Wait.", self.log(job_id))

    def test_note_only_and_unchanged_calls(self) -> None:
        job_id = self.job("Northstar", status="applied", applied_on=iso(-2), next_action="Wait", next_action_due=iso(3))
        before = (self.ws.job_dir(job_id) / "job.md").read_text(encoding="utf-8")
        for kwargs in ({}, {"status": "applied"}, {"status": "submitted", "next_action": "Wait", "due": iso(3), "applied_on": iso(-2)}):
            with self.subTest(kwargs=kwargs):
                result = track_job(self.ws, job_id, today=TODAY, **kwargs)
                self.assertEqual(result, {"ok": True, "unchanged": True, "job": job_header(self.ws.resolve_job(job_id))})
        self.assertEqual((self.ws.job_dir(job_id) / "job.md").read_text(encoding="utf-8"), before)

        result = track_job(self.ws, job_id, note="Recruiter is out until Monday.", today=TODAY)
        self.assertEqual((result["ok"], result["changed"]), (True, []))
        self.assertTrue(self.log(job_id).endswith("Recruiter is out until Monday."))
        self.assertNotIn("Status:", self.log(job_id))

    def test_applied_on_can_be_corrected_alone(self) -> None:
        job_id = self.job("Northstar", status="applied", applied_on=iso(-2))
        result = track_job(self.ws, job_id, applied_on=iso(-6), today=TODAY)
        self.assertEqual(result["changed"], ["applied_on"])
        self.assertEqual(result["job"]["applied_on"], iso(-6))
        self.assertIn(f"Applied on {iso(-6)}.", self.log(job_id))

    def test_result_reflects_the_file(self) -> None:
        job_id = self.job("Northstar", location="Remote", url="https://jobs.example.com/1")
        result = track_job(self.ws, job_id, status="interviewing", next_action="Prepare the system design round", due=iso(2), today=TODAY)
        self.assertEqual(result["job"], job_header(self.ws.resolve_job(job_id)))
        self.assertEqual(overview(self.ws, today=TODAY)["attention"]["due"][0]["job"], job_id)


class SavePersonTests(TrackingCase):
    def person_text(self, person_id: str) -> str:
        return (self.ws.people_dir / f"{person_id}.md").read_text(encoding="utf-8")

    def test_new_person_needs_a_name_and_a_reason(self) -> None:
        for kwargs in ({"name": "Jamie Chen"}, {"why": "Hiring manager."}, {"name": "  ", "why": "Hiring manager."}, {}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "needs a name and why they matter"):
                save_person(self.ws, today=TODAY, **kwargs)
        self.assertEqual(self.ws.people(), [])

    def test_validation_happens_before_any_write(self) -> None:
        with self.assertRaisesRegex(ValueError, ", ".join(("to_contact", "contacted", "follow_up", "replied", "paused"))):
            save_person(self.ws, name="Jamie Chen", why="x", status="friend", today=TODAY)
        with self.assertRaisesRegex(ValueError, "@"):
            save_person(self.ws, name="Jamie Chen", why="x", email="jamie at example", today=TODAY)
        with self.assertRaisesRegex(ValueError, "next_touch"):
            save_person(self.ws, name="Jamie Chen", why="x", next_touch="next week", today=TODAY)
        with self.assertRaises(KeyError):
            save_person(self.ws, name="Jamie Chen", why="x", job="nobody", today=TODAY)
        with self.assertRaises(KeyError):
            save_person(self.ws, person="nobody", note="Hi", today=TODAY)
        self.assertEqual(self.ws.people(), [])

    def test_creates_a_person_without_inventing_fields(self) -> None:
        result = save_person(self.ws, name="Jamie Chen", company="Northstar", why="Hiring manager for the agents team.", today=TODAY)
        self.assertEqual(
            result,
            {
                "ok": True,
                "created": True,
                "person": {
                    "person": "jamie-chen",
                    "name": "Jamie Chen",
                    "company": "Northstar",
                    "status": "to_contact",
                    "path": str(self.ws.people_dir / "jamie-chen.md"),
                },
            },
        )
        record = self.ws.resolve_person("jamie-chen")
        self.assertEqual((record["email"], record["linkedin"], record["role"], record["next_touch"]), ("", "", "", ""))
        self.assertEqual(record["jobs"], [])
        self.assertIn("Hiring manager for the agents team.", self.person_text("jamie-chen"))

    def test_create_with_everything(self) -> None:
        job_id = self.job("Northstar")
        result = save_person(
            self.ws,
            name="Jamie Chen",
            company="Northstar",
            role="Engineering Manager",
            email="jamie@example.com",
            linkedin="https://linkedin.example.com/in/jamie",
            why="Hiring manager.",
            status="contacted",
            job="northstar",
            note="Sent a short intro.",
            today=TODAY,
        )
        self.assertTrue(result["created"])
        self.assertEqual(
            result["person"],
            {
                "person": "jamie-chen",
                "name": "Jamie Chen",
                "company": "Northstar",
                "role": "Engineering Manager",
                "email": "jamie@example.com",
                "linkedin": "https://linkedin.example.com/in/jamie",
                "status": "contacted",
                "next_touch": iso(5),
                "jobs": [job_id],
                "path": str(self.ws.people_dir / "jamie-chen.md"),
            },
        )
        self.assertIn("Sent a short intro.", section(self.ws.read(self.ws.people_dir / "jamie-chen.md").body, "Log"))

    def test_same_name_updates_instead_of_duplicating(self) -> None:
        save_person(self.ws, name="Jamie Chen", company="Northstar", why="Hiring manager.", today=TODAY)
        result = save_person(self.ws, name="  jamie   CHEN ", role="Director of Engineering", email="jamie@example.com", today=TODAY)
        self.assertFalse(result["created"])
        self.assertEqual(len(self.ws.people()), 1)
        self.assertEqual(result["person"]["name"], "Jamie Chen")
        self.assertEqual(result["person"]["company"], "Northstar")
        self.assertEqual(result["person"]["role"], "Director of Engineering")
        self.assertEqual(result["person"]["email"], "jamie@example.com")
        self.assertIn("Hiring manager.", self.person_text("jamie-chen"))

    def test_updates_only_fields_that_were_passed(self) -> None:
        save_person(self.ws, name="Jamie Chen", company="Northstar", role="Manager", email="jamie@example.com", why="Hiring manager.", today=TODAY)
        result = save_person(self.ws, person="jamie-chen", name="Jamie L. Chen", company="", role="", linkedin="https://linkedin.example.com/in/jamie", today=TODAY)
        self.assertEqual(result["person"]["person"], "jamie-chen")
        self.assertEqual(result["person"]["name"], "Jamie L. Chen")
        self.assertEqual(result["person"]["company"], "Northstar")
        self.assertEqual(result["person"]["role"], "Manager")
        self.assertEqual(result["person"]["email"], "jamie@example.com")
        self.assertEqual(result["person"]["linkedin"], "https://linkedin.example.com/in/jamie")
        self.assertTrue((self.ws.people_dir / "jamie-chen.md").is_file())
        self.assertEqual(len(self.ws.people()), 1)

    def test_ambiguous_references_return_matches(self) -> None:
        self.ws.create_person(name="Jamie Chen", company="Northstar", why="x")
        self.ws.create_person(name="Jamie Ortiz", company="Fieldwork", why="x")
        result = save_person(self.ws, person="jamie", note="Hi", today=TODAY)
        self.assertTrue(result["ambiguous"])
        self.assertEqual({item["person"] for item in result["matches"]}, {"jamie-chen", "jamie-ortiz"})
        self.assertEqual(result["matches_total"], 2)

        self.ws.create_person(name="Jamie Chen", company="Meridian", why="x")
        twins = save_person(self.ws, name="Jamie Chen", status="contacted", today=TODAY)
        self.assertTrue(twins["ambiguous"])
        self.assertEqual({item["person"] for item in twins["matches"]}, {"jamie-chen", "jamie-chen-2"})
        self.assertEqual({item["status"] for item in self.ws.people()}, {"to_contact"})

        self.job("Northstar", "AI Engineer")
        self.job("Northstar", "Data Engineer")
        jobs = save_person(self.ws, person="jamie-ortiz", job="northstar", today=TODAY)
        self.assertTrue(jobs["ambiguous"])
        self.assertEqual({item["company"] for item in jobs["matches"]}, {"Northstar"})
        self.assertEqual(self.ws.resolve_person("jamie-ortiz").get("jobs"), [])

    def test_contacting_schedules_a_follow_up(self) -> None:
        save_person(self.ws, name="Jamie Chen", why="Hiring manager.", today=TODAY)
        result = save_person(self.ws, person="jamie", status="contacted", note="Sent the intro email.", today=TODAY)
        self.assertEqual(result["person"]["status"], "contacted")
        self.assertEqual(result["person"]["next_touch"], iso(5))
        log = section(self.ws.read(self.ws.people_dir / "jamie-chen.md").body, "Log")
        self.assertIn("Status: to_contact -> contacted. Sent the intro email.", log)

        self.ws.save_settings({"followups": {"networking_after_days": 2}})
        save_person(self.ws, name="Priya Raman", why="Recruiter.", today=TODAY)
        self.assertEqual(save_person(self.ws, person="priya", status="contacted", today=TODAY)["person"]["next_touch"], iso(2))

        save_person(self.ws, name="Sam Ortiz", why="Alum.", today=TODAY)
        explicit = save_person(self.ws, person="sam", status="contacted", next_touch=iso(14), today=TODAY)
        self.assertEqual(explicit["person"]["next_touch"], iso(14))

    def test_repeating_contacted_does_not_move_the_follow_up(self) -> None:
        save_person(self.ws, name="Jamie Chen", why="x", status="contacted", next_touch=iso(1), today=TODAY)
        result = save_person(self.ws, person="jamie", status="contacted", today=TODAY)
        self.assertTrue(result["unchanged"])
        self.assertEqual(result["person"]["next_touch"], iso(1))

    def test_reply_or_pause_clears_the_follow_up(self) -> None:
        for status in ("replied", "paused"):
            with self.subTest(status=status):
                name = f"Person {status}"
                save_person(self.ws, name=name, why="x", status="contacted", today=TODAY)
                result = save_person(self.ws, name=name, status=status, today=TODAY)
                self.assertEqual(result["person"]["status"], status)
                self.assertNotIn("next_touch", result["person"])
                self.assertEqual(self.ws.resolve_person(result["person"]["person"])["next_touch"], "")

        save_person(self.ws, name="Kept Date", why="x", status="contacted", today=TODAY)
        kept = save_person(self.ws, name="Kept Date", status="replied", next_touch=iso(7), today=TODAY)
        self.assertEqual(kept["person"]["next_touch"], iso(7))

        follow = save_person(self.ws, name="Kept Date", status="follow_up", today=TODAY)
        self.assertEqual(follow["person"]["next_touch"], iso(7))

    def test_next_touch_can_be_set_and_cleared(self) -> None:
        save_person(self.ws, name="Jamie Chen", why="x", today=TODAY)
        self.assertEqual(save_person(self.ws, person="jamie", next_touch=iso(3), today=TODAY)["person"]["next_touch"], iso(3))
        self.assertEqual(save_person(self.ws, person="jamie", today=TODAY)["person"]["next_touch"], iso(3))
        self.assertNotIn("next_touch", save_person(self.ws, person="jamie", next_touch="", today=TODAY)["person"])

    def test_jobs_are_linked_once(self) -> None:
        first = self.job("Northstar")
        second = self.job("Fieldwork")
        save_person(self.ws, name="Jamie Chen", why="x", job=first, today=TODAY)
        again = save_person(self.ws, person="jamie", job="northstar", today=TODAY)
        self.assertTrue(again["unchanged"])
        self.assertEqual(again["person"]["jobs"], [first])
        both = save_person(self.ws, person="jamie", job="fieldwork", today=TODAY)
        self.assertEqual(both["person"]["jobs"], [first, second])
        self.assertEqual(self.ws.resolve_person("jamie")["jobs"], [first, second])
        self.assertEqual([item["person"] for item in brief(self.ws, second)["people"]], ["jamie-chen"])

    def test_notes_go_to_the_log_and_no_op_leaves_the_file_alone(self) -> None:
        save_person(self.ws, name="Jamie Chen", company="Northstar", why="Hiring manager.", today=TODAY)
        before = self.person_text("jamie-chen")
        result = save_person(self.ws, name="Jamie Chen", company="Northstar", status="to_contact", today=TODAY)
        self.assertEqual((result["ok"], result["created"], result["unchanged"]), (True, False, True))
        self.assertEqual(self.person_text("jamie-chen"), before)

        result = save_person(self.ws, person="jamie-chen", note="Met at the\nmeetup.", today=TODAY)
        self.assertNotIn("unchanged", result)
        log = section(self.ws.read(self.ws.people_dir / "jamie-chen.md").body, "Log")
        self.assertTrue(log.endswith("Met at the meetup."))
        self.assertNotIn("Status:", log)

    def test_why_is_replaced_and_the_old_text_is_logged(self) -> None:
        save_person(self.ws, name="Jamie Chen", why="Hiring manager.", today=TODAY)
        save_person(self.ws, name="Jamie Chen", why="Hiring manager.", today=TODAY)
        result = save_person(self.ws, person="jamie", why="Now leads the agents team.", today=TODAY)
        self.assertNotIn("unchanged", result)
        body = self.ws.read(self.ws.people_dir / "jamie-chen.md").body
        self.assertEqual(section(body, "Why"), "Now leads the agents team.")
        self.assertEqual(section(body, "Log").count("Hiring manager."), 1)
        self.assertIn("Why replaced; it was: Hiring manager.", section(body, "Log"))



class StatsAndPrecedentTests(TrackingCase):
    def test_stats_count_only_sent_applications(self) -> None:
        self.job("Northstar", status="applied", applied_on=iso(-40), role_family="backend")
        self.job("Fieldwork", status="interviewing", applied_on=iso(-30), role_family="backend")
        self.job("Meridian", status="rejected", applied_on=iso(-65), role_family="data")
        self.job("Harbor", status="offer", applied_on=iso(-70), role_family="data")
        self.job("Common Ground", status="new")
        self.job("Lakeside", status="skipped")
        after_interview = self.job(
            "Ridgeline", status="rejected", applied_on=iso(-20), body_sections={"Log": "- 2027-03-01: Status: interview."}
        )
        stats = overview(self.ws, view="stats", today=TODAY)["stats"]
        self.assertEqual(stats["applied"], 5)
        self.assertEqual(stats["interviews"], 3)
        self.assertEqual(stats["offers"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["no_reply"], 1)
        self.assertEqual(stats["interview_rate"], "3 of 5")
        families = {row["role_family"]: row for row in stats["by_role_family"]}
        self.assertEqual(families["backend"]["applied"], 2)
        self.assertEqual(sum(row["applied"] for row in stats["by_month"]), 5)
        self.assertTrue(after_interview)

    def test_brief_points_to_the_closest_earlier_document(self) -> None:
        target = self.job("Northstar", "Backend Engineer", body_sections={"Requirements": "- Build Python data pipelines"})
        close = self.job("Fieldwork", "Backend Engineer", status="applied", body_sections={"Requirements": "- Python pipelines and APIs"})
        landed = self.job("Meridian", "Backend Engineer", status="interviewing", body_sections={"Requirements": "- Python services"})
        unrelated = self.job("Harbor", "Product Designer", status="applied", body_sections={"Requirements": "- Figma prototypes"})
        not_sent = self.job("Lakeside", "Backend Engineer", status="new")
        for job_id in (close, landed, unrelated, not_sent):
            self.material(job_id, "Jordan Example - Resume.typ")
        self.material(close, "cover-letter.typ")
        self.material(target, "Jordan Example - Resume.typ")

        result = brief(self.ws, target, purpose="resume")
        self.assertEqual([item["job"] for item in result["precedents"]], [landed, close])
        self.assertTrue(result["precedents"][0]["file"].endswith("Jordan Example - Resume.typ"))
        self.assertIn("precedents_note", result)

        letter = brief(self.ws, target, purpose="cover_letter")
        self.assertEqual([item["job"] for item in letter["precedents"]], [close])
        self.assertNotIn("precedents", brief(self.ws, unrelated, purpose="outreach"))


class TopApplicationTests(TrackingCase):
    def test_strategy_rides_in_the_brief_and_changes_the_next_step(self) -> None:
        job = self.job("Northstar", body_sections={"Strategy": "Thesis: the pipeline person.", "Application questions": "- Why us?"})
        result = brief(self.ws, job, purpose="application_answers")
        self.assertEqual(result["strategy"], "Thesis: the pipeline person.")
        self.assertEqual(result["application_questions"], "- Why us?")
        self.assertEqual(result["next"], "Write the document in the job folder, then run jobapps_check on it.")
        self.assertNotIn("application_questions", brief(self.ws, job, purpose="resume"))

    def test_a_second_brief_can_skip_the_evidence_text(self) -> None:
        job = self.job("Northstar")
        self.ws.write(self.ws.evidence_dir / "pipeline.md", {"title": "Pipeline", "status": "active"}, "LONG_FACT " * 50)
        full = brief(self.ws, job)
        light = brief(self.ws, job, purpose="cover_letter", evidence=False)
        self.assertIn("LONG_FACT", json.dumps(full))
        self.assertNotIn("LONG_FACT", json.dumps(light))
        self.assertEqual(light["evidence"]["mode"], "index")
        self.assertEqual(light["evidence"]["files"][0]["id"], "pipeline")

    def test_priority_and_referral_are_recorded_and_ordered(self) -> None:
        low = self.job("Fieldwork", next_action="Write resume", next_action_due=iso(0))
        high = self.job("Northstar", next_action="Write resume", next_action_due=iso(2))
        done = track_job(self.ws, high, priority="high", referral="Jamie Chen", today=TODAY)
        self.assertEqual(done["job"]["priority"], "high")
        self.assertEqual(done["job"]["referral"], "Jamie Chen")
        due = overview(self.ws, today=TODAY)["attention"]["due"]
        self.assertEqual([item["job"] for item in due], [high, low])
        self.assertNotIn("priority", due[1])
        with self.assertRaises(ValueError):
            track_job(self.ws, high, priority="urgent", today=TODAY)

    def test_reminders_arrive_when_marking_ready_and_applied(self) -> None:
        job = self.job(
            "Northstar",
            updated=-30,
            priority="high",
            body_sections={"Application questions": "- Why Northstar?"},
        )
        self.material(job, "Jordan Example - Resume.typ", qa="pass")
        ready = track_job(self.ws, job, status="ready", today=TODAY)
        joined = " ".join(ready["reminders"])
        self.assertIn("No one at Northstar is tracked", joined)
        self.assertIn("application questions", joined)
        self.assertIn("cover letter", joined)
        self.assertLessEqual(len(ready["reminders"]), 4)

        self.ws.create_person(name="Jamie Chen", company="Northstar", why="Hiring manager.")
        applied = track_job(self.ws, job, status="applied", today=TODAY)
        self.assertEqual(applied["reminders"], ["Tell Jamie Chen that the application is in."])
        self.assertNotIn("reminders", track_job(self.ws, job, note="Recruiter replied.", today=TODAY))

    def test_a_failing_letter_blocks_ready_like_a_failing_resume(self) -> None:
        job = self.job("Northstar")
        self.material(job, "Jordan Example - Resume.typ", qa="pass")
        self.material(job, "cover-letter.typ", qa="fail")
        blocked = track_job(self.ws, job, status="ready", today=TODAY)
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["blocked"], [{"name": "cover-letter.typ", "qa": "fail"}])

    def test_long_silent_applications_are_separated_from_the_ones_worth_chasing(self) -> None:
        fresh = self.job("Northstar", status="applied", applied_on=iso(-14))
        old = self.job("Fieldwork", status="applied", applied_on=iso(-80))
        attention = overview(self.ws, today=TODAY)["attention"]
        self.assertEqual([item["job"] for item in attention["applied_quiet"]], [fresh])
        self.assertEqual([item["job"] for item in attention["applied_stale"]], [old])
        self.assertEqual(attention["applied_stale_total"], 1)
        self.assertIn("45 days", attention["applied_stale_hint"])

    def test_due_date_can_be_cleared_while_keeping_the_action(self) -> None:
        job = self.job("Northstar", next_action="Write resume", next_action_due=iso(2))
        done = track_job(self.ws, job, due="", today=TODAY)
        self.assertEqual(done["changed"], ["next_action_due"])
        self.assertEqual(self.meta(job)["next_action"], "Write resume")
        self.assertEqual(self.meta(job)["next_action_due"], "")

    def test_close_stale_closes_only_long_silent_applications(self) -> None:
        from hermes_jobapps.tracking import close_stale

        fresh = self.job("Northstar", status="applied", applied_on=iso(-14))
        old = self.job("Fieldwork", status="applied", applied_on=iso(-80))
        chased = self.job("Meridian", status="applied", applied_on=iso(-80), next_action="Call Jamie", next_action_due=iso(3))
        result = close_stale(self.ws, today=TODAY)
        self.assertEqual(result["closed"], 1)
        self.assertEqual(self.meta(old)["status"], "closed")
        self.assertIn("No reply 80 days", self.log(old))
        self.assertEqual(self.meta(fresh)["status"], "applied")
        self.assertEqual(self.meta(chased)["status"], "applied")

    def test_stats_split_referrals_from_cold_applications(self) -> None:
        self.job("Northstar", status="interviewing", applied_on=iso(-20), referral="Jamie Chen")
        self.job("Fieldwork", status="applied", applied_on=iso(-20))
        rows = {row["channel"]: row for row in overview(self.ws, view="stats", today=TODAY)["stats"]["by_channel"]}
        self.assertEqual(rows["referral"]["interviews"], 1)
        self.assertEqual(rows["cold"]["applied"], 1)


if __name__ == "__main__":
    unittest.main()
