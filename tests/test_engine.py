from __future__ import annotations

import gzip
import json
import tempfile
import threading
import subprocess
import time
import urllib.request
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from hermes_jobapps.chat import ChatOrchestrator, parse_job_from_message
from hermes_jobapps.config import load_config
from hermes_jobapps.discovery import DiscoveryError, DiscoveryService, detect_ats
from hermes_jobapps.evaluator import evaluate_job
from hermes_jobapps.importer import import_private_seed
from hermes_jobapps.latex import compile_tex_to_pdf, job_material_filename, write_material_artifact
from hermes_jobapps.typst import compile_typst_to_pdf
from hermes_jobapps.networking import NetworkingError, NetworkingService
from hermes_jobapps.prompts import build_chat_instructions, build_opportunity_prompt
from hermes_jobapps.repository import JobRepository
from hermes_jobapps.runs import HermesRunManager, _extract_text
from hermes_jobapps.server import AppState, create_handler
from hermes_jobapps.tools import AgentToolbox, normalize_material_format
from hermes_jobapps.workflow import JobAppsWorkflow
from hermes_jobapps.writers import draft_materials


def seed_context(repo: JobRepository) -> dict:
    repo.upsert_profile_fact("name", "Candidate Example", category="identity", source="test")
    repo.upsert_proof_point(
        label="Agent retrieval project",
        role_family="ai_agent_systems",
        summary="Implemented a TypeScript agent with retrieval, tool calling, pgvector memory, and explicit evaluation traces.",
        evidence="Used retrieval, tool calls, memory, and evaluation traces in a production-style project.",
        tags=["llm", "retrieval", "tool-calling", "evaluation", "pgvector"],
        source="test",
    )
    repo.upsert_proof_point(
        label="Nonprofit data platform",
        role_family="data_engineering",
        summary="Built a Python and PostgreSQL data platform with validation rules, REST APIs, and operational reporting.",
        evidence="Owned database-backed workflow, validation, and reporting behavior.",
        tags=["python", "postgresql", "api", "data quality"],
        source="test",
    )
    return repo.career_context()


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = JobRepository(Path(self.tmpdir.name) / "state.sqlite3")
        self.context = seed_context(self.repo)
        self.config = load_config()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_user_supplied_jd_assumes_apply_and_builds_tailoring_targets(self) -> None:
        job = {
            "title": "AI Engineer",
            "company": "ExampleCo",
            "description": """
            We are hiring an AI Engineer to build LLM agents.
            Requirements:
            - Experience building retrieval systems and tool-calling workflows.
            - Develop evaluation traces for agent behavior.
            - Work with PostgreSQL and production APIs.
            Visa sponsorship is available.
            This is an entry level role.
            """,
        }

        evaluation = evaluate_job(job, self.context, self.config)

        self.assertEqual(evaluation["evaluation_mode"], "blocker_preflight")
        self.assertEqual(evaluation["fit_assumption"], "user_provided_jd_implies_apply_intent")
        self.assertEqual(evaluation["decision"], "apply")
        self.assertNotIn("score_0_to_5", evaluation)
        self.assertEqual(evaluation["role_family"], "ai_agent_systems")
        self.assertEqual(evaluation["sponsorship_risk"], "clear")
        self.assertTrue(evaluation["tailoring_targets"])
        first_target = evaluation["tailoring_targets"][0]
        self.assertIn("requirement", first_target)
        self.assertIn("requested_portrayal", first_target)

    def test_sponsorship_blocker_defaults_to_skip(self) -> None:
        job = {
            "title": "Backend Engineer",
            "company": "ExampleCo",
            "description": """
            Build APIs and services using Python and PostgreSQL.
            Candidates must be authorized to work in the United States without sponsorship.
            The team wants experience with backend systems and cloud services.
            """,
        }

        evaluation = evaluate_job(job, self.context, self.config)

        self.assertEqual(evaluation["decision"], "skip")
        self.assertEqual(evaluation["sponsorship_risk"], "blocker")
        self.assertTrue(any(item["area"] == "sponsorship" for item in evaluation["blocker_flags"]))

    def test_five_plus_years_defaults_to_skip_for_entry_level_user(self) -> None:
        job = {
            "title": "Machine Learning Engineer",
            "company": "SeniorCo",
            "description": """
            Build production ML systems, APIs, and model evaluation workflows.
            Requirements include 5+ years of professional machine learning engineering experience.
            Visa sponsorship is available for the right candidate.
            """,
        }

        evaluation = evaluate_job(job, self.context, self.config)

        self.assertEqual(evaluation["decision"], "skip")
        self.assertEqual(evaluation["seniority_risk"], "blocker")
        self.assertTrue(any(item["area"] == "seniority" for item in evaluation["blocker_flags"]))

    def test_high_pay_west_coast_roles_surface_competition_and_networking_risk(self) -> None:
        job = {
            "title": "New Grad Data Engineer",
            "company": "WeRide",
            "location": "San Jose, CA",
            "description": """
            Build data pipelines, ETL workflows, and SQL quality checks for autonomy datasets.
            Visa sponsorship is available for new graduates. This is an entry level role.
            The base salary range starts at $120K and goes to $160K.
            """,
        }

        evaluation = evaluate_job(job, self.context, self.config)

        self.assertEqual(evaluation["decision"], "apply")
        risks = "\n".join(evaluation["risks"])
        self.assertIn("$120k+", risks.lower())
        self.assertIn("competition signal", risks.lower())
        self.assertIn("west coast", risks.lower())
        self.assertIn("network", risks.lower())


class RepositoryTests(unittest.TestCase):
    def test_repository_enables_wal_and_busy_timeout_for_parallel_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            with repo._connect() as conn:
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

            self.assertEqual(str(journal_mode).lower(), "wal")
            self.assertGreaterEqual(int(busy_timeout), 30000)

    def test_repository_records_job_progress_materials_and_followup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "Data Engineer",
                    "company": "ExampleCo",
                    "description": "Build data pipelines with SQL and validation.",
                },
                {
                    "decision": "maybe",
                    "role_family": "data_engineering",
                    "facts": {"title": "Data Engineer", "company": "ExampleCo"},
                    "score_0_to_5": 3.4,
                    "next_action": "Research sponsorship and decide.",
                },
            )
            job_id = record["job"]["id"]
            repo.save_material(job_id, "cover_letter", "\\documentclass{letter}", format="tex")
            repo.create_progress_item("Send follow-up email", job_id=job_id, kind="networking")
            repo.create_followup("2026-05-15", "Check response", job_id=job_id)
            repo.create_approval(
                "manual_send_email",
                job_id=job_id,
                payload={"materials": ["cover_letter.tex"]},
            )
            updated = repo.record_event(job_id, "status_changed", {"status": "follow_up"})

            self.assertEqual(updated["job"]["status"], "follow_up")
            self.assertEqual(updated["materials"][0]["format"], "tex")
            self.assertEqual(len(updated["progress_items"]), 1)
            self.assertEqual(len(updated["followups"]), 1)
            self.assertEqual(updated["approvals"][0]["payload"]["materials"], ["cover_letter.tex"])

    def test_create_job_reuses_same_manual_job_instead_of_forking_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            job = {
                "title": "Data Engineer",
                "company": "BeaconFire Inc.",
                "location": "East Windsor, NJ",
                "description": "Create and maintain data pipeline architecture. Assemble large data sets. Automate manual processes and optimize data delivery for business stakeholders.",
            }
            first = repo.create_job(job, {"decision": "apply", "role_family": "data_engineering"})
            second = repo.create_job(
                {**job, "description": "\nCreate and maintain data pipeline architecture.  Assemble large data sets.\nAutomate manual processes and optimize data delivery for business stakeholders.\n"},
                {"decision": "apply", "role_family": "data_engineering", "next_action": "Prepare materials."},
            )

            with repo._connect() as conn:
                job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                evaluation_count = conn.execute("SELECT COUNT(*) FROM evaluations WHERE job_id = ?", (first["job"]["id"],)).fetchone()[0]

            self.assertEqual(second["job"]["id"], first["job"]["id"])
            self.assertEqual(job_count, 1)
            self.assertEqual(evaluation_count, 2)
            self.assertEqual(second["job"]["next_action"], "Prepare materials.")

    def test_create_job_does_not_merge_different_roles_from_same_company_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            first = repo.create_job(
                {
                    "title": "Analyst",
                    "company": "ExampleCo",
                    "url": "https://careers.example.com/",
                    "description": "Analyze operations data, write reports, and support stakeholders with recurring metrics.",
                },
                {"decision": "apply"},
            )
            second = repo.create_job(
                {
                    "title": "Software Engineer",
                    "company": "ExampleCo",
                    "url": "https://careers.example.com/",
                    "description": "Build backend APIs, ship product features, and maintain application services for customers.",
                },
                {"decision": "apply"},
            )

            self.assertNotEqual(second["job"]["id"], first["job"]["id"])

    def test_repository_updates_job_status_next_action_and_missing_jobs_visibly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": "Build agent workflows.",
                },
                {
                    "decision": "apply",
                    "role_family": "ai_agent_systems",
                    "next_action": "Tailor materials.",
                },
            )

            updated = repo.record_event(
                record["job"]["id"],
                "status_changed",
                {"status": "applied", "next_action": "Track response.", "source": "test"},
            )

            self.assertEqual(updated["job"]["status"], "applied")
            self.assertEqual(updated["job"]["next_action"], "Track response.")
            self.assertIn("status_changed", [event["event_type"] for event in updated["events"]])
            with self.assertRaises(KeyError):
                repo.record_event("missingjob123", "status_changed", {"status": "closed"})

    def test_cockpit_status_endpoint_returns_refreshed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            record = state.repo.create_job(
                {
                    "title": "Backend Engineer",
                    "company": "ExampleCo",
                    "description": "Build APIs.",
                },
                {
                    "decision": "apply",
                    "role_family": "backend",
                    "next_action": "Prepare materials.",
                },
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                body = json.dumps({"status": "applied", "note": "Submitted on company site."}).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/jobs/{record['job']['id']}/status",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(payload["state"]["jobs"][0]["status"], "applied")
            self.assertIn("watch for replies", payload["state"]["jobs"][0]["next_action"])

    def test_state_endpoint_returns_versioned_gzip_payload_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            state.repo.create_job(
                {
                    "title": "Backend Engineer",
                    "company": "ExampleCo",
                    "description": "Build APIs." * 500,
                },
                {"decision": "apply", "role_family": "backend"},
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/state",
                    headers={"Accept-Encoding": "gzip"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    encoded = response.read()
                    content_encoding = response.headers.get("Content-Encoding")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            payload = json.loads(gzip.decompress(encoded).decode("utf-8"))
            self.assertEqual(content_encoding, "gzip")
            self.assertIn("state_version", payload)
            self.assertEqual(payload["jobs"][0]["company"], "ExampleCo")

    def test_dashboard_exposes_lean_job_state_buckets_and_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            new_record = repo.create_job(
                {
                    "title": "Backend Engineer",
                    "company": "NewCo",
                    "status": "evaluated",
                    "description": "Build APIs.",
                },
                {"decision": "apply", "role_family": "backend", "next_action": "Review blocker preflight."},
            )
            legacy_ready_record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ReadyCo",
                    "status": "approved",
                    "description": "Build agent workflows.",
                },
                {"decision": "apply", "role_family": "ai_agent_systems", "next_action": "Apply with prepared materials."},
            )
            review_record = repo.create_job(
                {
                    "title": "Data Engineer",
                    "company": "ReviewCo",
                    "status": "materials_ready_for_review",
                    "description": "Build data systems.",
                },
                {"decision": "apply", "role_family": "data_engineering", "next_action": "Review generated materials."},
            )
            applied_record = repo.create_job(
                {
                    "title": "ML Engineer",
                    "company": "AppliedCo",
                    "description": "Build evaluation workflows.",
                },
                {"decision": "apply", "role_family": "ml_ds", "next_action": "Submit application."},
            )
            applied_skip_decision_record = repo.create_job(
                {
                    "title": "Oracle DBA",
                    "company": "Precision Technologies Corp.",
                    "status": "applied",
                    "description": "Maintain Oracle databases.",
                },
                {"decision": "skip", "role_family": "backend", "next_action": "Already applied."},
            )
            skip_record = repo.create_job(
                {
                    "title": "Senior DBA",
                    "company": "SkipCo",
                    "status": "skip",
                    "description": "Requires sponsorship not available.",
                },
                {"decision": "skip", "role_family": "backend", "next_action": "Skip due to blocker."},
            )
            repo.save_material(legacy_ready_record["job"]["id"], "resume", "\\documentclass{article}", format="tex")
            repo.save_material(review_record["job"]["id"], "resume", "\\documentclass{article}", format="tex")
            repo.record_event(
                applied_record["job"]["id"],
                "status_changed",
                {"status": "applied", "next_action": "Track response.", "source": "test"},
            )

            dashboard = repo.dashboard()
            jobs = {job["id"]: job for job in dashboard["jobs"]}

            self.assertEqual(dashboard["job_state_counts"], {"new": 3, "applied": 2, "skip": 1})
            self.assertEqual(jobs[new_record["job"]["id"]]["state_bucket"], "new")
            self.assertEqual(jobs[legacy_ready_record["job"]["id"]]["state_bucket"], "new")
            self.assertEqual(jobs[review_record["job"]["id"]]["state_bucket"], "new")
            self.assertTrue(jobs[review_record["job"]["id"]]["needs_material_review"])
            self.assertEqual(jobs[applied_record["job"]["id"]]["state_bucket"], "applied")
            self.assertEqual(jobs[applied_skip_decision_record["job"]["id"]]["state_bucket"], "applied")
            self.assertEqual(jobs[skip_record["job"]["id"]]["state_bucket"], "skip")
            self.assertTrue(jobs[applied_record["job"]["id"]]["state_dates"]["applied"])

    def test_batch_hermes_run_endpoint_queues_selected_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            state.config["materials_path"] = str(Path(tmpdir) / "materials")
            seed_context(state.repo)
            first = state.workflow.prepare_opportunity(
                {
                    "title": "Data Engineer",
                    "company": "FirstCo",
                    "description": "Build data pipelines with SQL and Python. Visa sponsorship is available. Entry level role.",
                }
            )["job"]["id"]
            second = state.workflow.prepare_opportunity(
                {
                    "title": "Software Engineer",
                    "company": "SecondCo",
                    "description": "Build backend APIs with Python and PostgreSQL. Visa sponsorship is available. Entry level role.",
                }
            )["job"]["id"]
            hermes = ParallelBlockingHermesClient()
            state.hermes = hermes
            state.runs = HermesRunManager(state.repo, state.toolbox, hermes, session_key=state.hermes_session_key)
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                body = json.dumps({"job_ids": [first, second]}).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/jobs/hermes-runs",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                started_at = time.monotonic()
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                elapsed = time.monotonic() - started_at

                self.assertLess(elapsed, 0.25)
                self.assertEqual(payload["queued_count"], 2)
                self.assertTrue(hermes.two_active.wait(timeout=0.5))
                self.assertEqual(len([item for item in payload["results"] if item["status"] == "queued"]), 2)
            finally:
                hermes.release.set()
                hermes.all_done.wait(timeout=1)
                wait_for_jobapps_launch_threads()
                wait_for_started_run_count(state.repo, 2)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_action_dispositions_close_progress_followups_and_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": "Build agent workflows.",
                },
                {
                    "decision": "apply",
                    "role_family": "ai_agent_systems",
                    "next_action": "Review materials.",
                },
            )
            job_id = record["job"]["id"]
            progress = repo.create_progress_item("Send email to recruiter", job_id=job_id, kind="networking")
            followup = repo.create_followup("2026-05-22", "Send follow-up", job_id=job_id)
            approval = repo.create_approval("manual_send_email", job_id=job_id)

            repo.update_progress_item(progress["id"], "done")
            repo.update_followup(followup["id"], "not_needed")
            repo.update_approval(approval["id"], "approved")
            dashboard = repo.dashboard()
            health = repo.database_health()["counts"]

            self.assertEqual(dashboard["progress_count"], 0)
            self.assertEqual(dashboard["followup_count"], 0)
            self.assertEqual(dashboard["approval_count"], 0)
            self.assertEqual(health["open_progress_items"], 0)
            self.assertEqual(health["open_followups"], 0)

    def test_backend_refuses_review_actions_at_creation_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "Data Engineer",
                    "company": "ExampleCo",
                    "description": "Build data systems.",
                },
                {"decision": "apply", "role_family": "data_engineering", "next_action": "Prepare materials."},
            )
            job_id = record["job"]["id"]

            blocked_progress_cases = [
                ("Review generated resume", "task"),
                ("Check cover letter", "material_review"),
                ("Review generated resume and cover letter", "material_review"),
            ]
            for title, kind in blocked_progress_cases:
                with self.subTest(title=title, kind=kind):
                    with self.assertRaises(ValueError):
                        repo.create_progress_item(title, job_id=job_id, kind=kind)

            blocked_approval_actions = [
                "review_generated_materials",
                "review_application_materials",
                "review_outreach_draft",
            ]
            for action in blocked_approval_actions:
                with self.subTest(action=action):
                    with self.assertRaises(ValueError):
                        repo.create_approval(action, job_id=job_id)
                    with self.assertRaises(ValueError):
                        repo.upsert_pending_approval(action, job_id=job_id)

            allowed = repo.create_progress_item("Send email to recruiter", job_id=job_id, kind="networking")
            approval = repo.create_approval("manual_send_email", job_id=job_id)
            saved = repo.get_job(job_id)

            self.assertEqual(allowed["title"], "Send email to recruiter")
            self.assertEqual(approval["action"], "manual_send_email")
            self.assertEqual([item["title"] for item in saved["progress_items"]], ["Send email to recruiter"])
            self.assertEqual([item["action"] for item in saved["approvals"]], ["manual_send_email"])

    def test_prepare_opportunity_does_not_create_review_or_research_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            state.config["materials_path"] = str(Path(tmpdir) / "materials")
            seed_context(state.repo)

            record = state.workflow.prepare_opportunity(
                {
                    "title": "Data Engineer",
                    "company": "ExampleCo",
                    "description": "Build Python and SQL data pipelines for production analytics, data validation, reporting, workflow automation, and stakeholder-facing data products. Work with software engineers and analysts to design reliable ingestion jobs, document data definitions, monitor data quality, and support cloud-based services.",
                }
            )
            job = state.repo.get_job(record["job"]["id"])

            self.assertEqual(job["progress_items"], [])
            self.assertEqual(job["approvals"], [])
            self.assertEqual(state.repo.dashboard()["progress_count"], 0)
            self.assertEqual(state.repo.dashboard()["approval_count"], 0)

    def test_action_disposition_endpoints_return_refreshed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            record = state.repo.create_job(
                {
                    "title": "Backend Engineer",
                    "company": "ExampleCo",
                    "description": "Build APIs.",
                },
                {
                    "decision": "apply",
                    "role_family": "backend",
                    "next_action": "Prepare materials.",
                },
            )
            job_id = record["job"]["id"]
            progress = state.repo.create_progress_item("Send application email", job_id=job_id, kind="networking")
            followup = state.repo.create_followup("2026-05-22", "Follow up", job_id=job_id)
            approval = state.repo.create_approval("manual_send_email", job_id=job_id)
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                requests = [
                    (f"{base}/api/progress-items/{progress['id']}/disposition", {"status": "done"}),
                    (f"{base}/api/followups/{followup['id']}/disposition", {"status": "not_needed"}),
                    (f"{base}/api/approvals/{approval['id']}/disposition", {"action": "approve"}),
                ]
                for url, payload_body in requests:
                    request = urllib.request.Request(
                        url,
                        data=json.dumps(payload_body).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(payload["state"]["progress_count"], 0)
            self.assertEqual(payload["state"]["followup_count"], 0)
            self.assertEqual(payload["state"]["approval_count"], 0)

    def test_material_approval_disposition_closes_linked_review_progress_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            record = state.repo.create_job(
                {
                    "title": "Data Operations Associate",
                    "company": "ExampleCo",
                    "description": "Review account data and reconciliation breaks.",
                },
                {"decision": "apply", "role_family": "data_engineering", "facts": {}},
            )
            job_id = record["job"]["id"]
            progress = {
                "id": "legacyprogress1",
                "title": "Review generated resume and cover letter",
            }
            approval = {
                "id": "abc123abc123",
                "action": "review_application_materials",
            }
            with state.repo._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO progress_items (id, job_id, title, kind, status, due_date, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        progress["id"],
                        job_id,
                        progress["title"],
                        "material_review",
                        "open",
                        "",
                        "Legacy review row from before sparse Actions policy.",
                        "2026-05-01T00:00:00Z",
                        "2026-05-01T00:00:00Z",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO approvals (id, job_id, action, status, payload, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        approval["id"],
                        job_id,
                        approval["action"],
                        "pending",
                        json.dumps({"progress_item_id": progress["id"], "material_ids": ["mat1"]}),
                        "2026-05-01T00:00:00Z",
                        "2026-05-01T00:00:00Z",
                    ),
                )
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/approvals/{approval['id']}/disposition",
                    data=json.dumps({"action": "approve", "note": "Looks good"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(payload["approval"]["status"], "approved")
            self.assertEqual(payload["state"]["approval_count"], 0)
            self.assertEqual(payload["state"]["progress_count"], 0)
            saved_progress = state.repo.get_job(job_id)["progress_items"][0]
            self.assertEqual(saved_progress["status"], "done")

    def test_dashboard_job_detail_surfaces_outreach_contacts_followups_and_named_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "New Grads 2026 Data Engineer",
                    "company": "WeRide",
                    "location": "San Jose, CA",
                    "description": "Build data pipelines. Visa sponsorship is available.",
                },
                {
                    "decision": "apply",
                    "role_family": "data_engineering",
                    "facts": {"title": "New Grads 2026 Data Engineer", "company": "WeRide"},
                    "next_action": "Review generated materials and contact a recruiter.",
                },
            )
            job_id = record["job"]["id"]
            contact = repo.upsert_contact(
                "Avery Recruiter",
                company="WeRide",
                role="University Recruiting",
                linkedin_url="https://www.linkedin.com/in/avery-recruiter",
                email_status="missing",
            )
            resume = repo.save_material(
                job_id,
                "resume",
                "resume typst",
                format="typ",
                file_path=str(Path(tmpdir) / "materials" / job_id / "weride_new_grads_2026_data_engineer_resume.typ"),
            )
            draft = repo.save_material(
                job_id,
                "outreach_draft",
                "Hi Avery, I am applying to the data engineer role.",
                format="text",
                metadata={"subject": "WeRide Data Engineer", "contact_id": contact["id"], "channel": "linkedin"},
            )
            followup = repo.create_followup("2026-05-20", "Follow up with Avery", job_id=job_id, contact_id=contact["id"])

            dashboard_job = repo.dashboard()["jobs"][0]

            self.assertEqual(dashboard_job["id"], job_id)
            self.assertEqual(dashboard_job["next_action"], "Review generated materials and contact a recruiter.")
            self.assertEqual(dashboard_job["materials_workbench"]["primary"]["resume"]["id"], resume["id"])
            self.assertEqual(
                dashboard_job["materials_workbench"]["primary"]["resume"]["display_name"],
                "weride_new_grads_2026_data_engineer_resume.typ",
            )
            self.assertEqual(dashboard_job["outreach"]["drafts"][0]["id"], draft["id"])
            self.assertEqual(dashboard_job["outreach"]["drafts"][0]["subject"], "WeRide Data Engineer")
            self.assertEqual(dashboard_job["outreach"]["contacts"][0]["id"], contact["id"])
            self.assertEqual(dashboard_job["outreach"]["followups"][0]["id"], followup["id"])

    def test_database_health_reports_unattached_records_without_deleting_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            repo.create_followup("2026-05-15", "Loose reminder")
            repo.create_agent_run("Interrupted run", status="failed")

            health = repo.database_health()

            self.assertEqual(health["status"], "needs_attention")
            self.assertEqual(len(health["stale_records"]["unattached_followups"]), 1)
            self.assertEqual(len(health["stale_records"]["unattached_agent_runs"]), 1)

    def test_database_health_summarizes_unattached_tool_calls_without_full_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            repo.record_tool_call("jobapps_read_context", {}, {"blob": "x" * 4000})

            health = repo.database_health()
            tool_call = health["stale_records"]["tool_calls_without_run"][0]

            self.assertEqual(tool_call["tool_name"], "jobapps_read_context")
            self.assertGreater(tool_call["output_bytes"], 4000)
            self.assertFalse(tool_call["archived"])
            self.assertNotIn("input", tool_call)
            self.assertNotIn("output", tool_call)

    def test_large_tool_call_payload_is_archived_out_of_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            repo.record_tool_call("jobapps_read_context", {"scope": "all"}, {"blob": "x" * 1_100_000})

            call = repo.list_tool_calls(limit=1)[0]
            archive_path = Path(call["output"]["archive_path"])

            self.assertTrue(call["input"]["_archived_tool_call"])
            self.assertTrue(call["output"]["_archived_tool_call"])
            self.assertTrue(archive_path.exists())
            with gzip.open(archive_path, "rt", encoding="utf-8") as handle:
                archived = json.load(handle)
            self.assertEqual(archived["tool_name"], "jobapps_read_context")
            self.assertEqual(archived["output"]["blob"], "x" * 1_100_000)

    def test_tool_call_retention_archives_old_inline_payloads_without_deleting_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            repo.record_tool_call("jobapps_read_context", {"old": True}, {"ok": True})
            with repo._connect() as conn:
                conn.execute("UPDATE tool_calls SET created_at = ?", ("2000-01-01T00:00:00+00:00",))

            preview = repo.archive_old_tool_calls(retain_days=30, limit=10, dry_run=True)
            before = repo.list_tool_calls(limit=1)[0]
            applied = repo.archive_old_tool_calls(retain_days=30, limit=10, dry_run=False)
            after = repo.list_tool_calls(limit=1)[0]

            self.assertEqual(preview["candidate_count"], 1)
            self.assertFalse(before["input"].get("_archived_tool_call", False))
            self.assertEqual(applied["archived_count"], 1)
            self.assertTrue(after["input"]["_archived_tool_call"])
            self.assertEqual(len(repo.list_tool_calls(limit=10)), 1)

    def test_tool_call_retention_can_target_recent_oversized_inline_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            repo.record_tool_call("jobapps_read_context", {}, {"blob": "x" * 2000})

            preview = repo.archive_old_tool_calls(retain_days=30, limit=10, min_bytes=1000, dry_run=True)
            applied = repo.archive_old_tool_calls(retain_days=30, limit=10, min_bytes=1000, dry_run=False)
            after = repo.list_tool_calls(limit=1)[0]

            self.assertEqual(preview["candidate_count"], 1)
            self.assertEqual(applied["archived_count"], 1)
            self.assertTrue(after["output"]["_archived_tool_call"])

    def test_app_state_cache_invalidates_after_repository_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            initial_meta = state.state_meta()
            first = state.full_state()
            cached = state.full_state()

            state.repo.create_job(
                {
                    "title": "Backend Engineer",
                    "company": "ExampleCo",
                    "description": "Build APIs.",
                },
                {"decision": "apply", "role_family": "backend"},
            )
            updated = state.full_state()

            self.assertIs(first, cached)
            self.assertGreater(state.state_meta()["state_version"], initial_meta["state_version"])
            self.assertNotEqual(first["state_version"], updated["state_version"])
            self.assertEqual(updated["jobs"][0]["company"], "ExampleCo")

    def test_repository_closes_connections_under_repeated_operations(self) -> None:
        fd_dir = Path("/dev/fd")
        if not fd_dir.exists():
            fd_dir = Path("/proc/self/fd")
        if not fd_dir.exists():
            self.skipTest("File descriptor directory is not available on this platform.")
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            before = len(list(fd_dir.iterdir()))
            for index in range(80):
                repo.upsert_profile_fact(f"fact_{index}", f"value_{index}", category="fd", source="test")
                repo.upsert_proof_point(
                    label=f"FD proof {index}",
                    summary="Connection lifecycle proof for repeated writes.",
                    evidence="Repository connections should close deterministically.",
                    tags=["fd", "sqlite"],
                    source="test",
                )
                repo.search_evidence("sqlite", limit=2)
            after = len(list(fd_dir.iterdir()))

            self.assertLessEqual(after, before + 8)

    def test_repository_records_tailoring_portrayal_and_learning_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "HistoryCo",
                    "description": "Build LLM agents with memory and evaluation traces.",
                },
                {
                    "decision": "apply",
                    "role_family": "ai_agent_systems",
                    "facts": {"title": "AI Engineer", "company": "HistoryCo"},
                    "score_0_to_5": None,
                },
            )
            job_id = record["job"]["id"]
            requirement = repo.record_tailoring_requirement(
                job_id,
                "Build LLM agents with memory and evaluation traces.",
                category="agent_systems",
                source_text="Requirements: build LLM agents with memory and evaluation traces.",
                priority=0.95,
                status="needs_story",
            )
            material = repo.save_material(job_id, "resume_tailoring", "initial", format="text")
            decision = repo.record_portrayal_decision(
                job_id,
                target="resume.projects.agent_harness",
                after_text="Portray Hermes/JobApps as an agent harness with DB-backed memory, tools, and eval traces.",
                rationale="JD asks for LLM agents with memory and evaluation traces.",
                requirement_id=requirement["id"],
                material_id=material["id"],
                source="agent",
            )
            pattern = repo.record_learning_pattern(
                "portrayal_preference",
                trigger="agent roles ask for memory and evaluation",
                preference="Use agent harness language instead of generic chatbot language.",
                source="user_correction",
            )

            loaded = repo.get_job(job_id)

            self.assertEqual(loaded["tailoring_requirements"][0]["id"], requirement["id"])
            self.assertEqual(loaded["portrayal_decisions"][0]["id"], decision["id"])
            self.assertEqual(repo.list_learning_patterns()[0]["id"], pattern["id"])
            self.assertEqual(repo.dashboard()["context_counts"]["learning_patterns"], 1)

    def test_career_context_includes_learning_and_tailoring_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ContextCo",
                    "description": "Build LLM agents with memory and evaluation traces.",
                },
                {
                    "decision": "apply",
                    "role_family": "ai_agent_systems",
                    "facts": {"title": "AI Engineer", "company": "ContextCo"},
                    "score_0_to_5": None,
                },
            )
            job_id = record["job"]["id"]
            requirement = repo.record_tailoring_requirement(
                job_id,
                "Build LLM agents with memory and evaluation traces.",
                category="agent_systems",
                priority=0.95,
            )
            repo.record_portrayal_decision(
                job_id,
                target="resume_tailoring.typ",
                after_text="Use agent harness language for this role.",
                rationale="JD asks for memory and evaluation traces.",
                requirement_id=requirement["id"],
            )
            repo.record_learning_pattern(
                "portrayal_preference",
                "agent roles ask for memory and evaluation",
                "Use agent harness language instead of generic chatbot language.",
                source="user_correction",
            )

            context = repo.career_context()

            self.assertEqual(context["learning_patterns"][0]["pattern_type"], "portrayal_preference")
            self.assertEqual(context["recent_tailoring_requirements"][0]["id"], requirement["id"])
            self.assertEqual(context["recent_portrayal_decisions"][0]["target"], "resume_tailoring.typ")
            self.assertIn("brain_context", context)
            self.assertGreaterEqual(context["brain_context"]["event_counts"].get("portrayal_decision", 0), 1)

    def test_career_brain_records_entities_events_and_searches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")

            event = repo.record_brain_event(
                "preference",
                "Avoid generic enthusiasm",
                "Prashant prefers direct, specific application writing over generic enthusiasm.",
                entity_type="job_search",
                entity_name="voice",
                source="test",
                importance=0.9,
            )
            search = repo.search_brain("generic enthusiasm", limit=5)
            context = repo.brain_context(limit=5)

            self.assertEqual(event["event_type"], "preference")
            self.assertEqual(event["entity"]["type"], "job_search")
            self.assertEqual(search["events"][0]["id"], event["id"])
            self.assertEqual(context["entity_counts"]["job_search"], 1)
            self.assertEqual(context["event_counts"]["preference"], 1)

    def test_app_writes_leave_a_personal_brain_trail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            repo.upsert_profile_fact(
                "work_authorization",
                "F-1 OPT with sponsorship sensitivity.",
                category="constraint",
                source="test",
            )
            proof = repo.upsert_proof_point(
                label="Agent memory cockpit",
                role_family="ai_agent_systems",
                summary="Built a cockpit with app-owned memory and Hermes tools.",
                evidence="Implemented database tools, event trails, and context injection.",
                tags=["agents", "memory"],
                source="test",
            )

            search = repo.search_brain("sponsorship memory cockpit", limit=10)
            event_types = {item["event_type"] for item in search["events"]}

            self.assertEqual(proof["label"], "Agent memory cockpit")
            self.assertIn("profile_fact_updated", event_types)
            self.assertIn("proof_point_updated", event_types)
            self.assertGreaterEqual(repo.dashboard()["context_counts"]["brain_events"], 2)

    def test_provenance_rejects_cross_job_material_and_ineligible_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            first = repo.create_job(
                {"title": "AI Engineer", "company": "OneCo", "description": "Build agents."},
                {"decision": "apply", "facts": {}, "score_0_to_5": None},
            )
            second = repo.create_job(
                {"title": "Data Engineer", "company": "TwoCo", "description": "Build data systems."},
                {"decision": "apply", "facts": {}, "score_0_to_5": None},
            )
            foreign_material = repo.save_material(second["job"]["id"], "resume_tailoring", "foreign", format="text")
            retired_proof = repo.upsert_proof_point(
                label="Retired proof",
                summary="Old story.",
                evidence="Old story.",
                tags=["old"],
                source="test",
                status="retired",
            )

            with self.assertRaises(KeyError):
                repo.record_application_change(
                    first["job"]["id"],
                    "resume_tailoring",
                    "resume_tailoring.typ",
                    "Do not attach foreign material.",
                    "Cross-job provenance must be rejected.",
                    material_id=foreign_material["id"],
                )

            with self.assertRaises(ValueError):
                repo.record_portrayal_decision(
                    first["job"]["id"],
                    target="resume_tailoring.typ",
                    after_text="Do not cite retired proof.",
                    rationale="Inactive proof should not support materials.",
                    proof_id=retired_proof["id"],
                )


class EvidenceLayerTests(unittest.TestCase):
    def test_search_evidence_uses_lifecycle_before_text_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            active = repo.upsert_proof_point(
                label="Current agent retrieval system",
                role_family="ai_agent_systems",
                summary="Built current LLM agent retrieval and evaluation workflow with tool calls.",
                evidence="Current narrative proof for agentic systems roles.",
                tags=["agents", "retrieval", "evaluation"],
                source="test",
                status="active",
                user_confirmed=True,
                narrative_version="agentic_systems_current",
            )
            repo.upsert_proof_point(
                label="Old 2024 agent bullet",
                role_family="ai_agent_systems",
                summary="Old agent retrieval bullet that is semantically close but no longer usable.",
                evidence="Legacy wording from an old resume variant.",
                tags=["agents", "retrieval", "evaluation"],
                source="test",
                status="retired",
                user_confirmed=True,
                narrative_version="generalist_2024",
            )
            repo.upsert_proof_point(
                label="Unconfirmed memory bullet",
                role_family="ai_agent_systems",
                summary="Agent retrieval claim pulled from a reference file but not confirmed.",
                evidence="Needs user review before use.",
                tags=["agents", "retrieval"],
                source="test",
                status="candidate",
                user_confirmed=False,
            )

            results = repo.search_evidence(
                "agent retrieval evaluation tool calls",
                role_family="ai_agent_systems",
                use="resume",
                limit=10,
            )

            labels = [item["source"]["label"] for item in results["results"]]
            self.assertIn(active["label"], labels)
            self.assertNotIn("Old 2024 agent bullet", labels)
            self.assertNotIn("Unconfirmed memory bullet", labels)
            self.assertEqual(results["eligibility_filter"]["status"], ["active"])
            self.assertEqual(results["retrieval_mode"], "fts5")

    def test_superseded_proof_point_is_retained_but_excluded_from_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            old = repo.upsert_proof_point(
                label="Built a RAG chatbot",
                role_family="ai_agent_systems",
                summary="Built a RAG chatbot.",
                evidence="Older generic phrasing.",
                tags=["rag", "agent"],
                source="test",
            )
            new = repo.upsert_proof_point(
                label="Built retrieval-augmented agent workflow",
                role_family="ai_agent_systems",
                summary="Built a retrieval-augmented agent workflow with tool calls, state, and evaluation traces.",
                evidence="Current narrative version for agent roles.",
                tags=["rag", "agent", "tool-calling", "evaluation"],
                source="test",
            )

            repo.update_proof_point_lifecycle(
                old["id"],
                status="superseded",
                superseded_by=new["id"],
                reason="Current narrative uses more precise agent workflow language.",
            )

            retained = repo.get_proof_point(old["id"])
            results = repo.search_evidence("RAG agent workflow", role_family="ai_agent_systems")
            labels = [item["source"]["label"] for item in results["results"]]

            self.assertEqual(retained["status"], "superseded")
            self.assertEqual(retained["superseded_by"], new["id"])
            self.assertIn(new["label"], labels)
            self.assertNotIn(old["label"], labels)

    def test_prepare_opportunity_records_reusable_job_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)

            record = workflow.prepare_opportunity(
                {
                    "title": "AI Engineer",
                    "company": "SignalCo",
                    "location": "Remote",
                    "description": """
                    We need an AI Engineer to build LLM agents with retrieval, tool calling, evaluation traces, and PostgreSQL-backed APIs.
                    Visa sponsorship is available. This is an entry level role.
                    The application includes a short cover letter but no take-home assignment.
                    """,
                }
            )

            job_id = record["job"]["id"]
            signals = repo.list_application_signals(job_id)
            signal_pairs = {(item["signal_type"], item["label"]) for item in signals}
            refreshed = repo.get_job(job_id)
            self.assertIn(("sponsorship", "clear"), signal_pairs)
            self.assertIn(("role_family", "ai_agent_systems"), signal_pairs)
            self.assertTrue(any(item["signal_type"] == "requirement" for item in signals))
            self.assertFalse(any(item["signal_type"] == "gap" for item in signals))
            self.assertTrue(refreshed["tailoring_requirements"])
            self.assertTrue(refreshed["portrayal_decisions"])
            self.assertTrue(all(item["job_id"] == job_id for item in signals))

    def test_search_evidence_filters_eligibility_before_rank_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            for index in range(30):
                repo.upsert_proof_point(
                    label=f"Retired high-match proof {index}",
                    role_family="ai_agent_systems",
                    summary="retrieval retrieval retrieval retrieval retrieval old stale retired",
                    evidence="Old wording that should never crowd out active evidence.",
                    tags=["retrieval", "agents"],
                    source="test",
                    status="retired",
                    user_confirmed=True,
                )
            active = repo.upsert_proof_point(
                label="Current weaker-match proof",
                role_family="ai_agent_systems",
                summary="Current proof mentions retrieval once.",
                evidence="Active evidence should survive eligibility filtering before ranking.",
                tags=["retrieval"],
                source="test",
                status="active",
                user_confirmed=True,
            )

            results = repo.search_evidence("retrieval", role_family="ai_agent_systems", limit=1)

            self.assertEqual([item["source"]["id"] for item in results["results"]], [active["id"]])

    def test_prepare_opportunity_does_not_draft_from_resume_disallowed_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            repo.upsert_profile_fact("name", "Candidate Example", category="identity", source="test")
            repo.upsert_proof_point(
                label="Interview-only agent proof",
                role_family="ai_agent_systems",
                summary="Built interview-only zebraorion agent systems.",
                evidence="Interview-only evidence should not appear in resume materials.",
                tags=["zebraorion", "agents"],
                source="test",
                status="active",
                user_confirmed=True,
                allowed_uses=["interview"],
            )
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            workflow = JobAppsWorkflow(repo, AgentToolbox(repo, config))

            record = workflow.prepare_opportunity(
                {
                    "title": "AI Engineer",
                    "company": "UseFilterCo",
                    "location": "Remote",
                    "description": "Build zebraorion LLM agents with retrieval and tool calling. Visa sponsorship is available. Entry level.",
                }
            )

            material_text = "\n".join(item["content"] for item in record["materials"])
            changes_text = "\n".join(str(item.get("after_text", "")) for item in record["application_changes"])
            self.assertNotIn("Interview-only evidence", material_text)
            self.assertNotIn("Interview-only evidence", changes_text)
            self.assertNotIn("Interview-only agent proof", material_text)

    def test_retrieve_for_job_returns_current_evidence_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            active = repo.upsert_proof_point(
                label="Agent orchestration proof",
                role_family="ai_agent_systems",
                summary="Built an agent orchestration harness with retrieval, tool-use, and evaluation traces.",
                evidence="Current user-confirmed proof.",
                tags=["agents", "retrieval", "evaluation"],
                source="test",
                status="active",
                user_confirmed=True,
            )
            repo.upsert_proof_point(
                label="Old generic ML proof",
                role_family="ai_agent_systems",
                summary="Old retrieval and agent bullet from a previous narrative.",
                evidence="Retired phrasing.",
                tags=["agents", "retrieval"],
                source="test",
                status="retired",
                user_confirmed=True,
            )
            job_record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "RetrieveCo",
                    "description": "Build LLM agents with retrieval and evaluation traces. Visa sponsorship is available.",
                },
                {
                    "decision": "apply",
                    "role_family": "ai_agent_systems",
                    "facts": {"title": "AI Engineer", "company": "RetrieveCo"},
                    "score_0_to_5": 4.2,
                    "top_requirements": ["Build LLM agents with retrieval and evaluation traces."],
                    "must_have_matches": [],
                },
            )

            retrieval = repo.retrieve_for_job(job_record["job"]["id"], use="resume")
            labels = [item["source"]["label"] for item in retrieval["evidence"]]
            excluded_labels = [item["label"] for item in retrieval["excluded"]]

            self.assertIn(active["label"], labels)
            self.assertIn("Old generic ML proof", excluded_labels)
            self.assertEqual(retrieval["job_id"], job_record["job"]["id"])
            self.assertEqual(retrieval["policy"], "active_user_confirmed_first")


class ImporterTests(unittest.TestCase):
    def test_import_private_seed_writes_structured_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "profile-seed.json"
            path.write_text(
                """
                {
                  "profile_facts": [
                    {
                      "fact_key": "target_direction",
                      "value": "AI engineering roles around agents and RAG.",
                      "category": "preference"
                    }
                  ],
                  "proof_points": [
                    {
                      "label": "Agent memory project",
                      "role_family": "ai_agent_systems",
                      "summary": "Built an agent memory workflow with retrieval and evaluation.",
                      "evidence": "Implemented retrieval, tool calls, and trace review.",
                      "tags": ["agents", "rag"]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")

            result = import_private_seed(repo, path)

            self.assertEqual(len(result["profile_facts"]), 1)
            self.assertEqual(len(result["proof_points"]), 1)
            self.assertEqual(repo.list_profile_facts()[0]["fact_key"], "target_direction")
            self.assertEqual(repo.list_proof_points()[0]["label"], "Agent memory project")


class ToolTests(unittest.TestCase):
    def test_material_format_normalization_keeps_legacy_tex_and_typst_aliases(self) -> None:
        self.assertEqual(normalize_material_format("latex"), "tex")
        self.assertEqual(normalize_material_format("ltx"), "tex")
        self.assertEqual(normalize_material_format("typst"), "typ")

    def test_prepare_opportunity_tool_accepts_unstructured_chat_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)

            record = toolbox.execute(
                "jobapps_prepare_opportunity",
                {
                    "text": """
                    AI Engineer at ExampleCo
                    Location: Remote / New York
                    Build LLM agents with retrieval, tool calling, evaluation traces, and PostgreSQL-backed APIs.
                    Visa sponsorship is available. This is an entry level role.
                    The team needs someone who can design production APIs and evaluation workflows.
                    """
                },
            )

            self.assertEqual(record["job"]["title"], "AI Engineer")
            self.assertEqual(record["job"]["company"], "ExampleCo")
            self.assertTrue(record["materials"])
            self.assertEqual(record["approvals"], [])

    def test_native_tui_material_prep_tool_queues_pending_jobs_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            hermes = ParallelBlockingHermesClient()
            toolbox = AgentToolbox(repo, config, hermes_factory=lambda _config: hermes)
            workflow = JobAppsWorkflow(repo, toolbox)
            workflow.prepare_opportunity(
                {
                    "title": "Data Engineer",
                    "company": "FirstCo",
                    "description": "Build data pipelines with SQL and Python. Visa sponsorship is available. Entry level role.",
                }
            )
            workflow.prepare_opportunity(
                {
                    "title": "Software Engineer",
                    "company": "SecondCo",
                    "description": "Build backend APIs with Python and PostgreSQL. Visa sponsorship is available. Entry level role.",
                }
            )

            try:
                started_at = time.monotonic()
                result = toolbox.execute("jobapps_start_material_prep", {"scope": "pending"})
                elapsed = time.monotonic() - started_at

                self.assertLess(elapsed, 0.25)
                self.assertEqual(result["queued_count"], 2)
                self.assertTrue(hermes.two_active.wait(timeout=0.5))
                self.assertGreaterEqual(hermes.max_active_count, 2)
            finally:
                hermes.release.set()
                hermes.all_done.wait(timeout=1)
                wait_for_jobapps_launch_threads()
                wait_for_started_run_count(repo, 2)

    def test_evidence_boolean_flags_reject_string_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())

            with self.assertRaises(ValueError):
                toolbox.execute(
                    "jobapps_upsert_proof_point",
                    {
                        "label": "String false proof",
                        "summary": "Should not coerce string booleans.",
                        "evidence": "Should not be stored as confirmed.",
                        "user_confirmed": "false",
                    },
                )
            with self.assertRaises(ValueError):
                toolbox.execute(
                    "jobapps_search_evidence",
                    {"query": "anything", "include_inactive": "false"},
                )

    def test_save_tex_material_writes_file_when_agent_omits_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": "Build LLM agents with retrieval and evaluation for internal tools.",
                },
                {"decision": "maybe", "facts": {}, "score_0_to_5": 3.0},
            )
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": record["job"]["id"],
                    "kind": "cover_letter",
                    "format": "tex",
                    "content": "\\documentclass{letter}",
                },
            )

            self.assertEqual(Path(saved["file_path"]).name, "Prashant Shah - Cover Letter - ExampleCo - AI Engineer.tex")
            self.assertFalse(Path(saved["file_path"]).name == "cover_letter.tex")
            self.assertTrue(Path(saved["file_path"]).exists())

    def test_save_typst_resume_material_writes_typ_file_when_agent_omits_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": "Build LLM agents with retrieval and evaluation for internal tools.",
                },
                {"decision": "maybe", "facts": {}, "score_0_to_5": 3.0},
            )
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": record["job"]["id"],
                    "kind": "resume_tailoring",
                    "format": "typst",
                    "content": "#show: doc => doc\nResume content",
                },
            )

            self.assertEqual(saved["format"], "typ")
            self.assertEqual(Path(saved["file_path"]).name, "Prashant Shah - Resume - ExampleCo - AI Engineer.typ")
            self.assertFalse(Path(saved["file_path"]).name == "resume_tailoring.typ")
            self.assertTrue(Path(saved["file_path"]).exists())

    def test_save_latex_material_writes_tex_file_when_agent_says_latex_for_legacy_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": "Build LLM agents with retrieval and evaluation for internal tools.",
                },
                {"decision": "maybe", "facts": {}, "score_0_to_5": 3.0},
            )
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": record["job"]["id"],
                    "kind": "resume_tailoring",
                    "format": "latex",
                    "content": "\\documentclass{article}",
                },
            )

            self.assertEqual(saved["format"], "tex")
            self.assertEqual(Path(saved["file_path"]).name, "Prashant Shah - Resume - ExampleCo - AI Engineer.tex")
            self.assertFalse(Path(saved["file_path"]).name == "resume_tailoring.typ")
            self.assertTrue(Path(saved["file_path"]).exists())

    def test_approval_tools_create_and_update_external_send_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": "Build agent workflows.",
                },
                {"decision": "maybe", "facts": {}, "score_0_to_5": 3.0},
            )
            approval = toolbox.execute(
                "jobapps_request_approval",
                {
                    "job_id": record["job"]["id"],
                    "action": "manual_send_email",
                    "payload": {"reason": "Send prepared outreach email."},
                },
            )

            updated = toolbox.execute(
                "jobapps_update_approval",
                {
                    "approval_id": approval["id"],
                    "status": "approved",
                    "payload": {"decided_from": "test"},
                },
            )

            self.assertEqual(updated["status"], "approved")
            self.assertEqual(updated["payload"]["decided_from"], "test")

    def test_progress_item_tool_reuses_equivalent_open_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())
            record = repo.create_job(
                {
                    "title": "Data Engineer",
                    "company": "ExampleCo",
                    "description": "Build SQL data quality workflows.",
                },
                {"decision": "apply", "facts": {}, "score_0_to_5": 3.0},
            )
            job_id = record["job"]["id"]

            first = toolbox.execute(
                "jobapps_create_progress_item",
                {
                    "job_id": job_id,
                    "title": "Send email to recruiter",
                    "kind": "networking",
                    "status": "open",
                    "notes": "First pass ready.",
                },
            )
            second = toolbox.execute(
                "jobapps_create_progress_item",
                {
                    "job_id": job_id,
                    "title": "  send   email to recruiter  ",
                    "kind": "networking",
                    "status": "open",
                    "due_date": "2026-05-28",
                    "notes": "Revised pass ready.",
                },
            )

            progress_items = repo.get_job(job_id)["progress_items"]
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(len(progress_items), 1)
            self.assertEqual(progress_items[0]["notes"], "Revised pass ready.")
            self.assertEqual(progress_items[0]["due_date"], "2026-05-28")

    def test_mark_material_ready_updates_material_metadata_without_action_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())
            record = repo.create_job(
                {
                    "title": "Data Operations Associate",
                    "company": "ExampleCo",
                    "description": "Review account data and reconciliation breaks.",
                },
                {"decision": "apply", "facts": {}, "score_0_to_5": 3.0},
            )
            job_id = record["job"]["id"]
            resume = repo.save_material(job_id, "resume", "resume tex", format="tex")
            cover = repo.save_material(job_id, "cover_letter", "cover tex", format="tex")

            result = toolbox.execute(
                "jobapps_mark_material_ready_for_review",
                {
                    "job_id": job_id,
                    "material_ids": [resume["id"], cover["id"]],
                    "reason": "Resume and cover revised.",
                },
            )

            job_state = repo.get_job(job_id)
            pending_approvals = [item for item in job_state["approvals"] if item["status"] == "pending"]
            open_progress = [item for item in job_state["progress_items"] if item["status"] == "open"]

            self.assertIsNone(result["approval"])
            self.assertIsNone(result["progress_item"])
            self.assertEqual(len(pending_approvals), 0)
            self.assertEqual(len(open_progress), 0)
            self.assertEqual([item["metadata"]["review_status"] for item in result["materials"]], ["ready_for_review", "ready_for_review"])

    def test_dashboard_actions_only_include_purposeful_send_and_followup_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = repo.create_job(
                {
                    "title": "Software Engineer",
                    "company": "ExampleCo",
                    "description": "Build internal workflow tools.",
                },
                {"decision": "apply", "facts": {}, "score_0_to_5": 3.0},
            )
            job_id = record["job"]["id"]
            repo.create_progress_item("Run quick company and sponsorship research", job_id=job_id, kind="research")
            repo.create_progress_item("Find networking targets", job_id=job_id, kind="networking")
            repo.create_progress_item("Submit ExampleCo application", job_id=job_id, kind="application")
            send_progress = repo.create_progress_item("Send email to Jane after application", job_id=job_id, kind="networking")
            followup = repo.create_followup("2026-06-05", "Send follow-up to Jane", job_id=job_id)
            send_approval = repo.create_approval("manual_send_email_to_jane", job_id=job_id)

            dashboard = repo.dashboard()
            job = next(item for item in dashboard["jobs"] if item["id"] == job_id)

            self.assertEqual([item["id"] for item in dashboard["progress_items"]], [send_progress["id"]])
            self.assertEqual([item["id"] for item in dashboard["followups"]], [followup["id"]])
            self.assertEqual([item["id"] for item in dashboard["approvals"]], [send_approval["id"]])
            self.assertEqual(dashboard["progress_count"], 1)
            self.assertEqual(dashboard["followup_count"], 1)
            self.assertEqual(dashboard["approval_count"], 1)
            self.assertEqual(job["open_action_count"], 3)

    def test_learning_pattern_tool_persists_user_correction_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())

            pattern = toolbox.execute(
                "jobapps_record_learning_pattern",
                {
                    "pattern_type": "portrayal_preference",
                    "trigger": "agent roles ask for memory and evaluation",
                    "preference": "Use agent harness language instead of generic chatbot language.",
                    "source": "user_correction",
                },
            )

            self.assertEqual(pattern["pattern_type"], "portrayal_preference")
            self.assertEqual(repo.list_learning_patterns()[0]["id"], pattern["id"])

    def test_brain_tools_persist_and_search_human_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())

            event = toolbox.execute(
                "jobapps_record_brain_event",
                {
                    "event_type": "networking_preference",
                    "title": "Warm intros should stay plainspoken",
                    "content": "Use concise, specific outreach; avoid performative excitement.",
                    "entity_type": "job_search",
                    "entity_name": "networking voice",
                    "source": "user_correction",
                    "importance": 0.85,
                },
            )
            search = toolbox.execute("jobapps_search_brain", {"query": "plainspoken outreach"})

            self.assertEqual(event["event_type"], "networking_preference")
            self.assertEqual(search["events"][0]["id"], event["id"])

    def test_chat_messages_are_captured_as_brain_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())
            chat = ChatOrchestrator(repo=repo, toolbox=toolbox, workflow=None)

            result = chat.handle("Remember that I don't like generic enthusiasm in cover letters.")
            search = repo.search_brain("generic enthusiasm cover letters", event_type="conversation_signal")

            self.assertEqual(result["action"], "no_op")
            self.assertTrue(search["events"])

    def test_tailoring_and_portrayal_tools_persist_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            toolbox = AgentToolbox(repo, load_config())
            record = repo.create_job(
                {
                    "title": "AI Engineer",
                    "company": "ToolCo",
                    "description": "Build LLM agents with memory and evaluation traces.",
                },
                {"decision": "apply", "facts": {}, "score_0_to_5": None},
            )
            material = repo.save_material(record["job"]["id"], "resume_tailoring", "initial", format="text")

            requirement = toolbox.execute(
                "jobapps_record_tailoring_requirement",
                {
                    "job_id": record["job"]["id"],
                    "requirement": "Build LLM agents with memory and evaluation traces.",
                    "category": "agent_systems",
                    "priority": 0.9,
                    "metadata": {"source": "test"},
                },
            )
            decision = toolbox.execute(
                "jobapps_record_portrayal_decision",
                {
                    "job_id": record["job"]["id"],
                    "requirement_id": requirement["id"],
                    "material_id": material["id"],
                    "target": "resume_tailoring.typ",
                    "after_text": "Frame this as an agent harness with state, tools, retrieval, and verification.",
                    "rationale": "The JD asks for memory and evaluation traces.",
                    "decision_type": "jd_grounded_portrayal",
                },
            )

            loaded = repo.get_job(record["job"]["id"])
            self.assertEqual(loaded["tailoring_requirements"][0]["id"], requirement["id"])
            self.assertEqual(loaded["portrayal_decisions"][0]["id"], decision["id"])


class WritingPromptTests(unittest.TestCase):
    def test_draft_materials_uses_tailoring_targets_and_learning_patterns(self) -> None:
        job = {
            "title": "AI Engineer",
            "company": "HarnessCo",
            "description": "Build LLM agents with memory, retrieval, tool use, and evaluation traces.",
        }
        evaluation = {
            "facts": {"company": "HarnessCo", "title": "AI Engineer"},
            "role_family": "ai_agent_systems",
            "strongest_angle": "Agentic systems with traceable state, tool use, retrieval, and evaluation.",
            "evaluation_mode": "blocker_preflight",
            "tailoring_targets": [
                {
                    "requirement": "Build LLM agents with memory and evaluation traces.",
                    "requested_portrayal": "Use agent harness language instead of generic chatbot language.",
                    "proof_candidates": [],
                    "status": "needs_story",
                }
            ],
            "must_have_matches": [
                {
                    "requirement": "Build LLM agents with memory and evaluation traces.",
                    "proof_id": None,
                    "proof_point": "No direct proof point found in the application database.",
                    "strength": "gap",
                }
            ],
        }
        context = {
            "profile_facts": [{"fact_key": "name", "value": "Candidate Example"}],
            "learning_patterns": [
                {
                    "pattern_type": "portrayal_preference",
                    "trigger": "agent roles ask for memory and evaluation",
                    "preference": "Use agent harness language instead of generic chatbot language.",
                }
            ],
        }

        drafts = draft_materials(job, evaluation, context, load_config())
        joined = "\n".join(drafts["resume_notes"]) + "\n" + drafts["cover_letter"]

        self.assertIn("agent harness language", joined)
        self.assertIn("Build LLM agents with memory and evaluation traces", joined)
        self.assertNotIn("Treat as a gap", joined)
        self.assertNotIn("Learned preference", joined)
        self.assertNotIn("JD-specific target", joined)

    def test_draft_materials_rejects_internal_state_leakage(self) -> None:
        job = {
            "title": "Data Operations Associate",
            "company": "ExampleCo",
            "description": "Reconcile account data and integrate third-party systems.",
        }
        evaluation = {
            "facts": {"company": "ExampleCo", "title": "Data Operations Associate"},
            "role_family": "data_engineering",
            "strongest_angle": "Data operations with validation, reconciliation, and integrations.",
            "evaluation_mode": "blocker_preflight",
            "tailoring_targets": [],
            "must_have_matches": [],
        }
        context = {
            "profile_facts": [{"fact_key": "name", "value": "Candidate Example"}],
            "learning_patterns": [
                {
                    "pattern_type": "materials_boundary",
                    "trigger": "cover letters",
                    "preference": "Learned preference: weak networking replies should not leak operational states.",
                }
            ],
        }

        drafts = draft_materials(job, evaluation, context, load_config())
        serialized = json.dumps(drafts).lower()

        self.assertNotIn("learned preference", serialized)
        self.assertNotIn("weak networking replies", serialized)
        self.assertNotIn("operational states", serialized)
        self.assertNotIn("follow up after", serialized)

    def test_opportunity_prompt_is_blocker_preflight_and_learning_aware(self) -> None:
        job = {
            "title": "AI Engineer",
            "company": "PromptCo",
            "description": "Build LLM agents with memory, retrieval, and evaluation traces.",
        }
        context = {
            "profile_facts": [],
            "proof_points": [],
            "recent_jobs": [],
            "learning_patterns": [
                {
                    "pattern_type": "portrayal_preference",
                    "trigger": "agent roles",
                    "preference": "Use agent harness language.",
                }
            ],
        }
        evaluation = {
            "evaluation_mode": "blocker_preflight",
            "fit_assumption": "user_provided_jd_implies_apply_intent",
            "tailoring_targets": [
                {
                    "requirement": "Build LLM agents with memory.",
                    "requested_portrayal": "Use agent harness language.",
                }
            ],
        }

        prompt = build_opportunity_prompt(job, context, evaluation)

        self.assertIn("blocker preflight", prompt.lower())
        self.assertIn("Do not fit-score", prompt)
        self.assertIn("learning_patterns", prompt)
        self.assertIn("tailoring_targets", prompt)
        self.assertNotIn("Gate for sponsorship, location, seniority, fit", prompt)


class MaterialWorkbenchTests(unittest.TestCase):
    def _create_job(self, repo: JobRepository) -> dict:
        return repo.create_job(
            {
                "title": "AI Engineer",
                "company": "ExampleCo",
                "description": "Build LLM agents with retrieval and evaluation for internal tools.",
            },
            {"decision": "maybe", "facts": {}, "score_0_to_5": 3.0},
        )

    def test_patch_material_records_revision_diff_and_updates_tex_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)
            job_id = record["job"]["id"]
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": job_id,
                    "kind": "resume",
                    "format": "tex",
                    "content": "\\documentclass{article}\n\\begin{document}\nOld agent bullet\n\\end{document}\n",
                },
            )

            patched = toolbox.execute(
                "jobapps_patch_material",
                {
                    "material_id": saved["id"],
                    "old_string": "Old agent bullet",
                    "new_string": "Production agent bullet",
                    "reason": "Match the role's production-agent requirement.",
                    "requirement": "production LLM agent experience",
                },
            )

            self.assertEqual(patched["material"]["content"].count("Production agent bullet"), 1)
            self.assertIn("-Old agent bullet", patched["diff"])
            self.assertIn("+Production agent bullet", patched["diff"])
            self.assertEqual(patched["revision"]["version"], 2)
            self.assertEqual(Path(saved["file_path"]).read_text(encoding="utf-8"), patched["material"]["content"])
            job = repo.get_job(job_id)
            self.assertEqual(len(job["material_revisions"]), 1)
            self.assertEqual(job["application_changes"][0]["target"], "resume.tex")

    def test_patch_material_rejects_ineligible_proof_before_mutating_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)
            job_id = record["job"]["id"]
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": job_id,
                    "kind": "resume",
                    "format": "tex",
                    "content": "\\documentclass{article}\n\\begin{document}\nOld agent bullet\n\\end{document}\n",
                },
            )
            retired_proof = repo.upsert_proof_point(
                label="Retired proof",
                summary="Old story.",
                evidence="Old story.",
                tags=["old"],
                source="test",
                status="retired",
            )
            before_file = Path(saved["file_path"]).read_text(encoding="utf-8")

            with self.assertRaises(ValueError):
                toolbox.execute(
                    "jobapps_patch_material",
                    {
                        "material_id": saved["id"],
                        "old_string": "Old agent bullet",
                        "new_string": "Production agent bullet",
                        "reason": "Should fail before mutation.",
                        "proof_id": retired_proof["id"],
                    },
                )

            material = repo.get_material(saved["id"])
            job = repo.get_job(job_id)
            self.assertIn("Old agent bullet", material["content"])
            self.assertEqual(Path(saved["file_path"]).read_text(encoding="utf-8"), before_file)
            self.assertEqual(job["material_revisions"], [])
            self.assertEqual(job["application_changes"], [])

    def test_compile_material_pdf_reports_missing_compiler_without_installing_anything(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            config["latex"] = {"compiler_order": ["definitely_missing_tex_compiler"]}
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": record["job"]["id"],
                    "kind": "cover_letter",
                    "format": "tex",
                    "content": "\\documentclass{letter}\n\\begin{document}Hello\\end{document}\n",
                },
            )

            compiled = toolbox.execute("jobapps_compile_material_pdf", {"material_id": saved["id"]})

            self.assertFalse(compiled["ok"])
            self.assertEqual(compiled["status"], "missing_compiler")
            self.assertIn("definitely_missing_tex_compiler", compiled["compiler_candidates"])
            self.assertIn("Install", compiled["next_step"])

    def test_compile_discovers_compiler_from_configured_paths_not_only_shell_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            tex = tmp / "hello.tex"
            tex.write_text("\\documentclass{article}\n\\begin{document}Hello\\end{document}\n", encoding="utf-8")
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            fake_tectonic = bin_dir / "tectonic"
            fake_tectonic.write_text(
                "#!/bin/sh\n"
                "outdir=''\n"
                "last=''\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = \"--outdir\" ]; then shift; outdir=\"$1\"; fi\n"
                "  last=\"$1\"\n"
                "  shift\n"
                "done\n"
                "stem=$(basename \"$last\" .tex)\n"
                "mkdir -p \"$outdir\"\n"
                "printf '%s' '%PDF-1.4 fake' > \"$outdir/$stem.pdf\"\n",
                encoding="utf-8",
            )
            fake_tectonic.chmod(0o755)

            compiled = compile_tex_to_pdf(
                tex,
                config={
                    "latex": {
                        "compiler_order": ["tectonic"],
                        "compiler_paths": [str(bin_dir)],
                        "timeout_seconds": 5,
                    }
                },
            )

            self.assertTrue(compiled["ok"], compiled)
            self.assertEqual(compiled["status"], "compiled")
            self.assertEqual(compiled["compiler"], str(fake_tectonic))
            self.assertTrue(Path(compiled["pdf_path"]).exists())

    def test_compile_material_pdf_is_one_shot_final_pdf_verify_and_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = JobRepository(tmp / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(tmp / "materials")
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            fake_tectonic = bin_dir / "tectonic"
            fake_tectonic.write_text(
                "#!/bin/sh\n"
                "outdir=''\n"
                "last=''\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = \"--outdir\" ]; then shift; outdir=\"$1\"; fi\n"
                "  last=\"$1\"\n"
                "  shift\n"
                "done\n"
                "stem=$(basename \"$last\" .tex)\n"
                "mkdir -p \"$outdir\"\n"
                "printf '%s' '%PDF-1.4 fake' > \"$outdir/$stem.pdf\"\n"
                "printf 'temporary log' > \"$outdir/$stem.log\"\n",
                encoding="utf-8",
            )
            fake_tectonic.chmod(0o755)
            fake_pdfinfo = bin_dir / "pdfinfo"
            fake_pdfinfo.write_text("#!/bin/sh\nprintf 'Pages:           1\\n'\n", encoding="utf-8")
            fake_pdfinfo.chmod(0o755)
            fake_pdftotext = bin_dir / "pdftotext"
            fake_pdftotext.write_text("#!/bin/sh\nprintf 'Hello supplier validation world\\n'\n", encoding="utf-8")
            fake_pdftotext.chmod(0o755)
            config["latex"] = {
                "compiler_order": ["tectonic"],
                "compiler_paths": [str(bin_dir)],
                "timeout_seconds": 5,
            }
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": record["job"]["id"],
                    "kind": "resume",
                    "format": "tex",
                    "content": "\\documentclass{article}\n\\begin{document}Hello supplier validation world\\end{document}\n",
                },
            )

            compiled = toolbox.execute("jobapps_compile_material_pdf", {"material_id": saved["id"]})

            source_path = Path(compiled["tex_path"])
            final_pdf = source_path.with_suffix(".pdf")
            self.assertTrue(compiled["ok"], compiled)
            self.assertEqual(compiled["pdf_path"], str(final_pdf))
            self.assertTrue(final_pdf.exists())
            self.assertFalse((source_path.parent / "build").exists())
            self.assertEqual(compiled["verification"]["pages"], 1)
            self.assertEqual(compiled["verification"]["word_count"], 4)
            self.assertEqual(compiled["verification"]["contamination"], [])
            updated = repo.get_material(saved["id"])
            self.assertEqual(updated["metadata"]["compile"]["pdf_path"], str(final_pdf))
            self.assertEqual(updated["metadata"]["pdf_path"], str(final_pdf))

    def test_compile_material_pdf_compiles_typst_resume_and_cleans_build_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            repo = JobRepository(tmp / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(tmp / "materials")
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            fake_typst = bin_dir / "typst"
            fake_typst.write_text(
                "#!/bin/sh\n"
                "out=''\n"
                "while [ $# -gt 0 ]; do\n"
                "  if [ \"$1\" = \"compile\" ]; then shift; continue; fi\n"
                "  last=\"$1\"\n"
                "  shift\n"
                "done\n"
                "out=\"$last\"\n"
                "mkdir -p \"$(dirname \"$out\")\"\n"
                "printf '%s' '%PDF-1.4 fake' > \"$out\"\n",
                encoding="utf-8",
            )
            fake_typst.chmod(0o755)
            fake_pdfinfo = bin_dir / "pdfinfo"
            fake_pdfinfo.write_text("#!/bin/sh\nprintf 'Pages:           1\\n'\n", encoding="utf-8")
            fake_pdfinfo.chmod(0o755)
            fake_pdftotext = bin_dir / "pdftotext"
            fake_pdftotext.write_text("#!/bin/sh\nprintf 'Hello typst resume world\\n'\n", encoding="utf-8")
            fake_pdftotext.chmod(0o755)
            config["typst"] = {
                "compiler_order": ["typst"],
                "compiler_paths": [str(bin_dir)],
                "timeout_seconds": 5,
            }
            config["latex"] = {
                "compiler_order": ["definitely_missing_tex_compiler"],
                "compiler_paths": [str(bin_dir)],
                "timeout_seconds": 5,
            }
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)
            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": record["job"]["id"],
                    "kind": "resume",
                    "format": "typ",
                    "content": "= Hello Typst Resume\nHello typst resume world\n",
                },
            )

            compiled = toolbox.execute("jobapps_compile_material_pdf", {"material_id": saved["id"]})

            source_path = Path(compiled["typst_path"])
            final_pdf = source_path.with_suffix(".pdf")
            self.assertTrue(compiled["ok"], compiled)
            self.assertEqual(compiled["pdf_path"], str(final_pdf))
            self.assertTrue(final_pdf.exists())
            self.assertFalse((source_path.parent / "build").exists())
            self.assertEqual(compiled["compiler"], str(fake_typst))
            self.assertEqual(compiled["verification"]["pages"], 1)
            self.assertEqual(compiled["verification"]["word_count"], 4)
            updated = repo.get_material(saved["id"])
            self.assertEqual(updated["metadata"]["compile"]["pdf_path"], str(final_pdf))
            self.assertEqual(updated["metadata"]["pdf_path"], str(final_pdf))

    def test_create_full_resume_typst_and_cover_letter_tex_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = repo.create_job(
                {
                    "title": "New Grads 2026 Data Engineer",
                    "company": "WeRide",
                    "description": "Build data pipelines with SQL and validation for autonomy datasets.",
                },
                {"decision": "apply", "facts": {}, "score_0_to_5": None},
            )
            job_id = record["job"]["id"]

            resume = toolbox.execute(
                "jobapps_create_resume_typst",
                {
                    "job_id": job_id,
                    "headline": "AI Engineer focused on agentic systems",
                    "sections": [
                        {"title": "Projects", "items": ["Built an agent retrieval system with evaluation traces."]}
                    ],
                    "rationale": "Create a full resume material, not only tailoring notes.",
                },
            )
            letter = toolbox.execute(
                "jobapps_create_cover_letter_tex",
                {
                    "job_id": job_id,
                    "body": "Agentic systems matter when state, tools, retrieval, and evaluation work together.",
                    "company": "WeRide",
                    "rationale": "Create a send-ready cover letter material.",
                },
            )

            self.assertEqual(resume["kind"], "resume")
            self.assertEqual(letter["kind"], "cover_letter")
            self.assertEqual(Path(resume["file_path"]).name, "Prashant Shah - Resume - WeRide - New Grads 2026 Data Engineer.typ")
            self.assertEqual(Path(letter["file_path"]).name, "Prashant Shah - Cover Letter - WeRide - New Grads 2026 Data Engineer.tex")
            self.assertFalse(Path(resume["file_path"]).name == "resume.typ")
            self.assertFalse(Path(letter["file_path"]).name == "cover_letter.tex")
            dashboard_job = repo.dashboard()["jobs"][0]
            self.assertIn("materials_workbench", dashboard_job)
            self.assertEqual(dashboard_job["materials_workbench"]["primary"]["resume"]["id"], resume["id"])
            self.assertEqual(
                dashboard_job["materials_workbench"]["primary"]["resume"]["display_name"],
                "Prashant Shah - Resume - WeRide - New Grads 2026 Data Engineer.typ",
            )

    def test_professional_material_filename_sanitizes_without_looking_programmatic(self) -> None:
        filename = job_material_filename(
            {"company": "ACME/Data, Inc.", "title": "Software Engineer (New Grad) / Backend"},
            "resume",
            "PDF",
        )

        self.assertEqual(filename, "Prashant Shah - Resume - ACME Data Inc. - Software Engineer New Grad Backend.pdf")
        self.assertNotIn("_", filename)
        self.assertNotIn("/", filename)

    def test_material_workbench_exposes_metadata_pdf_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = self._create_job(repo)
            pdf_path = str(Path(tmpdir) / "materials" / "cover_letter.pdf")
            Path(pdf_path).parent.mkdir(parents=True)
            Path(pdf_path).write_bytes(b"%PDF-1.4\n")
            material = repo.save_material(
                record["job"]["id"],
                "cover_letter",
                "\\documentclass{letter}",
                format="tex",
                file_path=str(Path(tmpdir) / "materials" / "cover_letter.tex"),
                metadata={"pdf_path": pdf_path},
            )

            dashboard_job = repo.dashboard()["jobs"][0]
            summary = next(item for item in dashboard_job["materials_workbench"]["items"] if item["id"] == material["id"])

            self.assertEqual(summary["pdf_path"], pdf_path)
            self.assertEqual(summary["compile_status"], "compiled")

    def test_resume_typst_final_alias_is_dashboard_visible_as_resume_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)
            material_dir = Path(config["materials_path"]) / record["job"]["id"]
            material_dir.mkdir(parents=True)
            typ_path = material_dir / "Applicant - Resume - ExampleCo - Data Engineer.typ"
            pdf_path = material_dir / "Applicant - Resume - ExampleCo - Data Engineer.pdf"
            typ_path.write_text("#show: doc => doc\nResume", encoding="utf-8")
            pdf_path.write_bytes(b"%PDF-1.4\n")

            saved = toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": record["job"]["id"],
                    "kind": "resume_typst_final",
                    "format": "typst",
                    "content": {
                        "source_format": "typst",
                        "source_path": str(typ_path),
                        "pdf_path": str(pdf_path),
                        "page_count": 1,
                    },
                    "file_path": str(typ_path),
                    "metadata": {"review_status": "ready_for_review"},
                },
            )

            dashboard_job = repo.dashboard()["jobs"][0]
            summary = next(item for item in dashboard_job["materials_workbench"]["items"] if item["id"] == saved["id"])

            self.assertEqual(saved["kind"], "resume")
            self.assertEqual(saved["format"], "typ")
            self.assertEqual(saved["metadata"]["pdf_path"], str(pdf_path))
            self.assertEqual(summary["kind"], "resume")
            self.assertEqual(summary["pdf_path"], str(pdf_path))
            self.assertEqual(summary["compile_status"], "compiled")
            self.assertEqual(dashboard_job["materials_workbench"]["primary"]["resume"]["id"], saved["id"])

    def test_material_workbench_uses_sibling_pdf_when_metadata_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = self._create_job(repo)
            material_dir = Path(tmpdir) / "materials" / record["job"]["id"]
            material_dir.mkdir(parents=True)
            tex_path = material_dir / "resume.tex"
            pdf_path = material_dir / "resume.pdf"
            tex_path.write_text("\\documentclass{article}\n", encoding="utf-8")
            pdf_path.write_bytes(b"%PDF-1.4\n")
            stale_pdf_path = material_dir / "build" / "resume.pdf"
            material = repo.save_material(
                record["job"]["id"],
                "resume",
                "\\documentclass{article}\n",
                format="tex",
                file_path=str(tex_path),
                metadata={"compile": {"status": "compiled", "pdf_path": str(stale_pdf_path)}},
            )

            dashboard_job = repo.dashboard()["jobs"][0]
            summary = next(item for item in dashboard_job["materials_workbench"]["items"] if item["id"] == material["id"])

            self.assertEqual(summary["pdf_path"], str(pdf_path))
            self.assertEqual(summary["compile_status"], "compiled")

    def test_material_workbench_uses_typst_sibling_pdf_when_metadata_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            record = self._create_job(repo)
            material_dir = Path(tmpdir) / "materials" / record["job"]["id"]
            material_dir.mkdir(parents=True)
            typ_path = material_dir / "resume.typ"
            pdf_path = material_dir / "resume.pdf"
            typ_path.write_text("#show: doc => doc\nResume", encoding="utf-8")
            pdf_path.write_bytes(b"%PDF-1.4\n")
            material = repo.save_material(
                record["job"]["id"],
                "resume",
                "#show: doc => doc\nResume",
                format="typst",
                file_path=str(typ_path),
            )

            dashboard_job = repo.dashboard()["jobs"][0]
            summary = next(item for item in dashboard_job["materials_workbench"]["items"] if item["id"] == material["id"])

            self.assertEqual(material["format"], "typ")
            self.assertEqual(summary["pdf_path"], str(pdf_path))
            self.assertEqual(summary["compile_status"], "compiled")

    def test_frontend_exposes_material_workbench_copy(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("materials_workbench", app_js)
        self.assertIn("Materials", app_js)
        self.assertIn("Compile PDF", app_js)
        self.assertIn("Build PDF", app_js)
        self.assertIn("openMaterialViewer", app_js)
        self.assertIn("materialViewer", index_html)
        self.assertIn("materialUrl", app_js)
        self.assertIn("materialIsCompilable", app_js)
        self.assertIn('item.format === "pdf"', app_js)
        self.assertIn("materialTryParseJson", app_js)
        self.assertIn("materialAppendLinkedText", app_js)
        self.assertIn("renderMaterialViewerContent", app_js)
        self.assertIn("material-rendered-content", (Path(__file__).resolve().parents[1] / "web" / "styles.css").read_text(encoding="utf-8"))
        self.assertIn("material-rendered-content a", (Path(__file__).resolve().parents[1] / "web" / "styles.css").read_text(encoding="utf-8"))
        self.assertIn("<h2>Jobs</h2>", index_html)
        self.assertIn("materialsOverview", index_html)
        self.assertIn("no PDFs yet for this job", app_js)
        self.assertIn("Saved in App", app_js)
        self.assertIn("Most recent job", app_js)
        self.assertIn("view-materials", index_html)
        self.assertNotIn("askHermesAboutMaterial", app_js)
        self.assertNotIn("Open Source", app_js)
        self.assertNotIn("/api/material-sources", app_js)
        self.assertNotIn("Reference Files", index_html)
        self.assertNotIn("referenceMaterialCount", index_html)

    def test_frontend_preserves_ui_state_across_state_refreshes(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('UI_STATE_KEY = "hermes-jobapps.uiState.v1"', app_js)
        self.assertIn("recordDisclosureState", app_js)
        self.assertIn("pointerdown", app_js)
        self.assertIn("captureViewScrollState", app_js)
        self.assertIn("restoreCurrentViewScrollState", app_js)
        self.assertIn('shell.dataset.disclosureKey = `materials:${group.job_id', app_js)
        self.assertIn('details.dataset.disclosureKey = `network:${group.key', app_js)
        self.assertIn('data-disclosure-key="job:${esc(job.id)}:tailoring-requirements"', app_js)

    def test_frontend_exposes_shortlist_approval_bulk_prepare_and_job_detail_outreach(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Lead Board", index_html)
        self.assertIn("Prepare Interesting", index_html)
        self.assertNotIn("discoveryPresets", app_js)
        self.assertNotIn("discovery-presets", index_html)
        self.assertIn("approved", app_js)
        self.assertIn("approveDiscoveryCandidate", app_js)
        self.assertIn("prepareApprovedDiscoveryCandidates", app_js)
        self.assertIn("/api/discovery/candidates/prepare-approved", app_js)
        self.assertIn("jobDetailPanel", index_html)
        self.assertIn("renderJobDetail", app_js)
        self.assertIn("Outreach", app_js)
        self.assertIn("Follow-ups", app_js)
        self.assertIn("next_action", app_js)

    def test_frontend_exposes_sessions_as_left_nav_view(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="sessions"', index_html)
        self.assertIn("sessionsList", index_html)
        self.assertIn("sessionSummary", app_js)
        self.assertNotIn("agentSessions", index_html)

    def test_server_serves_generated_material_files_from_materials_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            state.config["materials_path"] = str(Path(tmpdir) / "materials")
            record = self._create_job(state.repo)
            job_id = record["job"]["id"]
            material_dir = Path(state.config["materials_path"]) / job_id
            material_dir.mkdir(parents=True)
            typ_path = material_dir / "resume_tailoring.typ"
            typ_path.write_text("= Resume tailoring\n", encoding="utf-8")
            material = state.repo.save_material(
                job_id,
                "resume_tailoring",
                "= Resume tailoring\n",
                format="typ",
                file_path=str(typ_path),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/materials/{material['id']}/file"
                with urllib.request.urlopen(url, timeout=5) as response:
                    body = response.read().decode("utf-8")
                    disposition = response.headers.get("Content-Disposition", "")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertIn("= Resume tailoring", body)
            self.assertIn("resume_tailoring.typ", disposition)

    def test_server_serves_sibling_pdf_when_metadata_pdf_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            state.config["materials_path"] = str(Path(tmpdir) / "materials")
            record = self._create_job(state.repo)
            job_id = record["job"]["id"]
            material_dir = Path(state.config["materials_path"]) / job_id
            material_dir.mkdir(parents=True)
            tex_path = material_dir / "resume.tex"
            pdf_path = material_dir / "resume.pdf"
            tex_path.write_text("\\documentclass{article}\n", encoding="utf-8")
            pdf_path.write_bytes(b"%PDF-1.4\n")
            material = state.repo.save_material(
                job_id,
                "resume",
                "\\documentclass{article}\n",
                format="tex",
                file_path=str(tex_path),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/materials/{material['id']}/file?target=pdf"
                with urllib.request.urlopen(url, timeout=5) as response:
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "")
                    disposition = response.headers.get("Content-Disposition", "")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertIn(b"%PDF-1.4", body)
            self.assertEqual(content_type, "application/pdf")
            self.assertIn("resume.pdf", disposition)

    def test_server_serves_pdf_material_file_as_pdf_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            state.config["materials_path"] = str(Path(tmpdir) / "materials")
            record = self._create_job(state.repo)
            job_id = record["job"]["id"]
            material_dir = Path(state.config["materials_path"]) / job_id
            material_dir.mkdir(parents=True)
            pdf_path = material_dir / "resume.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            material = state.repo.save_material(
                job_id,
                "resume",
                {"pdf_path": str(pdf_path), "source_format": "typst"},
                format="pdf",
                file_path=str(pdf_path),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/materials/{material['id']}/file?target=pdf"
                with urllib.request.urlopen(url, timeout=5) as response:
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "")
                    disposition = response.headers.get("Content-Disposition", "")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertIn(b"%PDF-1.4", body)
            self.assertEqual(content_type, "application/pdf")
            self.assertIn("resume.pdf", disposition)

    def test_server_serves_material_record_for_in_app_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AppState(None, str(Path(tmpdir) / "state.sqlite3"))
            state.config["materials_path"] = str(Path(tmpdir) / "materials")
            record = self._create_job(state.repo)
            material = state.repo.save_material(
                record["job"]["id"],
                "research_json",
                {"angle": "backend systems", "checks": ["sponsorship", "location"]},
                format="json",
                metadata={"display_name": "research.json"},
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/materials/{material['id']}"
                with urllib.request.urlopen(url, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(payload["id"], material["id"])
            self.assertEqual(payload["format"], "json")
            self.assertIn("backend systems", payload["content"])

    def test_frontend_exposes_tailoring_lifecycle_state(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("tailoring_requirements", app_js)
        self.assertIn("criteria", app_js)
        self.assertIn("criteria", index_html)
        self.assertIn("dashboard", app_js)
        self.assertIn("pipeNew", app_js)

    def test_frontend_exposes_job_state_management_controls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("/api/jobs/${encodeURIComponent(jobId)}/status", app_js)
        self.assertIn("PIPELINE_PREVIEW_LIMIT = 10", app_js)
        self.assertIn("pipelineExpanded", app_js)
        self.assertIn("setupPipelineDropZone", app_js)
        self.assertIn("dashboardCurrentJob", app_js)
        self.assertIn("draggable = true", app_js)
        self.assertIn("data-job-status", app_js)
        self.assertIn("data-state-job", app_js)
        self.assertIn("pipelineMessage", index_html)
        self.assertIn("pipeline-more", styles)
        self.assertIn("drag-over", styles)

    def test_frontend_exposes_actions_control_center(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('data-view="actions"', index_html)
        self.assertIn("actionsBoard", index_html)
        self.assertIn("ACTION_ACTIVE_LANES", app_js)
        self.assertIn("buildActionRows", app_js)
        self.assertIn("actionDispositionButtons", app_js)
        self.assertIn("/api/progress-items/${encodeURIComponent(id)}/disposition", app_js)
        self.assertIn("/api/followups/${encodeURIComponent(id)}/disposition", app_js)
        self.assertIn("/api/approvals/${encodeURIComponent(id)}/disposition", app_js)
        self.assertIn("data-action-op", app_js)
        self.assertIn("data-action-prompt", app_js)
        self.assertIn(".actions-board", styles)
        self.assertIn(".action-dispositions", styles)

    def test_save_material_rejects_paths_outside_materials_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)

            with self.assertRaises(ValueError):
                toolbox.execute(
                    "jobapps_save_material",
                    {
                        "job_id": record["job"]["id"],
                        "kind": "resume",
                        "format": "tex",
                        "content": "\\documentclass{article}",
                        "file_path": str(Path(tmpdir) / "outside.tex"),
                    },
                )

    def test_generated_material_write_rejects_symlink_job_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            materials_root = Path(tmpdir) / "materials"
            outside = Path(tmpdir) / "outside"
            materials_root.mkdir()
            outside.mkdir()
            config["materials_path"] = str(materials_root)
            toolbox = AgentToolbox(repo, config)
            record = self._create_job(repo)
            job_id = record["job"]["id"]
            (materials_root / job_id).symlink_to(outside, target_is_directory=True)

            with self.assertRaises(ValueError):
                toolbox.execute(
                    "jobapps_save_material",
                    {
                        "job_id": job_id,
                        "kind": "resume",
                        "format": "tex",
                        "content": "AUTO_ESCAPE_SENTINEL",
                    },
                )
            self.assertFalse((outside / "resume.tex").exists())

    def test_frontend_whitelists_dynamic_css_classes(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("classToken", app_js)
        self.assertNotIn("match-confidence ${m.confidence}", app_js)
        self.assertNotIn("risk-item ${r.level", app_js)
        self.assertNotIn("body.innerHTML = msg.content", app_js)
        self.assertNotIn("onclick=\"compileMaterial", app_js)
        self.assertNotIn("' · ' + card.score", app_js)
        self.assertIn("String(s ??", app_js)


class WorkflowTests(unittest.TestCase):
    def test_dashboard_returns_harness_ready_flattened_job_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            record = workflow.prepare_opportunity(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "location": "Remote",
                    "description": """
                    Build LLM agents with retrieval, tool calling, evaluation traces, and PostgreSQL.
                    Visa sponsorship is available. This is an entry level role.
                    The team needs someone who can design production APIs and evaluation workflows.
                    """,
                }
            )
            repo.record_event(record["job"]["id"], "reviewed_state", {"note": "Dashboard shape check."})

            state = repo.dashboard()
            job = state["jobs"][0]

            self.assertEqual(state["job_count"], 1)
            self.assertEqual(state["approval_count"], 0)
            self.assertEqual(job["title"], "AI Engineer")
            self.assertEqual(job["company"], "ExampleCo")
            self.assertIsNone(job.get("score"))
            self.assertTrue(job["risks"])
            self.assertIn("severity", job["risks"][0])
            self.assertIn("label", job["risks"][0])
            self.assertIn("path", job["materials_workbench"]["items"][0])
            self.assertIn("summary", job["events"][0])
            self.assertIn("resume_tex", job)
            self.assertIn("cover_letter_tex", job)
            self.assertIn("prompt", job)
            self.assertEqual(job["progress"], [])
            self.assertTrue(job["risks"])

    def test_prepare_opportunity_creates_typst_resume_prompt_and_management_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            record = workflow.prepare_opportunity(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": """
                    Build LLM agents with retrieval, tool calling, evaluation traces, and PostgreSQL.
                    Visa sponsorship is available. This is an entry level role.
                    The team needs someone who can design production APIs and evaluation workflows.
                    """,
                }
            )

            formats = {item["kind"]: item["format"] for item in record["materials"]}
            self.assertEqual(formats["resume_tailoring"], "typ")
            self.assertEqual(formats["cover_letter"], "tex")
            self.assertTrue(record["prompts"])
            self.assertEqual(record["progress_items"], [])
            self.assertEqual(record["followups"], [])
            self.assertEqual(record["approvals"], [])


class FakeHermesClient:
    def __init__(self) -> None:
        self.started = False
        self.last_stream_kwargs = {}

    def start_run(self, prompt: str, **kwargs) -> dict:
        self.started = True
        return {"id": "hrun_test_1", "status": "queued", "session_id": "sess_test"}

    def get_run(self, run_id: str) -> dict:
        return {
            "id": run_id,
            "status": "completed",
            "output_text": """
            Hermes completed the opportunity pass.

            JOBAPPS_RECORDS
            {
              "research_notes": [
                {
                  "subject": "ExampleCo sponsorship signal",
                  "summary": "The role text says sponsorship is available, but confirm before applying.",
                  "confidence": 0.76
                }
              ],
              "materials": [
                {
                  "kind": "resume_tailoring",
                  "format": "tex",
                  "content": "\\\\documentclass{article}\\n\\\\begin{document}Hermes revision\\\\end{document}",
                  "rationale": "Hermes refined the requirement-to-proof angle."
                }
              ],
              "application_changes": [
                {
                  "change_type": "resume_tailoring",
                  "target": "resume_tailoring.typ",
                  "after_text": "Emphasize agent retrieval and evaluation traces.",
                  "reason": "The job asks for retrieval and evaluation.",
                  "requirement": "Experience building retrieval systems and evaluation traces."
                }
              ],
              "tailoring_requirements": [
                {
                  "job_id": "wrong_job_should_not_win",
                  "requirement": "Build LLM agents with memory and evaluation traces.",
                  "category": "agent_systems",
                  "priority": 0.95,
                  "status": "targeted"
                }
              ],
              "portrayal_decisions": [
                {
                  "job_id": "wrong_job_should_not_win",
                  "target": "resume_tailoring.typ",
                  "after_text": "Frame this as an agent harness with state, tools, retrieval, and verification.",
                  "rationale": "The JD asks for memory and evaluation traces.",
                  "decision_type": "jd_grounded_portrayal"
                }
              ],
              "learning_patterns": [
                {
                  "pattern_type": "portrayal_preference",
                  "trigger": "agent roles ask for memory and evaluation",
                  "preference": "Use agent harness language instead of generic chatbot language.",
                  "source": "user_correction"
                }
              ],
              "progress_items": [
                {
                  "title": "Review Hermes resume revision",
                  "kind": "material_review",
                  "status": "open"
                }
              ],
              "followups": [
                {
                  "due_date": "2026-05-20",
                  "reason": "Check whether the application was submitted.",
                  "status": "open"
                }
              ],
              "approvals": [
                {
                  "action": "review_hermes_materials",
                  "payload": {
                    "materials": ["resume_tailoring.typ"],
                    "reason": "Hermes revised the local draft."
                  }
                }
              ]
            }
            """,
        }

    def get_run_events(self, run_id: str) -> dict:
        raise AssertionError("refresh should not block on the Hermes SSE events endpoint")

    def stream_chat(self, message: str, **kwargs):
        self.last_stream_kwargs = kwargs
        yield {
            "event": "response.created",
            "data": {"response": {"id": "resp_test", "status": "in_progress"}},
        }
        yield {"event": "response.output_text.delta", "data": {"delta": "OK"}}
        yield {
            "event": "response.output_item.added",
            "data": {
                "item": {
                    "type": "function_call",
                    "name": "jobapps_read_context",
                    "status": "in_progress",
                    "call_id": "call_test",
                    "arguments": "{}",
                }
            },
        }
        yield {
            "event": "response.completed",
            "data": {
                "response": {
                    "id": "resp_test",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "OK"}],
                        }
                    ],
                    "usage": {"input_tokens": 11, "output_tokens": 2, "total_tokens": 13},
                }
            },
        }


class ParallelBlockingHermesClient(FakeHermesClient):
    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()
        self.two_active = threading.Event()
        self.all_done = threading.Event()
        self.lock = threading.Lock()
        self.calls: list[dict] = []
        self.active_count = 0
        self.max_active_count = 0

    def start_run(self, prompt: str, **kwargs) -> dict:
        with self.lock:
            call_number = len(self.calls) + 1
            self.calls.append(kwargs)
            self.active_count += 1
            self.max_active_count = max(self.max_active_count, self.active_count)
            if self.active_count >= 2:
                self.two_active.set()
        self.release.wait(timeout=0.4)
        with self.lock:
            self.active_count -= 1
            if self.active_count == 0:
                self.all_done.set()
        return {
            "id": f"hrun_parallel_{call_number}",
            "status": "running",
            "session_id": kwargs.get("session_id", f"sess_parallel_{call_number}"),
        }

    def get_run_events(self, run_id: str) -> dict:
        raise AssertionError("parallel launch should not poll events")

    def stream_chat(self, message: str, **kwargs):
        yield from ()


def wait_for_hermes_run_started(repo: JobRepository, job_id: str, timeout: float = 1.0) -> dict:
    deadline = time.monotonic() + timeout
    last_run: dict = {}
    while time.monotonic() < deadline:
        run = repo.get_active_hermes_run_for_job(job_id)
        if run:
            last_run = run
            if run.get("hermes_run_id"):
                return run
        time.sleep(0.01)
    raise AssertionError(f"Hermes run did not start in time: {last_run}")


def wait_for_started_run_count(repo: JobRepository, count: int, timeout: float = 1.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    last_runs: list[dict] = []
    while time.monotonic() < deadline:
        last_runs = [
            run for run in repo.list_agent_runs(limit=100)
            if run.get("kind") == "hermes_run" and run.get("hermes_run_id")
        ]
        if len(last_runs) >= count:
            return last_runs
        time.sleep(0.01)
    raise AssertionError(f"Expected {count} started Hermes runs, saw {len(last_runs)}: {last_runs}")


def wait_for_jobapps_launch_threads(timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    for thread in list(threading.enumerate()):
        if not thread.name.startswith("jobapps-hermes-run-"):
            continue
        remaining = max(0.01, deadline - time.monotonic())
        thread.join(timeout=remaining)


class FakeSlashClient:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, command: str) -> str:
        self.commands.append(command)
        return "JobApps command output"

    def model_options(self) -> dict:
        return {
            "model": "gpt-test",
            "provider": "test",
            "providers": [
                {
                    "slug": "test",
                    "name": "Test Provider",
                    "authenticated": True,
                    "models": ["gpt-test"],
                    "total_models": 1,
                    "is_current": True,
                }
            ],
        }


class ChatOrchestratorTests(unittest.TestCase):
    def test_parse_job_from_message_extracts_basic_fields(self) -> None:
        job = parse_job_from_message(
            """
            AI Engineer at ExampleCo
            Location: Remote / New York
            https://example.com/jobs/ai-engineer

            Build LLM agents with retrieval, tool calling, evaluation traces, and PostgreSQL-backed APIs.
            Visa sponsorship is available. This is an entry level role.
            The team needs someone who can design production APIs and evaluation workflows.
            """
        )

        self.assertEqual(job["title"], "AI Engineer")
        self.assertEqual(job["company"], "ExampleCo")
        self.assertEqual(job["location"], "Remote / New York")
        self.assertEqual(job["url"], "https://example.com/jobs/ai-engineer")
        self.assertIn("Build LLM agents", job["description"])

    def test_chat_prepare_from_pasted_description_creates_structured_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            orchestrator = ChatOrchestrator(repo=repo, toolbox=toolbox, workflow=workflow)

            result = orchestrator.handle(
                """
                AI Engineer at ExampleCo
                Location: Remote
                Build LLM agents with retrieval, tool calling, evaluation traces, and PostgreSQL-backed APIs.
                Visa sponsorship is available. This is an entry level role.
                The team needs someone who can design production APIs and evaluation workflows.
                """
            )

            self.assertEqual(result["action"], "prepared_opportunity")
            self.assertIn("job_id", result)
            self.assertIn("output_text", result)
            self.assertEqual(repo.dashboard()["jobs"][0]["title"], "AI Engineer")

    def test_chat_routes_slash_commands_to_native_hermes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            slash = FakeSlashClient()
            orchestrator = ChatOrchestrator(repo=repo, toolbox=toolbox, workflow=workflow, slash=slash)

            result = orchestrator.handle("/jobapps")

            self.assertEqual(result["action"], "hermes_command")
            self.assertEqual(result["output_text"], "JobApps command output")
            self.assertEqual(slash.commands, ["/jobapps"])

    def test_chat_stream_maps_hermes_response_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            orchestrator = ChatOrchestrator(
                repo=repo,
                toolbox=toolbox,
                workflow=workflow,
                hermes=FakeHermesClient(),
            )

            events = list(orchestrator.stream("Reply with OK"))

            self.assertTrue(any(event.get("type") == "message.delta" and event.get("text") == "OK" for event in events))
            self.assertTrue(any(event.get("type") == "tool" and event.get("name") == "jobapps_read_context" for event in events))
            self.assertTrue(any(event.get("type") == "usage" and event.get("usage", {}).get("total") == 13 for event in events))
            self.assertEqual(events[-1]["type"], "done")
            self.assertEqual(events[-1]["result"]["output_text"], "OK")

    def test_chat_stream_forwards_resumed_conversation_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            hermes = FakeHermesClient()
            orchestrator = ChatOrchestrator(
                repo=repo,
                toolbox=toolbox,
                workflow=workflow,
                hermes=hermes,
            )
            history = [{"role": "user", "content": "Earlier turn"}]

            list(orchestrator.stream("Continue", conversation="jobapps-old", conversation_history=history))

            self.assertEqual(hermes.last_stream_kwargs["conversation"], "jobapps-old")
            self.assertEqual(hermes.last_stream_kwargs["conversation_history"], history)

    def test_model_command_uses_native_model_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            config = load_config()
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            slash = FakeSlashClient()
            orchestrator = ChatOrchestrator(repo=repo, toolbox=toolbox, workflow=workflow, slash=slash)

            result = orchestrator.handle("/model")
            stream_events = list(orchestrator.stream("/model"))

            self.assertEqual(result["action"], "hermes_command_menu")
            self.assertIn("Current model: gpt-test", result["output_text"])
            self.assertTrue(any(event.get("type") == "menu" for event in stream_events))

    def test_chat_instructions_include_live_jobapps_context_and_tools(self) -> None:
        instructions = build_chat_instructions(
            {
                "jobs": [{"id": "abc123def456", "title": "AI Engineer", "company": "ExampleCo", "status": "saved", "decision": "apply", "score": 4.2}],
                "context_counts": {"profile_facts": 2, "proof_points": 5},
            },
            [{"name": "jobapps_read_context", "description": "Read app context."}],
        )

        self.assertIn("AI Engineer", instructions)
        self.assertIn("ExampleCo", instructions)
        self.assertIn("jobapps_read_context", instructions)


class HermesRunManagerTests(unittest.TestCase):
    def test_extract_text_accepts_hermes_output_string(self) -> None:
        self.assertEqual(_extract_text({"output": "Hermes API smoke OK"}), "Hermes API smoke OK")

    def test_starts_multiple_job_runs_without_serializing_hermes_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            first = workflow.prepare_opportunity(
                {
                    "title": "Data Engineer",
                    "company": "FirstCo",
                    "description": "Build data pipelines with SQL and Python. Visa sponsorship is available. Entry level role.",
                }
            )["job"]["id"]
            second = workflow.prepare_opportunity(
                {
                    "title": "Software Engineer",
                    "company": "SecondCo",
                    "description": "Build backend APIs with Python and PostgreSQL. Visa sponsorship is available. Entry level role.",
                }
            )["job"]["id"]
            hermes = ParallelBlockingHermesClient()
            manager = HermesRunManager(repo, toolbox, hermes)

            started_at = time.monotonic()
            try:
                first_record = manager.start_for_job(first)
                second_record = manager.start_for_job(second)
                elapsed = time.monotonic() - started_at

                self.assertLess(elapsed, 0.25, "JobApps should queue Hermes launches without waiting for Hermes acceptance.")
                self.assertTrue(hermes.two_active.wait(timeout=0.5), "Two Hermes start_run calls should be active at the same time.")
                self.assertGreaterEqual(hermes.max_active_count, 2)
                self.assertEqual(first_record["active_run"]["status"], "queued")
                self.assertEqual(second_record["active_run"]["status"], "queued")
            finally:
                hermes.release.set()
                hermes.all_done.wait(timeout=1)
                wait_for_jobapps_launch_threads()
                wait_for_started_run_count(repo, 2)

    def test_start_for_job_reuses_active_same_job_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            job_id = workflow.prepare_opportunity(
                {
                    "title": "Data Engineer",
                    "company": "FirstCo",
                    "description": "Build data pipelines with SQL and Python. Visa sponsorship is available. Entry level role.",
                }
            )["job"]["id"]
            hermes = ParallelBlockingHermesClient()
            manager = HermesRunManager(repo, toolbox, hermes)

            try:
                first_record = manager.start_for_job(job_id)
                second_record = manager.start_for_job(job_id)

                self.assertEqual(first_record["active_run"]["id"], second_record["active_run"]["id"])
                self.assertTrue(second_record["active_run"]["existing"])
                hermes_runs = [run for run in repo.list_agent_runs(job_id=job_id) if run["kind"] == "hermes_run"]
                self.assertEqual(len(hermes_runs), 1)
            finally:
                hermes.release.set()
                hermes.all_done.wait(timeout=1)
                wait_for_jobapps_launch_threads()
                wait_for_started_run_count(repo, 1)

    def test_start_for_job_dedupes_same_job_across_manager_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            job_id = workflow.prepare_opportunity(
                {
                    "title": "Data Engineer",
                    "company": "RaceCo",
                    "description": "Build data pipelines with SQL and Python. Visa sponsorship is available. Entry level role.",
                }
            )["job"]["id"]
            hermes = ParallelBlockingHermesClient()
            managers = [HermesRunManager(repo, toolbox, hermes), HermesRunManager(repo, toolbox, hermes)]
            records: list[dict] = []
            errors: list[BaseException] = []

            def start(manager: HermesRunManager) -> None:
                try:
                    records.append(manager.start_for_job(job_id))
                except BaseException as exc:  # pragma: no cover - surfaced by assertions below.
                    errors.append(exc)

            threads = [threading.Thread(target=start, args=(manager,)) for manager in managers]
            try:
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=1)

                self.assertFalse(errors)
                self.assertEqual(len(records), 2)
                hermes_runs = [run for run in repo.list_agent_runs(job_id=job_id) if run["kind"] == "hermes_run"]
                self.assertEqual(len(hermes_runs), 1)
                self.assertEqual({record["active_run"]["id"] for record in records}, {hermes_runs[0]["id"]})
            finally:
                hermes.release.set()
                hermes.all_done.wait(timeout=1)
                wait_for_jobapps_launch_threads()
                wait_for_started_run_count(repo, 1)

    def test_hermes_run_refresh_ingests_structured_records_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = JobRepository(Path(tmpdir) / "state.sqlite3")
            seed_context(repo)
            config = load_config()
            config["materials_path"] = str(Path(tmpdir) / "materials")
            toolbox = AgentToolbox(repo, config)
            workflow = JobAppsWorkflow(repo, toolbox)
            record = workflow.prepare_opportunity(
                {
                    "title": "AI Engineer",
                    "company": "ExampleCo",
                    "description": """
                    Build LLM agents with retrieval, tool calling, evaluation traces, and PostgreSQL.
                    Visa sponsorship is available. This is an entry level role.
                    The team needs someone who can design production APIs and evaluation workflows.
                    """,
                }
            )
            job_id = record["job"]["id"]
            manager = HermesRunManager(repo, toolbox, FakeHermesClient())

            started = manager.start_for_job(job_id)
            self.assertEqual(started["job"]["status"], "hermes_queued")
            started_run = wait_for_hermes_run_started(repo, job_id)
            self.assertEqual(started_run["status"], "running")
            wait_for_jobapps_launch_threads()

            refreshed = manager.refresh_for_job(job_id)
            self.assertEqual(refreshed["job"]["status"], "hermes_completed")
            self.assertTrue(refreshed["research_notes"])
            self.assertTrue([item for item in refreshed["materials"] if item["kind"] == "hermes_run_output"])
            self.assertTrue([item for item in refreshed["application_changes"] if item["reason"]])
            self.assertTrue(refreshed["tailoring_requirements"])
            self.assertTrue(refreshed["portrayal_decisions"])
            self.assertTrue(repo.list_learning_patterns())
            self.assertEqual([item for item in refreshed["approvals"] if item["action"].startswith("review")], [])

            refreshed_again = manager.refresh_for_job(job_id)
            output_materials = [
                item for item in refreshed_again["materials"]
                if item["kind"] == "hermes_run_output"
            ]
            self.assertEqual(len(output_materials), 1)


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = JobRepository(Path(self.tmpdir.name) / "state.sqlite3")
        self.config = load_config()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_detects_supported_ats_urls(self) -> None:
        self.assertEqual(
            detect_ats("https://boards.greenhouse.io/example/jobs/123")["provider"],
            "greenhouse",
        )
        self.assertEqual(
            detect_ats("https://jobs.lever.co/example/abc")["provider"],
            "lever",
        )
        self.assertEqual(
            detect_ats("https://jobs.ashbyhq.com/example/role-id")["provider"],
            "ashby",
        )

    def test_greenhouse_hydration_records_questions_and_ready_candidate(self) -> None:
        def fetch(url: str) -> dict:
            self.assertIn("questions=true", url)
            self.assertIn("pay_transparency=true", url)
            return {
                "title": "Applied AI Engineer",
                "location": {"name": "New York, NY"},
                "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
                "updated_at": "2026-05-16T12:00:00Z",
                "content": """
                <p>We build LLM agents with retrieval, tool calling, evaluation traces, and APIs.</p>
                <p>Visa sponsorship is available. This is an entry level role in New York.</p>
                <p>Requirements: Experience building production APIs and evaluation workflows.</p>
                """,
                "questions": [
                    {
                        "label": "Will you now or in the future require sponsorship?",
                        "required": True,
                        "fields": [{"type": "multi_value_single_select"}],
                    }
                ],
                "pay_input_ranges": [{"label": "Base salary", "min_value": 100000, "max_value": 140000}],
            }

        service = DiscoveryService(self.repo, self.config, fetch_json=fetch)
        candidate = service.hydrate_url("https://boards.greenhouse.io/example/jobs/123")

        self.assertEqual(candidate["source_provider"], "greenhouse")
        self.assertEqual(candidate["status"], "ready")
        self.assertEqual(candidate["blocker_status"], "clear")
        self.assertIn("sponsorship", candidate["application_form_summary"].lower())
        self.assertEqual(self.repo.discovery_counts()["total"], 1)

    def test_lever_hydration_does_not_claim_custom_questions(self) -> None:
        def fetch(url: str) -> dict:
            self.assertIn("api.lever.co", url)
            return {
                "text": "LLM Platform Engineer",
                "categories": {"location": "Remote", "commitment": "Full-time", "team": "Engineering"},
                "workplaceType": "remote",
                "descriptionPlain": "Build LLM platform APIs, retrieval services, and evaluation workflows for agents.",
                "additionalPlain": "Requirements: Experience with Python, PostgreSQL, and production backend systems.",
                "lists": [{"text": "Nice to have", "content": "<li>Tool-use systems</li>"}],
                "salaryDescription": "$120K - $160K",
                "urls": {
                    "show": "https://jobs.lever.co/example/abc",
                    "apply": "https://jobs.lever.co/example/abc/apply",
                },
            }

        service = DiscoveryService(self.repo, self.config, fetch_json=fetch)
        candidate = service.hydrate_url("https://jobs.lever.co/example/abc")

        self.assertEqual(candidate["source_provider"], "lever")
        self.assertEqual(candidate["status"], "needs_review")
        self.assertIn("do not expose custom", candidate["application_form_summary"])
        self.assertIn("$120K", candidate["compensation"])

    def test_ashby_hydration_can_block_no_sponsorship_roles(self) -> None:
        def fetch(url: str) -> dict:
            self.assertIn("includeCompensation=true", url)
            return {
                "jobs": [
                    {
                        "title": "Senior AI Engineer",
                        "location": "San Francisco",
                        "isRemote": False,
                        "workplaceType": "OnSite",
                        "employmentType": "FullTime",
                        "publishedAt": "2026-05-16T13:00:00Z",
                        "descriptionPlain": """
                        Build agentic AI systems, RAG workflows, and backend APIs.
                        Candidates must be authorized to work without sponsorship.
                        Requirements: 7 years experience building production ML systems.
                        """,
                        "jobUrl": "https://jobs.ashbyhq.com/example/senior-ai-engineer",
                        "applyUrl": "https://jobs.ashbyhq.com/example/senior-ai-engineer/application",
                        "compensation": {"compensationTierSummary": "$170K - $220K"},
                    }
                ]
            }

        service = DiscoveryService(self.repo, self.config, fetch_json=fetch)
        candidate = service.hydrate_url("https://jobs.ashbyhq.com/example/senior-ai-engineer")

        self.assertEqual(candidate["source_provider"], "ashby")
        self.assertEqual(candidate["status"], "blocked")
        self.assertEqual(candidate["blocker_status"], "hard_blocker")
        self.assertIn("sponsorship", {item["area"] for item in candidate["blocker_reasons"]})

    def test_prepare_candidate_requires_user_shortlist_approval(self) -> None:
        seed_context(self.repo)
        self.config["materials_path"] = str(Path(self.tmpdir.name) / "materials")
        candidate = self.repo.upsert_discovery_candidate(
            {
                "dedupe_key": "greenhouse:approval:123",
                "source_type": "ats_api",
                "source_provider": "greenhouse",
                "status": "ready",
                "title": "Applied AI Engineer",
                "company": "Example",
                "location": "New York, NY",
                "canonical_url": "https://boards.greenhouse.io/example/jobs/123",
                "description": "Build LLM agents with retrieval, tool calling, evaluation traces, and APIs. Visa sponsorship is available. This is entry level.",
                "blocker_status": "clear",
                "source_confidence": 0.95,
            }
        )
        service = DiscoveryService(self.repo, self.config)
        workflow = JobAppsWorkflow(self.repo, AgentToolbox(self.repo, self.config))

        with self.assertRaisesRegex(ValueError, "approve"):
            service.prepare_candidate(candidate["id"], workflow.prepare_opportunity)

        approved = self.repo.update_discovery_candidate(candidate["id"], status="approved", note="User approved from shortlist.")
        self.assertEqual(approved["status"], "approved")

        promoted = service.prepare_candidate(candidate["id"], workflow.prepare_opportunity)

        self.assertFalse(promoted["already_prepared"])
        self.assertEqual(promoted["candidate"]["status"], "prepared")
        self.assertTrue(promoted["candidate"]["job_id"])

    def test_prepare_approved_candidates_batches_only_user_approved_shortlist(self) -> None:
        self.config["materials_path"] = str(Path(self.tmpdir.name) / "materials")
        approved = self.repo.upsert_discovery_candidate(
            {
                "dedupe_key": "manual:approved",
                "source_type": "manual",
                "source_provider": "manual",
                "status": "approved",
                "title": "Data Engineer",
                "company": "ApprovedCo",
                "location": "New York, NY",
                "description": "Build SQL data pipelines. Visa sponsorship is available. Entry level role.",
                "blocker_status": "clear",
            }
        )
        self.repo.upsert_discovery_candidate(
            {
                "dedupe_key": "manual:ready",
                "source_type": "manual",
                "source_provider": "manual",
                "status": "ready",
                "title": "AI Engineer",
                "company": "NeedsApprovalCo",
                "description": "Build LLM agents. Visa sponsorship is available. Entry level role.",
                "blocker_status": "clear",
            }
        )
        service = DiscoveryService(self.repo, self.config)

        result = service.prepare_approved_candidates(
            lambda job: self.repo.create_job(
                job,
                {
                    "decision": "apply",
                    "role_family": "data_engineering",
                    "facts": {"title": job["title"], "company": job["company"]},
                    "next_action": "Review materials.",
                },
            ),
            limit=5,
        )

        self.assertEqual([item["candidate"]["id"] for item in result["prepared"]], [approved["id"]])
        self.assertEqual(result["prepared_count"], 1)
        self.assertEqual(self.repo.discovery_counts().get("ready", 0), 1)
        self.assertEqual(self.repo.get_discovery_candidate(approved["id"])["status"], "prepared")

    def test_prepare_candidate_records_discovery_provenance_once(self) -> None:
        seed_context(self.repo)
        self.config["materials_path"] = str(Path(self.tmpdir.name) / "materials")
        candidate = self.repo.upsert_discovery_candidate(
            {
                "dedupe_key": "greenhouse:example:123",
                "source_type": "ats_api",
                "source_provider": "greenhouse",
                "status": "ready",
                "title": "Applied AI Engineer",
                "company": "Example",
                "location": "New York, NY",
                "canonical_url": "https://boards.greenhouse.io/example/jobs/123",
                "discovered_url": "https://boards.greenhouse.io/example/jobs/123",
                "apply_url": "https://boards.greenhouse.io/example/jobs/123",
                "posted_at": "2026-05-16T12:00:00Z",
                "remote_updated_at": "2026-05-16T13:00:00Z",
                "retrieved_at": "2026-05-16T14:00:00Z",
                "workplace_type": "hybrid",
                "employment_type": "full-time",
                "compensation": "$100K - $140K",
                "description": """
                Build LLM agents with retrieval, tool calling, evaluation traces, and APIs.
                Visa sponsorship is available. This is an entry level role in New York.
                Requirements: Experience building production APIs and evaluation workflows.
                """,
                "application_form_summary": "required: Will you now or in the future require sponsorship? (multi_value_single_select)",
                "blocker_status": "clear",
                "blocker_reasons": [{"area": "preflight", "severity": "clear", "evidence": "sponsorship signal clear"}],
                "source_confidence": 0.95,
            }
        )
        service = DiscoveryService(self.repo, self.config)
        workflow = JobAppsWorkflow(self.repo, AgentToolbox(self.repo, self.config))
        candidate = self.repo.update_discovery_candidate(candidate["id"], status="approved", note="User approved from shortlist.")

        promoted = service.prepare_candidate(candidate["id"], workflow.prepare_opportunity)
        job_id = promoted["job"]["job"]["id"]
        job_record = self.repo.get_job(job_id)
        discovery_notes = [item for item in job_record["research_notes"] if item["subject"] == "Discovery source"]
        discovery_signals = [item for item in job_record["application_signals"] if item["source"] == "discovery"]

        self.assertFalse(promoted["already_prepared"])
        self.assertEqual(promoted["candidate"]["status"], "prepared")
        self.assertEqual(promoted["candidate"]["job_id"], job_id)
        self.assertEqual(len(discovery_notes), 1)
        self.assertIn("greenhouse", discovery_notes[0]["summary"])
        self.assertIn("application_form", {item["signal_type"] for item in discovery_signals})
        self.assertIn("discovery_source", {item["signal_type"] for item in discovery_signals})
        self.assertIn("blocker_preflight", {item["signal_type"] for item in discovery_signals})

        promoted_again = service.prepare_candidate(candidate["id"], workflow.prepare_opportunity)
        job_record_again = self.repo.get_job(job_id)
        discovery_notes_again = [item for item in job_record_again["research_notes"] if item["subject"] == "Discovery source"]

        self.assertTrue(promoted_again["already_prepared"])
        self.assertEqual(promoted_again["job"]["job"]["id"], job_id)
        self.assertEqual(len(discovery_notes_again), 1)

    def test_disabled_discovery_blocks_mutating_entrypoints(self) -> None:
        config = load_config()
        config["discovery"] = {**config.get("discovery", {}), "enabled": False}
        service = DiscoveryService(self.repo, config)
        candidate = self.repo.upsert_discovery_candidate(
            {
                "dedupe_key": "manual:disabled",
                "source_type": "manual",
                "source_provider": "manual",
                "status": "needs_review",
                "title": "AI Engineer",
                "company": "Example",
                "description": "Build LLM agent systems. Visa sponsorship is available.",
            }
        )

        self.assertFalse(service.status()["enabled"])
        self.assertIn("removable_boundary", service.status()["policy"])
        with self.assertRaisesRegex(DiscoveryError, "disabled"):
            service.search_exa("AI Engineer", limit=1)
        with self.assertRaisesRegex(DiscoveryError, "disabled"):
            service.hydrate_url("https://jobs.lever.co/example/abc")
        with self.assertRaisesRegex(DiscoveryError, "disabled"):
            service.prepare_candidate(candidate["id"], lambda job: {"job": {"id": "unused"}})

    def test_discovery_provider_failures_are_clear(self) -> None:
        def post(url: str, payload: dict, headers: dict[str, str]) -> dict:
            raise RuntimeError("provider down")

        service = DiscoveryService(self.repo, self.config, post_json=post)
        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}):
            with self.assertRaisesRegex(DiscoveryError, "Exa job search failed"):
                service.search_exa("AI Engineer", limit=1)

    def test_ats_hydration_failures_are_clear(self) -> None:
        def fetch(url: str) -> dict:
            raise RuntimeError("timeout")

        service = DiscoveryService(self.repo, self.config, fetch_json=fetch)
        with self.assertRaisesRegex(DiscoveryError, "Lever hydration failed"):
            service.hydrate_url("https://jobs.lever.co/example/abc")

    def test_exa_search_requires_env_key(self) -> None:
        service = DiscoveryService(self.repo, self.config)
        with patch.dict("os.environ", {"EXA_API_KEY": ""}):
            self.assertFalse(service.status()["providers"]["exa"]["configured"])
            self.assertEqual(service.status()["query_presets"], [])
            self.assertIn("jobs.ashbyhq.com", service.status()["providers"]["exa"]["include_domains"])
            with self.assertRaises(DiscoveryError):
                service.search_exa("AI Engineer", limit=1)


class NetworkingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = JobRepository(Path(self.tmpdir.name) / "state.sqlite3")
        self.config = load_config()
        self.config["networking"] = {**self.config.get("networking", {}), "gog_path": "/bin/echo"}

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_people_search_caches_public_contacts(self) -> None:
        def post(url: str, payload: dict, headers: dict[str, str]) -> dict:
            self.assertIn("api.exa.ai/search", url)
            self.assertEqual(payload["category"], "people")
            self.assertEqual(headers["x-api-key"], "test-key")
            return {
                "requestId": "req_people",
                "results": [
                    {
                        "title": "Avery Patel - Engineering Manager - Example AI | LinkedIn",
                        "url": "https://www.linkedin.com/in/avery-patel",
                        "highlights": ["Leads agent platform hiring at Example AI."],
                    }
                ],
            }

        service = NetworkingService(self.repo, self.config, post_json=post)
        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}):
            result = service.search_people(company="Example AI", limit=1)

        self.assertEqual(result["count"], 1)
        contact = result["contacts"][0]
        self.assertEqual(contact["name"], "Avery Patel")
        self.assertEqual(contact["company"], "Example AI")
        self.assertEqual(contact["source_provider"], "exa")
        self.assertEqual(contact["email_status"], "missing")
        self.assertEqual(len(self.repo.list_contacts(company="Example AI")), 1)

    def test_people_search_websets_is_explicit_missing_email_fallback(self) -> None:
        calls = []

        def post(url: str, payload: dict, headers: dict[str, str]) -> dict:
            calls.append((url, payload))
            self.assertEqual(headers["x-api-key"], "test-key")
            if url.endswith("/search"):
                return {
                    "requestId": "req_people",
                    "results": [
                        {
                            "title": "Avery Patel - Engineering Manager - Example AI | LinkedIn",
                            "url": "https://www.linkedin.com/in/avery-patel",
                            "highlights": ["Leads agent platform hiring at Example AI."],
                        }
                    ],
                }
            self.assertTrue(url.endswith("/websets"))
            self.assertEqual(payload["search"]["entity"]["type"], "person")
            self.assertEqual(payload["enrichments"][0]["format"], "email")
            return {"id": "ws_123", "status": "running"}

        def get(url: str, headers: dict[str, str]) -> dict:
            self.assertEqual(headers["x-api-key"], "test-key")
            if url.endswith("/websets/ws_123"):
                return {"id": "ws_123", "status": "idle"}
            self.assertIn("/websets/ws_123/items", url)
            return {
                "data": [
                    {
                        "id": "item_123",
                        "properties": {
                            "type": "person",
                            "url": "https://www.linkedin.com/in/avery-patel",
                            "description": "Engineering manager involved in AI hiring.",
                            "person": {
                                "name": "Avery Patel",
                                "position": "Engineering Manager",
                                "company": {"name": "Example AI"},
                            },
                        },
                        "enrichments": [
                            {"status": "completed", "format": "email", "result": ["avery@example.ai"]}
                        ],
                    }
                ]
            }

        config = load_config()
        config["networking"] = {
            **config.get("networking", {}),
            "gog_path": "/bin/echo",
            "websets": {**config.get("networking", {}).get("websets", {}), "max_wait_seconds": 1, "poll_seconds": 1},
        }
        service = NetworkingService(self.repo, config, post_json=post, get_json=get)
        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}):
            result = service.search_people(company="Example AI", limit=1, use_websets_fallback=True)

        self.assertEqual(result["provider"], "exa_search+websets")
        self.assertEqual(result["fallback_reason"], "missing_verified_email")
        self.assertTrue(any(url.endswith("/search") for url, _ in calls))
        self.assertTrue(any(url.endswith("/websets") for url, _ in calls))
        self.assertEqual(result["contacts"][0]["email_status"], "found")
        cached = self.repo.list_contacts(company="Example AI")[0]
        self.assertEqual(cached["email"], "avery@example.ai")
        self.assertEqual(cached["email_status"], "found")

    def test_gmail_draft_uses_gog_draft_only_command(self) -> None:
        calls = []

        def runner(command: list[str], stdin: str, timeout: int) -> subprocess.CompletedProcess[str]:
            calls.append((command, stdin, timeout))
            return subprocess.CompletedProcess(command, 0, '{"draftId":"draft_123","message":{"id":"msg_123"}}', "")

        service = NetworkingService(self.repo, self.config, command_runner=runner)
        result = service.create_gmail_draft(
            subject="Quick note",
            body="Hi, this is a draft.",
            to_email="person@example.com",
        )

        command, stdin, timeout = calls[0]
        self.assertIn("--gmail-no-send", command)
        self.assertEqual(command[command.index("gmail") + 1:command.index("gmail") + 3], ["drafts", "create"])
        self.assertNotIn("send", command)
        self.assertEqual(stdin, "Hi, this is a draft.")
        self.assertEqual(timeout, 30)
        self.assertEqual(result["policy"], "draft_only_no_send")
        self.assertEqual(result["draft"]["id"], "draft_123")
        self.assertEqual(result["draft"]["draftId"], "draft_123")

    def test_gmail_draft_does_not_auto_fill_missing_contact_email(self) -> None:
        contact = self.repo.upsert_contact(
            "Avery Patel",
            company="Example AI",
            role="Engineering Manager",
            email_status="missing",
            source_url="https://www.linkedin.com/in/avery-patel",
            source_provider="exa",
        )
        calls = []

        def runner(command: list[str], stdin: str, timeout: int) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, '{"draftId":"draft_123"}', "")

        service = NetworkingService(self.repo, self.config, command_runner=runner)
        result = service.create_gmail_draft(subject="Quick note", body="Draft body.", contact_id=contact["id"])

        self.assertNotIn("--to", calls[0])
        self.assertEqual(result["to_email"], "")
        self.assertEqual(result["contact_email_status"], "missing")

    def test_networking_disabled_fails_loudly(self) -> None:
        config = load_config()
        config["networking"] = {**config.get("networking", {}), "enabled": False, "gog_path": "/bin/echo"}
        service = NetworkingService(self.repo, config)
        with self.assertRaisesRegex(NetworkingError, "disabled"):
            service.search_people(company="Example AI")
        with self.assertRaisesRegex(NetworkingError, "disabled"):
            service.create_gmail_draft(subject="Subject", body="Body")


if __name__ == "__main__":
    unittest.main()
