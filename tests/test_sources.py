from __future__ import annotations

import html
import json
import subprocess
import unittest
from unittest import mock

from hermes_jobapps import sources
from hermes_jobapps.sources import SourceError
from hermes_jobapps.workspace import DEFAULTS_PATH


GREENHOUSE_URL = "https://boards.greenhouse.io/northstar/jobs/123"
LEVER_URL = "https://jobs.lever.co/fieldwork/abc-123"
ASHBY_URL = "https://jobs.ashbyhq.com/meridian/5f0c2d1e"
ENV = {"EXA_API_KEY": "test-key"}


def setUpModule() -> None:
    for name in ("urlopen", "_run_command"):
        patcher = mock.patch.object(sources, name, side_effect=AssertionError(f"tests must not reach {name}"))
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


def default_settings() -> dict:
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


def greenhouse_payload() -> dict:
    content = (
        "<p>Northstar builds scheduling tools for field teams.</p>"
        "<h3>Requirements</h3>"
        "<ul><li>Experience building production APIs &amp; services.</li><li><p>Proficiency in Python.</p></li></ul>"
        "<script>track()</script>"
    )
    return {
        "title": "Applied AI Engineer",
        "company_name": "Northstar Labs",
        "location": {"name": "Denver, CO"},
        "absolute_url": GREENHOUSE_URL + "?gh_src=abc",
        "first_published": "2026-10-28T09:00:00-04:00",
        "updated_at": "2026-11-01T12:00:00Z",
        "content": html.escape(content),
        "questions": [
            {
                "label": "Will you now or in the future require sponsorship?",
                "required": True,
                "fields": [{"type": "multi_value_single_select"}],
            },
            {"label": "LinkedIn profile", "required": False, "fields": [{"type": "input_text"}]},
        ],
        "pay_input_ranges": [{"title": "Base salary", "min_cents": 10000000, "max_cents": 14000000, "currency_type": "USD"}],
    }


def lever_payload() -> dict:
    return {
        "text": "Data Platform Engineer",
        "categories": {"location": "Remote", "commitment": "Full-time", "team": "Engineering"},
        "workplaceType": "remote",
        "createdAt": 1793491200000,
        "descriptionPlain": "Build the pipelines behind Fieldwork reporting.\nOwn data quality checks.",
        "additionalPlain": "Fieldwork is an equal opportunity employer.",
        "lists": [{"text": "Requirements", "content": "<li>Experience with PostgreSQL</li><li>Clear writing</li>"}],
        "salaryDescription": "$120K - $160K",
        "urls": {"show": LEVER_URL, "apply": LEVER_URL + "/apply"},
    }


def ashby_payload() -> dict:
    return {
        "jobs": [
            {
                "id": "0000aaaa",
                "title": "Designer",
                "jobUrl": "https://jobs.ashbyhq.com/meridian/0000aaaa",
                "descriptionPlain": "Design things.",
            },
            {
                "id": "5f0c2d1e",
                "title": "Senior Platform Engineer",
                "location": "Austin, TX",
                "isRemote": False,
                "workplaceType": "OnSite",
                "employmentType": "FullTime",
                "publishedAt": "2026-11-02T13:00:00Z",
                "descriptionPlain": "Build backend services.\nCandidates must be authorized to work without sponsorship.",
                "jobUrl": ASHBY_URL,
                "applyUrl": ASHBY_URL + "/application",
                "compensation": {"compensationTierSummary": "$170K - $220K"},
            },
        ]
    }


class UrlAndTextTests(unittest.TestCase):
    def test_detects_supported_ats_urls(self) -> None:
        self.assertEqual(sources.detect_ats(GREENHOUSE_URL), {"provider": "greenhouse", "board": "northstar", "job_id": "123"})
        self.assertEqual(
            sources.detect_ats("job-boards.greenhouse.io/northstar/jobs/456?gh_src=x")["job_id"],
            "456",
        )
        self.assertEqual(
            sources.detect_ats("https://boards.greenhouse.io/embed/job_app?for=northstar&token=789"),
            {"provider": "greenhouse", "board": "northstar", "job_id": "789"},
        )
        self.assertEqual(sources.detect_ats("https://boards.greenhouse.io/northstar?gh_jid=321")["job_id"], "321")
        self.assertEqual(sources.detect_ats(LEVER_URL + "/apply"), {"provider": "lever", "site": "fieldwork", "posting_id": "abc-123"})
        self.assertEqual(sources.detect_ats("https://jobs.eu.lever.co/fieldwork/abc")["region"], "eu")
        self.assertEqual(sources.detect_ats(ASHBY_URL + "/application"), {"provider": "ashby", "board": "meridian", "job_id": "5f0c2d1e"})
        for url in ("https://example.com/careers/1", "https://greenhouse.io/", "", "not a url"):
            with self.subTest(url=url):
                self.assertEqual(sources.detect_ats(url), {"provider": ""})

    def test_normalize_url(self) -> None:
        self.assertEqual(
            sources.normalize_url(" HTTPS://Boards.Greenhouse.io/northstar/jobs/123/?utm_source=x&gh_src=y&b=2&a=1#apply "),
            "https://boards.greenhouse.io/northstar/jobs/123?a=1&b=2",
        )
        self.assertEqual(sources.normalize_url("jobs.lever.co/fieldwork/abc/"), "https://jobs.lever.co/fieldwork/abc")
        self.assertEqual(sources.normalize_url("https://example.com/Jobs/A?gh_jid=5"), "https://example.com/Jobs/A?gh_jid=5")
        self.assertEqual(sources.normalize_url(""), "")

    def test_strip_html_keeps_structure_and_drops_markup(self) -> None:
        raw = (
            "<div><p>Build &amp; ship <b>agents</b>.</p><style>p{}</style><!-- note -->"
            "<h2>Requirements</h2><ul><li>Python</li><li><p>SQL &lt; 5 joins</p></li></ul>Line one<br>Line two</div>"
        )
        expected = "Build & ship agents .\n\nRequirements\n\n- Python\n- SQL < 5 joins\n\nLine one\n\nLine two"
        self.assertEqual(sources.strip_html(raw), expected)
        self.assertEqual(sources.strip_html(html.escape(raw)), expected)
        self.assertEqual(sources.strip_html("Plain  text\n\n\nstays"), "Plain text\n\nstays")
        self.assertEqual(sources.strip_html(""), "")


class HydrationTests(unittest.TestCase):
    def test_greenhouse(self) -> None:
        calls = []

        def fetch(url: str) -> dict:
            calls.append(url)
            return greenhouse_payload()

        posting = sources.hydrate_posting(GREENHOUSE_URL + "?utm_source=feed", fetch_json=fetch)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("https://boards-api.greenhouse.io/v1/boards/northstar/jobs/123?"))
        self.assertIn("questions=true", calls[0])
        self.assertIn("pay_transparency=true", calls[0])
        self.assertEqual(posting["provider"], "greenhouse")
        self.assertEqual(posting["title"], "Applied AI Engineer")
        self.assertEqual(posting["company"], "Northstar Labs")
        self.assertEqual(posting["location"], "Denver, CO")
        self.assertEqual(posting["url"], GREENHOUSE_URL)
        self.assertEqual(posting["apply_url"], GREENHOUSE_URL)
        self.assertEqual(posting["posted_at"], "2026-10-28")
        self.assertEqual(posting["compensation"], "Base salary: 100,000 - 140,000 USD")
        self.assertEqual(
            posting["description"],
            "Northstar builds scheduling tools for field teams.\n\nRequirements\n\n"
            "- Experience building production APIs & services.\n- Proficiency in Python.",
        )
        self.assertEqual(
            posting["questions"],
            "Will you now or in the future require sponsorship? (required, multi_value_single_select); "
            "LinkedIn profile (optional, input_text)",
        )

    def test_greenhouse_company_falls_back_to_board_token_and_empties_are_omitted(self) -> None:
        posting = sources.hydrate_posting(
            "https://boards.greenhouse.io/north-star_labs/jobs/9",
            fetch_json=lambda url: {"title": "Engineer", "content": "<p>Short.</p>"},
        )
        self.assertEqual(
            posting,
            {
                "provider": "greenhouse",
                "title": "Engineer",
                "company": "North Star Labs",
                "url": "https://boards.greenhouse.io/north-star_labs/jobs/9",
                "apply_url": "https://boards.greenhouse.io/north-star_labs/jobs/9",
                "description": "Short.",
            },
        )

    def test_lever(self) -> None:
        calls = []

        def fetch(url: str) -> dict:
            calls.append(url)
            return lever_payload()

        posting = sources.hydrate_posting(LEVER_URL, fetch_json=fetch)
        self.assertEqual(calls, ["https://api.lever.co/v0/postings/fieldwork/abc-123?mode=json"])
        self.assertEqual(posting["provider"], "lever")
        self.assertEqual(posting["title"], "Data Platform Engineer")
        self.assertEqual(posting["company"], "Fieldwork")
        self.assertEqual(posting["location"], "Remote")
        self.assertEqual(posting["url"], LEVER_URL)
        self.assertEqual(posting["apply_url"], LEVER_URL + "/apply")
        self.assertEqual(posting["posted_at"], "2026-11-01")
        self.assertEqual(posting["compensation"], "$120K - $160K")
        self.assertEqual(posting["workplace"], "remote")
        self.assertEqual(posting["employment_type"], "full-time")
        self.assertNotIn("questions", posting)
        self.assertEqual(
            posting["description"],
            "Build the pipelines behind Fieldwork reporting.\n\nOwn data quality checks.\n\n"
            "Requirements\n\n- Experience with PostgreSQL\n- Clear writing\n\n"
            "Fieldwork is an equal opportunity employer.",
        )

    def test_lever_eu_uses_the_eu_api(self) -> None:
        calls = []

        def fetch(url: str) -> dict:
            calls.append(url)
            return lever_payload()

        sources.hydrate_posting("https://jobs.eu.lever.co/fieldwork/abc-123", fetch_json=fetch)
        self.assertEqual(calls, ["https://api.eu.lever.co/v0/postings/fieldwork/abc-123?mode=json"])

    def test_ashby_picks_the_matching_job(self) -> None:
        calls = []

        def fetch(url: str) -> dict:
            calls.append(url)
            return ashby_payload()

        for url in (ASHBY_URL, ASHBY_URL + "/application?utm_medium=x"):
            with self.subTest(url=url):
                posting = sources.hydrate_posting(url, fetch_json=fetch)
                self.assertEqual(posting["title"], "Senior Platform Engineer")
                self.assertEqual(posting["company"], "Meridian")
                self.assertEqual(posting["location"], "Austin, TX")
                self.assertEqual(posting["url"], ASHBY_URL)
                self.assertEqual(posting["apply_url"], ASHBY_URL + "/application")
                self.assertEqual(posting["posted_at"], "2026-11-02")
                self.assertEqual(posting["compensation"], "$170K - $220K")
                self.assertEqual(posting["workplace"], "onsite")
                self.assertEqual(posting["employment_type"], "full-time")
                self.assertIn("without sponsorship", posting["description"])
        self.assertEqual(calls[0], "https://api.ashbyhq.com/posting-api/job-board/meridian?includeCompensation=true")

    def test_ashby_without_a_matching_job_fails(self) -> None:
        with self.assertRaisesRegex(SourceError, "no posting that matches"):
            sources.hydrate_posting("https://jobs.ashbyhq.com/meridian/ffff9999", fetch_json=lambda url: ashby_payload())

    def test_unsupported_urls_never_fetch(self) -> None:
        def fetch(url: str) -> dict:
            raise AssertionError("must not fetch")

        for url in (
            "https://example.com/careers/42",
            "https://boards.greenhouse.io/northstar",
            "https://jobs.lever.co/fieldwork",
            "https://jobs.ashbyhq.com/meridian",
            "",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(SourceError, "not a supported ATS URL"):
                    sources.hydrate_posting(url, fetch_json=fetch)

    def test_provider_failures_are_named(self) -> None:
        def fetch(url: str) -> dict:
            raise RuntimeError("timeout")

        with self.assertRaisesRegex(SourceError, "Lever hydration failed: timeout"):
            sources.hydrate_posting(LEVER_URL, fetch_json=fetch)
        with self.assertRaisesRegex(SourceError, "Greenhouse hydration failed"):
            sources.hydrate_posting(GREENHOUSE_URL, fetch_json=lambda url: ["not", "an", "object"])

    def test_http_helpers_refuse_non_http_urls(self) -> None:
        with self.assertRaisesRegex(SourceError, "Only http and https"):
            sources.http_get_json("file:///etc/hosts")
        with self.assertRaisesRegex(SourceError, "Only http and https"):
            sources.http_post_json("ftp://example.com/x", {}, {})


class JobSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = default_settings()

    def test_request_and_result_parsing(self) -> None:
        calls = []

        def post(url: str, payload: dict, headers: dict) -> dict:
            calls.append((url, payload, headers))
            return {
                "requestId": "req_1",
                "results": [
                    {
                        "title": "Job Application for Applied AI Engineer at Northstar",
                        "url": GREENHOUSE_URL + "?gh_src=feed",
                        "publishedDate": "2026-11-03T00:00:00.000Z",
                        "highlights": ["Build agents.", "Location: Denver, CO. Hybrid."],
                    },
                    {"title": "Fieldwork - Data Platform Engineer", "url": LEVER_URL, "text": "Own the pipelines."},
                    {"title": "Senior Platform Engineer @ Meridian", "url": ASHBY_URL},
                    {"title": "Research Engineer - Evaluation - Lumen Labs", "url": "https://lumen.example/careers/7"},
                    {"title": "Orbital | Backend Engineer", "url": "https://orbital.example/jobs/2"},
                    {"title": "Product Analyst", "url": "https://jobs.lever.co/harbor-works/xyz"},
                    {"title": "Duplicate", "url": GREENHOUSE_URL + "/"},
                    {"title": "No url"},
                    "garbage",
                ],
            }

        jobs = sources.search_jobs("  applied ai   engineer ", self.settings, limit=5, post_json=post, env=ENV)
        url, payload, headers = calls[0]
        self.assertEqual(url, "https://api.exa.ai/search")
        self.assertEqual(headers["x-api-key"], "test-key")
        self.assertEqual(payload["query"], "applied ai engineer")
        self.assertEqual(payload["numResults"], 5)
        self.assertEqual(payload["type"], "auto")
        self.assertIn("jobs.ashbyhq.com", payload["includeDomains"])
        self.assertNotIn("category", payload)
        self.assertEqual(
            [(job["title"], job["company"]) for job in jobs],
            [
                ("Applied AI Engineer", "Northstar"),
                ("Data Platform Engineer", "Fieldwork"),
                ("Senior Platform Engineer", "Meridian"),
                ("Research Engineer - Evaluation", "Lumen Labs"),
                ("Backend Engineer", "Orbital"),
                ("Product Analyst", "Harbor Works"),
            ],
        )
        self.assertEqual(
            jobs[0],
            {
                "title": "Applied AI Engineer",
                "company": "Northstar",
                "url": GREENHOUSE_URL,
                "location": "Denver, CO",
                "snippet": "Build agents. Location: Denver, CO. Hybrid.",
                "published": "2026-11-03",
            },
        )
        self.assertEqual(jobs[1]["snippet"], "Own the pipelines.")
        self.assertEqual(set(jobs[2]), {"title", "company", "url", "location", "snippet", "published"})

    def test_result_title_shapes(self) -> None:
        cases = (
            ("Senior Engineer, Platform at Northstar - Remote", "https://northstar.example/jobs/1", ("Senior Engineer, Platform", "Northstar")),
            ("Job Application for Engineer - Platform at Northstar", GREENHOUSE_URL, ("Engineer - Platform", "Northstar")),
            ("Data Engineer – Fieldwork", "https://fieldwork.example/jobs/1", ("Data Engineer", "Fieldwork")),
            ("Data Engineer", "https://fieldwork.example/jobs/2", ("Data Engineer", "")),
            ("", ASHBY_URL, ("", "Meridian")),
        )
        for title, url, expected in cases:
            with self.subTest(title=title):
                found = sources.search_jobs(
                    "engineer",
                    self.settings,
                    post_json=lambda *_args, t=title, u=url: {"results": [{"title": t, "url": u}]},
                    env=ENV,
                )
                self.assertEqual((found[0]["title"], found[0]["company"]), expected)

    def test_limit_is_bounded_and_settings_drive_the_request(self) -> None:
        self.settings["discovery"]["exa"].update(
            {"api_key_env": "CUSTOM_EXA", "base_url": "https://exa.internal/", "type": "neural", "include_domains": []}
        )
        calls = []

        def post(url: str, payload: dict, headers: dict) -> dict:
            calls.append((url, payload, headers))
            return {"results": []}

        self.assertEqual(sources.search_jobs("engineer", self.settings, limit=500, post_json=post, env={"CUSTOM_EXA": "k2"}), [])
        url, payload, headers = calls[0]
        self.assertEqual(url, "https://exa.internal/search")
        self.assertEqual(payload["numResults"], 25)
        self.assertEqual(payload["type"], "neural")
        self.assertNotIn("includeDomains", payload)
        self.assertEqual(headers["x-api-key"], "k2")

    def test_missing_key_names_the_env_var(self) -> None:
        def post(url: str, payload: dict, headers: dict) -> dict:
            raise AssertionError("must not call the API")

        with self.assertRaisesRegex(SourceError, "EXA_API_KEY is not set"):
            sources.search_jobs("engineer", self.settings, post_json=post, env={})
        self.settings["discovery"]["exa"]["api_key_env"] = "CUSTOM_EXA"
        with self.assertRaisesRegex(SourceError, "CUSTOM_EXA is not set"):
            sources.search_jobs("engineer", self.settings, post_json=post, env={"EXA_API_KEY": "other"})

    def test_failures_are_clear(self) -> None:
        def post(url: str, payload: dict, headers: dict) -> dict:
            raise RuntimeError("provider down")

        with self.assertRaisesRegex(SourceError, "Exa job search failed: provider down"):
            sources.search_jobs("engineer", self.settings, post_json=post, env=ENV)
        with self.assertRaisesRegex(SourceError, "query is required"):
            sources.search_jobs("   ", self.settings, post_json=post, env=ENV)
        self.settings["discovery"]["enabled"] = False
        with self.assertRaisesRegex(SourceError, "turned off"):
            sources.search_jobs("engineer", self.settings, post_json=post, env=ENV)


class PeopleSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = default_settings()

    def test_request_parsing_and_dedupe(self) -> None:
        calls = []

        def post(url: str, payload: dict, headers: dict) -> dict:
            calls.append((url, payload, headers))
            return {
                "results": [
                    {
                        "title": "Jordan Example - Engineering Manager - Northstar | LinkedIn",
                        "url": "https://www.linkedin.com/in/jordan-example",
                        "highlights": ["Leads platform hiring at Northstar. " + "Very long detail. " * 30],
                    },
                    {
                        "title": "Jordan Example | LinkedIn",
                        "url": "https://www.linkedin.com/in/jordan-example/",
                        "highlights": ["Same person again."],
                    },
                    {
                        "title": "Riley Sample | Recruiter at Northstar Labs",
                        "url": "https://northstar.example/team/riley",
                        "highlights": ["Reach Riley at Riley.Sample@northstar.example for roles."],
                    },
                    {"title": "Casey Placeholder, Staff Engineer", "url": "https://example.com/casey"},
                    {"title": "", "url": "https://example.com/nobody"},
                ]
            }

        people = sources.search_people(company="Northstar", settings=self.settings, limit=4, post_json=post, env=ENV)
        url, payload, headers = calls[0]
        self.assertEqual(url, "https://api.exa.ai/search")
        self.assertEqual(payload["category"], "people")
        self.assertEqual(payload["numResults"], 4)
        self.assertIn("Northstar", payload["query"])
        self.assertEqual(headers["x-api-key"], "test-key")
        self.assertEqual([person["name"] for person in people], ["Jordan Example", "Riley Sample", "Casey Placeholder"])
        first = people[0]
        self.assertEqual(first["role"], "Engineering Manager")
        self.assertEqual(first["company"], "Northstar")
        self.assertEqual(first["linkedin"], "https://www.linkedin.com/in/jordan-example")
        self.assertEqual(first["source_url"], "https://www.linkedin.com/in/jordan-example")
        self.assertLessEqual(len(first["snippet"]), 240)
        self.assertNotIn("email", first)
        self.assertEqual(set(first), {"name", "role", "company", "linkedin", "source_url", "snippet"})
        self.assertEqual(people[1]["role"], "Recruiter")
        self.assertEqual(people[1]["company"], "Northstar Labs")
        self.assertEqual(people[1]["linkedin"], "")
        self.assertEqual(people[1]["email"], "riley.sample@northstar.example")
        self.assertEqual((people[2]["role"], people[2]["company"]), ("Staff Engineer", "Northstar"))
        self.assertNotIn("email", people[2])

    def test_query_handling(self) -> None:
        queries = []

        def post(url: str, payload: dict, headers: dict) -> dict:
            queries.append(payload["query"])
            return {"results": []}

        sources.search_people(query="design leads in Denver", settings=self.settings, post_json=post, env=ENV)
        sources.search_people(company="Fieldwork", query="data engineering manager", settings=self.settings, post_json=post, env=ENV)
        self.settings["networking"]["people_query"] = "{company} talent partner"
        sources.search_people(company="Fieldwork", settings=self.settings, post_json=post, env=ENV)
        self.assertEqual(
            queries,
            ["design leads in Denver", "Fieldwork data engineering manager", "Fieldwork talent partner"],
        )

    def test_requirements_and_failures(self) -> None:
        def post(url: str, payload: dict, headers: dict) -> dict:
            raise RuntimeError("provider down")

        with self.assertRaisesRegex(SourceError, "company or a query"):
            sources.search_people(settings=self.settings, post_json=post, env=ENV)
        with self.assertRaisesRegex(SourceError, "EXA_API_KEY is not set"):
            sources.search_people(company="Northstar", settings=self.settings, post_json=post, env={})
        with self.assertRaisesRegex(SourceError, "Exa people search failed"):
            sources.search_people(company="Northstar", settings=self.settings, post_json=post, env=ENV)
        self.settings["networking"]["enabled"] = False
        with self.assertRaisesRegex(SourceError, "turned off"):
            sources.search_people(company="Northstar", settings=self.settings, post_json=post, env=ENV)


class GmailDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = default_settings()
        self.calls: list[tuple[list[str], str, float]] = []

    def run_ok(self, command: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, stdin, timeout))
        return subprocess.CompletedProcess(command, 0, '{"draftId":"draft_123","message":{"id":"msg_1"}}', "")

    def test_builds_a_draft_only_command(self) -> None:
        result = sources.create_gmail_draft(
            to="jordan@example.com",
            subject="Quick  note",
            body="\nHi Jordan, this is a draft.\n",
            account="me@example.com",
            settings=self.settings,
            run=self.run_ok,
        )
        self.assertEqual(result, {"ok": True, "draft_id": "draft_123", "to": "jordan@example.com"})
        command, stdin, timeout = self.calls[0]
        self.assertEqual(
            command,
            [
                "gog",
                "--account",
                "me@example.com",
                "--gmail-no-send",
                "--json",
                "--no-input",
                "gmail",
                "drafts",
                "create",
                "--subject",
                "Quick note",
                "--body-file",
                "-",
                "--to",
                "jordan@example.com",
            ],
        )
        self.assertNotIn("send", command)
        self.assertEqual(stdin, "Hi Jordan, this is a draft.")
        self.assertEqual(timeout, 30)

    def test_recipient_and_account_are_optional(self) -> None:
        self.settings["networking"].update({"gog_path": "/opt/tools/gog", "gog_timeout_seconds": 12})
        result = sources.create_gmail_draft(subject="Hello", body="Body", settings=self.settings, run=self.run_ok)
        command, _, timeout = self.calls[0]
        self.assertEqual(result["to"], "")
        self.assertEqual(command[:2], ["/opt/tools/gog", "--gmail-no-send"])
        self.assertNotIn("--to", command)
        self.assertNotIn("--account", command)
        self.assertEqual(timeout, 12)

    def test_draft_id_shapes(self) -> None:
        for stdout, expected in (
            ('{"id":"d1"}', "d1"),
            ('{"draft":{"id":"d2"}}', "d2"),
            ("created", ""),
            ("", ""),
        ):
            with self.subTest(stdout=stdout):
                result = sources.create_gmail_draft(
                    subject="Hello",
                    body="Body",
                    settings=self.settings,
                    run=lambda command, stdin, timeout, out=stdout: subprocess.CompletedProcess(command, 0, out, ""),
                )
                self.assertEqual(result["draft_id"], expected)

    def test_missing_gog_binary(self) -> None:
        self.settings["networking"]["gog_path"] = "/nonexistent/jobapps-test-gog"
        with self.assertRaisesRegex(SourceError, "gog command not found: /nonexistent/jobapps-test-gog"):
            sources.create_gmail_draft(subject="Hello", body="Body", settings=self.settings)

        def missing(command: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError(command[0])

        with self.assertRaisesRegex(SourceError, "gog command not found"):
            sources.create_gmail_draft(subject="Hello", body="Body", settings=self.settings, run=missing)

    def test_invalid_input_never_runs(self) -> None:
        cases = (
            {"to": "not-an-email", "subject": "Hello", "body": "Body"},
            {"to": "a@b.com, c@d.com", "subject": "Hello", "body": "Body"},
            {"to": "-x@example.com", "subject": "Hello", "body": "Body"},
            {"subject": " ", "body": "Body"},
            {"subject": "Hello", "body": "  "},
            {"subject": "Hello", "body": "Body", "account": "--send"},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SourceError):
                    sources.create_gmail_draft(settings=self.settings, run=self.run_ok, **kwargs)
        self.assertEqual(self.calls, [])

    def test_failures_report_the_stderr_tail(self) -> None:
        def failing(command: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 2, "", "x" * 1000 + " token expired")

        with self.assertRaises(SourceError) as caught:
            sources.create_gmail_draft(subject="Hello", body="Body", settings=self.settings, run=failing)
        self.assertTrue(str(caught.exception).endswith("token expired"))
        self.assertLess(len(str(caught.exception)), 460)

        def slow(command: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(command, timeout)

        with self.assertRaisesRegex(SourceError, "timed out"):
            sources.create_gmail_draft(subject="Hello", body="Body", settings=self.settings, run=slow)
        self.settings["networking"]["enabled"] = False
        with self.assertRaisesRegex(SourceError, "turned off"):
            sources.create_gmail_draft(subject="Hello", body="Body", settings=self.settings, run=self.run_ok)


if __name__ == "__main__":
    unittest.main()
