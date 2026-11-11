"""One application from posting to applied, through the real tools.

Nothing is mocked except the network. The build steps need Typst and Poppler;
the test skips when they are not installed.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hermes_jobapps import plugin
from hermes_jobapps.workspace import Workspace, qa_state, section


POSTING = """Backend Engineer

Northstar Labs builds routing software for regional delivery fleets. We are hiring a backend engineer
to make our data pipelines dependable as we grow.

Responsibilities
- Build and operate Python data pipelines on Airflow.
- Own PostgreSQL performance for the reporting service.
- Carry the pager for the services you build.

Requirements
- 1+ years of experience building backend services in Python.
- Experience with PostgreSQL and SQL performance tuning.
- Experience operating services in production with monitoring and on-call.

We are open to sponsorship for the right candidate. This role is remote within the United States.
"""

EVIDENCE = """# Software Engineer at Fieldwork Analytics

## What it was

Backend engineer on the reporting team of a logistics analytics company.

## Facts

- Rebuilt the nightly ingestion job as incremental loads, cutting a 6-hour run to 40 minutes.
- Carries the pager one week in four. Peer tutor for 30 students in Data Structures.
"""

TOOLCHAIN = all(shutil.which(tool, path=os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin") for tool in ("typst", "pdftotext", "pdfinfo"))


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "ws"
        self.ws = Workspace(self.root)
        self.ws.init(name="Jordan Example")
        self.ws.set_meta(self.ws.profile_dir / "profile.md", {"email": "jordan@example.com", "phone": "(555) 010-2030"})
        self.ws.write(
            self.ws.evidence_dir / "fieldwork.md",
            {"title": "Software Engineer", "organization": "Fieldwork Analytics", "status": "active", "type": "experience"},
            EVIDENCE,
        )
        self.ws.save_settings({"rules": {"needs_sponsorship": True}})
        self.env = patch.dict(os.environ, {"JOBAPPS_HOME": str(self.root)})
        self.env.start()
        plugin._workspaces.clear()
        plugin._configured_root = lambda: ""

    def tearDown(self) -> None:
        self.env.stop()
        plugin._workspaces.clear()
        self.tmp.cleanup()

    def call(self, tool: str, **args):
        return json.loads(plugin.run_tool(tool, args))

    def test_posting_to_applied(self) -> None:
        added = self.call("jobapps_add_job", text=POSTING, company="Northstar Labs", title="Backend Engineer", location="Remote")
        self.assertTrue(added["ok"], added)
        self.assertEqual(added["preflight"]["decision"], "apply")
        job_id = added["job"]["job"]
        self.assertTrue(self.call("jobapps_add_job", text=POSTING, company="Northstar Labs", title="Backend Engineer")["duplicate"])

        brief = self.call("jobapps_brief", job=job_id, purpose="resume")
        self.assertIn("routing software", brief["posting"])
        self.assertEqual(brief["evidence"]["mode"], "full")
        self.assertIn("6-hour run", brief["evidence"]["files"][0]["text"])
        self.assertIn("Strategy section", brief["next"])
        self.assertEqual(brief["profile"]["contact"]["email"], "jordan@example.com")

        doc = self.ws.job_doc(job_id)
        self.ws.set_body(doc.path, doc.body + "\n## Strategy\n\nThesis: ran the same kind of pipeline this team needs to steady.\n")
        self.assertIn("Thesis", self.call("jobapps_brief", job=job_id)["strategy"])

        if not TOOLCHAIN:
            self.skipTest("Typst and Poppler are needed for the build half of this test.")

        resume = self.ws.job_dir(job_id) / "Jordan Example - Resume - Northstar Labs - Backend Engineer.typ"
        shutil.copy(self.ws.templates_dir / "resume.typ", resume)
        blocked = self.call("jobapps_track", job=job_id, status="ready")
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["blocked"][0]["qa"], "none")

        checked = self.call("jobapps_check", job=job_id, path=resume.name)
        self.assertTrue(checked["ok"], checked)
        self.assertTrue(checked["build"]["ok"], checked)
        self.assertEqual(checked["build"]["pages"], 1)
        self.assertTrue(checked["layout"]["ready"], checked["layout"])
        self.assertTrue(checked["submission"]["ats"]["email_readable"])
        self.assertIn(checked["status"], ("pass", "review"))
        self.assertNotIn("wrong_company", json.dumps(checked))
        self.assertTrue(resume.with_suffix(".pdf").is_file())
        self.assertEqual(qa_state(resume)["state"], checked["status"])
        self.assertLess(len(json.dumps(checked)), 9000)

        ready = self.call("jobapps_track", job=job_id, status="ready", next_action="Submit on the careers page")
        self.assertTrue(ready["ok"], ready)
        self.assertIn("No one at Northstar Labs is tracked", " ".join(ready["reminders"]))

        resume.write_text(resume.read_text(encoding="utf-8").replace("jordan@example.com", "jordan@exmaple.com"), encoding="utf-8")
        self.assertEqual(qa_state(resume)["state"], "stale")
        broken = self.call("jobapps_check", job=job_id, path=resume.name)
        self.assertEqual(broken["status"], "fail")
        self.assertEqual(broken["submission"]["findings"][0]["rule"], "contact_mismatch")
        self.assertIn("submission", broken["next"])

        self.call("jobapps_person", name="Jamie Chen", company="Northstar Labs", why="Hiring manager for the role.", job=job_id)
        applied = self.call("jobapps_track", job=job_id, status="applied", referral="Jamie Chen")
        self.assertEqual(applied["job"]["stage"], "applied")
        self.assertEqual(applied["job"]["applied_on"], date.today().isoformat())
        self.assertEqual(applied["reminders"], ["Tell Jamie Chen that the application is in."])
        log = section(self.ws.job_doc(job_id).body, "Log")
        self.assertIn("Status: ready -> applied.", log)

        today = self.call("jobapps_overview")
        self.assertEqual(today["counts"]["applied"], 1)
        stats = self.call("jobapps_overview", view="stats")["stats"]
        self.assertEqual(stats["by_channel"], [{"channel": "referral", "applied": 1, "interviews": 0, "rejected": 0, "no_reply": 1}])
        self.assertIn("Northstar Labs: Backend Engineer", plugin.slash_command("jobs northstar"))

    def test_a_denied_sponsorship_posting_is_stopped_at_intake(self) -> None:
        text = POSTING.replace("We are open to sponsorship for the right candidate.", "We are unable to sponsor visas for this role.")
        added = self.call("jobapps_add_job", text=text, company="Meridian", title="Backend Engineer")
        self.assertEqual(added["preflight"]["decision"], "skip")
        self.assertEqual(added["preflight"]["blockers"][0]["area"], "sponsorship")
        self.assertIn("blocker", added["next"])


if __name__ == "__main__":
    unittest.main()
