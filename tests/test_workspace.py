from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_jobapps.workspace import (
    AmbiguousReference,
    Workspace,
    append_to_section,
    normalize_stage,
    parse_frontmatter,
    render_document,
    section,
    set_section,
    slugify,
    update_frontmatter,
)


class FrontmatterTests(unittest.TestCase):
    def test_values_round_trip(self) -> None:
        meta = {
            "company": "Northstar: Labs",
            "title": "AI Engineer #2",
            "applied_on": "2026-11-02",
            "tags": ["agents", "c++, c#", "rag"],
            "count": 3,
            "remote": True,
            "empty": "",
            "looks_bool": "true",
            "looks_int": "2026",
            "quoted": 'She said "hi"',
            "leading": " padded",
        }
        parsed, body = parse_frontmatter(render_document(meta, "# Title\n\nBody"))
        self.assertEqual(parsed, meta)
        self.assertEqual(body, "# Title\n\nBody\n")

    def test_block_lists_and_hand_written_quotes(self) -> None:
        text = "---\nname: 'O''Brien'\njobs:\n  - alpha\n  - \"beta: two\"\nurl: https://example.com/a?b=1\n---\nBody\n"
        parsed, body = parse_frontmatter(text)
        self.assertEqual(parsed, {"name": "O'Brien", "jobs": ["alpha", "beta: two"], "url": "https://example.com/a?b=1"})
        self.assertEqual(body, "Body\n")

    def test_update_keeps_untouched_lines_verbatim(self) -> None:
        text = "---\ncompany:   Northstar\nnested:\n  key: value\njobs:\n  - alpha\nstatus: new\n---\n\nBody\n"
        updated = update_frontmatter(text, {"status": "applied", "applied_on": "2026-11-02"})
        self.assertIn("company:   Northstar\n", updated)
        self.assertIn("nested:\n  key: value\n", updated)
        self.assertIn("jobs:\n  - alpha\n", updated)
        self.assertIn("status: applied\n", updated)
        self.assertIn("applied_on: 2026-11-02\n", updated)
        self.assertTrue(updated.endswith("\nBody\n"))

    def test_file_without_frontmatter(self) -> None:
        self.assertEqual(parse_frontmatter("# Just a note\n"), ({}, "# Just a note\n"))
        self.assertEqual(parse_frontmatter("---\nno closing fence\n"), ({}, "---\nno closing fence\n"))

    def test_sections(self) -> None:
        body = "# Job\n\n## Posting\n\nBuild things.\n\n## Log\n\n- 2026-11-01: Added.\n"
        self.assertEqual(section(body, "posting"), "Build things.")
        body = append_to_section(body, "Log", "- 2026-11-02: Applied.")
        self.assertEqual(section(body, "Log"), "- 2026-11-01: Added.\n- 2026-11-02: Applied.")
        body = set_section(body, "Posting", "New text")
        self.assertEqual(section(body, "Posting"), "New text")
        self.assertIn("## Log", body)
        body = append_to_section(body, "Research", "- note")
        self.assertEqual(section(body, "Research"), "- note")
        for index in range(3):
            body = append_to_section(body, "Log", f"- extra {index}")
        self.assertNotIn("\n\n\n", body)

    def test_stage_and_slug(self) -> None:
        cases = {
            "hermes_failed": "new",
            "materials_ready": "ready",
            "Applied": "applied",
            "phone-screen": "interviewing",
            "offer": "offer",
            "declined": "rejected",
            "closed_superseded": "closed",
            "not_interested": "skipped",
            None: "new",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_stage(raw), expected)
        self.assertEqual(slugify("Northstar Labs, Inc."), "northstar-labs-inc")
        self.assertEqual(slugify("???", fallback="role"), "role")
        self.assertLessEqual(len(slugify("word " * 40, limit=20)), 20)


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmp.name) / "ws")
        self.ws.init(name="Jordan Example")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_init_is_non_destructive(self) -> None:
        profile = self.ws.profile_dir / "profile.md"
        self.assertEqual(self.ws.profile_meta()["name"], "Jordan Example")
        profile.write_text("---\nname: Edited\n---\n\nMine\n", encoding="utf-8")
        self.assertEqual(self.ws.init(name="Other"), [])
        self.assertEqual(self.ws.profile_meta()["name"], "Edited")
        self.assertEqual(self.ws.evidence(), [])
        self.assertEqual(self.ws.people(), [])

    def test_starter_templates_are_installed_and_carry_no_real_person(self) -> None:
        names = sorted(path.name for path in self.ws.templates_dir.iterdir())
        self.assertEqual(names, ["cover-letter.typ", "resume.typ"])
        resume = (self.ws.templates_dir / "resume.typ").read_text(encoding="utf-8")
        self.assertIn("Jordan Example", resume)
        self.assertIn("ligatures: false", resume)
        self.assertNotIn("@preview", resume)
        (self.ws.templates_dir / "resume.typ").unlink()
        self.assertEqual(self.ws.init(), [])

    def test_job_lifecycle(self) -> None:
        first = self.ws.create_job(company="Northstar", title="AI Engineer", posting="Build agents.", created_on="2026-11-01")
        second = self.ws.create_job(company="Northstar", title="AI Engineer", created_on="2026-11-01")
        self.assertEqual(first["id"], "2026-11-northstar-ai-engineer")
        self.assertEqual(second["id"], "2026-11-northstar-ai-engineer-2")
        doc = self.ws.update_job(first["id"], {"status": "submitted", "applied_on": "2026-11-03"}, log="Applied on the site.")
        self.assertEqual(doc.meta["status"], "applied")
        self.assertIn("Applied on the site.", section(doc.body, "Log"))
        self.assertEqual(section(doc.body, "Posting"), "Build agents.")
        jobs = self.ws.jobs()
        self.assertEqual({job["stage"] for job in jobs}, {"applied", "new"})
        tricky = self.ws.create_job(company="Meridian", title="Engineer", posting="About\n\n## Notes\nBring ideas.\n# Requirements\n- Python", notes="mine")
        tricky_doc = self.ws.job_doc(tricky["id"])
        self.assertEqual(section(tricky_doc.body, "Notes"), "mine")
        self.assertIn("**Notes**\nBring ideas.\n**Requirements**\n- Python", section(tricky_doc.body, "Posting"))
        self.assertEqual(self.ws.resolve_job(first["id"])["id"], first["id"])
        with self.assertRaises(AmbiguousReference):
            self.ws.resolve_job("northstar")
        with self.assertRaises(KeyError):
            self.ws.resolve_job("nobody")

    def test_materials_pair_sources_with_pdfs_and_reports(self) -> None:
        job = self.ws.create_job(company="Fieldwork", title="Data Engineer")
        folder = self.ws.job_dir(job["id"])
        (folder / "Jordan Example - Resume - Fieldwork.typ").write_text("x", encoding="utf-8")
        (folder / "Jordan Example - Resume - Fieldwork.pdf").write_bytes(b"%PDF")
        (folder / "cover-letter.tex").write_text("x", encoding="utf-8")
        (folder / "offer.pdf").write_bytes(b"%PDF")
        (folder / "qa").mkdir()
        (folder / "qa" / "cover-letter.tex.json").write_text("{}", encoding="utf-8")
        by_name = {item["name"]: item for item in self.ws.materials(job["id"])}
        self.assertEqual(by_name["Jordan Example - Resume - Fieldwork.typ"]["kind"], "resume")
        self.assertIn("pdf", by_name["Jordan Example - Resume - Fieldwork.typ"])
        self.assertEqual(by_name["cover-letter.tex"]["kind"], "cover_letter")
        self.assertIn("qa_report", by_name["cover-letter.tex"])
        self.assertEqual(by_name["offer.pdf"]["format"], "pdf")
        self.assertNotIn("job.md", by_name)
        self.assertNotIn("Jordan Example - Resume - Fieldwork.pdf", by_name)

    def test_people_and_leads(self) -> None:
        person = self.ws.create_person(name="Jamie Chen", company="Northstar", why="Met at a meetup.", status="bogus")
        self.assertEqual(person["status"], "to_contact")
        doc = self.ws.update_person(person["id"], {"status": "contacted", "next_touch": "2026-11-20"}, log="Sent a note.")
        self.assertEqual(doc.meta["status"], "contacted")
        self.assertIn("Sent a note.", doc.body)
        self.assertEqual(self.ws.resolve_person("jamie")["id"], "jamie-chen")

        lead = self.ws.create_lead(company="Meridian", title="ML Engineer", url="https://jobs.example.com/1/")
        again = self.ws.create_lead(company="Meridian", title="ML Engineer", url="https://jobs.example.com/1")
        self.assertTrue(again.get("duplicate"))
        self.assertEqual(again["id"], lead["id"])
        self.assertEqual(len(self.ws.leads()), 1)

    def test_evidence_hides_retired_and_templates(self) -> None:
        self.ws.write(self.ws.evidence_dir / "atlas.md", {"title": "Atlas", "status": "active"}, "Facts")
        self.ws.write(self.ws.evidence_dir / "old.md", {"title": "Old", "status": "retired"}, "Facts")
        self.assertEqual([item["id"] for item in self.ws.evidence()], ["atlas"])
        self.assertEqual(len(self.ws.evidence(include_retired=True)), 2)

    def test_paths_cannot_escape(self) -> None:
        self.assertTrue(str(self.ws.inside("profile/profile.md")).endswith("profile/profile.md"))
        with self.assertRaises(ValueError):
            self.ws.inside("../outside.txt")
        with self.assertRaises(ValueError):
            self.ws.inside("/etc/hosts")

    def test_settings_overlay_defaults(self) -> None:
        self.ws.save_settings({"followups": {"application_check_after_days": 7}})
        settings = self.ws.settings()
        self.assertEqual(settings["followups"]["application_check_after_days"], 7)
        self.assertEqual(settings["followups"]["networking_after_days"], 5)
        self.assertIn("resume_qa", settings)


if __name__ == "__main__":
    unittest.main()
