from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from hermes_jobapps.migrate import COUNT_KEYS, SKIP_KEYS, migrate_legacy
from hermes_jobapps.workspace import Workspace, parse_frontmatter, section


TODAY = date(2026, 11, 10)

SCHEMA = {
    "profile_facts": "fact_key TEXT, value TEXT, category TEXT, source TEXT, confidence REAL, updated_at TEXT",
    "proof_points": (
        "id TEXT, label TEXT, role_family TEXT, summary TEXT, evidence TEXT, tags TEXT, source TEXT, "
        "confidence REAL, status TEXT, user_confirmed INTEGER, narrative_version TEXT, allowed_uses TEXT, "
        "risk_level TEXT, superseded_by TEXT, created_at TEXT, updated_at TEXT"
    ),
    "learning_patterns": (
        "id TEXT, pattern_type TEXT, trigger TEXT, preference TEXT, status TEXT, superseded_by TEXT, "
        "metadata TEXT, created_at TEXT, updated_at TEXT"
    ),
    "jobs": (
        "id TEXT, title TEXT, company TEXT, location TEXT, url TEXT, description TEXT, user_notes TEXT, "
        "status TEXT, role_family TEXT, decision TEXT, next_action TEXT, created_at TEXT, updated_at TEXT"
    ),
    "events": "id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, event_type TEXT, payload TEXT, created_at TEXT",
    "evaluations": "id TEXT, job_id TEXT, payload TEXT, created_at TEXT",
    "tailoring_requirements": "id TEXT, job_id TEXT, requirement TEXT, priority REAL, created_at TEXT",
    "research_notes": "id TEXT, job_id TEXT, subject TEXT, source_url TEXT, summary TEXT, created_at TEXT",
    "followups": "id TEXT, job_id TEXT, contact_id TEXT, due_date TEXT, reason TEXT, status TEXT, created_at TEXT",
    "progress_items": "id TEXT, job_id TEXT, title TEXT, status TEXT, due_date TEXT, created_at TEXT",
    "materials": (
        "id TEXT, job_id TEXT, kind TEXT, format TEXT, content TEXT, file_path TEXT, metadata TEXT, "
        "created_at TEXT, updated_at TEXT"
    ),
    "contacts": (
        "id TEXT, name TEXT, company TEXT, role TEXT, email TEXT, email_status TEXT, linkedin_url TEXT, "
        "source_url TEXT, notes TEXT, is_tracked INTEGER, why_added TEXT, network_status TEXT, "
        "created_at TEXT, updated_at TEXT"
    ),
    "discovery_candidates": (
        "id TEXT, source_provider TEXT, status TEXT, title TEXT, company TEXT, location TEXT, "
        "canonical_url TEXT, discovered_url TEXT, apply_url TEXT, retrieved_at TEXT, description TEXT, "
        "job_id TEXT, created_at TEXT, updated_at TEXT"
    ),
}

POSTING = "Build agent tooling for logistics teams.\n\nYou will own the planning service."


def insert(conn: sqlite3.Connection, table: str, **values: object) -> None:
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(values.values()))


def status_event(conn: sqlite3.Connection, job_id: str, when: str, status: str, note: str = "") -> None:
    payload = json.dumps({"status": status, "note": note})
    insert(conn, "events", job_id=job_id, event_type="status_changed", payload=payload, created_at=when)


def build_legacy(root: Path, *, without: tuple[str, ...] = ()) -> Path:
    db_path = root / "legacy" / "jobapps.db"
    materials = db_path.parent / "materials"
    external = root / "external"
    (materials / "j1" / "build").mkdir(parents=True)
    external.mkdir()
    (materials / "j1" / "Jordan Example - Resume - Northstar.typ").write_text("= Jordan Example\n", encoding="utf-8")
    (materials / "j1" / "Jordan Example - Resume - Northstar.pdf").write_bytes(b"%PDF-resume")
    (materials / "j1" / "compile.log").write_text("log", encoding="utf-8")
    (materials / "j1" / "build" / "scratch.pdf").write_bytes(b"%PDF-scratch")
    (external / "Jordan Example - Cover Letter - Northstar.tex").write_text("\\documentclass{letter}\n", encoding="utf-8")
    (external / "Jordan Example - Cover Letter - Northstar.pdf").write_bytes(b"%PDF-letter")

    conn = sqlite3.connect(db_path)
    for table, columns in SCHEMA.items():
        if table not in without:
            conn.execute(f"CREATE TABLE {table} ({columns})")

    def add(table: str, **values: object) -> None:
        if table not in without:
            insert(conn, table, **values)

    add("profile_facts", fact_key="candidate_name", value="Jordan Example", category="identity")
    add("profile_facts", fact_key="Email", value="jordan@example.com", category="identity")
    add("profile_facts", fact_key="linkedin_url", value="https://linkedin.example/in/jordan", category="identity")
    add("profile_facts", fact_key="portfolio", value="https://jordan.example", category="identity")
    add(
        "profile_facts",
        fact_key="work_authorization",
        value="Authorized to work.\nNo sponsorship needed.",
        category="hard_constraints",
    )
    add("profile_facts", fact_key="target_roles", value="Applied AI engineering", category="direction")

    proof = {"role_family": "ai_engineering", "summary": "Routing summary.", "evidence": "- Cut planning time."}
    add(
        "proof_points",
        id="p1",
        label="Atlas Routing Engine",
        tags='["python", "routing"]',
        status="active",
        user_confirmed=1,
        allowed_uses='["resume", "cover_letter", "interview", "outreach"]',
        risk_level="safe",
        created_at="2026-08-01T10:00:00+00:00",
        **proof,
    )
    add(
        "proof_points",
        id="p2",
        label="Atlas Routing Engine",
        tags="[]",
        status="candidate",
        user_confirmed=0,
        allowed_uses='["interview"]',
        risk_level="caution",
        created_at="2026-08-02T10:00:00+00:00",
        **proof,
    )
    add(
        "proof_points",
        id="p3",
        label="Old Claim",
        tags="[]",
        status="superseded",
        user_confirmed=1,
        allowed_uses="[]",
        risk_level="safe",
        superseded_by="p1",
        created_at="2026-08-03T10:00:00+00:00",
        **proof,
    )
    add(
        "proof_points",
        id="p4",
        label="Unconfirmed Win",
        tags="[]",
        status="active",
        user_confirmed=0,
        risk_level="safe",
        created_at="2026-08-04T10:00:00+00:00",
        **proof,
    )

    def rule(rule_id: str, key: str, preference: str, *, status: str = "active", superseded_by: str = "") -> None:
        add(
            "learning_patterns",
            id=rule_id,
            pattern_type="materials_quality",
            trigger=f"Trigger for {rule_id}",
            preference=preference,
            status=status,
            superseded_by=superseded_by,
            metadata=json.dumps({"rule_key": key} if key else {}),
            updated_at=f"2026-09-0{rule_id[-1]}T00:00:00+00:00",
        )

    rule("r1", "candidate.truth", "Only state confirmed facts.")
    rule("r2", "resume.bullets", "Lead with the mechanism.")
    rule("r3", "resume.evidence_selection", "Pick two projects.")
    rule("r4", "cover_letter.substance", "Open with the product.")
    rule("r5", "candidate.voice", "Short, plain sentences.")
    rule("r6", "", "Keep an eye on this one.")
    rule("r7", "workflow.operations", "Check blockers first.")
    rule("r8", "resume.layout", "Old layout rule.", status="superseded")
    rule("r9", "outreach.first_contact", "Replaced outreach rule.", superseded_by="r7")

    add(
        "jobs",
        id="j1",
        title="AI Engineer",
        company="Northstar",
        location="Remote",
        url="https://northstar.example/jobs/1",
        description=POSTING,
        user_notes="Referred by Jamie.\nAsk about the on-call rotation.",
        status="interviewing",
        role_family="ai_engineering",
        decision="apply",
        next_action="Old action",
        created_at="2026-09-01T09:00:00+00:00",
        updated_at="2026-09-20T09:00:00+00:00",
    )
    add(
        "jobs",
        id="j2",
        title="AI Engineer",
        company="Northstar",
        description="Second posting.",
        status="materials_ready",
        next_action="Review resume",
        created_at="2026-09-10T09:00:00+00:00",
        updated_at="2026-09-12T09:00:00+00:00",
    )
    add(
        "jobs",
        id="j3",
        title="Data Engineer",
        company="Fieldwork",
        description="Third posting.",
        status="rejected",
        next_action="Wait",
        decision="apply",
        created_at="2026-08-01T09:00:00+00:00",
        updated_at="2026-08-20T09:00:00+00:00",
    )

    if "events" not in without:
        status_event(conn, "j1", "2026-09-02T09:00:00+00:00", "materials_ready")
        status_event(conn, "j1", "2026-09-05T09:00:00+00:00", "submitted", "Applied on the company site.")
        status_event(conn, "j1", "2026-09-20T09:00:00+00:00", "interviewing")
        insert(conn, "events", job_id="j1", event_type="material_saved", payload="{}", created_at="2026-09-03T00:00:00")
        status_event(conn, "j2", "2026-09-12T09:00:00+00:00", "interview")
        status_event(conn, "j3", "2026-08-02T09:00:00+00:00", "phone_screen")
        status_event(conn, "j3", "2026-08-03T09:00:00+00:00", "applied")
        status_event(conn, "j3", "2026-08-20T09:00:00+00:00", "rejected")

    add(
        "evaluations",
        id="e1",
        job_id="j1",
        payload=json.dumps({"decision": "skip", "strongest_angle": "Outdated angle"}),
        created_at="2026-09-01T09:00:00+00:00",
    )
    add(
        "evaluations",
        id="e2",
        job_id="j1",
        payload=json.dumps(
            {
                "decision": "apply",
                "strongest_angle": "Agent tooling for operations",
                "blocker_flags": [{"area": "location", "evidence": "Hybrid in Denver"}],
                "risks": ["Sponsorship is unknown.", {"not": "a string"}],
                "top_requirements": ["Ignored because the table has rows"],
            }
        ),
        created_at="2026-09-02T09:00:00+00:00",
    )
    add(
        "evaluations",
        id="e3",
        job_id="j2",
        payload=json.dumps({"top_requirements": ["Python services", "python services", "Evaluation harnesses"]}),
        created_at="2026-09-10T09:00:00+00:00",
    )
    requirement_rows = (("Ship agents", 0.5, "01"), ("Own evaluation", 0.9, "02"), ("ship AGENTS", 0.4, "03"))
    for index, (text, priority, stamp) in enumerate(requirement_rows):
        add("tailoring_requirements", id=f"t{index}", job_id="j1", requirement=text, priority=priority, created_at=f"2026-09-{stamp}")
    add("research_notes", id="n1", job_id="j1", subject="Funding", source_url="https://news.example/a", summary="Raised a round.", created_at="2026-09-02")
    add("research_notes", id="n2", job_id="j1", subject="Team", source_url="", summary="Small platform team.", created_at="2026-09-03")

    def followup(followup_id: str, job_id: str, due: str, reason: str, *, status: str = "open", contact_id: str = "") -> None:
        add("followups", id=followup_id, job_id=job_id, contact_id=contact_id, due_date=due, reason=reason, status=status, created_at="2026-09-06")

    followup("f1", "j1", "2026-11-15", "Check in with the recruiter")
    followup("f2", "j1", "2026-11-25", "Send a thank-you note")
    followup("f3", "j1", "2026-11-01", "Already handled", status="Done")
    followup("f4", "j1", "2026-11-18", "Ask Jamie for an intro", contact_id="c1")
    followup("f5", "j2", "2026-11-12", "Ping the hiring manager")
    followup("f6", "j3", "2026-11-30", "Ask for feedback")
    add("progress_items", id="g1", job_id="j1", title="Prepare system design", status="pending", created_at="2026-09-07")
    add("progress_items", id="g2", job_id="j1", title="Finished task", status="completed", created_at="2026-09-07")

    def material(material_id: str, kind: str, content: str, *, file_path: str = "", stamp: str = "2026-09-04") -> None:
        add("materials", id=material_id, job_id="j1", kind=kind, format="text", content=content, file_path=file_path, metadata="{}", created_at=stamp, updated_at=stamp)

    material("m1", "resume", "= Jordan Example", file_path=str(materials / "j1" / "Jordan Example - Resume - Northstar.typ"))
    material("m2", "cover_letter", "tex", file_path=str(external / "Jordan Example - Cover Letter - Northstar.tex"))
    material("m3", "application_answers", "Old answers.", stamp="2026-09-03")
    material("m4", "application_answers", json.dumps("Why Northstar: the routing work."), stamp="2026-09-05")
    material("m5", "tailoring_notes", "Internal tailoring notes.")
    material("m6", "interview_prep", json.dumps({"pdf_path": "missing.pdf"}))
    material("m7", "outreach", "Hi Jamie, quick question.", file_path="/nonexistent/outreach.md")

    def contact(contact_id: str, name: str, company: str, *, tracked: int = 0, email: str = "", role: str = "Engineer", **more: object) -> None:
        add("contacts", id=contact_id, name=name, company=company, role=role, email=email, is_tracked=tracked, created_at="2026-09-03T12:00:00+00:00", **more)

    contact(
        "c1",
        "Jamie Chen",
        "Northstar",
        tracked=1,
        email="jamie@northstar.example",
        role="Staff Engineer",
        linkedin_url="https://linkedin.example/in/jamie",
        notes="Prefers email.",
        why_added="Met at a meetup.",
        network_status="contacted",
        email_status="found",
    )
    contact("c2", "Riley Park", "Northstar", linkedin_url="https://linkedin.example/in/riley")
    contact("c3", "Riley Park", "Northstar", linkedin_url="https://linkedin.example/in/riley")
    contact("c4", "Alex Kim", "Northstar", email="alex@northstar.example", source_url="https://northstar.example/team")
    contact("c5", "Sam Doe", "")

    def candidate(candidate_id: str, status: str, created: str, *, job_id: str = "", canonical: str = "", discovered: str = "") -> None:
        add(
            "discovery_candidates",
            id=candidate_id,
            source_provider="greenhouse",
            status=status,
            title=f"Role {candidate_id}",
            company="Meridian",
            location="Remote",
            canonical_url=canonical,
            discovered_url=discovered,
            description="Lead posting.",
            job_id=job_id,
            created_at=created,
            retrieved_at="2026-11-09T00:00:00+00:00",
        )

    candidate("d1", "new", "2026-11-01T00:00:00+00:00", canonical="https://meridian.example/1", discovered="https://board.example/1")
    candidate("d2", "approved", "2026-10-20T00:00:00+00:00", discovered="https://board.example/2")
    candidate("d3", "new", "2026-08-01T00:00:00+00:00", canonical="https://meridian.example/3")
    candidate("d4", "dismissed", "2026-11-02T00:00:00+00:00", canonical="https://meridian.example/4")
    candidate("d5", "new", "2026-11-03T00:00:00+00:00", job_id="j1", canonical="https://meridian.example/5")

    conn.commit()
    conn.close()
    return db_path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


class MigrateTestCase(unittest.TestCase):
    without: tuple[str, ...] = ()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = build_legacy(self.root, without=self.without)
        self.ws = Workspace(self.root / "ws")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def migrate(self, **options: object) -> dict:
        options.setdefault("today", TODAY)
        return migrate_legacy(self.db_path, self.ws, **options)

    def job(self, legacy_id: str) -> dict:
        return next(job for job in self.ws.jobs() if job.get("legacy_id") == legacy_id)

    def job_body(self, legacy_id: str) -> str:
        return self.ws.job_doc(self.job(legacy_id)["id"]).body


class MigrationTests(MigrateTestCase):
    def test_report_shape_and_source_is_untouched(self) -> None:
        before = digest(self.db_path)
        report = self.migrate()
        self.assertEqual(digest(self.db_path), before)
        self.assertEqual(sorted(path.name for path in self.db_path.parent.iterdir()), ["jobapps.db", "materials"])
        self.assertEqual(report["workspace"], str(self.ws.root))
        self.assertEqual(report["source"], str(self.db_path))
        self.assertFalse(report["dry_run"])
        self.assertEqual(tuple(report["counts"]), COUNT_KEYS)
        self.assertEqual(tuple(report["skipped"]), SKIP_KEYS)
        self.assertEqual(
            report["counts"],
            {
                "profile_facts": 6,
                "evidence": 4,
                "evidence_retired": 1,
                "playbook_rules": 7,
                "jobs": 3,
                "materials_copied": 4,
                "text_materials": 2,
                "people": 1,
                "discovered_contacts": 3,
                "leads": 2,
            },
        )
        self.assertEqual(
            report["skipped"],
            {
                "jobs_existing": 0,
                "people_existing": 0,
                "evidence_existing": 0,
                "leads_existing": 0,
                "leads_stale": 3,
                "materials_missing": 2,
            },
        )
        self.assertEqual(report["warnings"], [])

    def test_wal_database_is_read_through_without_changing_the_file(self) -> None:
        wal = self.root / "wal dir" / "jobapps.db"
        wal.parent.mkdir()
        writer = sqlite3.connect(wal)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE jobs (id TEXT, title TEXT, company TEXT, description TEXT, status TEXT, created_at TEXT)")
        writer.commit()
        insert(writer, "jobs", id="w1", title="Analyst", company="Fieldwork", description="Posting.", status="applied", created_at="2026-07-04")
        writer.commit()
        before = digest(wal)
        report = migrate_legacy(wal, self.ws, today=TODAY)
        self.assertEqual(digest(wal), before)
        self.assertEqual(report["counts"]["jobs"], 1)
        self.assertEqual(self.job("w1")["status"], "applied")

    def test_missing_database_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            migrate_legacy(self.root / "nope.db", self.ws, today=TODAY)
        self.assertFalse(self.ws.root.exists())

    def test_profile_is_written_from_facts(self) -> None:
        self.migrate()
        meta = self.ws.profile_meta()
        self.assertEqual(meta["name"], "Jordan Example")
        self.assertEqual(meta["email"], "jordan@example.com")
        self.assertEqual(meta["linkedin"], "https://linkedin.example/in/jordan")
        self.assertEqual(meta["website"], "https://jordan.example")
        self.assertEqual(meta["phone"], "")
        body = self.ws.profile_text("profile")
        self.assertTrue(body.startswith("# Profile\n\n## Direction\n\n- **target_roles**: Applied AI engineering\n"))
        self.assertEqual(
            section(body, "Hard Constraints"),
            "- **work_authorization**: Authorized to work.\n  No sponsorship needed.",
        )
        self.assertIn("- **candidate_name**: Jordan Example", section(body, "Identity"))
        self.assertLess(body.index("## Direction"), body.index("## Hard Constraints"))
        self.assertLess(body.index("## Hard Constraints"), body.index("## Identity"))
        self.assertNotIn("_What roles you want", body)
        self.assertFalse((self.ws.profile_dir / "profile.migrated.md").exists())

    def test_starter_profile_with_a_name_is_replaced(self) -> None:
        self.ws.init(name="Jordan E.")
        report = self.migrate()
        self.assertEqual(report["warnings"], [])
        self.assertEqual(self.ws.profile_meta()["name"], "Jordan Example")

    def test_edited_profile_is_kept(self) -> None:
        self.ws.init(name="Jordan Example")
        profile = self.ws.profile_dir / "profile.md"
        mine = "---\nname: Jordan Example\n---\n\n# Profile\n\nMy own words.\n"
        profile.write_text(mine, encoding="utf-8")
        report = self.migrate()
        self.assertEqual(profile.read_text(encoding="utf-8"), mine)
        migrated = (self.ws.profile_dir / "profile.migrated.md").read_text(encoding="utf-8")
        self.assertIn("- **target_roles**: Applied AI engineering", migrated)
        self.assertEqual(len(report["warnings"]), 1)
        self.assertIn("profile.migrated.md", report["warnings"][0])

    def test_evidence_files_and_status_mapping(self) -> None:
        self.migrate()
        self.assertEqual(
            sorted(item["id"] for item in self.ws.evidence()),
            ["atlas-routing-engine", "atlas-routing-engine-2", "unconfirmed-win"],
        )
        by_legacy = {item["legacy_id"]: item for item in self.ws.evidence(include_retired=True)}
        active = by_legacy["p1"]
        self.assertEqual(active["id"], "atlas-routing-engine")
        self.assertEqual(
            {key: active[key] for key in ("title", "type", "status", "role_family", "tags")},
            {
                "title": "Atlas Routing Engine",
                "type": "proof",
                "status": "active",
                "role_family": "ai_engineering",
                "tags": ["python", "routing"],
            },
        )
        for absent in ("legacy_status", "allowed_uses", "risk_level"):
            self.assertNotIn(absent, active)
        self.assertEqual(
            active["body"],
            "# Atlas Routing Engine\n\n## Summary\n\nRouting summary.\n\n## Facts\n\n- Cut planning time.\n",
        )

        candidate = by_legacy["p2"]
        self.assertEqual(candidate["id"], "atlas-routing-engine-2")
        self.assertEqual(candidate["status"], "needs_review")
        self.assertEqual(candidate["legacy_status"], "candidate")
        self.assertEqual(candidate["allowed_uses"], ["interview"])
        self.assertEqual(candidate["risk_level"], "caution")

        retired = by_legacy["p3"]
        self.assertEqual((retired["status"], retired["legacy_status"]), ("retired", "superseded"))
        self.assertNotIn("allowed_uses", retired)

        unconfirmed = by_legacy["p4"]
        self.assertEqual((unconfirmed["status"], unconfirmed["legacy_status"]), ("needs_review", "active"))

    def test_playbook_rules_land_under_their_headings(self) -> None:
        self.migrate()
        playbook = (self.ws.profile_dir / "playbook.md").read_text(encoding="utf-8")
        self.assertEqual(
            section(playbook, "All documents"),
            "### Truth\n\n**When:** Trigger for r1\n\nOnly state confirmed facts.",
        )
        self.assertEqual(
            section(playbook, "Resume"),
            "### Bullets\n\n**When:** Trigger for r2\n\nLead with the mechanism.\n\n"
            "### Evidence Selection\n\n**When:** Trigger for r3\n\nPick two projects.",
        )
        self.assertIn("### Substance\n\n**When:** Trigger for r4\n\nOpen with the product.", section(playbook, "Cover letter"))
        self.assertIn("Check blockers first.", section(playbook, "Workflow"))
        self.assertEqual(
            section(playbook, "Unsorted (review)"),
            "### Materials Quality\n\n**When:** Trigger for r6\n\nKeep an eye on this one.",
        )
        for empty in ("Application answers", "Outreach", "Interview"):
            self.assertEqual(section(playbook, empty), "")
        self.assertNotIn("Old layout rule.", playbook)
        self.assertNotIn("Replaced outreach rule.", playbook)
        self.assertNotIn("Short, plain sentences.", playbook)
        self.assertLess(playbook.index("## Workflow"), playbook.index("## Unsorted (review)"))
        self.assertNotIn("\n\n\n", playbook)

        voice = (self.ws.profile_dir / "voice.md").read_text(encoding="utf-8")
        self.assertEqual(section(voice, "Rules"), "### Voice\n\n**When:** Trigger for r5\n\nShort, plain sentences.")
        self.assertIn("## Sounds like me", voice)

    def test_placeholders_leave_a_section_that_receives_rules(self) -> None:
        self.ws.init()
        playbook = self.ws.profile_dir / "playbook.md"
        text = playbook.read_text(encoding="utf-8").replace("## Resume\n", "## Resume\n\n_Rules for resumes._\n\nKeep it to one page.\n")
        playbook.write_text(text, encoding="utf-8")
        self.migrate()
        resume = section(playbook.read_text(encoding="utf-8"), "Resume")
        self.assertTrue(resume.startswith("Keep it to one page.\n\n### Bullets\n"))
        self.assertNotIn("_Rules for resumes._", resume)

    def test_job_frontmatter(self) -> None:
        self.migrate()
        first = self.job("j1")
        self.assertEqual(first["id"], "2026-09-northstar-ai-engineer")
        expected = {
            "company": "Northstar",
            "title": "AI Engineer",
            "status": "interviewing",
            "location": "Remote",
            "url": "https://northstar.example/jobs/1",
            "created_on": "2026-09-01",
            "updated_on": "2026-09-20",
            "applied_on": "2026-09-05",
            "next_action": "Check in with the recruiter",
            "next_action_due": "2026-11-15",
            "decision": "apply",
            "role_family": "ai_engineering",
        }
        self.assertEqual({key: first[key] for key in expected}, expected)
        self.assertNotIn("legacy_status", first)

        second = self.job("j2")
        self.assertEqual(second["id"], "2026-09-northstar-ai-engineer-2")
        self.assertEqual((second["status"], second["legacy_status"]), ("ready", "materials_ready"))
        self.assertEqual((second["next_action"], second["next_action_due"]), ("Review resume", "2026-11-12"))
        self.assertEqual(second["applied_on"], "2026-09-12")
        self.assertNotIn("decision", second)
        self.assertNotIn("role_family", second)

        third = self.job("j3")
        self.assertEqual(third["status"], "rejected")
        self.assertEqual(third["applied_on"], "2026-08-03")
        self.assertEqual((third["next_action"], third["next_action_due"]), ("", ""))

    def test_job_sections(self) -> None:
        self.migrate()
        body = self.job_body("j1")
        self.assertTrue(body.startswith("# AI Engineer at Northstar\n"))
        headings = [line[3:] for line in body.split("\n") if line.startswith("## ")]
        self.assertEqual(headings, ["Posting", "Assessment", "Requirements", "Research", "Notes", "Log"])
        self.assertEqual(section(body, "Posting"), POSTING)
        self.assertEqual(
            section(body, "Assessment"),
            "- Decision: apply\n- Angle: Agent tooling for operations\n"
            "- Blocker (location): Hybrid in Denver\n- Risk: Sponsorship is unknown.",
        )
        self.assertEqual(section(body, "Requirements"), "- Own evaluation\n- Ship agents")
        self.assertEqual(
            section(body, "Research"),
            "- **Team**: Small platform team.\n- **Funding** (https://news.example/a): Raised a round.",
        )
        self.assertEqual(
            section(body, "Notes"),
            "Referred by Jamie.\nAsk about the on-call rotation.\n\n"
            "Open follow-ups:\n- 2026-11-18: Ask Jamie for an intro\n- 2026-11-25: Send a thank-you note\n\n"
            "Open tasks:\n- Prepare system design",
        )
        self.assertEqual(
            section(body, "Log"),
            "- 2026-09-01: Added (migrated from the legacy database).\n"
            "- 2026-09-02: Status: materials_ready.\n"
            "- 2026-09-05: Status: submitted. Applied on the company site.\n"
            "- 2026-09-20: Status: interviewing.",
        )

        second = self.job_body("j2")
        headings = [line[3:] for line in second.split("\n") if line.startswith("## ")]
        self.assertEqual(headings, ["Posting", "Requirements", "Notes", "Log"])
        self.assertEqual(section(second, "Requirements"), "- Python services\n- Evaluation harnesses")
        self.assertEqual(section(second, "Notes"), "Open follow-ups:\n- 2026-11-12: Ping the hiring manager")

        third = self.job_body("j3")
        self.assertEqual(section(third, "Notes"), "Open follow-ups:\n- 2026-11-30: Ask for feedback")

    def test_log_keeps_the_last_forty_status_changes(self) -> None:
        conn = sqlite3.connect(self.db_path)
        for index in range(45):
            status_event(conn, "j2", f"2026-10-01T00:{index:02d}:00+00:00", f"step_{index}")
        conn.commit()
        conn.close()
        self.migrate()
        log = section(self.job_body("j2"), "Log").split("\n")
        self.assertEqual(len(log), 41)
        self.assertIn("Added (migrated", log[0])
        self.assertEqual(log[1], "- 2026-10-01: Status: step_5.")
        self.assertEqual(log[-1], "- 2026-10-01: Status: step_44.")

    def test_materials_are_copied_and_text_rows_written(self) -> None:
        self.migrate()
        folder = self.ws.job_dir(self.job("j1")["id"])
        self.assertEqual(
            sorted(path.name for path in folder.iterdir()),
            [
                "Jordan Example - Cover Letter - Northstar.pdf",
                "Jordan Example - Cover Letter - Northstar.tex",
                "Jordan Example - Resume - Northstar.pdf",
                "Jordan Example - Resume - Northstar.typ",
                "application-answers.md",
                "job.md",
                "outreach.md",
            ],
        )
        self.assertEqual((folder / "Jordan Example - Resume - Northstar.pdf").read_bytes(), b"%PDF-resume")
        self.assertEqual((folder / "application-answers.md").read_text(encoding="utf-8"), "Why Northstar: the routing work.\n")
        self.assertEqual((folder / "outreach.md").read_text(encoding="utf-8"), "Hi Jamie, quick question.\n")
        kinds = {item["name"]: item["kind"] for item in self.ws.materials(self.job("j1")["id"])}
        self.assertEqual(kinds["Jordan Example - Resume - Northstar.typ"], "resume")
        self.assertEqual(sorted(path.name for path in self.ws.job_dir(self.job("j2")["id"]).iterdir()), ["job.md"])

    def test_asset_folders_travel_with_the_sources_and_fill_in_on_a_second_run(self) -> None:
        legacy = self.db_path.parent / "materials" / "j1" / "assets"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "link.svg").write_text("<svg/>", encoding="utf-8")
        self.migrate()
        folder = self.ws.job_dir(self.job("j1")["id"])
        self.assertEqual((folder / "assets" / "link.svg").read_text(encoding="utf-8"), "<svg/>")
        (legacy / "late.svg").write_text("<svg id='late'/>", encoding="utf-8")
        (folder / "assets" / "link.svg").write_text("edited", encoding="utf-8")
        self.migrate()
        self.assertTrue((folder / "assets" / "late.svg").is_file())
        self.assertEqual((folder / "assets" / "link.svg").read_text(encoding="utf-8"), "edited")

    def test_archived_evidence_is_not_recreated(self) -> None:
        self.migrate()
        archive = self.ws.evidence_dir / "_legacy"
        archive.mkdir()
        originals = [path for path in self.ws.evidence_dir.glob("*.md") if not path.name.startswith("_")]
        self.assertTrue(originals)
        for path in originals:
            path.rename(archive / path.name)
        report = self.migrate()
        self.assertEqual(report["counts"]["evidence"], 0)
        self.assertEqual([path for path in self.ws.evidence_dir.glob("*.md") if not path.name.startswith("_")], [])

    def test_custom_materials_root(self) -> None:
        other = self.root / "elsewhere"
        (other / "j2").mkdir(parents=True)
        (other / "j2" / "answers.txt").write_text("Answers", encoding="utf-8")
        report = self.migrate(materials_root=other)
        self.assertEqual(report["skipped"]["materials_missing"], 2)
        self.assertTrue((self.ws.job_dir(self.job("j2")["id"]) / "answers.txt").is_file())
        names = {path.name for path in self.ws.job_dir(self.job("j1")["id"]).iterdir()}
        self.assertIn("Jordan Example - Resume - Northstar.typ", names)
        self.assertIn("Jordan Example - Cover Letter - Northstar.pdf", names)

    def test_tracked_people_and_discovered_rollups(self) -> None:
        self.migrate()
        people = self.ws.people()
        self.assertEqual([person["id"] for person in people], ["jamie-chen"])
        expected = {
            "name": "Jamie Chen",
            "company": "Northstar",
            "role": "Staff Engineer",
            "email": "jamie@northstar.example",
            "linkedin": "https://linkedin.example/in/jamie",
            "status": "contacted",
            "next_touch": "2026-11-18",
            "jobs": ["2026-09-northstar-ai-engineer"],
            "added_on": "2026-09-03",
            "legacy_id": "c1",
            "email_status": "found",
        }
        self.assertEqual({key: people[0][key] for key in expected}, expected)
        body = self.ws.read(Path(people[0]["path"])).body
        self.assertEqual(section(body, "Why"), "Met at a meetup.")
        self.assertEqual(section(body, "Notes"), "Prefers email.")

        discovered = self.ws.people_dir / "_discovered"
        self.assertEqual(sorted(path.name for path in discovered.iterdir()), ["northstar.md", "unknown.md"])
        self.assertEqual(
            (discovered / "northstar.md").read_text(encoding="utf-8"),
            "# Discovered contacts: Northstar\n\n"
            "- Alex Kim | Engineer | https://northstar.example/team | alex@northstar.example\n"
            "- Riley Park | Engineer | https://linkedin.example/in/riley | no email\n",
        )
        self.assertEqual(
            (discovered / "unknown.md").read_text(encoding="utf-8"),
            "# Discovered contacts: Unknown\n\n- Sam Doe | Engineer |  | no email\n",
        )

    def test_leads_respect_the_freshness_cut_off(self) -> None:
        self.migrate()
        leads = {lead["legacy_id"]: lead for lead in self.ws.leads()}
        self.assertEqual(sorted(leads), ["d1", "d2"])
        first = leads["d1"]
        self.assertEqual(
            {key: first[key] for key in ("company", "title", "status", "url", "source", "found_on", "location")},
            {
                "company": "Meridian",
                "title": "Role d1",
                "status": "new",
                "url": "https://meridian.example/1",
                "source": "greenhouse",
                "found_on": "2026-11-01",
                "location": "Remote",
            },
        )
        self.assertEqual(section(self.ws.read(Path(first["path"])).body, "Posting"), "Lead posting.")
        self.assertEqual((leads["d2"]["status"], leads["d2"]["url"]), ("shortlisted", "https://board.example/2"))

    def test_lead_days_moves_the_cut_off(self) -> None:
        report = self.migrate(lead_days=10)
        self.assertEqual((report["counts"]["leads"], report["skipped"]["leads_stale"]), (1, 4))
        wide = migrate_legacy(self.db_path, Workspace(self.root / "wide"), lead_days=200, today=TODAY)
        self.assertEqual((wide["counts"]["leads"], wide["skipped"]["leads_stale"]), (3, 2))

    def test_second_run_adds_nothing(self) -> None:
        self.migrate()
        (self.ws.root / "MIGRATION.md").unlink()
        before = tree(self.ws.root)
        report = self.migrate()
        self.assertEqual({key: value for key, value in report["counts"].items() if value}, {"profile_facts": 6})
        self.assertEqual(
            report["skipped"],
            {
                "jobs_existing": 3,
                "people_existing": 1,
                "evidence_existing": 4,
                "leads_existing": 2,
                "leads_stale": 3,
                "materials_missing": 0,
            },
        )
        self.assertEqual(report["warnings"], [])
        (self.ws.root / "MIGRATION.md").unlink()
        self.assertEqual(tree(self.ws.root), before)
        self.assertEqual(len(list(self.ws.jobs_dir.iterdir())), 3)

    def test_second_run_keeps_edited_rules_and_files(self) -> None:
        self.migrate()
        playbook = self.ws.profile_dir / "playbook.md"
        playbook.write_text(
            playbook.read_text(encoding="utf-8").replace("Lead with the mechanism.", "Lead with the outcome."),
            encoding="utf-8",
        )
        self.ws.update_job(self.job("j1")["id"], {"status": "offer"}, log="Offer received.")
        self.migrate()
        text = playbook.read_text(encoding="utf-8")
        self.assertEqual(text.count("### Bullets"), 1)
        self.assertIn("Lead with the outcome.", text)
        self.assertNotIn("Lead with the mechanism.", text)
        self.assertEqual(self.job("j1")["status"], "offer")

    def test_dry_run_writes_nothing(self) -> None:
        real = migrate_legacy(self.db_path, Workspace(self.root / "real"), today=TODAY)
        report = self.migrate(dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertFalse(self.ws.root.exists())
        self.assertEqual(report["counts"], real["counts"])
        self.assertEqual(report["skipped"], real["skipped"])

        before = tree(self.root / "real")
        again = migrate_legacy(self.db_path, Workspace(self.root / "real"), today=TODAY, dry_run=True)
        self.assertEqual(tree(self.root / "real"), before)
        self.assertEqual(again["skipped"]["jobs_existing"], 3)
        self.assertEqual(again["counts"]["jobs"], 0)

    def test_migration_file(self) -> None:
        self.migrate()
        text = (self.ws.root / "MIGRATION.md").read_text(encoding="utf-8")
        self.assertIn("- Date: 2026-11-10", text)
        self.assertIn(str(self.db_path), text)
        self.assertIn("| Jobs | 3 |", text)
        self.assertIn("| Leads stale | 3 |", text)
        self.assertIn("## Warnings\n\nNone.", text)
        self.assertIn("opened read-only and was not modified", section(text, "Not migrated"))


class OlderDatabaseTests(MigrateTestCase):
    without = (
        "discovery_candidates",
        "learning_patterns",
        "events",
        "evaluations",
        "tailoring_requirements",
        "research_notes",
        "followups",
        "progress_items",
        "materials",
    )

    def test_missing_optional_tables_are_tolerated(self) -> None:
        before = digest(self.db_path)
        report = self.migrate()
        self.assertEqual(digest(self.db_path), before)
        self.assertEqual(report["counts"]["jobs"], 3)
        self.assertEqual(report["counts"]["playbook_rules"], 0)
        self.assertEqual(report["counts"]["leads"], 0)
        self.assertEqual(report["counts"]["materials_copied"], 2)
        self.assertEqual(report["counts"]["text_materials"], 0)
        self.assertEqual(len(report["warnings"]), 2)
        self.assertTrue(any("discovery_candidates" in warning for warning in report["warnings"]))
        self.assertTrue(any("learning_patterns" in warning for warning in report["warnings"]))
        first = self.job("j1")
        self.assertEqual((first["applied_on"], first["next_action"], first["next_action_due"]), ("", "Old action", ""))
        body = self.job_body("j1")
        headings = [line[3:] for line in body.split("\n") if line.startswith("## ")]
        self.assertEqual(headings, ["Posting", "Notes", "Log"])
        self.assertEqual(section(body, "Log"), "- 2026-09-01: Added (migrated from the legacy database).")
        self.assertEqual(self.ws.people()[0]["next_touch"], "")
        self.assertEqual(self.ws.people()[0]["jobs"], [])

    def test_missing_columns_are_treated_as_empty(self) -> None:
        old = self.root / "old" / "jobapps.db"
        old.parent.mkdir()
        conn = sqlite3.connect(old)
        conn.execute("CREATE TABLE jobs (id TEXT, title TEXT, company TEXT, description TEXT, status TEXT, created_at TEXT)")
        conn.execute("CREATE TABLE proof_points (id TEXT, label TEXT, summary TEXT, evidence TEXT)")
        conn.execute("CREATE TABLE contacts (id TEXT, name TEXT, company TEXT)")
        insert(conn, "jobs", id="o1", title="Analyst", company="Fieldwork", description="Old posting.", status="new", created_at="2026-07-04")
        insert(conn, "proof_points", id="op1", label="Early Project", summary="Summary.", evidence="Facts.")
        insert(conn, "contacts", id="oc1", name="Pat Lee", company="Fieldwork")
        conn.commit()
        conn.close()

        report = migrate_legacy(old, self.ws, today=TODAY)
        self.assertEqual(report["counts"]["jobs"], 1)
        self.assertEqual(report["counts"]["evidence"], 1)
        self.assertEqual(report["counts"]["discovered_contacts"], 1)
        self.assertEqual(report["counts"]["people"], 0)
        job = self.ws.jobs()[0]
        self.assertEqual((job["id"], job["legacy_id"], job["updated_on"]), ("2026-07-fieldwork-analyst", "o1", "2026-07-04"))
        evidence = self.ws.evidence()[0]
        self.assertEqual((evidence["status"], evidence["tags"], evidence["role_family"]), ("active", [], ""))
        self.assertEqual(self.ws.profile_meta()["name"], "")


if __name__ == "__main__":
    unittest.main()
