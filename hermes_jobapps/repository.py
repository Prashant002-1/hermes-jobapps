"""SQLite state store for JobApps.

The database is the application source of truth. Private seed files can import
into this schema, but runtime workflows should read and write structured rows.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


ACTION_CLOSED_STATUSES = ("done", "closed", "complete", "completed", "dismissed", "not_needed", "canceled", "cancelled")
ACTION_CLOSED_SQL = "('done','closed','complete','completed','dismissed','not_needed','canceled','cancelled')"
ACTIVE_HERMES_RUN_STATUSES = ("queued", "starting", "running", "requires_action", "in_progress")
ACTIVE_HERMES_RUN_SQL = "('queued','starting','running','requires_action','in_progress')"
MATERIAL_REVIEW_APPROVAL_ACTIONS = {"review_application_materials", "review_generated_materials"}
NON_ACTION_APPROVAL_ACTIONS = MATERIAL_REVIEW_APPROVAL_ACTIONS | {"review_outreach_draft"}
MATERIAL_REVIEW_PROGRESS_TITLE = "Review generated resume and cover letter"
PURPOSEFUL_ACTION_TERMS = ("send", "email", "message", "follow up", "follow-up", "follow_up", "contact")
REVIEW_PROGRESS_KINDS = {"material_review"}
REVIEW_PROGRESS_TERMS = ("review", "approve", "approval", "check")
REVIEW_PROGRESS_OBJECTS = ("material", "materials", "resume", "cover", "letter", "draft", "pdf")
JOB_STATE_BUCKETS = ("new", "applied", "skip")
JOB_APPLIED_STATUSES = {
    "applied",
    "waiting",
    "follow_up",
    "interview",
    "phone_screen",
    "offer",
    "closed",
    "rejected",
    "declined",
    "archived",
}
JOB_SKIP_STATUSES = {"skip", "skipped", "not_interested", "not_needed"}
MATERIAL_REVIEW_STATUSES = {"materials_ready_for_review"}
ACTION_RESOLVED_STATUSES = set(ACTION_CLOSED_STATUSES) | {"approved", "rejected", "superseded"}
TOOL_CALL_INLINE_LIMIT_BYTES = 1_000_000
TOOL_CALL_ARCHIVE_ROOT = Path("data/tool-call-archive")
STATE_REVISION_KEY = "state_revision"


class JobRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.on_change: Callable[[], None] | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            before_changes = conn.total_changes
            yield conn
            has_changes = conn.total_changes > before_changes
            if has_changes:
                self._touch_state_revision_conn(conn)
            conn.commit()
            if has_changes and self.on_change is not None:
                try:
                    self.on_change()
                except Exception:
                    pass
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _touch_state_revision_conn(conn: sqlite3.Connection) -> None:
        now = utc_now()
        conn.execute(
            """
            INSERT INTO app_state_meta (key, value, updated_at)
            VALUES (?, '1', ?)
            ON CONFLICT(key) DO UPDATE SET
                value = CAST(CAST(app_state_meta.value AS INTEGER) + 1 AS TEXT),
                updated_at = excluded.updated_at
            """,
            (STATE_REVISION_KEY, now),
        )

    def state_revision(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, updated_at FROM app_state_meta WHERE key = ?",
                (STATE_REVISION_KEY,),
            ).fetchone()
        if row is None:
            return {"revision": 0, "updated_at": ""}
        try:
            revision = int(row["value"])
        except (TypeError, ValueError):
            revision = 0
        return {"revision": revision, "updated_at": row["updated_at"] or ""}

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    url TEXT,
                    description TEXT NOT NULL,
                    user_notes TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    role_family TEXT,
                    decision TEXT,
                    score REAL,
                    next_action TEXT,
                    hermes_session_id TEXT,
                    hermes_run_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS brain_entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    privacy TEXT NOT NULL DEFAULT 'private',
                    source TEXT NOT NULL DEFAULT 'agent',
                    confidence REAL NOT NULL DEFAULT 0.8,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(entity_type, slug)
                );

                CREATE INDEX IF NOT EXISTS idx_brain_entities_type
                ON brain_entities(entity_type, updated_at);

                CREATE TABLE IF NOT EXISTS brain_events (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT,
                    job_id TEXT,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'agent',
                    evidence_text TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.8,
                    importance REAL NOT NULL DEFAULT 0.5,
                    occurred_at TEXT NOT NULL,
                    hermes_session_id TEXT,
                    hermes_run_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(entity_id) REFERENCES brain_entities(id) ON DELETE SET NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_brain_events_entity
                ON brain_events(entity_id, occurred_at);

                CREATE INDEX IF NOT EXISTS idx_brain_events_job
                ON brain_events(job_id, occurred_at);

                CREATE INDEX IF NOT EXISTS idx_brain_events_type
                ON brain_events(event_type, occurred_at);

                CREATE TABLE IF NOT EXISTS evaluations (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS profile_facts (
                    id TEXT PRIMARY KEY,
                    fact_key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'profile',
                    source TEXT NOT NULL DEFAULT 'manual',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proof_points (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    role_family TEXT NOT NULL DEFAULT 'other',
                    summary TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL DEFAULT 'manual',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    status TEXT NOT NULL DEFAULT 'active',
                    user_confirmed INTEGER NOT NULL DEFAULT 1,
                    narrative_version TEXT NOT NULL DEFAULT 'current',
                    allowed_uses TEXT NOT NULL DEFAULT '["resume", "cover_letter", "interview", "outreach"]',
                    risk_level TEXT NOT NULL DEFAULT 'safe',
                    valid_from TEXT,
                    valid_to TEXT,
                    superseded_by TEXT,
                    last_used_at TEXT,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS application_signals (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    value TEXT NOT NULL,
                    evidence_text TEXT,
                    source TEXT NOT NULL DEFAULT 'local_evaluation',
                    confidence REAL NOT NULL DEFAULT 0.7,
                    actionability TEXT NOT NULL DEFAULT 'medium',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_application_signals_job
                ON application_signals(job_id, signal_type, created_at);

                CREATE TABLE IF NOT EXISTS discovery_candidates (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL DEFAULT 'manual',
                    source_provider TEXT NOT NULL DEFAULT 'unknown',
                    status TEXT NOT NULL DEFAULT 'new',
                    title TEXT NOT NULL DEFAULT '',
                    company TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    canonical_url TEXT NOT NULL DEFAULT '',
                    discovered_url TEXT NOT NULL DEFAULT '',
                    apply_url TEXT NOT NULL DEFAULT '',
                    posted_at TEXT,
                    remote_updated_at TEXT,
                    retrieved_at TEXT NOT NULL,
                    workplace_type TEXT NOT NULL DEFAULT '',
                    employment_type TEXT NOT NULL DEFAULT '',
                    compensation TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    application_form_summary TEXT NOT NULL DEFAULT '',
                    blocker_status TEXT NOT NULL DEFAULT 'unknown',
                    blocker_reasons TEXT NOT NULL DEFAULT '[]',
                    source_confidence REAL NOT NULL DEFAULT 0.5,
                    discovery_query TEXT NOT NULL DEFAULT '',
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    job_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_discovery_candidates_status
                ON discovery_candidates(status, updated_at);

                CREATE INDEX IF NOT EXISTS idx_discovery_candidates_provider
                ON discovery_candidates(source_provider, updated_at);

                CREATE TABLE IF NOT EXISTS discovery_sightings (
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'manual',
                    source_provider TEXT NOT NULL DEFAULT 'unknown',
                    discovered_url TEXT NOT NULL DEFAULT '',
                    discovery_query TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    snippet TEXT NOT NULL DEFAULT '',
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    seen_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES discovery_candidates(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_discovery_sightings_candidate
                ON discovery_sightings(candidate_id, seen_at);

                CREATE TABLE IF NOT EXISTS retrieval_chunks (
                    id TEXT PRIMARY KEY,
                    source_table TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    chunk_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    role_family TEXT NOT NULL DEFAULT 'other',
                    status TEXT NOT NULL DEFAULT 'active',
                    user_confirmed INTEGER NOT NULL DEFAULT 1,
                    narrative_version TEXT NOT NULL DEFAULT 'current',
                    allowed_uses TEXT NOT NULL DEFAULT '[]',
                    risk_level TEXT NOT NULL DEFAULT 'safe',
                    valid_from TEXT,
                    valid_to TEXT,
                    superseded_by TEXT,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_retrieval_chunks_source
                ON retrieval_chunks(source_table, source_id, chunk_type);

                CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_eligibility
                ON retrieval_chunks(status, user_confirmed, role_family, narrative_version);

                CREATE TABLE IF NOT EXISTS retrieval_embeddings (
                    chunk_id TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    source_checksum TEXT NOT NULL,
                    embedded_at TEXT NOT NULL,
                    PRIMARY KEY(chunk_id, embedding_model),
                    FOREIGN KEY(chunk_id) REFERENCES retrieval_chunks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS materials (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    format TEXT NOT NULL DEFAULT 'text',
                    content TEXT NOT NULL,
                    file_path TEXT,
                    rationale TEXT,
                    source TEXT NOT NULL DEFAULT 'agent',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS material_revisions (
                    id TEXT PRIMARY KEY,
                    material_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    before_text TEXT NOT NULL,
                    after_text TEXT NOT NULL,
                    diff TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'agent',
                    requirement TEXT,
                    proof_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS app_state_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_material_revisions_material
                ON material_revisions(material_id, version);

                CREATE INDEX IF NOT EXISTS idx_material_revisions_job
                ON material_revisions(job_id, created_at);

                CREATE TABLE IF NOT EXISTS prompt_builds (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    prompt_type TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    context_snapshot TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'drafted',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS research_notes (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    subject TEXT NOT NULL,
                    source_url TEXT,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS application_changes (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    material_id TEXT,
                    change_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    before_text TEXT,
                    after_text TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    requirement TEXT,
                    proof_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS tailoring_requirements (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    requirement TEXT NOT NULL,
                    source_text TEXT,
                    category TEXT NOT NULL DEFAULT 'general',
                    priority REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'targeted',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tailoring_requirements_job
                ON tailoring_requirements(job_id, status, priority);

                CREATE TABLE IF NOT EXISTS portrayal_decisions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    requirement_id TEXT,
                    material_id TEXT,
                    proof_id TEXT,
                    decision_type TEXT NOT NULL DEFAULT 'resume_tailoring',
                    target TEXT NOT NULL,
                    before_text TEXT,
                    after_text TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'agent',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    FOREIGN KEY(requirement_id) REFERENCES tailoring_requirements(id) ON DELETE SET NULL,
                    FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE SET NULL,
                    FOREIGN KEY(proof_id) REFERENCES proof_points(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_portrayal_decisions_job
                ON portrayal_decisions(job_id, created_at);

                CREATE TABLE IF NOT EXISTS learning_patterns (
                    id TEXT PRIMARY KEY,
                    pattern_type TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    preference TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'agent',
                    confidence REAL NOT NULL DEFAULT 0.8,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_learning_patterns_type
                ON learning_patterns(pattern_type, updated_at);

                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    company TEXT,
                    role TEXT,
                    email TEXT,
                    email_status TEXT NOT NULL DEFAULT 'unknown',
                    linkedin_url TEXT,
                    source_url TEXT,
                    source_provider TEXT NOT NULL DEFAULT 'manual',
                    source_confidence REAL NOT NULL DEFAULT 0.5,
                    channel TEXT,
                    relationship TEXT,
                    notes TEXT,
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    last_seen_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS followups (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    contact_id TEXT,
                    due_date TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL,
                    FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS progress_items (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'task',
                    status TEXT NOT NULL DEFAULT 'open',
                    due_date TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    kind TEXT NOT NULL DEFAULT 'local_prepare',
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    prompt_id TEXT,
                    hermes_run_id TEXT,
                    hermes_session_id TEXT,
                    output TEXT,
                    error TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL,
                    FOREIGN KEY(prompt_id) REFERENCES prompt_builds(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS agent_run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    tool_name TEXT NOT NULL,
                    input TEXT NOT NULL,
                    output TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE SET NULL
                );
                """
            )
            self._ensure_columns(conn)
            self._ensure_contact_indexes(conn)
            self._ensure_performance_indexes(conn)
            self._ensure_retrieval_index(conn)
            self._ensure_brain_index(conn)
            self._backfill_retrieval_chunks(conn)

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        self._add_columns(
            conn,
            "jobs",
            {
                "role_family": "TEXT",
                "decision": "TEXT",
                "score": "REAL",
                "next_action": "TEXT",
                "hermes_session_id": "TEXT",
                "hermes_run_id": "TEXT",
            },
        )
        self._add_columns(
            conn,
            "materials",
            {
                "format": "TEXT NOT NULL DEFAULT 'text'",
                "file_path": "TEXT",
                "source": "TEXT NOT NULL DEFAULT 'agent'",
                "metadata": "TEXT NOT NULL DEFAULT '{}'",
            },
        )
        self._add_columns(
            conn,
            "agent_runs",
            {
                "job_id": "TEXT",
                "kind": "TEXT NOT NULL DEFAULT 'local_prepare'",
                "prompt_id": "TEXT",
                "hermes_run_id": "TEXT",
                "hermes_session_id": "TEXT",
                "output": "TEXT",
                "error": "TEXT",
                "metadata": "TEXT NOT NULL DEFAULT '{}'",
            },
        )
        self._add_columns(
            conn,
            "proof_points",
            {
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "user_confirmed": "INTEGER NOT NULL DEFAULT 1",
                "narrative_version": "TEXT NOT NULL DEFAULT 'current'",
                "allowed_uses": "TEXT NOT NULL DEFAULT '[\"resume\", \"cover_letter\", \"interview\", \"outreach\"]'",
                "risk_level": "TEXT NOT NULL DEFAULT 'safe'",
                "valid_from": "TEXT",
                "valid_to": "TEXT",
                "superseded_by": "TEXT",
                "last_used_at": "TEXT",
                "usage_count": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        self._add_columns(
            conn,
            "contacts",
            {
                "email": "TEXT",
                "email_status": "TEXT NOT NULL DEFAULT 'unknown'",
                "linkedin_url": "TEXT",
                "source_url": "TEXT",
                "source_provider": "TEXT NOT NULL DEFAULT 'manual'",
                "source_confidence": "REAL NOT NULL DEFAULT 0.5",
                "raw_payload": "TEXT NOT NULL DEFAULT '{}'",
                "last_seen_at": "TEXT",
            },
        )

    @staticmethod
    def _ensure_contact_indexes(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_source_url ON contacts(source_url)")

    @staticmethod
    def _ensure_performance_indexes(conn: sqlite3.Connection) -> None:
        """Keep the fully hydrated dashboard path index-backed as data grows."""

        indexes = (
            "CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_evaluations_job_created ON evaluations(job_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id, id)",
            "CREATE INDEX IF NOT EXISTS idx_materials_job_created ON materials(job_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_prompt_builds_created ON prompt_builds(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_prompt_builds_job_created ON prompt_builds(job_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_research_notes_job_created ON research_notes(job_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_application_changes_job_created ON application_changes(job_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_progress_items_job_created ON progress_items(job_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_progress_items_due_created ON progress_items(due_date, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_followups_job_due_created ON followups(job_id, due_date, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_followups_due_created ON followups(due_date, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_approvals_job_updated ON approvals(job_id, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_approvals_status_updated ON approvals(status, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_updated ON agent_runs(updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_agent_runs_job_created ON agent_runs(job_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_agent_run_events_run_created ON agent_run_events(run_id, created_at DESC, id DESC)",
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_run_created ON tool_calls(run_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_created ON tool_calls(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_tool_calls_unattached_created ON tool_calls(created_at DESC) WHERE run_id IS NULL",
            "CREATE INDEX IF NOT EXISTS idx_contacts_company_lookup ON contacts(lower(COALESCE(company, '')), updated_at DESC)",
        )
        for sql in indexes:
            conn.execute(sql)

    def _ensure_retrieval_index(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_chunks_fts
            USING fts5(chunk_id UNINDEXED, text, tags, tokenize='porter')
            """
        )

    def _ensure_brain_index(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS brain_events_fts
            USING fts5(event_id UNINDEXED, entity_title, title, content, evidence, tokenize='porter')
            """
        )

    def _backfill_retrieval_chunks(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT * FROM proof_points").fetchall()
        for row in rows:
            self._sync_proof_point_chunk_conn(conn, decode_proof_point(row))

    @staticmethod
    def _add_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def create_job(self, job: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        eval_id = uuid.uuid4().hex[:12]
        evaluation = dict(evaluation)
        title = job.get("title") or evaluation.get("facts", {}).get("title") or "Untitled role"
        company = job.get("company") or evaluation.get("facts", {}).get("company") or "Unknown company"
        location = job.get("location") or evaluation.get("facts", {}).get("location") or ""
        url = job.get("url") or ""
        description = job.get("description") or ""
        user_notes = job.get("user_notes") or ""
        with self._connect() as conn:
            existing_job_id = _find_existing_job_for_create(
                conn,
                job_id=str(job.get("id") or job.get("job_id") or ""),
                title=title,
                company=company,
                url=url,
                description=description,
            )
            job_id = existing_job_id or uuid.uuid4().hex[:12]
            evaluation["job_id"] = job_id
            if existing_job_id:
                conn.execute(
                    """
                    UPDATE jobs
                    SET title = COALESCE(NULLIF(?, ''), title),
                        company = COALESCE(NULLIF(?, ''), company),
                        location = COALESCE(NULLIF(?, ''), location),
                        url = COALESCE(NULLIF(?, ''), url),
                        description = COALESCE(NULLIF(?, ''), description),
                        user_notes = COALESCE(NULLIF(?, ''), user_notes),
                        status = COALESCE(NULLIF(?, ''), status),
                        role_family = COALESCE(?, role_family),
                        decision = COALESCE(?, decision),
                        score = COALESCE(?, score),
                        next_action = COALESCE(?, next_action),
                        hermes_session_id = COALESCE(NULLIF(?, ''), hermes_session_id),
                        hermes_run_id = COALESCE(NULLIF(?, ''), hermes_run_id),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        company,
                        location,
                        url,
                        description,
                        user_notes,
                        job.get("status") or "",
                        evaluation.get("role_family"),
                        evaluation.get("decision"),
                        evaluation.get("score_0_to_5"),
                        evaluation.get("next_action"),
                        job.get("hermes_session_id") or evaluation.get("hermes_session_id") or "",
                        job.get("hermes_run_id") or evaluation.get("hermes_run_id") or "",
                        now,
                        job_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        id, title, company, location, url, description, user_notes,
                        status, role_family, decision, score, next_action,
                        hermes_session_id, hermes_run_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        title,
                        company,
                        location,
                        url,
                        description,
                        user_notes,
                        job.get("status") or "new",
                        evaluation.get("role_family"),
                        evaluation.get("decision"),
                        evaluation.get("score_0_to_5"),
                        evaluation.get("next_action"),
                        job.get("hermes_session_id") or evaluation.get("hermes_session_id"),
                        job.get("hermes_run_id") or evaluation.get("hermes_run_id"),
                        now,
                        now,
                    ),
                )
            conn.execute(
                "INSERT INTO evaluations (id, job_id, payload, created_at) VALUES (?, ?, ?, ?)",
                (eval_id, job_id, json.dumps(evaluation), now),
            )
            conn.execute(
                "INSERT INTO events (job_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (job_id, "evaluated", json.dumps({"decision": evaluation.get("decision")}), now),
            )
            self._record_brain_event_conn(
                conn,
                event_type="opportunity_updated" if existing_job_id else "opportunity_created",
                title=f"{title} at {company}",
                content=description,
                job_id=job_id,
                entity_type="company",
                entity_title=company,
                source="local_prepare",
                confidence=0.8,
                importance=0.5 if existing_job_id else 0.68,
                occurred_at=now,
                metadata={
                    "decision": evaluation.get("decision"),
                    "role_family": evaluation.get("role_family"),
                    "next_action": evaluation.get("next_action"),
                    "deduped_existing_job": bool(existing_job_id),
                },
            )
        return self.get_job(job_id)

    def update_job_hermes_run(
        self,
        job_id: str,
        *,
        hermes_run_id: str = "",
        hermes_session_id: str = "",
        status: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if current is None:
                raise KeyError(job_id)
            conn.execute(
                """
                UPDATE jobs
                SET hermes_run_id = COALESCE(NULLIF(?, ''), hermes_run_id),
                    hermes_session_id = COALESCE(NULLIF(?, ''), hermes_session_id),
                    status = COALESCE(?, status),
                    updated_at = ?
                WHERE id = ?
                """,
                (hermes_run_id, hermes_session_id, status, now, job_id),
            )
        return self.get_job(job_id)

    def save_material(
        self,
        job_id: str,
        kind: str,
        content: Any,
        rationale: str = "",
        *,
        format: str = "text",
        file_path: str = "",
        source: str = "agent",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        material_id = uuid.uuid4().hex[:12]
        serialized = content if isinstance(content, str) else json.dumps(content, indent=2)
        clean_format = normalize_material_format_for_db(format)
        clean_kind = normalize_material_kind_for_db(kind, format=clean_format, file_path=file_path, content=content)
        clean_metadata = dict(metadata or {})
        content_metadata = material_payload_metadata(content)
        for key in ("pdf_path", "source_path", "source_format", "template", "display_name", "filename", "name"):
            if content_metadata.get(key) and not clean_metadata.get(key):
                clean_metadata[key] = content_metadata[key]
        if clean_format == "pdf" and not file_path and content_metadata.get("pdf_path"):
            file_path = str(content_metadata["pdf_path"])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO materials (
                    id, job_id, kind, format, content, file_path, rationale,
                    source, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    job_id,
                    clean_kind,
                    clean_format,
                    serialized,
                    file_path,
                    rationale,
                    source,
                    json.dumps(clean_metadata),
                    now,
                    now,
                ),
            )
            self._record_brain_event_conn(
                conn,
                event_type="material_saved",
                title=f"{kind} material saved",
                content=serialized[:12000],
                job_id=job_id,
                entity_type="material",
                entity_title=clean_kind,
                source=source,
                confidence=0.8,
                importance=0.55,
                occurred_at=now,
                metadata={"material_id": material_id, "format": clean_format, "file_path": file_path},
            )
        return {
            "id": material_id,
            "job_id": job_id,
            "kind": clean_kind,
            "format": clean_format,
            "content": serialized,
            "file_path": file_path,
            "rationale": rationale,
            "source": source,
            "metadata": clean_metadata,
        }

    def get_material(self, material_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
        if row is None:
            raise KeyError(material_id)
        return decode_material(row)

    def find_material(self, job_id: str, kind: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM materials
                WHERE job_id = ? AND kind = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (job_id, kind),
            ).fetchone()
        if row is None:
            raise KeyError(f"{job_id}:{kind}")
        return decode_material(row)

    def update_material(
        self,
        material_id: str,
        *,
        content: str | None = None,
        file_path: str | None = None,
        rationale: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
            if current is None:
                raise KeyError(material_id)
            merged_metadata = json.loads(current["metadata"] or "{}")
            if metadata:
                merged_metadata.update(metadata)
            conn.execute(
                """
                UPDATE materials
                SET content = COALESCE(?, content),
                    file_path = COALESCE(?, file_path),
                    rationale = COALESCE(?, rationale),
                    metadata = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (content, file_path, rationale, json.dumps(merged_metadata), now, material_id),
            )
            row = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
        if row is None:
            raise KeyError(material_id)
        return decode_material(row)

    def record_material_revision(
        self,
        material_id: str,
        *,
        before_text: str,
        after_text: str,
        diff: str,
        reason: str,
        source: str = "agent",
        requirement: str = "",
        proof_id: str | None = None,
    ) -> dict[str, Any]:
        material = self.get_material(material_id)
        now = utc_now()
        revision_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            if proof_id:
                _validate_eligible_proof(conn, proof_id, _provenance_use(material.get("kind") or requirement))
            count = conn.execute(
                "SELECT COUNT(*) FROM material_revisions WHERE material_id = ?",
                (material_id,),
            ).fetchone()[0]
            version = int(count) + 2
            conn.execute(
                """
                INSERT INTO material_revisions (
                    id, material_id, job_id, version, before_text, after_text,
                    diff, reason, source, requirement, proof_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    material_id,
                    material["job_id"],
                    version,
                    before_text,
                    after_text,
                    diff,
                    reason,
                    source,
                    requirement,
                    proof_id,
                    now,
                ),
            )
            self._record_brain_event_conn(
                conn,
                event_type="material_revision",
                title=f"Revision {version}: {reason}",
                content=after_text[:12000],
                job_id=material["job_id"],
                entity_type="material",
                entity_title=material.get("kind") or material_id,
                source=source,
                confidence=0.85,
                importance=0.7,
                occurred_at=now,
                metadata={
                    "material_id": material_id,
                    "revision_id": revision_id,
                    "version": version,
                    "requirement": requirement,
                    "proof_id": proof_id,
                },
            )
            row = conn.execute("SELECT * FROM material_revisions WHERE id = ?", (revision_id,)).fetchone()
        return decode_material_revision(row)

    def list_material_revisions(
        self,
        *,
        job_id: str | None = None,
        material_id: str | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if material_id:
            clauses.append("material_id = ?")
            params.append(material_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM material_revisions {where} ORDER BY created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [decode_material_revision(row) for row in rows]

    def save_prompt_build(
        self,
        prompt_type: str,
        prompt: str,
        *,
        job_id: str | None = None,
        context_snapshot: dict[str, Any] | None = None,
        status: str = "drafted",
    ) -> dict[str, Any]:
        now = utc_now()
        prompt_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO prompt_builds (id, job_id, prompt_type, prompt, context_snapshot, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (prompt_id, job_id, prompt_type, prompt, json.dumps(context_snapshot or {}), status, now, now),
            )
        return {
            "id": prompt_id,
            "job_id": job_id,
            "prompt_type": prompt_type,
            "prompt": prompt,
            "context_snapshot": context_snapshot or {},
            "status": status,
            "created_at": now,
            "updated_at": now,
        }

    def save_research_note(
        self,
        subject: str,
        summary: str,
        *,
        job_id: str | None = None,
        source_url: str = "",
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        now = utc_now()
        note_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO research_notes (id, job_id, subject, source_url, summary, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (note_id, job_id, subject, source_url, summary, confidence, now, now),
            )
            self._record_brain_event_conn(
                conn,
                event_type="research_note",
                title=subject,
                content=summary,
                job_id=job_id,
                entity_type="company" if job_id else "job_search",
                entity_title=subject,
                source="research",
                evidence_text=source_url,
                confidence=confidence,
                importance=0.6,
                occurred_at=now,
                metadata={"research_note_id": note_id, "source_url": source_url},
            )
        return {
            "id": note_id,
            "job_id": job_id,
            "subject": subject,
            "source_url": source_url,
            "summary": summary,
            "confidence": confidence,
            "created_at": now,
            "updated_at": now,
        }

    def record_application_change(
        self,
        job_id: str,
        change_type: str,
        target: str,
        after_text: str,
        reason: str,
        *,
        material_id: str | None = None,
        before_text: str = "",
        requirement: str = "",
        proof_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        change_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() or (_raise_key(job_id))
            if material_id:
                conn.execute(
                    "SELECT id FROM materials WHERE id = ? AND job_id = ?",
                    (material_id, job_id),
                ).fetchone() or (_raise_key(material_id))
            if proof_id:
                _validate_eligible_proof(conn, proof_id, _provenance_use(change_type or target))
            conn.execute(
                """
                INSERT INTO application_changes (
                    id, job_id, material_id, change_type, target, before_text,
                    after_text, reason, requirement, proof_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    job_id,
                    material_id,
                    change_type,
                    target,
                    before_text,
                    after_text,
                    reason,
                    requirement,
                    proof_id,
                    now,
                ),
            )
            self._record_brain_event_conn(
                conn,
                event_type="application_change",
                title=f"{change_type}: {target}",
                content=after_text,
                job_id=job_id,
                entity_type="decision",
                entity_title=target,
                source="agent",
                evidence_text=reason,
                confidence=0.86,
                importance=0.72,
                occurred_at=now,
                metadata={
                    "application_change_id": change_id,
                    "material_id": material_id,
                    "requirement": requirement,
                    "proof_id": proof_id,
                },
            )
        return {
            "id": change_id,
            "job_id": job_id,
            "material_id": material_id,
            "change_type": change_type,
            "target": target,
            "before_text": before_text,
            "after_text": after_text,
            "reason": reason,
            "requirement": requirement,
            "proof_id": proof_id,
            "created_at": now,
        }

    def record_tailoring_requirement(
        self,
        job_id: str,
        requirement: str,
        *,
        source_text: str = "",
        category: str = "general",
        priority: float = 0.5,
        status: str = "targeted",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        requirement_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() or (_raise_key(job_id))
            conn.execute(
                """
                INSERT INTO tailoring_requirements (
                    id, job_id, requirement, source_text, category, priority,
                    status, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    requirement_id,
                    job_id,
                    requirement,
                    source_text,
                    category or "general",
                    float(priority),
                    status or "targeted",
                    json.dumps(metadata or {}),
                    now,
                    now,
                ),
            )
            self._record_brain_event_conn(
                conn,
                event_type="tailoring_requirement",
                title=truncate_signal_label(requirement),
                content=requirement,
                job_id=job_id,
                entity_type="decision",
                entity_title=category or "tailoring",
                source="agent",
                evidence_text=source_text,
                confidence=0.78,
                importance=0.62,
                occurred_at=now,
                metadata={"tailoring_requirement_id": requirement_id, "category": category, "priority": priority},
            )
            row = conn.execute("SELECT * FROM tailoring_requirements WHERE id = ?", (requirement_id,)).fetchone()
        return decode_tailoring_requirement(row)

    def list_tailoring_requirements(self, job_id: str | None = None, *, limit: int = 120) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if job_id:
                rows = conn.execute(
                    """
                    SELECT * FROM tailoring_requirements
                    WHERE job_id = ?
                    ORDER BY priority DESC, created_at DESC
                    LIMIT ?
                    """,
                    (job_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM tailoring_requirements
                    ORDER BY priority DESC, created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [decode_tailoring_requirement(row) for row in rows]

    def record_portrayal_decision(
        self,
        job_id: str,
        target: str,
        after_text: str,
        rationale: str,
        *,
        requirement_id: str | None = None,
        material_id: str | None = None,
        proof_id: str | None = None,
        before_text: str = "",
        decision_type: str = "resume_tailoring",
        source: str = "agent",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        decision_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() or (_raise_key(job_id))
            if requirement_id:
                conn.execute(
                    "SELECT id FROM tailoring_requirements WHERE id = ? AND job_id = ?",
                    (requirement_id, job_id),
                ).fetchone() or (_raise_key(requirement_id))
            if material_id:
                conn.execute(
                    "SELECT id FROM materials WHERE id = ? AND job_id = ?",
                    (material_id, job_id),
                ).fetchone() or (_raise_key(material_id))
            if proof_id:
                _validate_eligible_proof(conn, proof_id, _provenance_use(decision_type or target))
            conn.execute(
                """
                INSERT INTO portrayal_decisions (
                    id, job_id, requirement_id, material_id, proof_id, decision_type,
                    target, before_text, after_text, rationale, source, metadata, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    job_id,
                    requirement_id,
                    material_id,
                    proof_id,
                    decision_type or "resume_tailoring",
                    target,
                    before_text,
                    after_text,
                    rationale,
                    source or "agent",
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            self._record_brain_event_conn(
                conn,
                event_type="portrayal_decision",
                title=f"{decision_type or 'portrayal'}: {target}",
                content=after_text,
                job_id=job_id,
                entity_type="decision",
                entity_title=target,
                source=source or "agent",
                evidence_text=rationale,
                confidence=0.9,
                importance=0.78,
                occurred_at=now,
                metadata={
                    "portrayal_decision_id": decision_id,
                    "requirement_id": requirement_id,
                    "material_id": material_id,
                    "proof_id": proof_id,
                },
            )
            row = conn.execute("SELECT * FROM portrayal_decisions WHERE id = ?", (decision_id,)).fetchone()
        return decode_portrayal_decision(row)

    def list_portrayal_decisions(self, job_id: str | None = None, *, limit: int = 120) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if job_id:
                rows = conn.execute(
                    """
                    SELECT * FROM portrayal_decisions
                    WHERE job_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (job_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM portrayal_decisions
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [decode_portrayal_decision(row) for row in rows]

    def record_learning_pattern(
        self,
        pattern_type: str,
        trigger: str,
        preference: str,
        *,
        source: str = "agent",
        confidence: float = 0.8,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        pattern_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_patterns (
                    id, pattern_type, trigger, preference, source, confidence,
                    metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pattern_id,
                    pattern_type,
                    trigger,
                    preference,
                    source or "agent",
                    float(confidence),
                    json.dumps(metadata or {}),
                    now,
                    now,
                ),
            )
            self._record_brain_event_conn(
                conn,
                event_type="learning_pattern",
                title=pattern_type,
                content=preference,
                entity_type="job_search",
                entity_title=trigger,
                source=source or "agent",
                evidence_text=trigger,
                confidence=confidence,
                importance=0.86,
                occurred_at=now,
                metadata={"learning_pattern_id": pattern_id, **(metadata or {})},
            )
            row = conn.execute("SELECT * FROM learning_patterns WHERE id = ?", (pattern_id,)).fetchone()
        return decode_learning_pattern(row)

    def list_learning_patterns(
        self,
        pattern_type: str | None = None,
        *,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if pattern_type:
                rows = conn.execute(
                    """
                    SELECT * FROM learning_patterns
                    WHERE pattern_type = ?
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT ?
                    """,
                    (pattern_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM learning_patterns
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [decode_learning_pattern(row) for row in rows]

    def create_progress_item(
        self,
        title: str,
        *,
        job_id: str | None = None,
        kind: str = "task",
        status: str = "open",
        due_date: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        return self.upsert_open_progress_item(
            title,
            job_id=job_id,
            kind=kind,
            status=status,
            due_date=due_date,
            notes=notes,
        )

    def upsert_open_progress_item(
        self,
        title: str,
        *,
        job_id: str | None = None,
        kind: str = "task",
        status: str = "open",
        due_date: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        clean_title = normalize_space_for_db(title)
        clean_kind = normalize_space_for_db(kind) or "task"
        clean_status = normalize_space_for_db(status) or "open"
        clean_due_date = normalize_space_for_db(due_date)
        clean_notes = str(notes or "").strip()
        _raise_if_review_progress_action(clean_title, clean_kind)
        title_key = normalize_action_title(clean_title)
        now = utc_now()
        item_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            if job_id is None:
                candidate_rows = conn.execute(
                    f"""
                    SELECT * FROM progress_items
                    WHERE job_id IS NULL
                      AND lower(COALESCE(kind, '')) = lower(?)
                      AND lower(COALESCE(status, '')) NOT IN {ACTION_CLOSED_SQL}
                    ORDER BY updated_at DESC, created_at DESC
                    """,
                    (clean_kind,),
                ).fetchall()
            else:
                candidate_rows = conn.execute(
                    f"""
                    SELECT * FROM progress_items
                    WHERE job_id = ?
                      AND lower(COALESCE(kind, '')) = lower(?)
                      AND lower(COALESCE(status, '')) NOT IN {ACTION_CLOSED_SQL}
                    ORDER BY updated_at DESC, created_at DESC
                    """,
                    (job_id, clean_kind),
                ).fetchall()
            current = next((row for row in candidate_rows if normalize_action_title(row["title"]) == title_key), None)
            if current is not None:
                next_due_date = clean_due_date or current["due_date"] or ""
                next_notes = clean_notes or current["notes"] or ""
                conn.execute(
                    """
                    UPDATE progress_items
                    SET title = ?, kind = ?, status = ?, due_date = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (current["title"], clean_kind, clean_status, next_due_date, next_notes, now, current["id"]),
                )
                self._record_brain_event_conn(
                    conn,
                    event_type="progress_item_updated",
                    title=current["title"],
                    content=next_notes or current["title"],
                    job_id=current["job_id"],
                    entity_type="job_search",
                    entity_title=clean_kind,
                    source="app",
                    confidence=0.75,
                    importance=0.5,
                    occurred_at=now,
                    metadata={
                        "progress_item_id": current["id"],
                        "kind": clean_kind,
                        "status": clean_status,
                        "due_date": next_due_date,
                        "idempotent_reuse": True,
                    },
                )
                row = conn.execute("SELECT * FROM progress_items WHERE id = ?", (current["id"],)).fetchone()
                return dict(row)
            conn.execute(
                """
                INSERT INTO progress_items (id, job_id, title, kind, status, due_date, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, job_id, clean_title, clean_kind, clean_status, clean_due_date, clean_notes, now, now),
            )
            self._record_brain_event_conn(
                conn,
                event_type="progress_item",
                title=clean_title,
                content=clean_notes or clean_title,
                job_id=job_id,
                entity_type="job_search",
                entity_title=clean_kind,
                source="app",
                confidence=0.75,
                importance=0.5,
                occurred_at=now,
                metadata={"progress_item_id": item_id, "kind": clean_kind, "status": clean_status, "due_date": clean_due_date},
            )
            row = conn.execute("SELECT * FROM progress_items WHERE id = ?", (item_id,)).fetchone()
        return dict(row)

    def update_progress_item(
        self,
        item_id: str,
        status: str,
        notes: str | None = None,
        due_date: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM progress_items WHERE id = ?", (item_id,)).fetchone()
            if current is None:
                raise KeyError(item_id)
            next_notes = current["notes"] if notes is None else notes
            next_due_date = current["due_date"] if due_date is None else due_date
            conn.execute(
                """
                UPDATE progress_items
                SET status = ?, due_date = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, next_due_date, next_notes, now, item_id),
            )
            self._record_brain_event_conn(
                conn,
                event_type="progress_item_disposition",
                title=f"{current['title']}: {status}",
                content=notes or f"Progress item marked {status}.",
                job_id=current["job_id"],
                entity_type="job_search",
                entity_title=current["kind"],
                source="cockpit",
                confidence=0.9,
                importance=0.56,
                occurred_at=now,
                metadata={"progress_item_id": item_id, "status": status, "due_date": next_due_date},
            )
            row = conn.execute("SELECT * FROM progress_items WHERE id = ?", (item_id,)).fetchone()
        return dict(row)

    def _close_material_review_progress_for_approval_conn(
        self,
        conn: sqlite3.Connection,
        *,
        job_id: str | None,
        approval_id: str,
        approval_status: str,
        payload: dict[str, Any],
        now: str,
    ) -> None:
        if not job_id:
            return
        rows = conn.execute(
            f"""
            SELECT * FROM progress_items
            WHERE job_id = ?
              AND lower(COALESCE(kind, '')) = 'material_review'
              AND lower(COALESCE(status, '')) NOT IN {ACTION_CLOSED_SQL}
            ORDER BY updated_at DESC, created_at DESC
            """,
            (job_id,),
        ).fetchall()
        linked_progress_id = normalize_space_for_db(payload.get("progress_item_id", ""))
        review_title_key = normalize_action_title(MATERIAL_REVIEW_PROGRESS_TITLE)
        rows_to_close = [
            row
            for row in rows
            if row["id"] == linked_progress_id or normalize_action_title(row["title"]) == review_title_key
        ]
        progress_status = "done" if approval_status == "approved" else "not_needed"
        for row in rows_to_close:
            note = row["notes"] or ""
            disposition_note = f"Material review {approval_status} via approval {approval_id}."
            next_note = note if disposition_note in note else "\n".join(part for part in [note, disposition_note] if part)
            conn.execute(
                """
                UPDATE progress_items
                SET status = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (progress_status, next_note, now, row["id"]),
            )
            self._record_brain_event_conn(
                conn,
                event_type="progress_item_disposition",
                title=f"{row['title']}: {progress_status}",
                content=disposition_note,
                job_id=job_id,
                entity_type="job_search",
                entity_title=row["kind"],
                source="cockpit",
                confidence=0.9,
                importance=0.56,
                occurred_at=now,
                metadata={
                    "progress_item_id": row["id"],
                    "approval_id": approval_id,
                    "approval_status": approval_status,
                    "status": progress_status,
                },
            )

    def upsert_contact(
        self,
        name: str,
        *,
        company: str = "",
        role: str = "",
        email: str = "",
        email_status: str = "",
        linkedin_url: str = "",
        source_url: str = "",
        source_provider: str = "manual",
        source_confidence: float = 0.5,
        channel: str = "",
        relationship: str = "",
        notes: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = normalize_space_for_db(name)
        if not name:
            raise ValueError("Contact name is required.")
        now = utc_now()
        email = normalize_space_for_db(email).lower()
        email_status = normalize_email_status(email_status or ("found" if email else "missing"))
        company = normalize_space_for_db(company)
        role = normalize_space_for_db(role)
        source_url = normalize_space_for_db(source_url)
        linkedin_url = normalize_space_for_db(linkedin_url)
        contact_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            row = None
            if email:
                row = conn.execute("SELECT * FROM contacts WHERE lower(email) = ?", (email,)).fetchone()
            if row is None and source_url:
                row = conn.execute("SELECT * FROM contacts WHERE source_url = ?", (source_url,)).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT * FROM contacts
                    WHERE lower(name) = ? AND lower(COALESCE(company, '')) = ? AND lower(COALESCE(role, '')) = ?
                    LIMIT 1
                    """,
                    (name.lower(), company.lower(), role.lower()),
                ).fetchone()
            if row is None:
                is_new = True
                conn.execute(
                    """
                    INSERT INTO contacts (
                        id, name, company, role, email, linkedin_url, source_url,
                        source_provider, source_confidence, channel, relationship,
                        email_status,
                        notes, raw_payload, last_seen_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contact_id,
                        name,
                        company,
                        role,
                        email,
                        linkedin_url,
                        source_url,
                        source_provider or "manual",
                        float(source_confidence),
                        channel,
                        relationship,
                        email_status,
                        notes,
                        json.dumps(raw_payload or {}),
                        now,
                        now,
                        now,
                    ),
                )
            else:
                is_new = False
                contact_id = row["id"]
                merged = _merge_contact(
                    dict(row),
                    {
                        "name": name,
                        "company": company,
                        "role": role,
                        "email": email,
                        "linkedin_url": linkedin_url,
                        "source_url": source_url,
                        "source_provider": source_provider,
                        "source_confidence": source_confidence,
                        "email_status": email_status,
                        "channel": channel,
                        "relationship": relationship,
                        "notes": notes,
                        "raw_payload": raw_payload or {},
                    },
                )
                conn.execute(
                    """
                    UPDATE contacts
                    SET name = ?, company = ?, role = ?, email = ?, email_status = ?, linkedin_url = ?,
                        source_url = ?, source_provider = ?, source_confidence = ?,
                        channel = ?, relationship = ?, notes = ?, raw_payload = ?,
                        last_seen_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        merged["name"],
                        merged.get("company") or "",
                        merged.get("role") or "",
                        merged.get("email") or "",
                        normalize_email_status(merged.get("email_status") or ("found" if merged.get("email") else "missing")),
                        merged.get("linkedin_url") or "",
                        merged.get("source_url") or "",
                        merged.get("source_provider") or "manual",
                        float(merged.get("source_confidence") or 0.5),
                        merged.get("channel") or "",
                        merged.get("relationship") or "",
                        merged.get("notes") or "",
                        json.dumps(merged.get("raw_payload") or {}),
                        now,
                        now,
                        contact_id,
                    ),
                )
            if is_new:
                self._record_brain_event_conn(
                    conn,
                    event_type="contact_cached",
                    title=name,
                    content=notes or f"{role} at {company}".strip(" at"),
                    entity_type="person",
                    entity_title=name,
                    source=source_provider or "manual",
                    evidence_text=source_url or linkedin_url or email,
                    confidence=float(source_confidence),
                    importance=0.64,
                    occurred_at=now,
                    metadata={"contact_id": contact_id, "company": company, "role": role, "email_status": email_status},
                )
            contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        return decode_contact(contact)

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if row is None:
                raise KeyError(contact_id)
        return decode_contact(row)

    def list_contacts(self, company: str | None = None, *, limit: int = 80) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if company:
            where = "WHERE lower(company) = ?"
            params.append(company.lower())
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM contacts {where} ORDER BY updated_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [decode_contact(row) for row in rows]

    def create_followup(
        self,
        due_date: str,
        reason: str,
        *,
        job_id: str | None = None,
        contact_id: str | None = None,
        status: str = "open",
    ) -> dict[str, Any]:
        now = utc_now()
        followup_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO followups (id, job_id, contact_id, due_date, reason, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (followup_id, job_id, contact_id, due_date, reason, status, now, now),
            )
            self._record_brain_event_conn(
                conn,
                event_type="followup_created",
                title=reason,
                content=f"Due {due_date}: {reason}",
                job_id=job_id,
                entity_type="job_search",
                entity_title="follow up",
                source="app",
                confidence=0.8,
                importance=0.62,
                occurred_at=now,
                metadata={"followup_id": followup_id, "contact_id": contact_id, "status": status},
            )
        return {
            "id": followup_id,
            "job_id": job_id,
            "contact_id": contact_id,
            "due_date": due_date,
            "reason": reason,
            "status": status,
            "created_at": now,
            "updated_at": now,
        }

    def update_followup(
        self,
        followup_id: str,
        status: str,
        *,
        due_date: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM followups WHERE id = ?", (followup_id,)).fetchone()
            if current is None:
                raise KeyError(followup_id)
            next_due_date = current["due_date"] if due_date is None else due_date
            next_reason = current["reason"] if reason is None else reason
            conn.execute(
                """
                UPDATE followups
                SET status = ?, due_date = ?, reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, next_due_date, next_reason, now, followup_id),
            )
            self._record_brain_event_conn(
                conn,
                event_type="followup_disposition",
                title=f"{current['reason']}: {status}",
                content=f"Follow-up marked {status}. Due {next_due_date}: {next_reason}",
                job_id=current["job_id"],
                entity_type="job_search",
                entity_title="follow up",
                source="cockpit",
                confidence=0.9,
                importance=0.62,
                occurred_at=now,
                metadata={"followup_id": followup_id, "contact_id": current["contact_id"], "status": status},
            )
            row = conn.execute("SELECT * FROM followups WHERE id = ?", (followup_id,)).fetchone()
        return dict(row)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                raise KeyError(job_id)
            evaluation = conn.execute(
                "SELECT payload FROM evaluations WHERE job_id = ? ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            events = conn.execute(
                "SELECT event_type, payload, created_at FROM events WHERE job_id = ? ORDER BY id",
                (job_id,),
            ).fetchall()
            materials = conn.execute(
                "SELECT * FROM materials WHERE job_id = ? ORDER BY created_at",
                (job_id,),
            ).fetchall()
            material_revisions = conn.execute(
                "SELECT * FROM material_revisions WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            prompts = conn.execute(
                "SELECT * FROM prompt_builds WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            research = conn.execute(
                "SELECT * FROM research_notes WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            changes = conn.execute(
                "SELECT * FROM application_changes WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            tailoring_requirements = conn.execute(
                "SELECT * FROM tailoring_requirements WHERE job_id = ? ORDER BY priority DESC, created_at",
                (job_id,),
            ).fetchall()
            portrayal_decisions = conn.execute(
                "SELECT * FROM portrayal_decisions WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            signals = conn.execute(
                "SELECT * FROM application_signals WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            brain_events = conn.execute(
                """
                SELECT e.*, be.entity_type, be.slug AS entity_slug,
                       be.title AS entity_title, be.summary AS entity_summary,
                       0.0 AS rank
                FROM brain_events e
                LEFT JOIN brain_entities be ON be.id = e.entity_id
                WHERE e.job_id = ?
                ORDER BY e.occurred_at DESC, e.created_at DESC
                LIMIT 80
                """,
                (job_id,),
            ).fetchall()
            progress = conn.execute(
                "SELECT * FROM progress_items WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            followups = conn.execute(
                "SELECT * FROM followups WHERE job_id = ? ORDER BY due_date, created_at",
                (job_id,),
            ).fetchall()
            contact_ids = {str(row["contact_id"]) for row in followups if row["contact_id"]}
            for material_row in materials:
                try:
                    metadata = json.loads(material_row["metadata"] or "{}")
                except json.JSONDecodeError:
                    metadata = {}
                if metadata.get("contact_id"):
                    contact_ids.add(str(metadata["contact_id"]))
            contact_rows = []
            company = str(job["company"] or "").strip().lower()
            if contact_ids or company:
                clauses = []
                params: list[Any] = []
                if contact_ids:
                    placeholders = ",".join("?" for _ in contact_ids)
                    clauses.append(f"id IN ({placeholders})")
                    params.extend(sorted(contact_ids))
                if company:
                    clauses.append("lower(COALESCE(company, '')) = ?")
                    params.append(company)
                contact_rows = conn.execute(
                    f"SELECT * FROM contacts WHERE {' OR '.join(clauses)} ORDER BY updated_at DESC LIMIT 40",
                    tuple(params),
                ).fetchall()
            approvals = conn.execute(
                "SELECT * FROM approvals WHERE job_id = ? ORDER BY updated_at DESC",
                (job_id,),
            ).fetchall()
            agent_runs = conn.execute(
                "SELECT * FROM agent_runs WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            run_ids = [row["id"] for row in agent_runs]
            run_events = []
            tool_calls = []
            if run_ids:
                placeholders = ",".join("?" for _ in run_ids)
                run_events = conn.execute(
                    f"""
                    SELECT * FROM agent_run_events
                    WHERE run_id IN ({placeholders})
                    ORDER BY created_at DESC, id DESC
                    LIMIT 100
                    """,
                    tuple(run_ids),
                ).fetchall()
                tool_calls = conn.execute(
                    f"""
                    SELECT * FROM tool_calls
                    WHERE run_id IN ({placeholders})
                    ORDER BY created_at DESC
                    LIMIT 100
                    """,
                    tuple(run_ids),
                ).fetchall()
        decoded_agent_runs = [decode_agent_run(row) for row in agent_runs]
        return {
            "job": dict(job),
            "evaluation": json.loads(evaluation["payload"]) if evaluation else None,
            "events": [
                {
                    "event_type": row["event_type"],
                    "payload": json.loads(row["payload"]),
                    "created_at": row["created_at"],
                }
                for row in events
            ],
            "materials": [decode_material(row) for row in materials],
            "material_revisions": [decode_material_revision(row) for row in material_revisions],
            "prompts": [decode_prompt(row) for row in prompts],
            "research_notes": [dict(row) for row in research],
            "application_changes": [dict(row) for row in changes],
            "tailoring_requirements": [decode_tailoring_requirement(row) for row in tailoring_requirements],
            "portrayal_decisions": [decode_portrayal_decision(row) for row in portrayal_decisions],
            "application_signals": [decode_application_signal(row) for row in signals],
            "brain_events": [decode_brain_event(row) for row in brain_events],
            "progress_items": [dict(row) for row in progress],
            "followups": [dict(row) for row in followups],
            "contacts": [decode_contact(row) for row in contact_rows],
            "approvals": [decode_approval(row) for row in approvals],
            "agent_runs": decoded_agent_runs,
            "active_run": _active_hermes_run(decoded_agent_runs),
            "agent_run_events": [decode_agent_run_event(row) for row in run_events],
            "tool_calls": [decode_tool_call(row) for row in tool_calls],
        }

    def list_jobs(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT jobs.*, evaluations.payload AS evaluation_payload
                FROM jobs
                LEFT JOIN evaluations ON evaluations.job_id = jobs.id
                GROUP BY jobs.id
                ORDER BY jobs.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            payload = item.pop("evaluation_payload", None)
            item["evaluation"] = json.loads(payload) if payload else None
            output.append(item)
        return output

    def dashboard(self) -> dict[str, Any]:
        with self._connect() as conn:
            followups = conn.execute(
                f"""
                SELECT followups.*, jobs.title AS job_title, jobs.company AS job_company
                FROM followups
                LEFT JOIN jobs ON jobs.id = followups.job_id
                WHERE lower(COALESCE(followups.status, '')) NOT IN {ACTION_CLOSED_SQL}
                ORDER BY followups.due_date, followups.created_at
                LIMIT 40
                """
            ).fetchall()
            progress = conn.execute(
                f"""
                SELECT progress_items.*, jobs.title AS job_title, jobs.company AS job_company
                FROM progress_items
                LEFT JOIN jobs ON jobs.id = progress_items.job_id
                WHERE lower(COALESCE(progress_items.status, '')) NOT IN {ACTION_CLOSED_SQL}
                ORDER BY progress_items.due_date IS NULL, progress_items.due_date, progress_items.created_at
                LIMIT 60
                """
            ).fetchall()
            prompts = conn.execute(
                "SELECT * FROM prompt_builds ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            agent_runs = conn.execute(
                "SELECT * FROM agent_runs ORDER BY updated_at DESC LIMIT 12"
            ).fetchall()
            approvals = conn.execute(
                """
                SELECT approvals.*, jobs.title AS job_title, jobs.company AS job_company
                FROM approvals
                LEFT JOIN jobs ON jobs.id = approvals.job_id
                WHERE approvals.status = 'pending'
                ORDER BY approvals.updated_at DESC
                LIMIT 40
                """
            ).fetchall()
        jobs = [self._dashboard_job(self.get_job(job["id"])) for job in self.list_jobs()]
        followup_rows = [dict(row) for row in followups]
        progress_rows = _purposeful_progress_rows([dict(row) for row in progress])
        approval_rows = _purposeful_approval_rows([decode_approval(row) for row in approvals])
        return {
            "jobs": jobs,
            "active_job": jobs[0] if jobs else None,
            "job_count": len(jobs),
            "job_state_counts": _job_state_counts(jobs),
            "discovery": {
                "candidates": self.list_discovery_candidates(limit=80),
                "counts": self.discovery_counts(),
            },
            "contacts": self.list_contacts(limit=80),
            "followup_count": len(followup_rows),
            "progress_count": len(progress_rows),
            "approval_count": len(approval_rows),
            "followups": followup_rows,
            "progress_items": progress_rows,
            "approvals": approval_rows,
            "prompt_builds": [decode_prompt(row) for row in prompts],
            "agent_runs": [decode_agent_run(row) for row in agent_runs],
            "learning_patterns": self.list_learning_patterns(limit=40),
            "brain": self.brain_context(limit=30),
            "database_health": self.database_health(),
            "context_counts": {
                "profile_facts": len(self.list_profile_facts()),
                "proof_points": len(self.list_proof_points()),
                "application_signals": len(self.list_application_signals(limit=1000)),
                "tailoring_requirements": len(self.list_tailoring_requirements(limit=1000)),
                "portrayal_decisions": len(self.list_portrayal_decisions(limit=1000)),
                "learning_patterns": len(self.list_learning_patterns(limit=1000)),
                "brain_entities": self.count_brain_entities(),
                "brain_events": self.count_brain_events(),
                "discovery_candidates": self.discovery_counts().get("total", 0),
                "contacts": len(self.list_contacts(limit=1000)),
            },
        }

    def _dashboard_job(self, record: dict[str, Any]) -> dict[str, Any]:
        job = dict(record["job"])
        evaluation = record.get("evaluation") or {}
        materials = record.get("materials") or []
        material_revisions = record.get("material_revisions") or []
        prompts = record.get("prompts") or []
        progress = record.get("progress_items") or []
        followups = record.get("followups") or []
        contacts = record.get("contacts") or []
        events = record.get("events") or []
        research_notes = record.get("research_notes") or []
        tailoring_requirements = record.get("tailoring_requirements") or []
        portrayal_decisions = record.get("portrayal_decisions") or []
        application_signals = record.get("application_signals") or []
        brain_events = record.get("brain_events") or []
        agent_runs = record.get("agent_runs") or []
        latest_run = agent_runs[0] if agent_runs else None

        material_by_kind = {item.get("kind"): item for item in materials}
        job["evaluation"] = evaluation
        job["decision"] = job.get("decision") or evaluation.get("decision")
        job["role_family"] = job.get("role_family") or evaluation.get("role_family")
        job["next_action"] = job.get("next_action") or evaluation.get("next_action")
        job["risks"] = _dashboard_risks(evaluation)
        job["resume_tex"] = _material_content(material_by_kind.get("resume_tailoring"))
        job["cover_letter_tex"] = _material_content(material_by_kind.get("cover_letter"))
        job["prompt"] = prompts[0]["prompt"] if prompts else ""
        job["hermes_output"] = _latest_run_output(agent_runs)
        job["research_notes"] = [
            {
                "id": item.get("id"),
                "subject": item.get("subject", ""),
                "content": item.get("summary", ""),
                "source_url": item.get("source_url", ""),
                "confidence": item.get("confidence"),
            }
            for item in research_notes
        ]
        job["progress"] = [
            {
                "id": item.get("id"),
                "summary": item.get("title", ""),
                "status": item.get("status", ""),
                "kind": item.get("kind", ""),
                "due_date": item.get("due_date", ""),
            }
            for item in progress
        ]
        job["followups"] = [dict(item) for item in followups]
        job["contacts"] = contacts
        job["outreach"] = _dashboard_outreach(materials, contacts, followups)
        job["events"] = [_dashboard_event(item) for item in events]
        job["materials"] = materials
        job["material_revisions"] = material_revisions
        job["tailoring_requirements"] = tailoring_requirements
        job["portrayal_decisions"] = portrayal_decisions
        job["application_signals"] = application_signals
        job["brain_events"] = brain_events
        job["materials_workbench"] = _materials_workbench(materials, material_revisions)
        job["approvals"] = record.get("approvals") or []
        job["active_run"] = _active_hermes_run(agent_runs)
        job["hermes_run_status"] = latest_run.get("status") if latest_run else job.get("status")
        job["hermes_run_id"] = latest_run.get("hermes_run_id") if latest_run else job.get("hermes_run_id")
        state = _dashboard_job_state(job, events, materials, progress, followups, job["approvals"])
        job["state_bucket"] = state["bucket"]
        job["state_label"] = state["label"]
        job["state_dates"] = state["dates"]
        job["last_activity_at"] = state["last_activity_at"]
        job["open_action_count"] = state["open_action_count"]
        job["needs_material_review"] = state["needs_material_review"]
        return job

    def create_approval(
        self,
        action: str,
        *,
        job_id: str | None = None,
        status: str = "pending",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_action = normalize_space_for_db(action)
        _raise_if_review_approval_action(clean_action)
        now = utc_now()
        approval_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (id, job_id, action, status, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (approval_id, job_id, clean_action, status, json.dumps(payload or {}), now, now),
            )
            self._record_brain_event_conn(
                conn,
                event_type="approval_requested",
                title=clean_action,
                content=json.dumps(payload or {}, indent=2, sort_keys=True),
                job_id=job_id,
                entity_type="decision",
                entity_title=action,
                source="app",
                confidence=0.9,
                importance=0.72,
                occurred_at=now,
                metadata={"approval_id": approval_id, "status": status},
            )
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return decode_approval(row)

    def upsert_pending_approval(
        self,
        action: str,
        *,
        job_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_action = normalize_space_for_db(action)
        _raise_if_review_approval_action(clean_action)
        incoming_payload = payload or {}
        with self._connect() as conn:
            if job_id is None:
                row = conn.execute(
                    """
                    SELECT * FROM approvals
                    WHERE job_id IS NULL AND action = ? AND status = 'pending'
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    (clean_action,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM approvals
                    WHERE job_id = ? AND action = ? AND status = 'pending'
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    (job_id, clean_action),
                ).fetchone()
        if row is None:
            return self.create_approval(clean_action, job_id=job_id, status="pending", payload=incoming_payload)
        existing_payload = json.loads(row["payload"] or "{}")
        existing_payload.update(incoming_payload)
        return self.update_approval(row["id"], "pending", payload=existing_payload)

    def update_approval(
        self,
        approval_id: str,
        status: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if current is None:
                raise KeyError(approval_id)
            merged_payload = json.loads(current["payload"] or "{}")
            if payload:
                merged_payload.update(payload)
            conn.execute(
                """
                UPDATE approvals
                SET status = ?, payload = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, json.dumps(merged_payload), now, approval_id),
            )
            self._record_brain_event_conn(
                conn,
                event_type="approval_updated",
                title=f"{current['action']}: {status}",
                content=json.dumps(merged_payload, indent=2, sort_keys=True),
                job_id=current["job_id"],
                entity_type="decision",
                entity_title=current["action"],
                source="app",
                confidence=0.9,
                importance=0.72,
                occurred_at=now,
                metadata={"approval_id": approval_id, "status": status},
            )
            if status in {"approved", "rejected"} and current["action"] in MATERIAL_REVIEW_APPROVAL_ACTIONS:
                self._close_material_review_progress_for_approval_conn(
                    conn,
                    job_id=current["job_id"],
                    approval_id=approval_id,
                    approval_status=status,
                    payload=merged_payload,
                    now=now,
                )
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return decode_approval(row)

    def list_approvals(
        self,
        *,
        job_id: str | None = None,
        status: str | None = None,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if job_id:
            clauses.append("job_id = ?")
            params.append(job_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM approvals {where} ORDER BY updated_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [decode_approval(row) for row in rows]

    def database_health(self) -> dict[str, Any]:
        with self._connect() as conn:
            counts = {
                "jobs": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                "profile_facts": conn.execute("SELECT COUNT(*) FROM profile_facts").fetchone()[0],
                "proof_points": conn.execute("SELECT COUNT(*) FROM proof_points").fetchone()[0],
                "tailoring_requirements": conn.execute("SELECT COUNT(*) FROM tailoring_requirements").fetchone()[0],
                "portrayal_decisions": conn.execute("SELECT COUNT(*) FROM portrayal_decisions").fetchone()[0],
                "learning_patterns": conn.execute("SELECT COUNT(*) FROM learning_patterns").fetchone()[0],
                "brain_entities": conn.execute("SELECT COUNT(*) FROM brain_entities").fetchone()[0],
                "brain_events": conn.execute("SELECT COUNT(*) FROM brain_events").fetchone()[0],
                "discovery_candidates": conn.execute("SELECT COUNT(*) FROM discovery_candidates").fetchone()[0],
                "pending_approvals": conn.execute(
                    "SELECT COUNT(*) FROM approvals WHERE status = 'pending'"
                ).fetchone()[0],
                "open_followups": conn.execute(
                    f"SELECT COUNT(*) FROM followups WHERE lower(COALESCE(status, '')) NOT IN {ACTION_CLOSED_SQL}"
                ).fetchone()[0],
                "open_progress_items": conn.execute(
                    f"SELECT COUNT(*) FROM progress_items WHERE lower(COALESCE(status, '')) NOT IN {ACTION_CLOSED_SQL}"
                ).fetchone()[0],
                "failed_agent_runs": conn.execute(
                    "SELECT COUNT(*) FROM agent_runs WHERE status = 'failed'"
                ).fetchone()[0],
            }
            stale_records = {
                "unattached_followups": [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT * FROM followups
                        WHERE job_id IS NULL
                          AND contact_id IS NULL
                          AND lower(COALESCE(status, '')) NOT IN {ACTION_CLOSED_SQL}
                        ORDER BY updated_at DESC
                        LIMIT 20
                        """
                    ).fetchall()
                ],
                "unattached_agent_runs": [
                    decode_agent_run(row)
                    for row in conn.execute(
                        """
                        SELECT * FROM agent_runs
                        WHERE job_id IS NULL
                        ORDER BY updated_at DESC
                        LIMIT 20
                        """
                    ).fetchall()
                ],
                "tool_calls_without_run": [
                    decode_tool_call_summary(row)
                    for row in conn.execute(
                        """
                        SELECT id, run_id, tool_name, status, created_at,
                               length(CAST(input AS BLOB)) AS input_bytes,
                               length(CAST(output AS BLOB)) AS output_bytes
                        FROM tool_calls
                        WHERE run_id IS NULL
                        ORDER BY created_at DESC
                        LIMIT 20
                        """
                    ).fetchall()
                ],
            }
        actionable = len(stale_records["unattached_followups"]) + len(stale_records["unattached_agent_runs"])
        recommendations = []
        if stale_records["unattached_followups"]:
            recommendations.append("Review unattached follow-ups before starting a real opportunity.")
        if stale_records["unattached_agent_runs"]:
            recommendations.append("Review unattached agent runs; they usually come from interrupted local prep.")
        if stale_records["tool_calls_without_run"]:
            recommendations.append("Tool calls without a run can be normal for direct API/tool use.")
        return {
            "status": "needs_attention" if actionable else "ok",
            "counts": counts,
            "stale_records": stale_records,
            "recommendations": recommendations,
        }

    def record_event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        status = payload.get("status")
        next_action = payload.get("next_action")
        with self._connect() as conn:
            updates = ["updated_at = ?"]
            params: list[Any] = [now]
            if status:
                updates.insert(0, "status = ?")
                params.insert(0, status)
            if next_action is not None:
                updates.insert(0, "next_action = ?")
                params.insert(0, str(next_action))
            if payload.get("hermes_run_id"):
                updates.insert(0, "hermes_run_id = ?")
                params.insert(0, payload["hermes_run_id"])
            if payload.get("hermes_session_id"):
                updates.insert(0, "hermes_session_id = ?")
                params.insert(0, payload["hermes_session_id"])
            params.append(job_id)
            cursor = conn.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", tuple(params))
            if cursor.rowcount == 0:
                raise KeyError(job_id)
            conn.execute(
                "INSERT INTO events (job_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (job_id, event_type, json.dumps(payload), now),
            )
            self._record_brain_event_conn(
                conn,
                event_type="application_event",
                title=event_type.replace("_", " "),
                content=json.dumps(payload, indent=2, sort_keys=True),
                job_id=job_id,
                entity_type="job_search",
                entity_title=event_type.replace("_", " "),
                source=payload.get("source") or "app_event",
                confidence=0.75,
                importance=0.55,
                occurred_at=now,
                hermes_run_id=payload.get("hermes_run_id") or None,
                hermes_session_id=payload.get("hermes_session_id") or None,
                metadata={"job_event_type": event_type},
            )
        return self.get_job(job_id)

    def upsert_brain_entity(
        self,
        entity_type: str,
        title: str,
        *,
        slug: str = "",
        summary: str = "",
        status: str = "active",
        privacy: str = "private",
        source: str = "agent",
        confidence: float = 0.8,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = self._upsert_brain_entity_conn(
                conn,
                entity_type=entity_type,
                title=title,
                slug=slug,
                summary=summary,
                status=status,
                privacy=privacy,
                source=source,
                confidence=confidence,
                metadata=metadata or {},
            )
        return decode_brain_entity(row)

    def record_brain_event(
        self,
        event_type: str,
        title: str,
        content: str,
        *,
        entity_type: str = "job_search",
        entity_name: str = "",
        entity_slug: str = "",
        entity_id: str | None = None,
        job_id: str | None = None,
        source: str = "agent",
        evidence_text: str = "",
        confidence: float = 0.8,
        importance: float = 0.5,
        occurred_at: str | None = None,
        hermes_session_id: str | None = None,
        hermes_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = self._record_brain_event_conn(
                conn,
                event_type=event_type,
                title=title,
                content=content,
                entity_type=entity_type,
                entity_title=entity_name,
                entity_slug=entity_slug,
                entity_id=entity_id,
                job_id=job_id,
                source=source,
                evidence_text=evidence_text,
                confidence=confidence,
                importance=importance,
                occurred_at=occurred_at,
                hermes_session_id=hermes_session_id,
                hermes_run_id=hermes_run_id,
                metadata=metadata or {},
            )
        return decode_brain_event(row)

    def list_brain_entities(self, entity_type: str | None = None, *, limit: int = 80) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if entity_type:
            where = "WHERE entity_type = ?"
            params.append(normalize_brain_entity_type(entity_type))
        params.append(bounded_limit(limit, default=80, maximum=500))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM brain_entities {where} ORDER BY updated_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [decode_brain_entity(row) for row in rows]

    def list_brain_events(
        self,
        *,
        entity_type: str | None = None,
        event_type: str | None = None,
        job_id: str | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        rows = self._select_brain_events(
            entity_type=entity_type,
            event_type=event_type,
            job_id=job_id,
            limit=limit,
        )
        return [decode_brain_event(row) for row in rows]

    def search_brain(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        event_type: str | None = None,
        job_id: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        normalized_query = normalize_search_query(query)
        result_limit = bounded_limit(limit, default=12, maximum=80)
        fts_query = fts_query_for(normalized_query)
        rows: list[sqlite3.Row] = []
        mode = "fts5"
        with self._connect() as conn:
            clauses, params = brain_event_filters(entity_type=entity_type, event_type=event_type, job_id=job_id)
            if fts_query:
                fts_clauses = ["brain_events_fts MATCH ?"] + clauses
                try:
                    rows = conn.execute(
                        f"""
                        SELECT e.*, be.entity_type, be.slug AS entity_slug,
                               be.title AS entity_title, be.summary AS entity_summary,
                               bm25(brain_events_fts) AS rank
                        FROM brain_events_fts
                        JOIN brain_events e ON e.id = brain_events_fts.event_id
                        LEFT JOIN brain_entities be ON be.id = e.entity_id
                        WHERE {' AND '.join(fts_clauses)}
                        ORDER BY rank
                        LIMIT ?
                        """,
                        tuple([fts_query] + params + [result_limit]),
                    ).fetchall()
                except sqlite3.OperationalError:
                    mode = "keyword_fallback"
            if not fts_query or mode == "keyword_fallback":
                rows = conn.execute(
                    f"""
                    SELECT e.*, be.entity_type, be.slug AS entity_slug,
                           be.title AS entity_title, be.summary AS entity_summary,
                           0.0 AS rank
                    FROM brain_events e
                    LEFT JOIN brain_entities be ON be.id = e.entity_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY e.importance DESC, e.occurred_at DESC
                    LIMIT ?
                    """,
                    tuple(params + [result_limit * 3]),
                ).fetchall()
        events = [decode_brain_event(row) for row in rows]
        if mode == "keyword_fallback" and normalized_query:
            terms = set(keywords_for_text(normalized_query))
            events = sorted(
                [
                    item | {"rank": -len(terms & set(keywords_for_text(brain_event_corpus(item))))}
                    for item in events
                ],
                key=lambda item: item.get("rank", 0),
            )
        return {
            "query": query,
            "retrieval_mode": mode,
            "filters": {
                "entity_type": entity_type or "any",
                "event_type": event_type or "any",
                "job_id": job_id or "any",
            },
            "events": events[:result_limit],
        }

    def brain_context(self, *, query: str = "", limit: int = 12) -> dict[str, Any]:
        result_limit = bounded_limit(limit, default=12, maximum=80)
        recent_events = self.list_brain_events(limit=result_limit)
        search = self.search_brain(query, limit=result_limit) if query else None
        with self._connect() as conn:
            entity_counts = {
                row["entity_type"]: row["count"]
                for row in conn.execute(
                    """
                    SELECT entity_type, COUNT(*) AS count
                    FROM brain_entities
                    GROUP BY entity_type
                    ORDER BY count DESC, entity_type
                    """
                ).fetchall()
            }
            event_counts = {
                row["event_type"]: row["count"]
                for row in conn.execute(
                    """
                    SELECT event_type, COUNT(*) AS count
                    FROM brain_events
                    GROUP BY event_type
                    ORDER BY count DESC, event_type
                    """
                ).fetchall()
            }
        return {
            "entity_counts": entity_counts,
            "event_counts": event_counts,
            "recent_events": recent_events,
            "search": search,
            "policy": {
                "source_of_truth": "JobApps SQLite career brain",
                "shape": "entity registry plus immutable event ledger",
                "hermes_memory_role": "durable preferences and lessons; app DB keeps job-search facts and provenance",
            },
        }

    def count_brain_entities(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM brain_entities").fetchone()[0])

    def count_brain_events(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM brain_events").fetchone()[0])

    def upsert_profile_fact(
        self,
        fact_key: str,
        value: str,
        category: str = "profile",
        source: str = "manual",
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        now = utc_now()
        fact_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO profile_facts (id, fact_key, value, category, source, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fact_key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                (fact_id, fact_key, value, category, source, confidence, now, now),
            )
            self._record_brain_event_conn(
                conn,
                event_type="profile_fact_updated",
                title=fact_key,
                content=value,
                entity_type=profile_category_to_brain_type(category),
                entity_title=fact_key,
                source=source,
                confidence=confidence,
                importance=0.74 if profile_category_to_brain_type(category) in {"identity", "constraint"} else 0.58,
                occurred_at=now,
                metadata={"fact_key": fact_key, "category": category},
            )
        return self.get_profile_fact(fact_key)

    def get_profile_fact(self, fact_key: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM profile_facts WHERE fact_key = ?", (fact_key,)).fetchone()
        if row is None:
            raise KeyError(fact_key)
        return dict(row)

    def list_profile_facts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM profile_facts ORDER BY category, fact_key").fetchall()
        return [dict(row) for row in rows]

    def upsert_proof_point(
        self,
        label: str,
        summary: str,
        evidence: str,
        role_family: str = "other",
        tags: list[str] | None = None,
        source: str = "manual",
        confidence: float = 1.0,
        proof_id: str | None = None,
        status: str = "active",
        user_confirmed: bool = True,
        narrative_version: str = "current",
        allowed_uses: list[str] | None = None,
        risk_level: str = "safe",
        valid_from: str | None = None,
        valid_to: str | None = None,
        superseded_by: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        item_id = proof_id or uuid.uuid4().hex[:12]
        allowed = allowed_uses or ["resume", "cover_letter", "interview", "outreach"]
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM proof_points WHERE id = ?", (item_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE proof_points
                    SET label = ?, role_family = ?, summary = ?, evidence = ?, tags = ?,
                        source = ?, confidence = ?, status = ?, user_confirmed = ?,
                        narrative_version = ?, allowed_uses = ?, risk_level = ?,
                        valid_from = ?, valid_to = ?, superseded_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        label,
                        role_family,
                        summary,
                        evidence,
                        json.dumps(tags or []),
                        source,
                        confidence,
                        normalize_proof_status(status),
                        1 if user_confirmed else 0,
                        narrative_version or "current",
                        json.dumps(allowed),
                        risk_level or "safe",
                        valid_from,
                        valid_to,
                        superseded_by,
                        now,
                        item_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO proof_points (
                        id, label, role_family, summary, evidence, tags, source, confidence,
                        status, user_confirmed, narrative_version, allowed_uses, risk_level,
                        valid_from, valid_to, superseded_by, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        label,
                        role_family,
                        summary,
                        evidence,
                        json.dumps(tags or []),
                        source,
                        confidence,
                        normalize_proof_status(status),
                        1 if user_confirmed else 0,
                        narrative_version or "current",
                        json.dumps(allowed),
                        risk_level or "safe",
                        valid_from,
                        valid_to,
                        superseded_by,
                        now,
                        now,
                    ),
                )
            row = conn.execute("SELECT * FROM proof_points WHERE id = ?", (item_id,)).fetchone()
            self._sync_proof_point_chunk_conn(conn, decode_proof_point(row))
            self._record_brain_event_conn(
                conn,
                event_type="proof_point_updated",
                title=label,
                content=f"{summary}\n\nEvidence: {evidence}",
                entity_type="proof_point",
                entity_title=label,
                source=source,
                confidence=confidence,
                importance=0.76,
                occurred_at=now,
                metadata={
                    "proof_id": item_id,
                    "role_family": role_family,
                    "status": normalize_proof_status(status),
                    "user_confirmed": bool(user_confirmed),
                    "allowed_uses": allowed,
                },
            )
        return self.get_proof_point(item_id)

    def update_proof_point_lifecycle(
        self,
        proof_id: str,
        *,
        status: str | None = None,
        user_confirmed: bool | None = None,
        narrative_version: str | None = None,
        allowed_uses: list[str] | None = None,
        risk_level: str | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        superseded_by: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM proof_points WHERE id = ?", (proof_id,)).fetchone()
            if current is None:
                raise KeyError(proof_id)
            current_item = decode_proof_point(current)
            merged = {
                "status": normalize_proof_status(status or current_item.get("status") or "active"),
                "user_confirmed": current_item.get("user_confirmed", True) if user_confirmed is None else bool(user_confirmed),
                "narrative_version": narrative_version if narrative_version is not None else current_item.get("narrative_version", "current"),
                "allowed_uses": allowed_uses if allowed_uses is not None else current_item.get("allowed_uses", []),
                "risk_level": risk_level if risk_level is not None else current_item.get("risk_level", "safe"),
                "valid_from": valid_from if valid_from is not None else current_item.get("valid_from"),
                "valid_to": valid_to if valid_to is not None else current_item.get("valid_to"),
                "superseded_by": superseded_by if superseded_by is not None else current_item.get("superseded_by"),
            }
            conn.execute(
                """
                UPDATE proof_points
                SET status = ?, user_confirmed = ?, narrative_version = ?, allowed_uses = ?,
                    risk_level = ?, valid_from = ?, valid_to = ?, superseded_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["status"],
                    1 if merged["user_confirmed"] else 0,
                    merged["narrative_version"] or "current",
                    json.dumps(merged["allowed_uses"] or []),
                    merged["risk_level"] or "safe",
                    merged["valid_from"],
                    merged["valid_to"],
                    merged["superseded_by"],
                    now,
                    proof_id,
                ),
            )
            row = conn.execute("SELECT * FROM proof_points WHERE id = ?", (proof_id,)).fetchone()
            self._sync_proof_point_chunk_conn(conn, decode_proof_point(row))
            self._record_brain_event_conn(
                conn,
                event_type="proof_lifecycle_updated",
                title=current_item.get("label") or proof_id,
                content=reason or f"Proof lifecycle updated to {merged['status']}.",
                entity_type="proof_point",
                entity_title=current_item.get("label") or proof_id,
                source="agent",
                confidence=0.85,
                importance=0.72,
                occurred_at=now,
                metadata={"proof_id": proof_id, **merged},
            )
        return self.get_proof_point(proof_id)

    def get_proof_point(self, proof_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proof_points WHERE id = ?", (proof_id,)).fetchone()
        if row is None:
            raise KeyError(proof_id)
        return decode_proof_point(row)

    def validate_proof_for_use(self, proof_id: str | None, use: str) -> None:
        if not proof_id:
            return
        with self._connect() as conn:
            _validate_eligible_proof(conn, proof_id, use)

    def list_proof_points(
        self,
        role_family: str | None = None,
        *,
        include_inactive: bool = False,
        use: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if role_family:
            clauses.append("role_family IN (?, 'other', '')")
            params.append(role_family)
        if not include_inactive:
            clauses.append("status = 'active'")
            clauses.append("user_confirmed = 1")
            clauses.append("(superseded_by IS NULL OR superseded_by = '')")
            if use:
                clauses.append("(allowed_uses = '[]' OR allowed_uses = '' OR allowed_uses LIKE ?)")
                params.append(f'%"{use}"%')
        elif use:
            clauses.append("(allowed_uses = '[]' OR allowed_uses = '' OR allowed_uses LIKE ?)")
            params.append(f'%"{use}"%')
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "confidence DESC, updated_at DESC" if role_family else "role_family, label"
        query = "SELECT * FROM proof_points"
        if where:
            query += f" {where}"
        query += f" ORDER BY {order}"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [decode_proof_point(row) for row in rows]

    def record_application_signal(
        self,
        job_id: str,
        signal_type: str,
        label: str,
        value: str,
        *,
        evidence_text: str = "",
        source: str = "local_evaluation",
        confidence: float = 0.7,
        actionability: str = "medium",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        signal_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() or (_raise_key(job_id))
            conn.execute(
                """
                INSERT INTO application_signals (
                    id, job_id, signal_type, label, value, evidence_text, source,
                    confidence, actionability, metadata, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    job_id,
                    signal_type,
                    label,
                    value,
                    evidence_text,
                    source,
                    confidence,
                    actionability,
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM application_signals WHERE id = ?", (signal_id,)).fetchone()
        return decode_application_signal(row)

    def list_application_signals(self, job_id: str | None = None, *, limit: int = 120) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if job_id:
            where = "WHERE job_id = ?"
            params.append(job_id)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM application_signals {where} ORDER BY created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [decode_application_signal(row) for row in rows]

    def upsert_discovery_candidate(
        self,
        candidate: dict[str, Any],
        *,
        sighting: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        dedupe_key = str(candidate.get("dedupe_key") or "").strip()
        if not dedupe_key:
            raise ValueError("Discovery candidate requires a dedupe_key.")
        raw_payload = candidate.get("raw_payload", {})
        blocker_reasons = candidate.get("blocker_reasons", [])
        with self._connect() as conn:
            current = conn.execute(
                "SELECT * FROM discovery_candidates WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            if current is None:
                candidate_id = uuid.uuid4().hex[:12]
                values = _discovery_insert_values(candidate, candidate_id, dedupe_key, now)
                conn.execute(
                    """
                    INSERT INTO discovery_candidates (
                        id, dedupe_key, source_type, source_provider, status,
                        title, company, location, canonical_url, discovered_url, apply_url,
                        posted_at, remote_updated_at, retrieved_at, workplace_type,
                        employment_type, compensation, description, application_form_summary,
                        blocker_status, blocker_reasons, source_confidence, discovery_query,
                        raw_payload, job_id, created_at, updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    values,
                )
            else:
                candidate_id = current["id"]
                merged = _merge_discovery_candidate(dict(current), candidate)
                conn.execute(
                    """
                    UPDATE discovery_candidates
                    SET source_type = ?, source_provider = ?, status = ?,
                        title = ?, company = ?, location = ?, canonical_url = ?,
                        discovered_url = ?, apply_url = ?, posted_at = ?,
                        remote_updated_at = ?, retrieved_at = ?, workplace_type = ?,
                        employment_type = ?, compensation = ?, description = ?,
                        application_form_summary = ?, blocker_status = ?,
                        blocker_reasons = ?, source_confidence = ?, discovery_query = ?,
                        raw_payload = ?, job_id = COALESCE(NULLIF(?, ''), job_id),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        merged["source_type"],
                        merged["source_provider"],
                        merged["status"],
                        merged["title"],
                        merged["company"],
                        merged["location"],
                        merged["canonical_url"],
                        merged["discovered_url"],
                        merged["apply_url"],
                        merged["posted_at"],
                        merged["remote_updated_at"],
                        merged["retrieved_at"],
                        merged["workplace_type"],
                        merged["employment_type"],
                        merged["compensation"],
                        merged["description"],
                        merged["application_form_summary"],
                        merged["blocker_status"],
                        json.dumps(blocker_reasons if "blocker_reasons" in candidate else json.loads(current["blocker_reasons"] or "[]")),
                        merged["source_confidence"],
                        merged["discovery_query"],
                        json.dumps(raw_payload if "raw_payload" in candidate else json.loads(current["raw_payload"] or "{}")),
                        merged["job_id"],
                        now,
                        candidate_id,
                    ),
                )
            if sighting:
                self._record_discovery_sighting_conn(conn, candidate_id, sighting, now)
            row = conn.execute("SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return decode_discovery_candidate(row)

    def get_discovery_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            candidate = decode_discovery_candidate(row)
            sightings = conn.execute(
                """
                SELECT * FROM discovery_sightings
                WHERE candidate_id = ?
                ORDER BY seen_at DESC
                LIMIT 20
                """,
                (candidate_id,),
            ).fetchall()
        candidate["sightings"] = [decode_discovery_sighting(item) for item in sightings]
        candidate["sighting_count"] = len(candidate["sightings"])
        return candidate

    def list_discovery_candidates(
        self,
        *,
        status: str | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status and status != "all":
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(bounded_limit(limit, default=80, maximum=300))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT c.*,
                       COUNT(s.id) AS sighting_count,
                       MAX(s.seen_at) AS latest_seen_at
                FROM discovery_candidates c
                LEFT JOIN discovery_sightings s ON s.candidate_id = c.id
                {where}
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [decode_discovery_candidate(row) for row in rows]

    def update_discovery_candidate(
        self,
        candidate_id: str,
        *,
        status: str | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            if status:
                conn.execute(
                    "UPDATE discovery_candidates SET status = ?, updated_at = ? WHERE id = ?",
                    (normalize_discovery_status(status), now, candidate_id),
                )
            if note:
                self._record_discovery_sighting_conn(
                    conn,
                    candidate_id,
                    {
                        "source_type": "app",
                        "source_provider": "jobapps",
                        "title": "candidate note",
                        "snippet": note,
                    },
                    now,
                )
            updated = conn.execute("SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return decode_discovery_candidate(updated)

    def link_discovery_candidate_job(self, candidate_id: str, job_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() or (_raise_key(job_id))
            conn.execute("SELECT id FROM discovery_candidates WHERE id = ?", (candidate_id,)).fetchone() or (_raise_key(candidate_id))
            conn.execute(
                """
                UPDATE discovery_candidates
                SET job_id = ?, status = 'prepared', updated_at = ?
                WHERE id = ?
                """,
                (job_id, now, candidate_id),
            )
            self._record_discovery_sighting_conn(
                conn,
                candidate_id,
                {
                    "source_type": "app",
                    "source_provider": "jobapps",
                    "title": "prepared opportunity",
                    "snippet": f"Promoted into JobApps job {job_id}.",
                },
                now,
            )
        return self.get_discovery_candidate(candidate_id)

    def discovery_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM discovery_candidates
                GROUP BY status
                """
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM discovery_candidates").fetchone()[0]
        output = {row["status"]: int(row["count"]) for row in rows}
        output["total"] = int(total)
        return output

    def _record_discovery_sighting_conn(
        self,
        conn: sqlite3.Connection,
        candidate_id: str,
        sighting: dict[str, Any],
        seen_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO discovery_sightings (
                id, candidate_id, source_type, source_provider, discovered_url,
                discovery_query, title, snippet, raw_payload, seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex[:12],
                candidate_id,
                sighting.get("source_type") or "manual",
                sighting.get("source_provider") or "unknown",
                sighting.get("discovered_url") or "",
                sighting.get("discovery_query") or "",
                sighting.get("title") or "",
                sighting.get("snippet") or "",
                json.dumps(sighting.get("raw_payload") or {}),
                seen_at,
            ),
        )

    def record_evaluation_signals(self, job_id: str, evaluation: dict[str, Any]) -> list[dict[str, Any]]:
        facts = evaluation.get("facts") or {}
        signals: list[dict[str, Any]] = []
        for signal_type, key, evidence_key in (
            ("sponsorship", "sponsorship_risk", "sponsorship_evidence"),
            ("location", "location_risk", "location_evidence"),
            ("seniority", "seniority_risk", "seniority_evidence"),
            ("effort", "effort_risk", "effort_evidence"),
        ):
            value = str(evaluation.get(key) or facts.get(key) or "unknown")
            signals.append(
                self.record_application_signal(
                    job_id,
                    signal_type,
                    value,
                    value,
                    evidence_text=str(facts.get(evidence_key) or ""),
                    confidence=0.9 if value not in {"unknown", ""} else 0.55,
                    actionability="high" if signal_type in {"sponsorship", "seniority"} else "medium",
                )
            )
        role_family = str(evaluation.get("role_family") or "other")
        signals.append(
            self.record_application_signal(
                job_id,
                "role_family",
                role_family,
                role_family,
                evidence_text=str(evaluation.get("strongest_angle") or ""),
                confidence=0.78,
                actionability="high",
            )
        )
        for requirement in evaluation.get("top_requirements", []) or []:
            signals.append(
                self.record_application_signal(
                    job_id,
                    "requirement",
                    truncate_signal_label(str(requirement)),
                    str(requirement),
                    evidence_text=str(requirement),
                    confidence=0.72,
                    actionability="high",
                    metadata={"role_family": role_family},
                )
            )
        if evaluation.get("evaluation_mode") != "blocker_preflight":
            for match in evaluation.get("must_have_matches", []) or []:
                if match.get("strength") in {"weak", "gap"}:
                    signals.append(
                        self.record_application_signal(
                            job_id,
                            "gap",
                            truncate_signal_label(str(match.get("requirement") or "gap")),
                            str(match.get("requirement") or ""),
                            evidence_text=str(match.get("risk") or "Needs stronger evidence."),
                            confidence=float(match.get("confidence") or 0.4),
                            actionability="high",
                            metadata={"proof_id": match.get("proof_id"), "strength": match.get("strength")},
                        )
                    )
        return signals

    def search_evidence(
        self,
        query: str,
        *,
        role_family: str | None = None,
        use: str = "resume",
        limit: int = 8,
        include_inactive: bool = False,
    ) -> dict[str, Any]:
        normalized_query = normalize_search_query(query)
        result_limit = bounded_limit(limit)
        eligibility = {
            "status": ["active"] if not include_inactive else ["active", "candidate", "needs_review", "superseded", "retired", "forbidden", "archived"],
            "user_confirmed": True if not include_inactive else "any",
            "allowed_use": use,
            "role_family": role_family or "any",
            "exclude_superseded": not include_inactive,
            "rank_limit_applied_after_eligibility": True,
        }
        rows: list[sqlite3.Row] = []
        retrieval_mode = "fts5"
        with self._connect() as conn:
            fts_query = fts_query_for(normalized_query)
            clauses, params = retrieval_sql_filters(
                alias="c",
                role_family=role_family,
                use=use,
                include_inactive=include_inactive,
            )
            if fts_query:
                clauses = ["retrieval_chunks_fts MATCH ?"] + clauses
                query_params: list[Any] = [fts_query] + params + [result_limit]
                try:
                    rows = conn.execute(
                        f"""
                        SELECT c.*, bm25(retrieval_chunks_fts) AS rank
                        FROM retrieval_chunks_fts
                        JOIN retrieval_chunks c ON c.id = retrieval_chunks_fts.chunk_id
                        WHERE {' AND '.join(clauses)}
                        ORDER BY rank
                        LIMIT ?
                        """,
                        tuple(query_params),
                    ).fetchall()
                except sqlite3.OperationalError:
                    retrieval_mode = "keyword_fallback"
                    fallback_clauses, fallback_params = retrieval_sql_filters(
                        alias="retrieval_chunks",
                        role_family=role_family,
                        use=use,
                        include_inactive=include_inactive,
                    )
                    rows = conn.execute(
                        f"""
                        SELECT *, 0.0 AS rank
                        FROM retrieval_chunks
                        WHERE {' AND '.join(fallback_clauses)}
                        ORDER BY updated_at DESC
                        """,
                        tuple(fallback_params),
                    ).fetchall()
            else:
                plain_clauses, plain_params = retrieval_sql_filters(
                    alias="retrieval_chunks",
                    role_family=role_family,
                    use=use,
                    include_inactive=include_inactive,
                )
                rows = conn.execute(
                    f"""
                    SELECT *, 0.0 AS rank
                    FROM retrieval_chunks
                    WHERE {' AND '.join(plain_clauses)}
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    tuple(plain_params + [result_limit]),
                ).fetchall()
        candidates = [decode_retrieval_chunk(row) for row in rows]
        if retrieval_mode == "keyword_fallback":
            terms = set(keywords_for_text(normalized_query))
            candidates = sorted(
                [item | {"rank": -len(terms & set(keywords_for_text(item["text"])))} for item in candidates],
                key=lambda item: item.get("rank", 0),
            )[:result_limit]
        eligible = []
        for item in candidates:
            if item.get("source_table") != "proof_points":
                continue
            if not include_inactive and not chunk_is_eligible(item, role_family=role_family, use=use):
                continue
            if include_inactive and use and use not in item.get("allowed_uses", []) and item.get("allowed_uses"):
                continue
            try:
                source = self.get_proof_point(item["source_id"])
            except KeyError:
                continue
            eligible.append(
                {
                    "chunk_id": item["id"],
                    "text": item["text"],
                    "rank": item.get("rank", 0),
                    "source": source,
                    "why": evidence_reason(query, source),
                }
            )
            if len(eligible) >= result_limit:
                break
        return {
            "query": query,
            "retrieval_mode": retrieval_mode,
            "eligibility_filter": eligibility,
            "results": eligible,
        }

    def retrieve_for_job(self, job_id: str, *, use: str = "resume", limit: int = 8) -> dict[str, Any]:
        record = self.get_job(job_id)
        job = record["job"]
        evaluation = record.get("evaluation") or {}
        role_family = evaluation.get("role_family") or job.get("role_family")
        requirements = evaluation.get("top_requirements") or []
        query = " ".join(requirements) or " ".join(
            [str(job.get("title") or ""), str(job.get("description") or "")]
        )
        search = self.search_evidence(query, role_family=role_family, use=use, limit=limit)
        excluded = self._excluded_evidence_for(query, role_family=role_family, use=use, limit=20)
        if search["results"]:
            now = utc_now()
            proof_ids = [item["source"]["id"] for item in search["results"]]
            with self._connect() as conn:
                conn.executemany(
                    "UPDATE proof_points SET last_used_at = ?, usage_count = usage_count + 1 WHERE id = ?",
                    [(now, proof_id) for proof_id in proof_ids],
                )
        return {
            "job_id": job_id,
            "job": job,
            "policy": "active_user_confirmed_first",
            "query": query,
            "requirements": requirements,
            "signals": self.list_application_signals(job_id),
            "evidence": search["results"],
            "excluded": excluded,
            "eligibility_filter": search["eligibility_filter"],
            "retrieval_mode": search["retrieval_mode"],
        }

    def _excluded_evidence_for(
        self,
        query: str,
        *,
        role_family: str | None = None,
        use: str = "resume",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        terms = set(keywords_for_text(query))
        excluded: list[dict[str, Any]] = []
        for proof in self.list_proof_points(role_family=role_family, include_inactive=True):
            if chunk_is_eligible(proof_to_chunk_like(proof), role_family=role_family, use=use):
                continue
            overlap = terms & set(keywords_for_text(proof_corpus_for_repo(proof)))
            if not overlap and role_family and proof.get("role_family") != role_family:
                continue
            reason = proof_exclusion_reason(proof, use=use)
            excluded.append(
                {
                    "id": proof["id"],
                    "label": proof["label"],
                    "status": proof.get("status"),
                    "user_confirmed": proof.get("user_confirmed"),
                    "narrative_version": proof.get("narrative_version"),
                    "superseded_by": proof.get("superseded_by"),
                    "reason": reason,
                    "overlap": sorted(overlap),
                }
            )
            if len(excluded) >= limit:
                break
        return excluded

    def _sync_proof_point_chunk_conn(self, conn: sqlite3.Connection, proof: dict[str, Any]) -> None:
        text = proof_corpus_for_repo(proof)
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        now = utc_now()
        existing = conn.execute(
            "SELECT id FROM retrieval_chunks WHERE source_table = ? AND source_id = ? AND chunk_type = ?",
            ("proof_points", proof["id"], "proof_point"),
        ).fetchone()
        chunk_id = existing["id"] if existing else uuid.uuid4().hex[:12]
        params = (
            chunk_id,
            "proof_points",
            proof["id"],
            "proof_point",
            text,
            json.dumps(proof.get("tags", [])),
            proof.get("role_family", "other"),
            proof.get("status", "active"),
            1 if proof.get("user_confirmed", True) else 0,
            proof.get("narrative_version", "current"),
            json.dumps(proof.get("allowed_uses", [])),
            proof.get("risk_level", "safe"),
            proof.get("valid_from"),
            proof.get("valid_to"),
            proof.get("superseded_by"),
            checksum,
            now,
            now,
        )
        conn.execute(
            """
            INSERT INTO retrieval_chunks (
                id, source_table, source_id, chunk_type, text, tags, role_family, status,
                user_confirmed, narrative_version, allowed_uses, risk_level, valid_from,
                valid_to, superseded_by, checksum, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_table, source_id, chunk_type) DO UPDATE SET
                text = excluded.text,
                tags = excluded.tags,
                role_family = excluded.role_family,
                status = excluded.status,
                user_confirmed = excluded.user_confirmed,
                narrative_version = excluded.narrative_version,
                allowed_uses = excluded.allowed_uses,
                risk_level = excluded.risk_level,
                valid_from = excluded.valid_from,
                valid_to = excluded.valid_to,
                superseded_by = excluded.superseded_by,
                checksum = excluded.checksum,
                updated_at = excluded.updated_at
            """,
            params,
        )
        conn.execute("DELETE FROM retrieval_chunks_fts WHERE chunk_id = ?", (chunk_id,))
        conn.execute(
            "INSERT INTO retrieval_chunks_fts(chunk_id, text, tags) VALUES (?, ?, ?)",
            (chunk_id, text, " ".join(proof.get("tags", []))),
        )

    def career_context(self, *, use: str | None = "resume") -> dict[str, Any]:
        return {
            "profile_facts": self.list_profile_facts(),
            "proof_points": self.list_proof_points(use=use),
            "recent_jobs": self.list_jobs(limit=12),
            "learning_patterns": self.list_learning_patterns(limit=40),
            "brain_context": self.brain_context(limit=12),
            "recent_tailoring_requirements": self.list_tailoring_requirements(limit=40),
            "recent_portrayal_decisions": self.list_portrayal_decisions(limit=40),
            "proof_filter": {"use": use, "policy": "active_user_confirmed_not_superseded"},
        }

    def create_agent_run(
        self,
        objective: str,
        *,
        job_id: str | None = None,
        kind: str = "local_prepare",
        prompt_id: str | None = None,
        hermes_run_id: str = "",
        hermes_session_id: str = "",
        status: str = "running",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        run_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_runs (
                    id, job_id, kind, objective, status, prompt_id, hermes_run_id,
                    hermes_session_id, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    job_id,
                    kind,
                    objective,
                    status,
                    prompt_id,
                    hermes_run_id,
                    hermes_session_id,
                    json.dumps(metadata or {}),
                    now,
                    now,
                ),
            )
        return {
            "id": run_id,
            "job_id": job_id,
            "kind": kind,
            "objective": objective,
            "status": status,
            "prompt_id": prompt_id,
            "hermes_run_id": hermes_run_id,
            "hermes_session_id": hermes_session_id,
            "output": None,
            "error": None,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }

    def create_hermes_run_unless_active(
        self,
        objective: str,
        *,
        job_id: str,
        prompt_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> tuple[dict[str, Any], bool]:
        """Atomically create a Hermes run unless the job already has an active one."""

        now = utc_now()
        run_id = uuid.uuid4().hex[:12]
        encoded_metadata = json.dumps(metadata or {})
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                f"""
                SELECT * FROM agent_runs
                WHERE job_id = ?
                  AND kind = 'hermes_run'
                  AND status IN {ACTIVE_HERMES_RUN_SQL}
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if existing is not None:
                return decode_agent_run(existing), False
            conn.execute(
                """
                INSERT INTO agent_runs (
                    id, job_id, kind, objective, status, prompt_id, hermes_run_id,
                    hermes_session_id, metadata, created_at, updated_at
                )
                VALUES (?, ?, 'hermes_run', ?, ?, ?, '', '', ?, ?, ?)
                """,
                (run_id, job_id, objective, status, prompt_id, encoded_metadata, now, now),
            )
            row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return decode_agent_run(row), True

    def update_agent_run(
        self,
        run_id: str,
        *,
        job_id: str | None = None,
        prompt_id: str | None = None,
        status: str | None = None,
        hermes_run_id: str = "",
        hermes_session_id: str = "",
        output: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
            if current is None:
                raise KeyError(run_id)
            merged_metadata = json.loads(current["metadata"] or "{}")
            if metadata:
                merged_metadata.update(metadata)
            conn.execute(
                """
                UPDATE agent_runs
                SET status = COALESCE(?, status),
                    job_id = COALESCE(?, job_id),
                    prompt_id = COALESCE(?, prompt_id),
                    hermes_run_id = COALESCE(NULLIF(?, ''), hermes_run_id),
                    hermes_session_id = COALESCE(NULLIF(?, ''), hermes_session_id),
                    output = COALESCE(?, output),
                    error = COALESCE(?, error),
                    metadata = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    job_id,
                    prompt_id,
                    hermes_run_id,
                    hermes_session_id,
                    output,
                    error,
                    json.dumps(merged_metadata),
                    now,
                    run_id,
                ),
            )
            row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return decode_agent_run(row)

    def finish_agent_run(self, run_id: str, status: str = "completed") -> dict[str, Any]:
        return self.update_agent_run(run_id, status=status)

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            events = conn.execute(
                "SELECT * FROM agent_run_events WHERE run_id = ? ORDER BY created_at DESC, id DESC",
                (run_id,),
            ).fetchall()
            tool_calls = conn.execute(
                "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY created_at DESC",
                (run_id,),
            ).fetchall()
        item = decode_agent_run(row)
        item["events"] = [decode_agent_run_event(event) for event in events]
        item["tool_calls"] = [decode_tool_call(call) for call in tool_calls]
        return item

    def list_agent_runs(self, job_id: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if job_id:
                rows = conn.execute(
                    "SELECT * FROM agent_runs WHERE job_id = ? ORDER BY updated_at DESC LIMIT ?",
                    (job_id, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM agent_runs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [decode_agent_run(row) for row in rows]

    def get_active_hermes_run_for_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT * FROM agent_runs
                WHERE job_id = ?
                  AND kind = 'hermes_run'
                  AND status IN {ACTIVE_HERMES_RUN_SQL}
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return decode_agent_run(row) if row else None

    def record_agent_run_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_run_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (run_id, event_type, json.dumps(payload), now),
            )
            row = conn.execute("SELECT * FROM agent_run_events WHERE rowid = last_insert_rowid()").fetchone()
        return decode_agent_run_event(row)

    def record_tool_call(
        self,
        tool_name: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        status: str = "completed",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        call_id = uuid.uuid4().hex[:12]
        input_json, output_json = self._stored_tool_call_payloads(
            call_id,
            tool_name,
            input_payload,
            output_payload,
            status=status,
            run_id=run_id,
            created_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_calls (id, run_id, tool_name, input, output, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id,
                    run_id,
                    tool_name,
                    input_json,
                    output_json,
                    status,
                    now,
                ),
            )
        return {
            "id": call_id,
            "run_id": run_id,
            "tool_name": tool_name,
            "input": input_payload,
            "output": output_payload,
            "status": status,
            "created_at": now,
        }

    def _stored_tool_call_payloads(
        self,
        call_id: str,
        tool_name: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        *,
        status: str,
        run_id: str | None,
        created_at: str,
    ) -> tuple[str, str]:
        input_json = json.dumps(input_payload)
        output_json = json.dumps(output_payload)
        total_bytes = len(input_json.encode("utf-8")) + len(output_json.encode("utf-8"))
        if total_bytes <= TOOL_CALL_INLINE_LIMIT_BYTES:
            return input_json, output_json

        archive_path = self._archive_tool_call_payload(
            call_id,
            tool_name,
            input_payload,
            output_payload,
            status=status,
            run_id=run_id,
            created_at=created_at,
            input_bytes=len(input_json.encode("utf-8")),
            output_bytes=len(output_json.encode("utf-8")),
        )
        marker = _tool_call_archive_marker(
            archive_path,
            input_bytes=len(input_json.encode("utf-8")),
            output_bytes=len(output_json.encode("utf-8")),
            inline_limit_bytes=TOOL_CALL_INLINE_LIMIT_BYTES,
        )
        return json.dumps(marker | {"payload": "input"}), json.dumps(marker | {"payload": "output"})

    def _archive_tool_call_payload(
        self,
        call_id: str,
        tool_name: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any],
        *,
        status: str,
        run_id: str | None,
        created_at: str,
        input_bytes: int,
        output_bytes: int,
    ) -> str:
        archive_root = self.path.parent / TOOL_CALL_ARCHIVE_ROOT.name
        archive_root.mkdir(parents=True, exist_ok=True)
        safe_tool = re.sub(r"[^a-zA-Z0-9_.-]+", "_", tool_name).strip("_") or "tool"
        safe_date = created_at[:10] if created_at else "unknown-date"
        archive_path = archive_root / f"{safe_date}-{call_id}-{safe_tool}.json.gz"
        payload = {
            "id": call_id,
            "run_id": run_id,
            "tool_name": tool_name,
            "status": status,
            "created_at": created_at,
            "input_bytes": input_bytes,
            "output_bytes": output_bytes,
            "input": input_payload,
            "output": output_payload,
        }
        with gzip.open(archive_path, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
        return str(archive_path)

    def list_tool_calls(self, run_id: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if run_id:
                rows = conn.execute(
                    "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY created_at DESC LIMIT ?",
                    (run_id, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tool_calls ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        output = []
        for row in rows:
            output.append(decode_tool_call(row))
        return output

    def tool_call_retention_report(self, *, retain_days: int = 30, limit: int = 20) -> dict[str, Any]:
        retain_days = max(1, int(retain_days or 30))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).isoformat()
        payload_size_sql = "length(CAST(input AS BLOB)) + length(CAST(output AS BLOB))"
        with self._connect() as conn:
            total = conn.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(length(CAST(input AS BLOB)) + length(CAST(output AS BLOB))), 0) AS bytes
                FROM tool_calls
                """
            ).fetchone()
            old = conn.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(length(CAST(input AS BLOB)) + length(CAST(output AS BLOB))), 0) AS bytes
                FROM tool_calls
                WHERE created_at < ?
                """,
                (cutoff,),
            ).fetchone()
            oversized = conn.execute(
                f"""
                SELECT COUNT(*) AS count, COALESCE(SUM({payload_size_sql}), 0) AS bytes
                FROM tool_calls
                WHERE {payload_size_sql} > ?
                """,
                (TOOL_CALL_INLINE_LIMIT_BYTES,),
            ).fetchone()
            largest = [
                decode_tool_call_summary(row)
                for row in conn.execute(
                    """
                    SELECT id, run_id, tool_name, status, created_at,
                           length(CAST(input AS BLOB)) AS input_bytes,
                           length(CAST(output AS BLOB)) AS output_bytes
                    FROM tool_calls
                    ORDER BY length(CAST(input AS BLOB)) + length(CAST(output AS BLOB)) DESC
                    LIMIT ?
                    """,
                    (bounded_limit(limit, default=20, maximum=100),),
                ).fetchall()
            ]
            by_tool = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT tool_name, COUNT(*) AS count,
                           COALESCE(SUM(length(CAST(input AS BLOB)) + length(CAST(output AS BLOB))), 0) AS bytes
                    FROM tool_calls
                    GROUP BY tool_name
                    ORDER BY bytes DESC
                    LIMIT 20
                    """
                ).fetchall()
            ]
        return {
            "retain_days": retain_days,
            "cutoff": cutoff,
            "total": {"count": int(total["count"]), "bytes": int(total["bytes"])},
            "older_than_cutoff": {"count": int(old["count"]), "bytes": int(old["bytes"])},
            "oversized_inline": {
                "min_bytes": TOOL_CALL_INLINE_LIMIT_BYTES,
                "count": int(oversized["count"]),
                "bytes": int(oversized["bytes"]),
            },
            "largest": largest,
            "by_tool": by_tool,
            "policy": {
                "core_state": "jobs, materials, contacts, proof points, decisions, follow-ups, progress, and learning patterns are retained",
                "audit_payloads": "large tool call input/output JSON is archived to compressed local files before inline SQLite cleanup",
                "default_mode": "dry_run",
            },
        }

    def archive_old_tool_calls(
        self,
        *,
        retain_days: int = 30,
        limit: int = 100,
        min_bytes: int | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        retain_days = max(1, int(retain_days or 30))
        row_limit = bounded_limit(limit, default=100, maximum=2000)
        min_bytes = int(min_bytes) if min_bytes is not None else None
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).isoformat()
        payload_size_sql = "length(CAST(input AS BLOB)) + length(CAST(output AS BLOB))"
        if min_bytes is None:
            where_sql = "created_at < ?"
            params: tuple[Any, ...] = (cutoff, row_limit)
        else:
            where_sql = f"(created_at < ? OR {payload_size_sql} > ?)"
            params = (cutoff, max(1, min_bytes), row_limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM tool_calls
                WHERE {where_sql}
                ORDER BY created_at
                LIMIT ?
                """,
                params,
            ).fetchall()
            candidates = [row for row in rows if not _tool_call_row_archived(row)]
            summaries = [decode_tool_call_summary(row) for row in candidates]
            if dry_run:
                return {
                    "dry_run": True,
                    "retain_days": retain_days,
                    "cutoff": cutoff,
                    "min_bytes": min_bytes,
                    "candidate_count": len(candidates),
                    "candidate_bytes": sum(item.get("input_bytes", 0) + item.get("output_bytes", 0) for item in summaries),
                    "candidates": summaries,
                }
            archived = []
            for row in candidates:
                item = decode_tool_call(row)
                input_json = json.dumps(item["input"])
                output_json = json.dumps(item["output"])
                archive_path = self._archive_tool_call_payload(
                    item["id"],
                    item["tool_name"],
                    item["input"],
                    item["output"],
                    status=item["status"],
                    run_id=item.get("run_id"),
                    created_at=item["created_at"],
                    input_bytes=len(input_json.encode("utf-8")),
                    output_bytes=len(output_json.encode("utf-8")),
                )
                marker = _tool_call_archive_marker(
                    archive_path,
                    input_bytes=len(input_json.encode("utf-8")),
                    output_bytes=len(output_json.encode("utf-8")),
                    inline_limit_bytes=TOOL_CALL_INLINE_LIMIT_BYTES,
                )
                conn.execute(
                    "UPDATE tool_calls SET input = ?, output = ? WHERE id = ?",
                    (
                        json.dumps(marker | {"payload": "input"}),
                        json.dumps(marker | {"payload": "output"}),
                        item["id"],
                    ),
                )
                archived.append(decode_tool_call_summary(row) | {"archive_path": archive_path})
        return {
            "dry_run": False,
            "retain_days": retain_days,
            "cutoff": cutoff,
            "min_bytes": min_bytes,
            "archived_count": len(archived),
            "archived_bytes": sum(item.get("input_bytes", 0) + item.get("output_bytes", 0) for item in archived),
            "archived": archived,
            "next_step": "Run SQLite VACUUM during maintenance if you need the database file itself to shrink after archiving.",
        }

    def _upsert_brain_entity_conn(
        self,
        conn: sqlite3.Connection,
        *,
        entity_type: str,
        title: str,
        slug: str = "",
        summary: str = "",
        status: str = "active",
        privacy: str = "private",
        source: str = "agent",
        confidence: float = 0.8,
        metadata: dict[str, Any] | None = None,
    ) -> sqlite3.Row:
        now = utc_now()
        normalized_type = normalize_brain_entity_type(entity_type)
        safe_title = normalize_space_for_db(title) or normalized_type.replace("_", " ")
        safe_slug = slugify_brain_slug(slug or safe_title)
        existing = conn.execute(
            "SELECT * FROM brain_entities WHERE entity_type = ? AND slug = ?",
            (normalized_type, safe_slug),
        ).fetchone()
        merged_metadata = json.loads(existing["metadata"] or "{}") if existing else {}
        if metadata:
            merged_metadata.update(metadata)
        entity_id = existing["id"] if existing else uuid.uuid4().hex[:12]
        if existing:
            conn.execute(
                """
                UPDATE brain_entities
                SET title = ?, summary = COALESCE(NULLIF(?, ''), summary),
                    status = ?, privacy = ?, source = ?, confidence = ?,
                    metadata = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    safe_title,
                    summary or "",
                    normalize_brain_status(status),
                    privacy or "private",
                    source or "agent",
                    float(confidence),
                    json.dumps(merged_metadata),
                    now,
                    entity_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO brain_entities (
                    id, entity_type, slug, title, summary, status, privacy,
                    source, confidence, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    normalized_type,
                    safe_slug,
                    safe_title,
                    summary or "",
                    normalize_brain_status(status),
                    privacy or "private",
                    source or "agent",
                    float(confidence),
                    json.dumps(merged_metadata),
                    now,
                    now,
                ),
            )
        row = conn.execute("SELECT * FROM brain_entities WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            raise KeyError(entity_id)
        return row

    def _record_brain_event_conn(
        self,
        conn: sqlite3.Connection,
        *,
        event_type: str,
        title: str,
        content: str,
        entity_type: str = "job_search",
        entity_title: str = "",
        entity_slug: str = "",
        entity_id: str | None = None,
        job_id: str | None = None,
        source: str = "agent",
        evidence_text: str = "",
        confidence: float = 0.8,
        importance: float = 0.5,
        occurred_at: str | None = None,
        hermes_session_id: str | None = None,
        hermes_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> sqlite3.Row:
        now = utc_now()
        if job_id:
            conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() or (_raise_key(job_id))
        entity_row = None
        if entity_id:
            entity_row = conn.execute("SELECT * FROM brain_entities WHERE id = ?", (entity_id,)).fetchone()
            if entity_row is None:
                raise KeyError(entity_id)
        elif entity_title or entity_slug or entity_type:
            entity_row = self._upsert_brain_entity_conn(
                conn,
                entity_type=entity_type or "job_search",
                title=entity_title or title or event_type,
                slug=entity_slug,
                source=source,
                confidence=confidence,
                metadata={"last_event_type": normalize_brain_event_type(event_type)},
            )
            entity_id = entity_row["id"]
        event_id = uuid.uuid4().hex[:12]
        normalized_event_type = normalize_brain_event_type(event_type)
        safe_title = normalize_space_for_db(title) or normalized_event_type.replace("_", " ")
        safe_content = str(content or "").strip()
        occurred = occurred_at or now
        conn.execute(
            """
            INSERT INTO brain_events (
                id, entity_id, job_id, event_type, title, content, source,
                evidence_text, confidence, importance, occurred_at,
                hermes_session_id, hermes_run_id, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                entity_id,
                job_id,
                normalized_event_type,
                safe_title,
                safe_content,
                source or "agent",
                evidence_text or "",
                float(confidence),
                max(0.0, min(1.0, float(importance))),
                occurred,
                hermes_session_id,
                hermes_run_id,
                json.dumps(metadata or {}),
                now,
            ),
        )
        entity_title_for_index = entity_row["title"] if entity_row else ""
        conn.execute("DELETE FROM brain_events_fts WHERE event_id = ?", (event_id,))
        conn.execute(
            """
            INSERT INTO brain_events_fts(event_id, entity_title, title, content, evidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, entity_title_for_index, safe_title, safe_content, evidence_text or ""),
        )
        row = conn.execute(
            """
            SELECT e.*, be.entity_type, be.slug AS entity_slug,
                   be.title AS entity_title, be.summary AS entity_summary,
                   0.0 AS rank
            FROM brain_events e
            LEFT JOIN brain_entities be ON be.id = e.entity_id
            WHERE e.id = ?
            """,
            (event_id,),
        ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return row

    def _select_brain_events(
        self,
        *,
        entity_type: str | None = None,
        event_type: str | None = None,
        job_id: str | None = None,
        limit: int = 80,
    ) -> list[sqlite3.Row]:
        clauses, params = brain_event_filters(entity_type=entity_type, event_type=event_type, job_id=job_id)
        params.append(bounded_limit(limit, default=80, maximum=500))
        with self._connect() as conn:
            return conn.execute(
                f"""
                SELECT e.*, be.entity_type, be.slug AS entity_slug,
                       be.title AS entity_title, be.summary AS entity_summary,
                       0.0 AS rank
                FROM brain_events e
                LEFT JOIN brain_entities be ON be.id = e.entity_id
                WHERE {' AND '.join(clauses)}
                ORDER BY e.occurred_at DESC, e.created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()


def _material_content(material: dict[str, Any] | None) -> str:
    if not material:
        return ""
    return str(material.get("content") or "")


def _latest_run_output(agent_runs: list[dict[str, Any]]) -> str:
    for run in agent_runs:
        output = run.get("output")
        if output:
            return str(output)
    return ""


def _materials_workbench(materials: list[dict[str, Any]], revisions: list[dict[str, Any]]) -> dict[str, Any]:
    revision_counts: dict[str, int] = {}
    latest_revision: dict[str, dict[str, Any]] = {}
    for revision in revisions:
        material_id = revision.get("material_id")
        if not material_id:
            continue
        revision_counts[material_id] = revision_counts.get(material_id, 0) + 1
        latest_revision.setdefault(material_id, revision)

    items = []
    primary: dict[str, Any] = {}
    for material in materials:
        summary = _material_summary(material, revision_counts, latest_revision)
        items.append(summary)
        kind = material.get("kind") or "material"
        primary[kind] = summary
        if kind == "resume_tailoring" and "resume" not in primary:
            primary["resume"] = summary
    return {
        "items": items,
        "primary": primary,
        "revision_count": len(revisions),
        "can_compile": any(item.get("format") in {"tex", "typ"} for item in items),
        "note": "Materials are app-owned artifacts. External use still requires approval.",
    }


def _material_summary(
    material: dict[str, Any],
    revision_counts: dict[str, int],
    latest_revision: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metadata = material.get("metadata") or {}
    compile_info = metadata.get("compile") or {}
    pdf_path = _material_existing_pdf_path(material)
    compile_status = "compiled" if pdf_path else "not_compiled"
    material_id = material.get("id", "")
    filename = _material_display_name(material)
    content_preview = "" if material.get("format") == "tex" else str(material.get("content") or "")[:4000]
    return {
        "id": material_id,
        "kind": material.get("kind", ""),
        "format": material.get("format", ""),
        "display_name": filename,
        "filename": filename,
        "file_path": material.get("file_path", ""),
        "path": material.get("file_path", ""),
        "rationale": material.get("rationale", ""),
        "source": material.get("source", ""),
        "revision_count": revision_counts.get(material_id, 0),
        "latest_revision": latest_revision.get(material_id),
        "compile_status": compile_status,
        "pdf_path": pdf_path,
        "log_path": compile_info.get("log_path", ""),
        "content_preview": content_preview,
        "has_content": bool(material.get("content")),
        "updated_at": material.get("updated_at", ""),
    }


def _material_existing_pdf_path(material: dict[str, Any]) -> str:
    metadata = material.get("metadata") or {}
    compile_info = metadata.get("compile") or {}
    content_metadata = material_payload_metadata(material.get("content"))
    candidates = [
        compile_info.get("pdf_path"),
        metadata.get("pdf_path"),
        content_metadata.get("pdf_path"),
    ]
    file_path = str(material.get("file_path") or "")
    if file_path:
        source_path = Path(file_path).expanduser()
        if source_path.suffix.lower() == ".pdf":
            candidates.append(str(source_path))
        if source_path.suffix.lower() in {".tex", ".ltx", ".typ", ".typst"}:
            candidates.append(str(source_path.with_suffix(".pdf")))
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser()
        if path.exists() and path.is_file():
            return str(path)
    return ""


def _material_display_name(material: dict[str, Any]) -> str:
    metadata = material.get("metadata") or {}
    content_metadata = material_payload_metadata(material.get("content"))
    for key in ("display_name", "filename", "name"):
        if metadata.get(key):
            return Path(str(metadata[key])).name
    file_path = str(material.get("file_path") or "")
    if file_path:
        return Path(file_path).name
    pdf_path = str((metadata.get("compile") or {}).get("pdf_path") or metadata.get("pdf_path") or content_metadata.get("pdf_path") or "")
    if pdf_path:
        return Path(pdf_path).name
    if metadata.get("subject"):
        return str(metadata["subject"])
    extension = material.get("format") or "txt"
    kind = str(material.get("kind") or "material")
    return f"{kind}.{extension}"


def _dashboard_outreach(
    materials: list[dict[str, Any]],
    contacts: list[dict[str, Any]],
    followups: list[dict[str, Any]],
) -> dict[str, Any]:
    contact_by_id = {item.get("id"): item for item in contacts if item.get("id")}
    drafts = []
    for material in materials:
        if material.get("kind") not in {"outreach", "outreach_draft", "linkedin_draft", "email_draft"}:
            continue
        metadata = material.get("metadata") or {}
        contact_id = metadata.get("contact_id") or ""
        drafts.append(
            {
                "id": material.get("id", ""),
                "kind": material.get("kind", ""),
                "subject": metadata.get("subject") or _material_display_name(material),
                "channel": metadata.get("channel") or ("email" if metadata.get("to_email") else "linkedin"),
                "to_email": metadata.get("to_email") or "",
                "contact_id": contact_id,
                "contact": contact_by_id.get(contact_id),
                "display_name": _material_display_name(material),
                "content_preview": str(material.get("content") or "")[:500],
                "created_at": material.get("created_at", ""),
                "updated_at": material.get("updated_at", ""),
                "material_url": f"/api/materials/{material.get('id', '')}/file" if material.get("file_path") else "",
            }
        )
    return {
        "drafts": drafts,
        "contacts": contacts,
        "followups": [dict(item) for item in followups],
        "draft_count": len(drafts),
        "contact_count": len(contacts),
        "followup_count": len(followups),
    }


def _dashboard_risks(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    risk_items = []
    for area, key in (
        ("sponsorship", "sponsorship_risk"),
        ("location", "location_risk"),
        ("seniority", "seniority_risk"),
        ("effort", "effort_risk"),
    ):
        value = evaluation.get(key)
        if value:
            risk_items.append({
                "area": area,
                "label": area,
                "assessment": value,
                "severity": _risk_level(value),
                "level": _risk_level(value),
            })
    for item in evaluation.get("risks", []) or []:
        if isinstance(item, str):
            level = _risk_level(item)
            risk_items.append({"area": "risk", "label": "risk", "assessment": item, "severity": level, "level": level})
            continue
        area = item.get("type") or item.get("area") or item.get("label") or "risk"
        assessment = item.get("evidence") or item.get("assessment") or item.get("value") or ""
        level = item.get("level") or _risk_level(str(item.get("risk", assessment)))
        risk_items.append({"area": area, "label": area, "assessment": assessment, "severity": level, "level": level})
    return risk_items


def _risk_level(value: str) -> str:
    normalized = str(value).lower()
    if normalized in {"clear", "low", "ok"}:
        return "low"
    if normalized in {"blocker", "high", "reject"}:
        return "high"
    return "medium"


def _dashboard_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    event_type = event.get("event_type", "event")
    description = payload.get("note") or payload.get("description") or payload.get("decision") or event_type
    return {
        "event_type": event_type,
        "description": description,
        "summary": description,
        "note": description,
        "payload": payload,
        "created_at": event.get("created_at", ""),
    }


def _job_state_counts(jobs: list[dict[str, Any]]) -> dict[str, int]:
    counts = {bucket: 0 for bucket in JOB_STATE_BUCKETS}
    for job in jobs:
        bucket = str(job.get("state_bucket") or "new")
        counts[bucket if bucket in counts else "new"] += 1
    return counts


def _dashboard_job_state(
    job: dict[str, Any],
    events: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    progress: list[dict[str, Any]],
    followups: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
) -> dict[str, Any]:
    bucket = _job_state_bucket(job)
    dates = {
        "new": job.get("created_at") or "",
        "applied": _latest_state_transition(events, "applied"),
        "skip": _latest_state_transition(events, "skip"),
        "updated": job.get("updated_at") or "",
    }
    if bucket == "applied" and not dates["applied"]:
        dates["applied"] = dates["updated"] or dates["new"]
    if bucket == "skip" and not dates["skip"]:
        dates["skip"] = dates["updated"] or dates["new"]
    dates["current"] = dates.get(bucket) or dates["updated"] or dates["new"]
    return {
        "bucket": bucket,
        "label": {"new": "New", "applied": "Applied", "skip": "Skip"}[bucket],
        "dates": dates,
        "last_activity_at": _latest_timestamp(
            [job],
            "updated_at",
            "created_at",
            extra_items=[events, materials, progress, followups, approvals],
        ),
        "open_action_count": _open_action_count(progress, followups, approvals),
        "needs_material_review": _needs_material_review(job, progress, approvals),
    }


def _job_state_bucket(job: dict[str, Any]) -> str:
    status = str(job.get("status") or "new").strip().lower().replace("-", "_")
    if status in JOB_SKIP_STATUSES:
        return "skip"
    if status in JOB_APPLIED_STATUSES:
        return "applied"
    return "new"


def _needs_material_review(
    job: dict[str, Any],
    progress: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
) -> bool:
    status = str(job.get("status") or "").strip().lower()
    if status in MATERIAL_REVIEW_STATUSES:
        return True
    for item in progress:
        kind = str(item.get("kind") or "").strip().lower()
        item_status = str(item.get("status") or "").strip().lower()
        if kind == "material_review" and item_status not in ACTION_RESOLVED_STATUSES:
            return True
    for item in approvals:
        action = str(item.get("action") or "").strip().lower()
        item_status = str(item.get("status") or "").strip().lower()
        if action in MATERIAL_REVIEW_APPROVAL_ACTIONS and item_status not in ACTION_RESOLVED_STATUSES:
            return True
    return False


def _open_action_count(
    progress: list[dict[str, Any]],
    followups: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
) -> int:
    rows = [*_purposeful_progress_rows(progress), *followups, *_purposeful_approval_rows(approvals)]
    return sum(1 for item in rows if str(item.get("status") or "").strip().lower() not in ACTION_RESOLVED_STATUSES)


def _raise_if_review_progress_action(title: str, kind: str) -> None:
    clean_kind = str(kind or "").strip().lower()
    clean_title = str(title or "").strip()
    title_key = normalize_action_title(clean_title)
    if clean_kind in REVIEW_PROGRESS_KINDS or (
        any(term in title_key for term in REVIEW_PROGRESS_TERMS)
        and any(obj in title_key for obj in REVIEW_PROGRESS_OBJECTS)
    ):
        raise ValueError(
            "Review/material-review work is not a dashboard Action. "
            "Save material state, revisions, metadata, or events instead."
        )


def _raise_if_review_approval_action(action: str) -> None:
    clean_action = str(action or "").strip().lower()
    if clean_action.startswith("review") or clean_action in NON_ACTION_APPROVAL_ACTIONS:
        raise ValueError(
            "Review approvals are not dashboard Actions. "
            "Use material metadata/events for review state; create approvals only for real external sends/actions."
        )


def _purposeful_progress_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _is_purposeful_progress_action(row)]


def _purposeful_approval_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _is_purposeful_approval_action(row)]


def _is_purposeful_approval_action(item: dict[str, Any]) -> bool:
    action = str(item.get("action") or "").strip().lower()
    if not action or action in NON_ACTION_APPROVAL_ACTIONS:
        return False
    text = " ".join(
        str(part or "")
        for part in [
            action,
            (item.get("payload") or {}).get("reason") if isinstance(item.get("payload"), dict) else "",
        ]
    ).lower()
    return any(term in text for term in PURPOSEFUL_ACTION_TERMS)


def _is_purposeful_progress_action(item: dict[str, Any]) -> bool:
    kind = str(item.get("kind") or "").strip().lower()
    text = f"{item.get('title') or ''} {item.get('notes') or ''}".lower()
    if kind in {"material_review", "research", "application"}:
        return False
    if (
        "find networking target" in text
        or "run quick company" in text
        or "sponsorship research" in text
        or "outreach batch" in text
        or text.strip().startswith("build ")
    ):
        return False
    if kind == "follow_up":
        return True
    if kind == "networking" and any(term in text for term in PURPOSEFUL_ACTION_TERMS):
        return True
    return any(term in text for term in ("send follow", "send email", "email ", "message ", "contact "))


def _latest_state_transition(events: list[dict[str, Any]], target_bucket: str) -> str:
    dates: list[str] = []
    for event in events:
        payload = event.get("payload") or {}
        bucket = _event_status_bucket(payload.get("status"))
        if bucket == target_bucket and event.get("created_at"):
            dates.append(str(event["created_at"]))
    return max(dates) if dates else ""


def _event_status_bucket(status: Any) -> str:
    value = str(status or "").strip().lower().replace("-", "_")
    if value in JOB_SKIP_STATUSES:
        return "skip"
    if value in JOB_APPLIED_STATUSES:
        return "applied"
    return "new"


def _latest_timestamp(
    items: list[dict[str, Any]],
    *keys: str,
    extra_items: list[list[dict[str, Any]]] | None = None,
) -> str:
    values: list[str] = []
    for item in items:
        values.extend(str(item.get(key) or "") for key in keys if item.get(key))
    for group in extra_items or []:
        for item in group:
            values.extend(str(item.get(key) or "") for key in keys if item.get(key))
    return max(values) if values else ""


def decode_tailoring_requirement(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    return item


def decode_portrayal_decision(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    return item


def decode_learning_pattern(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    return item


def decode_application_signal(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    return item


def decode_contact(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["raw_payload"] = json.loads(item.get("raw_payload") or "{}")
    item["source_confidence"] = float(item.get("source_confidence") or 0)
    item["email_status"] = normalize_email_status(item.get("email_status") or ("found" if item.get("email") else "missing"))
    return item


def decode_discovery_candidate(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["blocker_reasons"] = json.loads(item.get("blocker_reasons") or "[]")
    item["raw_payload"] = json.loads(item.get("raw_payload") or "{}")
    item["source_confidence"] = float(item.get("source_confidence") or 0)
    if "sighting_count" in item:
        item["sighting_count"] = int(item.get("sighting_count") or 0)
    return item


def decode_discovery_sighting(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["raw_payload"] = json.loads(item.get("raw_payload") or "{}")
    return item


def normalize_discovery_status(status: str) -> str:
    allowed = {
        "new",
        "hydrated",
        "needs_review",
        "ready",
        "approved",
        "blocked",
        "dismissed",
        "prepared",
        "stale",
        "duplicate",
    }
    value = str(status or "new").strip().lower()
    if value not in allowed:
        raise ValueError(f"Unsupported discovery status: {status}")
    return value


def _discovery_insert_values(candidate: dict[str, Any], candidate_id: str, dedupe_key: str, now: str) -> tuple[Any, ...]:
    return (
        candidate_id,
        dedupe_key,
        candidate.get("source_type") or "manual",
        candidate.get("source_provider") or "unknown",
        normalize_discovery_status(candidate.get("status") or "new"),
        candidate.get("title") or "",
        candidate.get("company") or "",
        candidate.get("location") or "",
        candidate.get("canonical_url") or "",
        candidate.get("discovered_url") or "",
        candidate.get("apply_url") or "",
        candidate.get("posted_at") or "",
        candidate.get("remote_updated_at") or "",
        candidate.get("retrieved_at") or now,
        candidate.get("workplace_type") or "",
        candidate.get("employment_type") or "",
        candidate.get("compensation") or "",
        candidate.get("description") or "",
        candidate.get("application_form_summary") or "",
        candidate.get("blocker_status") or "unknown",
        json.dumps(candidate.get("blocker_reasons") or []),
        float(candidate.get("source_confidence") or 0.5),
        candidate.get("discovery_query") or "",
        json.dumps(candidate.get("raw_payload") or {}),
        candidate.get("job_id") or None,
        now,
        now,
    )


def _merge_discovery_candidate(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key in (
        "source_type",
        "source_provider",
        "title",
        "company",
        "location",
        "canonical_url",
        "discovered_url",
        "apply_url",
        "posted_at",
        "remote_updated_at",
        "retrieved_at",
        "workplace_type",
        "employment_type",
        "compensation",
        "description",
        "application_form_summary",
        "blocker_status",
        "discovery_query",
        "job_id",
    ):
        value = incoming.get(key)
        if value not in (None, ""):
            merged[key] = value
    if "status" in incoming and incoming.get("status"):
        merged["status"] = _merge_discovery_status(str(current.get("status") or "new"), str(incoming["status"]))
    if "source_confidence" in incoming:
        merged["source_confidence"] = max(float(current.get("source_confidence") or 0), float(incoming.get("source_confidence") or 0))
    return merged


def _merge_discovery_status(current: str, incoming: str) -> str:
    current = normalize_discovery_status(current)
    incoming = normalize_discovery_status(incoming)
    precedence = {
        "prepared": 90,
        "dismissed": 85,
        "blocked": 70,
        "ready": 60,
        "needs_review": 50,
        "hydrated": 40,
        "new": 30,
        "stale": 20,
        "duplicate": 10,
    }
    return incoming if precedence[incoming] >= precedence[current] else current


def _merge_contact(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key in (
        "name",
        "company",
        "role",
        "email",
        "linkedin_url",
        "source_url",
        "source_provider",
        "channel",
        "relationship",
        "notes",
    ):
        value = incoming.get(key)
        if value not in (None, ""):
            merged[key] = value
    if "source_confidence" in incoming:
        merged["source_confidence"] = max(float(current.get("source_confidence") or 0), float(incoming.get("source_confidence") or 0))
    merged["email_status"] = strongest_email_status(
        current.get("email_status") or ("found" if current.get("email") else "missing"),
        incoming.get("email_status") or ("found" if incoming.get("email") else "unknown"),
    )
    if incoming.get("raw_payload"):
        merged["raw_payload"] = incoming["raw_payload"]
    elif isinstance(merged.get("raw_payload"), str):
        merged["raw_payload"] = json.loads(merged.get("raw_payload") or "{}")
    return merged


def decode_brain_entity(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    return item


def decode_brain_event(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    entity = None
    if item.get("entity_id"):
        entity = {
            "id": item.get("entity_id"),
            "type": item.pop("entity_type", None),
            "slug": item.pop("entity_slug", None),
            "title": item.pop("entity_title", None),
            "summary": item.pop("entity_summary", None),
        }
    else:
        item.pop("entity_type", None)
        item.pop("entity_slug", None)
        item.pop("entity_title", None)
        item.pop("entity_summary", None)
    item["entity"] = entity
    return item


def decode_retrieval_chunk(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tags"] = json.loads(item.get("tags") or "[]")
    item["allowed_uses"] = json.loads(item.get("allowed_uses") or "[]")
    item["user_confirmed"] = bool(item.get("user_confirmed"))
    return item


def decode_proof_point(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tags"] = json.loads(item.get("tags") or "[]")
    item["allowed_uses"] = json.loads(
        item.get("allowed_uses") or '["resume", "cover_letter", "interview", "outreach"]'
    )
    item["user_confirmed"] = bool(item.get("user_confirmed", 1))
    item.setdefault("status", "active")
    item.setdefault("narrative_version", "current")
    item.setdefault("risk_level", "safe")
    item.setdefault("usage_count", 0)
    return item


def normalize_proof_status(status: str) -> str:
    allowed = {"candidate", "active", "needs_review", "superseded", "retired", "forbidden", "archived"}
    value = str(status or "active").strip().lower()
    if value not in allowed:
        raise ValueError(f"Unsupported proof point lifecycle status: {status}")
    return value


def normalize_brain_entity_type(entity_type: str) -> str:
    value = re.sub(r"[^a-z0-9_]+", "_", str(entity_type or "job_search").strip().lower()).strip("_")
    aliases = {
        "constraints": "constraint",
        "people": "person",
        "companies": "company",
        "proof_points": "proof_point",
        "decisions": "decision",
        "projects": "project",
        "job_search": "job_search",
        "job_searches": "job_search",
        "daily": "daily",
        "identity": "identity",
    }
    return aliases.get(value, value or "other")


def normalize_brain_event_type(event_type: str) -> str:
    value = re.sub(r"[^a-z0-9_]+", "_", str(event_type or "note").strip().lower()).strip("_")
    return value or "note"


def normalize_brain_status(status: str) -> str:
    value = str(status or "active").strip().lower()
    if value in {"active", "archived", "merged", "stale", "needs_review"}:
        return value
    return "active"


def profile_category_to_brain_type(category: str) -> str:
    value = normalize_brain_entity_type(category)
    if value in {"identity", "constraint", "job_search", "preference", "project", "daily"}:
        return value
    if "constraint" in value or "sponsorship" in value or "authorization" in value:
        return "constraint"
    if "identity" in value or "profile" in value:
        return "identity"
    if "voice" in value or "preference" in value or "style" in value:
        return "preference"
    return "job_search"


def slugify_brain_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:96] or "untitled"


def normalize_space_for_db(value: str) -> str:
    return " ".join(str(value or "").split())


def normalize_material_format_for_db(value: Any) -> str:
    material_format = str(value or "text").strip().lower()
    if material_format in {"latex", "ltx"}:
        return "tex"
    if material_format == "typst":
        return "typ"
    if material_format == "plain":
        return "text"
    return material_format or "text"


def normalize_material_kind_for_db(
    value: Any,
    *,
    format: str = "",
    file_path: str = "",
    content: Any = None,
) -> str:
    kind = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    aliases = {
        "resume_typst_final": "resume",
        "resume_tex_final": "resume",
        "resume_pdf_final": "resume",
        "resume_final": "resume",
        "final_resume": "resume",
        "compiled_resume": "resume",
        "upload_resume": "resume",
        "uploadable_resume": "resume",
        "cover_letter_final": "cover_letter",
        "final_cover_letter": "cover_letter",
        "compiled_cover_letter": "cover_letter",
    }
    if kind in aliases:
        return aliases[kind]
    if kind.startswith("resume_") and any(token in kind for token in ("final", "compiled", "upload")):
        return "resume"
    if kind.startswith("cover") and any(token in kind for token in ("final", "compiled", "upload")):
        return "cover_letter"
    if not kind and (format == "pdf" or str(file_path).lower().endswith(".pdf")):
        content_metadata = material_payload_metadata(content)
        source = " ".join(str(content_metadata.get(key) or "") for key in ("source_format", "source_path", "pdf_path"))
        if "resume" in source.lower():
            return "resume"
    return kind or "material"


def material_payload_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text or text[0] not in "{[":
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _find_existing_job_for_create(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    title: str,
    company: str,
    url: str,
    description: str,
) -> str:
    if job_id:
        row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is not None:
            return str(row["id"])

    normalized_url = normalize_job_url_for_match(url)
    title_key = normalize_space_for_db(title).casefold()
    company_key = normalize_space_for_db(company).casefold()
    description_key = normalize_job_description_for_match(description)
    if normalized_url:
        rows = conn.execute(
            "SELECT id, title, company, url, description FROM jobs WHERE COALESCE(url, '') <> '' ORDER BY updated_at DESC"
        ).fetchall()
        for row in rows:
            if normalize_job_url_for_match(row["url"]) == normalized_url:
                same_title_company = (
                    title_key
                    and company_key
                    and normalize_space_for_db(row["title"]).casefold() == title_key
                    and normalize_space_for_db(row["company"]).casefold() == company_key
                )
                same_description = (
                    description_key
                    and normalize_job_description_for_match(row["description"]) == description_key
                )
                if same_title_company or same_description:
                    return str(row["id"])

    if not title_key or not company_key or not description_key:
        return ""
    rows = conn.execute(
        """
        SELECT id, description
        FROM jobs
        WHERE lower(title) = lower(?) AND lower(company) = lower(?)
        ORDER BY updated_at DESC, created_at DESC
        """,
        (title, company),
    ).fetchall()
    for row in rows:
        if normalize_job_description_for_match(row["description"]) == description_key:
            return str(row["id"])
    return ""


def normalize_job_url_for_match(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.rstrip("/").casefold()


def normalize_job_description_for_match(value: str) -> str:
    text = normalize_space_for_db(value).casefold()
    return text if len(text) >= 80 else ""


def normalize_action_title(value: str) -> str:
    return normalize_space_for_db(value).casefold()


def normalize_email_status(status: str) -> str:
    value = str(status or "unknown").strip().lower().replace("-", "_")
    if value in {"found", "missing", "unverified", "unknown"}:
        return value
    return "unverified"


def strongest_email_status(current: str, incoming: str) -> str:
    precedence = {"unknown": 0, "missing": 1, "unverified": 2, "found": 3}
    current_status = normalize_email_status(current)
    incoming_status = normalize_email_status(incoming)
    return incoming_status if precedence[incoming_status] >= precedence[current_status] else current_status


def brain_event_filters(
    *,
    entity_type: str | None = None,
    event_type: str | None = None,
    job_id: str | None = None,
) -> tuple[list[str], list[Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if entity_type:
        clauses.append("be.entity_type = ?")
        params.append(normalize_brain_entity_type(entity_type))
    if event_type:
        clauses.append("e.event_type = ?")
        params.append(normalize_brain_event_type(event_type))
    if job_id:
        clauses.append("e.job_id = ?")
        params.append(job_id)
    return clauses, params


def brain_event_corpus(event: dict[str, Any]) -> str:
    entity = event.get("entity") or {}
    return " ".join(
        [
            str(event.get("title", "")),
            str(event.get("content", "")),
            str(event.get("evidence_text", "")),
            str(event.get("event_type", "")),
            str(entity.get("title", "")),
            str(entity.get("type", "")),
        ]
    )


def _provenance_use(value: str) -> str:
    normalized = str(value or "").lower()
    if "cover" in normalized or "letter" in normalized:
        return "cover_letter"
    if "outreach" in normalized or "network" in normalized:
        return "outreach"
    if "interview" in normalized:
        return "interview"
    return "resume"


def _validate_eligible_proof(conn: sqlite3.Connection, proof_id: str, use: str) -> None:
    row = conn.execute("SELECT * FROM proof_points WHERE id = ?", (proof_id,)).fetchone()
    if row is None:
        _raise_key(proof_id)
    proof = decode_proof_point(row)
    allowed_uses = proof.get("allowed_uses") or []
    allowed_for_use = not allowed_uses or use in allowed_uses or "*" in allowed_uses
    if (
        proof.get("status") != "active"
        or not proof.get("user_confirmed")
        or proof.get("superseded_by")
        or not allowed_for_use
    ):
        raise ValueError(f"Proof point is not eligible for {use}: {proof_id}")


def normalize_search_query(query: str) -> str:
    return " ".join(str(query or "").split())


def keywords_for_text(text: str) -> list[str]:
    stopwords = {
        "and", "are", "for", "from", "have", "into", "that", "the", "this",
        "with", "will", "you", "your", "our", "build", "built", "using", "role",
    }
    words = [word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", str(text or ""))]
    return [word for word in words if word not in stopwords]


def fts_query_for(query: str) -> str:
    terms = keywords_for_text(query)
    # OR prevents one missing term from hiding a valid proof point. Eligibility filters still run first.
    return " OR ".join(dict.fromkeys(terms[:12]))


def proof_corpus_for_repo(proof: dict[str, Any]) -> str:
    return " ".join(
        [
            str(proof.get("label", "")),
            str(proof.get("summary", "")),
            str(proof.get("evidence", "")),
            " ".join(proof.get("tags", [])),
            str(proof.get("role_family", "")),
            str(proof.get("narrative_version", "")),
        ]
    )


def proof_to_chunk_like(proof: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_table": "proof_points",
        "source_id": proof.get("id"),
        "role_family": proof.get("role_family", "other"),
        "status": proof.get("status", "active"),
        "user_confirmed": proof.get("user_confirmed", True),
        "allowed_uses": proof.get("allowed_uses", []),
        "superseded_by": proof.get("superseded_by"),
    }


def chunk_is_eligible(chunk: dict[str, Any], *, role_family: str | None = None, use: str = "resume") -> bool:
    if chunk.get("status") != "active":
        return False
    if not bool(chunk.get("user_confirmed")):
        return False
    if chunk.get("superseded_by"):
        return False
    allowed = chunk.get("allowed_uses") or []
    if use and allowed and use not in allowed:
        return False
    if role_family and chunk.get("role_family") not in {role_family, "other", ""}:
        return False
    return True


def evidence_reason(query: str, proof: dict[str, Any]) -> str:
    overlap = sorted(set(keywords_for_text(query)) & set(keywords_for_text(proof_corpus_for_repo(proof))))
    if overlap:
        return "Matched eligible proof on: " + ", ".join(overlap[:8])
    return "Eligible proof point after lifecycle filters."


def proof_exclusion_reason(proof: dict[str, Any], *, use: str = "resume") -> str:
    if proof.get("status") != "active":
        return f"status={proof.get('status')}"
    if not proof.get("user_confirmed"):
        return "not user-confirmed"
    if proof.get("superseded_by"):
        return f"superseded by {proof.get('superseded_by')}"
    allowed = proof.get("allowed_uses") or []
    if use and allowed and use not in allowed:
        return f"not allowed for {use}"
    return "excluded by retrieval policy"


def truncate_signal_label(value: str, limit: int = 90) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _raise_key(key: str) -> None:
    raise KeyError(key)


def retrieval_sql_filters(
    *,
    alias: str,
    role_family: str | None,
    use: str | None,
    include_inactive: bool,
) -> tuple[list[str], list[Any]]:
    clauses = [f"{alias}.source_table = 'proof_points'"]
    params: list[Any] = []
    if role_family:
        clauses.append(f"{alias}.role_family IN (?, 'other', '')")
        params.append(role_family)
    if not include_inactive:
        clauses.append(f"{alias}.status = 'active'")
        clauses.append(f"{alias}.user_confirmed = 1")
        clauses.append(f"({alias}.superseded_by IS NULL OR {alias}.superseded_by = '')")
        if use:
            clauses.append(f"({alias}.allowed_uses = '[]' OR {alias}.allowed_uses = '' OR {alias}.allowed_uses LIKE ?)")
            params.append(f'%"{use}"%')
    elif use:
        clauses.append(f"({alias}.allowed_uses = '[]' OR {alias}.allowed_uses = '' OR {alias}.allowed_uses LIKE ?)")
        params.append(f'%"{use}"%')
    return clauses, params


def bounded_limit(value: Any, *, default: int = 8, maximum: int = 50) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def decode_prompt(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["context_snapshot"] = json.loads(item.get("context_snapshot") or "{}")
    return item


def decode_material(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    raw_format = item.get("format") or ""
    clean_format = normalize_material_format_for_db(raw_format)
    clean_kind = normalize_material_kind_for_db(
        item.get("kind"),
        format=clean_format,
        file_path=item.get("file_path") or "",
        content=item.get("content"),
    )
    if clean_kind != item.get("kind"):
        item["raw_kind"] = item.get("kind")
        item["kind"] = clean_kind
    if clean_format != raw_format:
        item["raw_format"] = raw_format
        item["format"] = clean_format
    content_metadata = material_payload_metadata(item.get("content"))
    for key in ("pdf_path", "source_path", "source_format", "template", "display_name", "filename", "name"):
        if content_metadata.get(key) and not item["metadata"].get(key):
            item["metadata"][key] = content_metadata[key]
    return item


def decode_material_revision(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def decode_agent_run(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = json.loads(item.get("metadata") or "{}")
    item["description"] = item.get("objective", "")
    return item


def decode_approval(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = json.loads(item.get("payload") or "{}")
    return item


def decode_agent_run_event(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = json.loads(item["payload"])
    return item


def decode_tool_call(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["input"] = json.loads(item["input"])
    item["output"] = json.loads(item["output"])
    return item


def decode_tool_call_summary(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    raw_input = item.pop("input", None)
    raw_output = item.pop("output", None)
    input_bytes = item.get("input_bytes")
    output_bytes = item.get("output_bytes")
    item["input_bytes"] = int(input_bytes if input_bytes is not None else len(str(raw_input or "").encode("utf-8")))
    item["output_bytes"] = int(output_bytes if output_bytes is not None else len(str(raw_output or "").encode("utf-8")))
    marker = _tool_call_marker_from_json(raw_input) or _tool_call_marker_from_json(raw_output)
    item["archived"] = bool(marker)
    if marker:
        item["archive_path"] = marker.get("archive_path", "")
        item["input_bytes"] = int(marker.get("input_bytes") or item["input_bytes"])
        item["output_bytes"] = int(marker.get("output_bytes") or item["output_bytes"])
    return item


def _tool_call_archive_marker(
    archive_path: str,
    *,
    input_bytes: int,
    output_bytes: int,
    inline_limit_bytes: int,
) -> dict[str, Any]:
    return {
        "_archived_tool_call": True,
        "archive_path": archive_path,
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "inline_limit_bytes": inline_limit_bytes,
    }


def _tool_call_marker_from_json(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, dict) and decoded.get("_archived_tool_call"):
        return decoded
    return None


def _tool_call_row_archived(row: sqlite3.Row) -> bool:
    keys = set(row.keys()) if hasattr(row, "keys") else set(dict(row).keys())
    return any(_tool_call_marker_from_json(row[key]) for key in ("input", "output") if key in keys)


def _active_hermes_run(agent_runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for run in agent_runs:
        if run.get("kind") == "hermes_run" and run.get("status") in ACTIVE_HERMES_RUN_STATUSES:
            return run
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
