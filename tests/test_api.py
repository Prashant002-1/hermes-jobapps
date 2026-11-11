from __future__ import annotations

import contextlib
import importlib
import json
import sys
import tempfile
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import hermes_jobapps
from hermes_jobapps import api
from hermes_jobapps.workspace import STAGES, AmbiguousReference, Workspace, section


def iso(offset: int = 0) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


@contextlib.contextmanager
def patched(module: str, name: str, fake):
    """Replace hermes_jobapps.<module>.<name>, with a stub module when the real one is absent."""
    full = f"hermes_jobapps.{module}"
    try:
        real = importlib.import_module(full)
    except ImportError:
        stub = types.ModuleType(full)
        setattr(stub, name, fake)
        with mock.patch.dict(sys.modules, {full: stub}), mock.patch.object(hermes_jobapps, module, stub, create=True):
            yield fake
    else:
        with mock.patch.object(real, name, fake, create=True):
            yield fake


class ApiCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace(Path(self.tmp.name) / "ws")
        self.ws.init(name="Jordan Example")
        posting = "Northstar is hiring a product designer to shape the planning tools.\n" * 6
        self.new = self.job("Northstar", "Product Designer", posting=posting, url="https://northstar.example/jobs/1")
        self.ready = self.job("Harbor", "Design Engineer", status="ready")
        self.applied = self.job("Fieldwork", "Design Engineer", status="applied", applied_on=iso(-30))
        self.interviewing = self.job(
            "Quill", "Staff Designer", status="interviewing", next_action="Prepare the portfolio review", next_action_due=iso(1)
        )
        self.rejected = self.job("Lumen", "Designer", status="rejected")
        self.ws.create_person(
            name="Riley Stone", company="Northstar", role="Design Manager", email="riley@northstar.example", why="Leads the team."
        )
        self.lead = self.ws.create_lead(
            company="Northstar",
            title="Research Lead",
            url="https://northstar.example/jobs/2",
            posting="Lead research.",
            extra_meta={"preflight": "apply"},
        )["id"]
        self.ws.write(
            self.ws.evidence_dir / "fieldwork-redesign.md",
            {"title": "Fieldwork redesign", "type": "project", "status": "active", "tags": ["design", "research"]},
            "# Fieldwork redesign\n\nRebuilt the scheduling flow with the field team.",
        )
        folder = self.ws.job_dir(self.new)
        (folder / "resume.typ").write_text("= Jordan Example\nProduct designer.\n", encoding="utf-8")
        (folder / "resume.pdf").write_bytes(b"%PDF-1.4\n% invented\n")

    def job(self, company: str, title: str, *, status: str = "new", posting: str = "", url: str = "", **meta) -> str:
        return self.ws.create_job(
            company=company, title=title, status=status, posting=posting, url=url, created_on=iso(-2), extra_meta=meta
        )["id"]

    def get(self, route: str, **query: str):
        return api.handle(self.ws, "GET", route, query, None)

    def post(self, route: str, body: dict | None = None):
        return api.handle(self.ws, "POST", route, {}, body)


class StateTests(ApiCase):
    def test_state_shape_and_every_job(self) -> None:
        status, state = self.get("/state")
        self.assertEqual(status, 200)
        for key in ("version", "workspace", "ready", "as_of", "counts", "attention", "setup", "jobs", "people", "leads", "followups"):
            self.assertIn(key, state)
        self.assertTrue(state["ready"])
        self.assertEqual(state["as_of"], iso())
        self.assertEqual(
            {item["job"] for item in state["jobs"]},
            {self.new, self.ready, self.applied, self.interviewing, self.rejected},
        )
        self.assertEqual({item["stage"] for item in state["jobs"]}, {"new", "ready", "applied", "interviewing", "rejected"})
        self.assertEqual(state["counts"]["total"], 5)
        self.assertEqual(sum(state["counts"][stage] for stage in STAGES), 5)
        self.assertEqual(state["counts"]["people"], 1)
        self.assertEqual(state["counts"]["leads"], 1)
        self.assertEqual(state["people"][0]["name"], "Riley Stone")
        self.assertEqual(state["leads"][0]["lead"], self.lead)
        self.assertEqual(state["leads"][0]["preflight"], "apply")
        json.dumps(state)

    def test_attention_lists_carry_true_totals(self) -> None:
        attention = self.get("/state")[1]["attention"]
        self.assertEqual([item["job"] for item in attention["due"]], [self.interviewing])
        self.assertEqual(attention["due"][0]["days_overdue"], -1)
        self.assertEqual(attention["due_total"], 1)
        self.assertEqual(attention["applied_quiet"][0]["job"], self.applied)
        self.assertEqual(attention["applied_quiet"][0]["days"], 30)
        self.assertEqual(attention["ready_total"], 1)
        self.assertEqual(attention["interviewing_total"], 1)
        self.assertEqual([item["job"] for item in attention["in_progress"]], [self.new])
        self.assertEqual(attention["people"][0]["person"], "riley-stone")
        self.assertEqual(attention["leads_total"], 1)

    def test_job_detail(self) -> None:
        status, detail = self.get(f"/jobs/{self.new}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["job"]["company"], "Northstar")
        self.assertEqual(detail["job"]["url"], "https://northstar.example/jobs/1")
        self.assertEqual(detail["path"], f"jobs/{self.new}/job.md")
        self.assertTrue(detail["folder"].endswith(self.new))
        self.assertIn("planning tools", detail["sections"]["posting"])
        self.assertIn("Added.", detail["sections"]["log"])
        self.assertEqual(len(detail["materials"]), 1)
        material = detail["materials"][0]
        self.assertEqual(
            {key: material[key] for key in ("name", "kind", "format", "qa", "path", "pdf")},
            {
                "name": "resume.typ",
                "kind": "resume",
                "format": "typ",
                "qa": "none",
                "path": f"jobs/{self.new}/resume.typ",
                "pdf": f"jobs/{self.new}/resume.pdf",
            },
        )
        self.assertEqual([person["name"] for person in detail["people"]], ["Riley Stone"])
        self.assertEqual(detail["people"][0]["email"], "riley@northstar.example")
        json.dumps(detail)

    def test_unknown_job_is_404(self) -> None:
        status, payload = self.get("/jobs/2020-01-nobody-nothing")
        self.assertEqual(status, 404)
        self.assertIn("2020-01-nobody-nothing", payload["error"])

    def test_evidence_index(self) -> None:
        status, payload = self.get("/evidence")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["evidence"]), 1)
        record = payload["evidence"][0]
        self.assertEqual(record["title"], "Fieldwork redesign")
        self.assertEqual(record["type"], "project")
        self.assertEqual(record["status"], "active")
        self.assertEqual(record["tags"], ["design", "research"])
        self.assertEqual(record["path"], "evidence/fieldwork-redesign.md")
        self.assertNotIn("body", record)


class FileTests(ApiCase):
    def test_doc_returns_meta_and_body(self) -> None:
        status, doc = self.get("/doc", path="profile/profile.md")
        self.assertEqual(status, 200)
        self.assertEqual(doc["path"], "profile/profile.md")
        self.assertEqual(doc["meta"]["name"], "Jordan Example")
        self.assertTrue(doc["body"])
        status, doc = self.get("/doc", path="evidence/fieldwork-redesign.md")
        self.assertEqual(status, 200)
        self.assertEqual(doc["meta"]["tags"], ["design", "research"])
        self.assertIn("scheduling flow", doc["body"])
        status, doc = self.get("/doc", path=f"jobs/{self.new}/resume.typ")
        self.assertEqual((status, doc["meta"]), (200, {}))
        self.assertIn("Jordan Example", doc["body"])

    def test_doc_refuses_binary_and_bad_paths(self) -> None:
        self.assertEqual(self.get("/doc", path=f"jobs/{self.new}/resume.pdf")[0], 400)
        self.assertEqual(self.get("/doc")[0], 400)
        self.assertEqual(self.get("/doc", path="profile/missing.md")[0], 404)
        self.assertEqual(self.get("/doc", path="settings.json")[0], 400)

    def test_file_allows_viewable_types(self) -> None:
        folder = self.ws.job_dir(self.new)
        (folder / "shot.png").write_bytes(b"\x89PNG\r\n")
        for name in ("resume.pdf", "resume.typ", "job.md", "shot.png"):
            status, result = self.get("/file", path=f"jobs/{self.new}/{name}")
            self.assertEqual(status, 200, name)
            self.assertIsInstance(result, api.FileResult)
            self.assertEqual(result.path, (folder / name).resolve())

    def test_file_refuses_traversal(self) -> None:
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        for attempt in ("../outside.md", "jobs/../../outside.md", str(outside), "profile/../../outside.md"):
            status, payload = self.get("/file", path=attempt)
            self.assertEqual(status, 400, attempt)
            self.assertIn("inside the workspace", payload["error"])
            self.assertEqual(self.get("/doc", path=attempt)[0], 400, attempt)

    def test_file_refuses_symlink_out_of_the_workspace(self) -> None:
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        (self.ws.root / "link.md").symlink_to(outside)
        self.assertEqual(self.get("/file", path="link.md")[0], 400)

    def test_file_missing_and_refused_types(self) -> None:
        self.assertEqual(self.get("/file", path="jobs/nope/resume.pdf")[0], 404)
        self.assertEqual(self.get("/file", path="jobs")[0], 404)
        self.assertEqual(self.get("/file")[0], 400)
        status, payload = self.get("/file", path="settings.json")
        self.assertEqual(status, 400)
        self.assertIn("cannot be opened", payload["error"])
        (self.ws.root / "run.sh").write_text("echo hi", encoding="utf-8")
        self.assertEqual(self.get("/file", path="run.sh")[0], 400)


class WriteTests(ApiCase):
    def test_track_changes_stage_and_next_action(self) -> None:
        status, result = self.post(f"/jobs/{self.new}/track", {"status": "applied"})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(result["job"]["stage"], "applied")
        meta = self.ws.job_doc(self.new).meta
        self.assertEqual((meta["status"], str(meta["applied_on"])), ("applied", iso()))

        status, result = self.post(
            f"/jobs/{self.new}/track", {"next_action": "Follow up on the application", "due": iso(7)}
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["job"]["due"], iso(7))
        status, result = self.post(f"/jobs/{self.new}/track", {"next_action": "", "note": "Done: Follow up"})
        self.assertEqual(status, 200)
        self.assertNotIn("due", result["job"])
        self.assertIn("Done: Follow up", section(self.ws.job_doc(self.new).body, "Log"))

    def test_track_ready_is_blocked_until_forced(self) -> None:
        status, result = self.post(f"/jobs/{self.new}/track", {"status": "ready"})
        self.assertEqual(status, 200)
        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked"], [{"name": "resume.typ", "qa": "none"}])
        self.assertEqual(self.ws.job_doc(self.new).meta["status"], "new")
        self.assertFalse(self.post(f"/jobs/{self.new}/track", {"status": "ready", "force": "true"})[1]["ok"])
        status, result = self.post(f"/jobs/{self.new}/track", {"status": "ready", "force": True})
        self.assertTrue(result["ok"])
        self.assertEqual(self.ws.job_doc(self.new).meta["status"], "ready")

    def test_track_errors(self) -> None:
        status, payload = self.post(f"/jobs/{self.new}/track", {"due": "next week"})
        self.assertEqual(status, 400)
        self.assertIn("YYYY-MM-DD", payload["error"])
        self.assertEqual(self.post(f"/jobs/{self.new}/track", {"status": "promoted"})[0], 400)
        self.assertEqual(self.post("/jobs/2020-01-nobody-nothing/track", {"status": "applied"})[0], 404)

    def test_notes_replace_only_the_notes_section(self) -> None:
        status, result = self.post(f"/jobs/{self.new}/notes", {"text": "Ask about the team size.\nSecond line."})
        self.assertEqual((status, result), (200, {"ok": True}))
        body = self.ws.job_doc(self.new).body
        self.assertEqual(section(body, "Notes"), "Ask about the team size.\nSecond line.")
        self.assertIn("planning tools", section(body, "Posting"))
        self.assertIn("Added.", section(body, "Log"))
        self.assertEqual(self.get(f"/jobs/{self.new}")[1]["sections"]["notes"], "Ask about the team size.\nSecond line.")
        self.assertEqual(self.post("/jobs/2020-01-nobody-nothing/notes", {"text": "x"})[0], 404)

    def test_notes_with_headings_stay_inside_notes(self) -> None:
        text = "First line\n\n## Follow-ups\n\n- call Riley\n\n## Log\n\nnot the log\n\n##\nloose"
        self.post(f"/jobs/{self.new}/notes", {"text": text})
        sections = self.get(f"/jobs/{self.new}")[1]["sections"]
        for part in ("First line", "Follow-ups", "call Riley", "not the log", "loose"):
            self.assertIn(part, sections["notes"])
        self.assertIn("Added.", sections["log"])
        self.assertNotIn("not the log", sections["log"])
        self.post(f"/jobs/{self.new}/track", {"note": "Called the recruiter."})
        sections = self.get(f"/jobs/{self.new}")[1]["sections"]
        self.assertIn("Called the recruiter.", sections["log"])
        self.assertNotIn("Called the recruiter.", sections["notes"])

    def test_people_create_and_update(self) -> None:
        status, result = self.post(
            "/people", {"name": "Sam Park", "company": "Fieldwork", "why": "Hiring manager for the role.", "job": self.applied}
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["created"])
        self.assertEqual(result["person"]["person"], "sam-park")
        self.assertEqual(result["person"]["jobs"], [self.applied])

        status, result = self.post("/people", {"person": "riley-stone", "status": "contacted", "note": "Sent a short note."})
        self.assertEqual(status, 200)
        self.assertFalse(result["created"])
        self.assertEqual(result["person"]["status"], "contacted")
        self.assertTrue(result["person"]["next_touch"])
        status, result = self.post("/people", {"person": "riley-stone", "next_touch": ""})
        self.assertNotIn("next_touch", result["person"])
        self.assertEqual({item["name"] for item in self.get("/state")[1]["people"]}, {"Riley Stone", "Sam Park"})

    def test_people_errors(self) -> None:
        self.assertEqual(self.post("/people", {"name": "No Reason"})[0], 400)
        self.assertEqual(self.post("/people", {"person": "riley-stone", "email": "not-an-address"})[0], 400)
        self.assertEqual(self.post("/people", {"person": "nobody-here", "status": "paused"})[0], 404)


class DelegatedTests(ApiCase):
    def test_add_job_receives_string_fields(self) -> None:
        fake = mock.Mock(return_value={"ok": True, "job": {"job": "2026-11-fieldwork-researcher"}})
        with patched("intake", "add_job", fake):
            status, result = self.post("/jobs", {"url": "https://fieldwork.example/jobs/9", "company": "Fieldwork", "title": None})
        self.assertEqual(status, 200)
        self.assertEqual(result["job"]["job"], "2026-11-fieldwork-researcher")
        fake.assert_called_once_with(
            self.ws,
            url="https://fieldwork.example/jobs/9",
            text="",
            company="Fieldwork",
            title="",
            location="",
            notes="",
            lead="",
        )

    def test_add_job_needs_message_passes_through(self) -> None:
        answer = {"ok": False, "needs": ["company", "title"], "hint": "Read them from the posting and call again."}
        with patched("intake", "add_job", mock.Mock(return_value=answer)):
            self.assertEqual(self.post("/jobs", {"text": "A posting."}), (200, answer))

    def test_lead_status_and_promote(self) -> None:
        status_fake = mock.Mock(return_value={"ok": True, "lead": self.lead, "status": "shortlisted"})
        add_fake = mock.Mock(return_value={"ok": True, "job": {"job": "2026-11-northstar-research-lead"}})
        with patched("intake", "set_lead_status", status_fake), patched("intake", "add_job", add_fake):
            status, result = self.post(f"/leads/{self.lead}", {"status": "shortlisted"})
            self.assertEqual((status, result["status"]), (200, "shortlisted"))
            status_fake.assert_called_once_with(self.ws, self.lead, "shortlisted")
            add_fake.assert_not_called()

            status, result = self.post(f"/leads/{self.lead}", {"status": "promote"})
            self.assertEqual(status, 200)
            add_fake.assert_called_once_with(self.ws, lead=self.lead)
            status_fake.assert_called_once()

    def test_lead_errors_map_to_status_codes(self) -> None:
        with patched("intake", "set_lead_status", mock.Mock(side_effect=ValueError("Lead status must be one of: new."))):
            status, payload = self.post(f"/leads/{self.lead}", {"status": "bogus"})
        self.assertEqual((status, payload), (400, {"error": "Lead status must be one of: new."}))
        with patched("intake", "set_lead_status", mock.Mock(side_effect=KeyError("No leads match 'gone'."))):
            status, payload = self.post("/leads/gone", {"status": "dismissed"})
        self.assertEqual((status, payload), (404, {"error": "No leads match 'gone'."}))

    def test_ambiguous_reference_is_409(self) -> None:
        matches = [{"id": "northstar-research-lead"}, {"id": "northstar-design-lead"}]
        fake = mock.Mock(side_effect=AmbiguousReference("leads", "northstar", matches))
        with patched("intake", "set_lead_status", fake):
            status, payload = self.post("/leads/northstar", {"status": "dismissed"})
        self.assertEqual(status, 409)
        self.assertIn("northstar-research-lead", payload["error"])
        self.assertIn("Use the exact id", payload["error"])

    def test_check_receives_path_kind_and_job(self) -> None:
        answer = {"ok": True, "file": f"jobs/{self.new}/resume.typ", "status": "review"}
        fake = mock.Mock(return_value=answer)
        with patched("check", "check_material", fake):
            status, result = self.post("/check", {"path": f"jobs/{self.new}/resume.typ"})
            self.assertEqual((status, result), (200, answer))
            fake.assert_called_once_with(self.ws, f"jobs/{self.new}/resume.typ", kind="", job="")
            self.post("/check", {"path": "resume.typ", "kind": "resume", "job": self.new})
            fake.assert_called_with(self.ws, "resume.typ", kind="resume", job=self.new)


class StatsTests(ApiCase):
    def test_stats_route_reports_sent_applications(self) -> None:
        self.job(
            "Tidewater", "Designer", status="applied", applied_on=iso(-5), referral="Riley Stone", role_family="product_design"
        )
        status, payload = self.get("/stats")
        self.assertEqual(status, 200)
        self.assertEqual(payload["counts"]["total"], 6)
        stats = payload["stats"]
        self.assertEqual(
            {key: stats[key] for key in ("applied", "interviews", "offers", "rejected", "no_reply", "interview_rate")},
            {"applied": 3, "interviews": 1, "offers": 0, "rejected": 0, "no_reply": 2, "interview_rate": "1 of 3"},
        )
        channels = {row["channel"]: row for row in stats["by_channel"]}
        self.assertEqual(channels["referral"], {"channel": "referral", "applied": 1, "interviews": 0, "rejected": 0, "no_reply": 1})
        self.assertEqual(channels["cold"], {"channel": "cold", "applied": 2, "interviews": 1, "rejected": 0, "no_reply": 1})
        self.assertEqual(sum(row["applied"] for row in stats["by_month"]), 3)
        for row in stats["by_month"]:
            self.assertEqual(set(row), {"month", "applied", "interviews", "rejected", "no_reply"})
        families = {row["role_family"]: row["applied"] for row in stats["by_role_family"]}
        self.assertEqual(families, {"product_design": 1, "unlabelled": 2})
        json.dumps(payload)

    def test_stats_with_nothing_sent(self) -> None:
        empty = Workspace(Path(self.tmp.name) / "empty")
        empty.init(name="Jordan Example")
        empty.create_job(company="Northstar", title="Product Designer")
        status, payload = api.handle(empty, "GET", "/stats")
        self.assertEqual(status, 200)
        stats = payload["stats"]
        self.assertEqual((stats["applied"], stats["interviews"], stats["no_reply"]), (0, 0, 0))
        self.assertNotIn("interview_rate", stats)
        self.assertEqual((stats["by_channel"], stats["by_month"], stats["by_role_family"]), ([], [], []))

    def test_stats_is_read_only(self) -> None:
        self.assertEqual(self.post("/stats", {})[0], 404)


class CloseStaleTests(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.stale = self.job("Oakridge", "Designer", status="applied", applied_on=iso(-60), next_action="Check on the application")
        self.waiting = self.job(
            "Pinecrest", "Designer", status="applied", applied_on=iso(-80), next_action="Riley is asking", next_action_due=iso(5)
        )
        (self.ws.job_dir(self.stale) / "resume.typ").write_text("= Jordan Example\n", encoding="utf-8")

    def test_state_separates_quiet_from_stale(self) -> None:
        attention = self.get("/state")[1]["attention"]
        self.assertEqual([item["job"] for item in attention["applied_quiet"]], [self.applied])
        self.assertEqual([item["job"] for item in attention["applied_stale"]], [self.stale])
        self.assertEqual(attention["applied_stale_total"], 1)
        self.assertEqual(attention["applied_stale"][0]["days"], 60)
        self.assertIn("No reply for 45 days", attention["applied_stale_hint"])

    def test_close_stale_closes_only_long_silent_applications(self) -> None:
        status, result = self.post("/jobs/close-stale", {})
        self.assertEqual((status, result), (200, {"ok": True, "closed": 1, "jobs": [self.stale]}))
        doc = self.ws.job_doc(self.stale)
        self.assertEqual((doc.meta["status"], doc.meta["next_action"], doc.meta["next_action_due"]), ("closed", "", ""))
        self.assertIn("No reply 60 days after applying.", section(doc.body, "Log"))
        self.assertTrue((self.ws.job_dir(self.stale) / "resume.typ").is_file(), "closing keeps the files")
        self.assertEqual(self.ws.job_doc(self.applied).meta["status"], "applied")
        self.assertEqual(self.ws.job_doc(self.waiting).meta["status"], "applied")
        self.assertEqual(self.ws.job_doc(self.interviewing).meta["status"], "interviewing")

        state = self.get("/state")[1]
        self.assertNotIn("applied_stale", state["attention"])
        self.assertNotIn("applied_stale_hint", state["attention"])
        self.assertEqual(state["counts"]["closed"], 1)
        self.assertEqual(self.post("/jobs/close-stale")[1], {"ok": True, "closed": 0, "jobs": []})

    def test_close_stale_is_post_only_and_not_a_job_id(self) -> None:
        status, payload = self.get("/jobs/close-stale")
        self.assertEqual(status, 404)
        self.assertEqual(self.ws.job_doc(self.stale).meta["status"], "applied")
        self.assertEqual(self.post("/jobs/close-stale/track", {"status": "closed"})[0], 404)


class RoutingTests(ApiCase):
    def test_unknown_routes(self) -> None:
        status, payload = self.get("/nope")
        self.assertEqual((status, payload), (404, {"error": "Unknown route: /nope"}))
        self.assertEqual(self.post("/nope", {})[0], 404)
        self.assertEqual(self.get("/jobs")[0], 404)
        self.assertEqual(self.get("/jobs/../state")[0], 404)
        self.assertEqual(self.post(f"/jobs/{self.new}", {})[0], 404)

    def test_other_methods_are_refused(self) -> None:
        self.assertEqual(api.handle(self.ws, "DELETE", f"/jobs/{self.new}", {}, None)[0], 405)

    def test_path_and_body_are_normalized(self) -> None:
        self.assertEqual(api.handle(self.ws, "get", "state/")[0], 200)
        status, result = api.handle(self.ws, "POST", f"/jobs/{self.new}/track", None, ["not", "a", "dict"])
        self.assertEqual(status, 200)
        self.assertTrue(result["unchanged"])


if __name__ == "__main__":
    unittest.main()
