"""One-way export from the legacy SQLite database into a plain-file workspace.

The database is opened read-only and never modified. Running the export again
skips every job, person, evidence file and lead whose `legacy_id` is already in
the workspace.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .scaffold import starter_files
from .workspace import (
    Workspace,
    atomic_write,
    clip,
    day,
    normalize_stage,
    parse_frontmatter,
    render_document,
    section,
    set_section,
    slugify,
    split_frontmatter,
)


COUNT_KEYS = (
    "profile_facts",
    "evidence",
    "evidence_retired",
    "playbook_rules",
    "jobs",
    "materials_copied",
    "text_materials",
    "people",
    "discovered_contacts",
    "leads",
)
SKIP_KEYS = (
    "jobs_existing",
    "people_existing",
    "evidence_existing",
    "leads_existing",
    "leads_stale",
    "materials_missing",
)

_TABLES: dict[str, tuple[str, ...]] = {
    "profile_facts": ("fact_key", "value", "category"),
    "proof_points": (
        "id",
        "label",
        "summary",
        "evidence",
        "role_family",
        "tags",
        "status",
        "user_confirmed",
        "allowed_uses",
        "risk_level",
        "superseded_by",
        "created_at",
    ),
    "learning_patterns": (
        "id",
        "pattern_type",
        "trigger",
        "preference",
        "status",
        "superseded_by",
        "metadata",
        "updated_at",
    ),
    "jobs": (
        "id",
        "title",
        "company",
        "location",
        "url",
        "description",
        "user_notes",
        "status",
        "role_family",
        "decision",
        "next_action",
        "created_at",
        "updated_at",
    ),
    "events": ("id", "job_id", "event_type", "payload", "created_at"),
    "evaluations": ("job_id", "payload", "created_at"),
    "tailoring_requirements": ("job_id", "requirement", "priority", "created_at"),
    "research_notes": ("job_id", "subject", "source_url", "summary", "created_at"),
    "followups": ("id", "job_id", "contact_id", "due_date", "reason", "status", "created_at"),
    "progress_items": ("job_id", "title", "status", "created_at"),
    "materials": ("id", "job_id", "kind", "content", "file_path", "created_at", "updated_at"),
    "contacts": (
        "id",
        "name",
        "company",
        "role",
        "email",
        "linkedin_url",
        "notes",
        "why_added",
        "network_status",
        "is_tracked",
        "email_status",
        "source_url",
        "created_at",
    ),
    "discovery_candidates": (
        "id",
        "title",
        "company",
        "location",
        "canonical_url",
        "discovered_url",
        "apply_url",
        "description",
        "status",
        "source_provider",
        "job_id",
        "first_seen_at",
        "discovered_at",
        "created_at",
        "retrieved_at",
    ),
}
_PRIMARY_TABLES = ("profile_facts", "proof_points", "learning_patterns", "jobs", "contacts", "discovery_candidates")

_PROFILE_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "candidate_name", "full_name"),
    "email": ("email",),
    "phone": ("phone",),
    "location": ("location",),
    "linkedin": ("linkedin", "linkedin_url"),
    "github": ("github", "github_url"),
    "website": ("website", "website_url", "portfolio"),
    "headline": ("headline",),
}
_RULE_SECTIONS = (
    ("candidate.truth", "All documents"),
    ("resume", "Resume"),
    ("cover_letter", "Cover letter"),
    ("application_answers", "Application answers"),
    ("outreach", "Outreach"),
    ("interview", "Interview"),
    ("workflow", "Workflow"),
)
_UNSORTED = "Unsorted (review)"
_PLAYBOOK = "profile/playbook.md"
_VOICE = "profile/voice.md"

_MATERIAL_SUFFIXES = {".typ", ".tex", ".pdf", ".md", ".txt", ".docx"}
_ASSET_DIRS = ("assets", "images", "fonts")
_SKIPPED_TEXT_KINDS = ("tailoring", "prompt", "note")
_CLOSED_STATUSES = {"done", "closed", "complete", "completed", "dismissed", "not_needed", "canceled", "cancelled"}
_RETIRED_STATUSES = {"superseded", "retired", "forbidden", "archived"}
_DEFAULT_USES = {"resume", "cover_letter", "interview", "outreach"}
_LEAD_STATUSES = {"new", "needs_review", "hydrated", "approved", "shortlisted"}
_LEAD_DATE_COLUMNS = ("first_seen_at", "discovered_at", "created_at", "retrieved_at")
_APPLIED_STAGES = {"applied", "interviewing", "offer"}
_FINISHED_STAGES = {"rejected", "closed", "skipped"}
_PLACEHOLDER_RE = re.compile(r"^\s*(?:-\s+)?_.+_\s*$")

_NOT_MIGRATED = (
    "Event history, signals, portrayal decisions, prompt builds and tool-call logs stay in the legacy "
    "database file. That file was opened read-only and was not modified."
)


def migrate_legacy(
    db_path: Any,
    ws: Workspace,
    *,
    materials_root: Any = None,
    lead_days: int = 45,
    dry_run: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    source = Path(db_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Legacy database not found: {source}")
    data, missing = _load(source)
    root = Path(materials_root).expanduser() if materials_root else source.parent / "materials"
    migration = _Migration(
        ws,
        data,
        source=source,
        materials_root=root,
        lead_days=lead_days,
        dry_run=dry_run,
        today=today or date.today(),
    )
    for table in missing:
        if table in _PRIMARY_TABLES:
            migration.warnings.append(f"The legacy database has no {table} table, so nothing was read from it.")
    return migration.run()


def _load(source: Path) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    conn = sqlite3.connect(f"file:{quote(str(source.resolve()))}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        data: dict[str, list[dict[str, Any]]] = {}
        for table, columns in _TABLES.items():
            data[table] = []
            if table not in tables:
                continue
            present = {row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            wanted = [column for column in columns if column in present]
            if not wanted:
                continue
            select = ", ".join(f'"{column}"' for column in wanted)
            data[table] = [
                {column: (row[column] if column in present else None) for column in columns}
                for row in conn.execute(f'SELECT {select} FROM "{table}"')
            ]
    finally:
        conn.close()
    return data, [table for table in _TABLES if table not in tables]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _json(value: Any, default: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _heading(value: str) -> str:
    return " ".join(part for part in re.split(r"[_\-\s]+", value.strip()) if part).title()


def _cell(value: Any) -> str:
    return " ".join(_text(value).split()).replace("|", "/")


def _is_open(status: Any) -> bool:
    return _text(status).lower() not in _CLOSED_STATUSES


def _group(rows: list[dict[str, Any]], column: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _text(row[column])
        if key:
            grouped.setdefault(key, []).append(row)
    return grouped


def _legacy_ids(records: list[dict[str, Any]]) -> dict[str, str]:
    return {str(item["legacy_id"]): str(item["id"]) for item in records if item.get("legacy_id") not in (None, "")}


def _drop_name_line(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if not line.startswith("name:"))


def _fact_line(key: str, value: str) -> str:
    first, *rest = value.replace("\r\n", "\n").split("\n")
    lines = [f"- **{key}**: {first.rstrip()}"]
    lines.extend(f"  {line.rstrip()}" if line.strip() else "" for line in rest)
    return "\n".join(lines)


def _rule_target(key: str) -> tuple[str, str]:
    if key == "candidate.voice" or key.startswith("candidate.voice."):
        return _VOICE, "Rules"
    for prefix, heading in _RULE_SECTIONS:
        if key == prefix or key.startswith(prefix + "."):
            return _PLAYBOOK, heading
    return _PLAYBOOK, _UNSORTED


def _put_section(body: str, heading: str, content: str) -> str:
    # set_section leaves one more blank line under the heading on every call.
    updated = set_section(body, heading, content)
    gap = re.compile(rf"^(##\s+{re.escape(heading)}[ \t]*)\n{{3,}}", re.IGNORECASE | re.MULTILINE)
    return gap.sub(r"\1\n\n", updated, count=1)


def _material_text(value: Any) -> str:
    text = _text(value)
    if not text or text[0] not in '{["':
        return text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(parsed, str):
        return parsed.strip()
    return "" if isinstance(parsed, (dict, list)) else text


def _is_material_file(path: Path) -> bool:
    try:
        return path.suffix.lower() in _MATERIAL_SUFFIXES and path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _within(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


def _applied_on(events: list[dict[str, Any]]) -> str:
    hits = [
        (normalize_stage(event["status"]), day(event["created_at"]))
        for event in events
        if normalize_stage(event["status"]) in _APPLIED_STAGES and day(event["created_at"])
    ]
    applied = [when for stage, when in hits if stage == "applied"]
    if applied:
        return applied[0]
    return hits[0][1] if hits else ""


def _assessment(evaluation: dict[str, Any]) -> str:
    lines: list[str] = []
    decision = clip(evaluation.get("decision"), 120)
    if decision:
        lines.append(f"- Decision: {decision}")
    angle = clip(evaluation.get("strongest_angle"), 300)
    if angle:
        lines.append(f"- Angle: {angle}")
    flags = [item for item in evaluation.get("blocker_flags") or [] if isinstance(item, dict)]
    for flag in flags[:6]:
        area = clip(flag.get("area"), 60)
        detail = clip(flag.get("assessment") or flag.get("evidence") or flag.get("label"), 240)
        if area or detail:
            lines.append(f"- Blocker{f' ({area})' if area else ''}: {detail}".rstrip())
    risks = [item for item in evaluation.get("risks") or [] if isinstance(item, str) and item.strip()]
    lines.extend(f"- Risk: {clip(risk, 240)}" for risk in risks[:5])
    return "\n".join(lines)


def _requirements(rows: list[dict[str, Any]], evaluation: dict[str, Any]) -> str:
    ordered = sorted(rows, key=lambda row: (-_number(row["priority"]), _text(row["created_at"])))
    candidates: list[Any] = [row["requirement"] for row in ordered]
    if not any(_text(item) for item in candidates):
        candidates = [
            (item.get("requirement") or item.get("text")) if isinstance(item, dict) else item
            for item in evaluation.get("top_requirements") or []
        ]
    seen: set[str] = set()
    lines: list[str] = []
    for item in candidates:
        requirement = clip(item, 300) if isinstance(item, str) else ""
        if not requirement or requirement.lower() in seen:
            continue
        seen.add(requirement.lower())
        lines.append(f"- {requirement}")
        if len(lines) == 15:
            break
    return "\n".join(lines)


def _research(rows: list[dict[str, Any]]) -> str:
    lines = []
    for row in sorted(rows, key=lambda item: _text(item["created_at"]), reverse=True)[:10]:
        url = _text(row["source_url"])
        subject = clip(row["subject"], 100) or "Note"
        lines.append(f"- **{subject}**{f' ({url})' if url else ''}: {clip(row['summary'], 500)}")
    return "\n".join(lines)


class _Migration:
    def __init__(
        self,
        ws: Workspace,
        data: dict[str, list[dict[str, Any]]],
        *,
        source: Path,
        materials_root: Path,
        lead_days: int,
        dry_run: bool,
        today: date,
    ) -> None:
        self.ws = ws
        self.data = data
        self.source = source
        self.materials_root = materials_root
        self.lead_days = lead_days
        self.dry_run = dry_run
        self.today = today
        self.counts = dict.fromkeys(COUNT_KEYS, 0)
        self.skipped = dict.fromkeys(SKIP_KEYS, 0)
        self.warnings: list[str] = []
        self.job_ids: dict[str, str] = {}
        self.followups_by_job = _group(self._open_followups(), "job_id")
        self.followups_by_contact = _group(self._open_followups(), "contact_id")
        self.materials_by_job = _group(data["materials"], "job_id")
        bases = (source.parent.parent, source.parent, materials_root.parent.parent, materials_root.parent, materials_root)
        self.path_bases = list(dict.fromkeys(bases))

    def run(self) -> dict[str, Any]:
        if not self.dry_run:
            self.ws.init()
        self._profile()
        self._evidence()
        self._playbook()
        self._jobs()
        self._people()
        self._discovered_contacts()
        self._leads()
        report = {
            "workspace": str(self.ws.root),
            "source": str(self.source),
            "dry_run": self.dry_run,
            "counts": dict(self.counts),
            "skipped": dict(self.skipped),
            "warnings": list(self.warnings),
        }
        if not self.dry_run:
            atomic_write(self.ws.root / "MIGRATION.md", self._summary())
        return report

    def _open_followups(self) -> list[dict[str, Any]]:
        rows = [row for row in self.data["followups"] if _is_open(row["status"])]
        return sorted(rows, key=lambda row: (_text(row["due_date"]) or "9999", _text(row["created_at"])))

    # -- profile -----------------------------------------------------------

    def _profile(self) -> None:
        facts = [
            (_text(row["fact_key"]), _text(row["value"]), _heading(_text(row["category"]) or "profile"))
            for row in self.data["profile_facts"]
            if _text(row["fact_key"]) and _text(row["value"])
        ]
        if not facts:
            return
        self.counts["profile_facts"] = len(facts)
        path = self.ws.profile_dir / "profile.md"
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        untouched = not existing or _drop_name_line(existing) == _drop_name_line(starter_files()["profile/profile.md"])

        lookup = {key.lower(): value for key, value, _ in facts}
        meta = {field: "" for field in _PROFILE_ALIASES}
        for field, aliases in _PROFILE_ALIASES.items():
            meta[field] = next((" ".join(lookup[alias].split()) for alias in aliases if alias in lookup), "")
        if untouched and existing and not meta["name"]:
            meta["name"] = _text(parse_frontmatter(existing)[0].get("name"))

        by_category: dict[str, list[tuple[str, str]]] = {}
        for key, value, category in facts:
            by_category.setdefault(category, []).append((key, value))
        parts = ["# Profile"]
        for category in sorted(by_category):
            lines = [_fact_line(key, value) for key, value in sorted(by_category[category], key=lambda item: item[0].lower())]
            parts.append(f"## {category}\n\n" + "\n".join(lines))
        text = render_document(meta, "\n\n".join(parts))

        if existing == text:
            return
        target = path
        if not untouched:
            target = path.with_name("profile.migrated.md")
            self.warnings.append(
                "profile/profile.md already holds your own text, so the legacy facts went to "
                "profile/profile.migrated.md. Merge what you need by hand."
            )
        if not self.dry_run:
            atomic_write(target, text)

    # -- evidence ----------------------------------------------------------

    def _evidence(self) -> None:
        existing = _legacy_ids(self.ws.evidence(include_retired=True))
        if self.ws.evidence_dir.is_dir():
            # Files the user archived or merged still count as migrated.
            for path in self.ws.evidence_dir.rglob("*.md"):
                if path.parent != self.ws.evidence_dir:
                    meta = self.ws.read(path).meta
                    if meta.get("legacy_id") not in (None, ""):
                        existing.setdefault(str(meta["legacy_id"]), path.stem)
        taken = {path.stem for path in self.ws.evidence_dir.glob("*.md")} if self.ws.evidence_dir.is_dir() else set()
        rows = sorted(self.data["proof_points"], key=lambda row: (_text(row["created_at"]), _text(row["id"])))
        for row in rows:
            legacy_id = _text(row["id"])
            if legacy_id and legacy_id in existing:
                self.skipped["evidence_existing"] += 1
                continue
            label = _text(row["label"]) or "Untitled proof"
            legacy_status = (_text(row["status"]) or "active").lower()
            confirmed = row["user_confirmed"] is None or bool(_number(row["user_confirmed"]))
            if legacy_status in _RETIRED_STATUSES or _text(row["superseded_by"]):
                status = "retired"
            elif legacy_status == "active" and confirmed:
                status = "active"
            else:
                status = "needs_review"
            meta: dict[str, Any] = {"title": label, "type": "proof", "status": status}
            if legacy_status != status:
                meta["legacy_status"] = legacy_status
            meta["role_family"] = _text(row["role_family"])
            meta["tags"] = [_text(tag) for tag in _json(row["tags"], []) if _text(tag)]
            uses = [_text(use) for use in _json(row["allowed_uses"], []) if _text(use)]
            if uses and set(uses) != _DEFAULT_USES:
                meta["allowed_uses"] = uses
            risk = _text(row["risk_level"]).lower()
            if risk and risk != "safe":
                meta["risk_level"] = risk
            meta["legacy_id"] = legacy_id

            base = slugify(label)
            name = base
            counter = 2
            while name in taken:
                name = f"{base}-{counter}"
                counter += 1
            taken.add(name)
            self.counts["evidence"] += 1
            if status == "retired":
                self.counts["evidence_retired"] += 1
            if not self.dry_run:
                body = f"# {label}\n\n## Summary\n\n{_text(row['summary'])}\n\n## Facts\n\n{_text(row['evidence'])}\n"
                self.ws.write(self.ws.evidence_dir / f"{name}.md", meta, body)

    # -- playbook ----------------------------------------------------------

    def _playbook(self) -> None:
        rules: list[tuple[str, str, dict[str, Any]]] = []
        for row in self.data["learning_patterns"]:
            if (_text(row["status"]) or "active").lower() != "active" or _text(row["superseded_by"]):
                continue
            if not _text(row["preference"]):
                continue
            key = _text(_json(row["metadata"], {}).get("rule_key")).lower()
            rules.append((key, _text(row["updated_at"]), row))
        rules.sort(key=lambda item: (item[0], item[1], _text(item[2]["id"])))

        by_file: dict[str, list[tuple[str, str, str, bool]]] = {}
        for key, _, row in rules:
            relative, heading = _rule_target(key)
            title = _heading(key.rsplit(".", 1)[-1] if key else _text(row["pattern_type"])) or "Rule"
            trigger = " ".join(_text(row["trigger"]).split())
            block = f"### {title}\n\n" + (f"**When:** {trigger}\n\n" if trigger else "") + _text(row["preference"])
            by_file.setdefault(relative, []).append((heading, title, block, bool(key)))
        for relative, entries in by_file.items():
            self.counts["playbook_rules"] += self._add_rules(relative, entries)

    def _add_rules(self, relative: str, entries: list[tuple[str, str, str, bool]]) -> int:
        path = self.ws.root / relative
        text = path.read_text(encoding="utf-8") if path.is_file() else starter_files()[relative]
        frontmatter, original = split_frontmatter(text)
        body = original
        added = 0
        for heading, title, block, keyed in entries:
            before = section(original, heading)
            has_title = re.search(rf"^###\s+{re.escape(title)}\s*$", before, re.MULTILINE)
            if block in before or (keyed and has_title):
                continue
            kept = "\n".join(line for line in section(body, heading).split("\n") if not _PLACEHOLDER_RE.match(line))
            kept = re.sub(r"\n{3,}", "\n\n", kept).strip("\n")
            body = _put_section(body, heading, f"{kept}\n\n{block}" if kept else block)
            added += 1
        if added and not self.dry_run:
            head = "---\n" + "\n".join(frontmatter) + "\n---\n\n" if frontmatter else ""
            atomic_write(path, head + body.strip("\n") + "\n")
        return added

    # -- jobs --------------------------------------------------------------

    def _jobs(self) -> None:
        existing = _legacy_ids(self.ws.jobs())
        events_by_job: dict[str, list[dict[str, Any]]] = {}
        ordered_events = sorted(self.data["events"], key=lambda row: (_text(row["created_at"]), _number(row["id"])))
        for row in ordered_events:
            if _text(row["event_type"]) != "status_changed":
                continue
            payload = _json(row["payload"], {})
            status = _text(payload.get("status"))
            if status and _text(row["job_id"]):
                events_by_job.setdefault(_text(row["job_id"]), []).append(
                    {"status": status, "note": payload.get("note"), "created_at": row["created_at"]}
                )
        evaluations: dict[str, dict[str, Any]] = {}
        for row in sorted(self.data["evaluations"], key=lambda item: _text(item["created_at"])):
            if _text(row["job_id"]):
                evaluations[_text(row["job_id"])] = _json(row["payload"], {})
        requirements = _group(self.data["tailoring_requirements"], "job_id")
        research = _group(self.data["research_notes"], "job_id")
        tasks = _group([row for row in self.data["progress_items"] if _is_open(row["status"])], "job_id")

        for row in sorted(self.data["jobs"], key=lambda item: (_text(item["created_at"]), _text(item["id"]))):
            legacy_id = _text(row["id"])
            if legacy_id and legacy_id in existing:
                self.job_ids[legacy_id] = existing[legacy_id]
                self.skipped["jobs_existing"] += 1
                if not self.dry_run:
                    self._assets(legacy_id, self.ws.jobs_dir / existing[legacy_id])
                continue
            status = _text(row["status"]) or "new"
            stage = normalize_stage(status)
            created = day(row["created_at"]) or self.today.isoformat()
            events = events_by_job.get(legacy_id, [])
            followups = self.followups_by_job.get(legacy_id, [])
            evaluation = evaluations.get(legacy_id, {})

            next_action = next_due = ""
            listed = followups
            if stage not in _FINISHED_STAGES:
                next_action = clip(row["next_action"], 200)
                if followups:
                    next_due = day(followups[0]["due_date"])
                    reason = clip(followups[0]["reason"], 200)
                    if reason and (not next_action or stage in {"applied", "interviewing"}):
                        next_action = reason
                        listed = followups[1:]

            extra: dict[str, Any] = {"legacy_id": legacy_id}
            if _text(row["decision"]):
                extra["decision"] = _text(row["decision"])
            if _text(row["role_family"]):
                extra["role_family"] = _text(row["role_family"])
            extra["applied_on"] = _applied_on(events)
            extra["next_action"] = next_action
            extra["next_action_due"] = next_due
            if day(row["updated_at"]):
                extra["updated_on"] = day(row["updated_at"])
            if stage != status:
                extra["legacy_status"] = status

            notes = [str(row["user_notes"] or "").strip("\n")] if _text(row["user_notes"]) else []
            if listed:
                lines = [f"- {day(item['due_date']) or _text(item['due_date'])}: {clip(item['reason'], 200)}" for item in listed]
                notes.append("Open follow-ups:\n" + "\n".join(lines))
            open_tasks = [clip(item["title"], 160) for item in tasks.get(legacy_id, []) if _text(item["title"])]
            if open_tasks:
                notes.append("Open tasks:\n" + "\n".join(f"- {title}" for title in open_tasks))

            log = [f"- {created}: Added (migrated from the legacy database)."]
            for event in events[-40:]:
                note = clip(event["note"], 200)
                log.append(f"- {day(event['created_at']) or created}: Status: {event['status']}." + (f" {note}" if note else ""))

            sections = {
                "Assessment": _assessment(evaluation),
                "Requirements": _requirements(requirements.get(legacy_id, []), evaluation),
                "Research": _research(research.get(legacy_id, [])),
            }
            sections = {heading: content for heading, content in sections.items() if content}
            sections["Notes"] = "\n\n".join(notes)
            sections["Log"] = "\n".join(log)

            self.counts["jobs"] += 1
            if self.dry_run:
                self._materials(legacy_id, None)
                continue
            record = self.ws.create_job(
                company=_text(row["company"]),
                title=_text(row["title"]),
                location=_text(row["location"]),
                url=_text(row["url"]),
                posting=str(row["description"] or ""),
                status=status,
                created_on=created,
                extra_meta=extra,
                body_sections=sections,
            )
            self.job_ids[legacy_id] = record["id"]
            self._materials(legacy_id, Path(record["path"]).parent)

    # -- materials ---------------------------------------------------------

    def _material_source(self, raw: Any) -> Path | None:
        text = _text(raw)
        if not text:
            return None
        candidate = Path(text).expanduser()
        options = [candidate] if candidate.is_absolute() else [base / candidate for base in self.path_bases]
        for option in options:
            try:
                if option.is_file():
                    return option
            except OSError:
                continue
        return None

    def _assets(self, legacy_id: str, target: Path | None) -> None:
        """Copy the asset folders a document source refers to (icons, images, fonts)."""
        folder = self.materials_root / legacy_id if legacy_id else None
        if folder is None or not folder.is_dir():
            return
        for name in _ASSET_DIRS:
            source_dir = folder / name
            if not source_dir.is_dir() or source_dir.is_symlink():
                continue
            for source in sorted(path for path in source_dir.rglob("*") if path.is_file() and not path.is_symlink()):
                if target is None:
                    self.counts["materials_copied"] += 1
                    continue
                destination = target / name / source.relative_to(source_dir)
                if destination.exists():
                    continue
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                except OSError as exc:
                    self.warnings.append(f"Could not copy {source} into {target.name}: {exc}")
                    continue
                self.counts["materials_copied"] += 1

    def _materials(self, legacy_id: str, target: Path | None) -> None:
        self._assets(legacy_id, target)
        folder = self.materials_root / legacy_id if legacy_id else None
        copies: dict[str, Path] = {}
        if folder is not None and folder.is_dir():
            for path in sorted(folder.iterdir()):
                if _is_material_file(path) and path.name.lower() != "job.md":
                    copies.setdefault(path.name, path)
        else:
            self.skipped["materials_missing"] += 1

        newest: dict[str, tuple[dict[str, Any], bool]] = {}
        rows = sorted(
            self.materials_by_job.get(legacy_id, []),
            key=lambda row: (_text(row["updated_at"]) or _text(row["created_at"]), _text(row["created_at"])),
        )
        for row in rows:
            source = self._material_source(row["file_path"])
            newest[_text(row["kind"]).lower()] = (row, source is not None)
            if source is None or (folder is not None and _within(source, folder)):
                continue
            for path in (source, source.with_suffix(".pdf")):
                if _is_material_file(path) and path.name.lower() != "job.md":
                    copies.setdefault(path.name, path)

        texts: dict[str, str] = {}
        for kind, (row, has_file) in newest.items():
            if has_file or not kind or any(term in kind for term in _SKIPPED_TEXT_KINDS):
                continue
            content = _material_text(row["content"])
            name = f"{slugify(kind, limit=60, fallback='material')}.md"
            if content and name not in copies and name != "job.md":
                texts.setdefault(name, content)

        if target is None:
            self.counts["materials_copied"] += len(copies)
            self.counts["text_materials"] += len(texts)
            return
        for name, source in copies.items():
            destination = target / name
            if destination.exists():
                continue
            try:
                shutil.copy2(source, destination)
            except OSError as exc:
                self.warnings.append(f"Could not copy {source} into {target.name}: {exc}")
                continue
            self.counts["materials_copied"] += 1
        for name, content in texts.items():
            destination = target / name
            if not destination.exists():
                atomic_write(destination, content.rstrip("\n") + "\n")
                self.counts["text_materials"] += 1

    # -- people ------------------------------------------------------------

    def _people(self) -> None:
        existing = _legacy_ids(self.ws.people())
        tracked = [row for row in self.data["contacts"] if _number(row["is_tracked"])]
        for row in sorted(tracked, key=lambda item: (_text(item["created_at"]), _text(item["id"]))):
            legacy_id = _text(row["id"])
            if legacy_id and legacy_id in existing:
                self.skipped["people_existing"] += 1
                continue
            name = _text(row["name"])
            if not name:
                self.warnings.append(f"Tracked contact {legacy_id or '(no id)'} has no name and was not migrated.")
                continue
            followups = self.followups_by_contact.get(legacy_id, [])
            next_touch = next((day(item["due_date"]) for item in followups if day(item["due_date"])), "")
            linked = [self.job_ids[_text(item["job_id"])] for item in followups if _text(item["job_id"]) in self.job_ids]
            self.counts["people"] += 1
            if self.dry_run:
                continue
            person = self.ws.create_person(
                name=name,
                company=_text(row["company"]),
                role=_text(row["role"]),
                email=_text(row["email"]),
                linkedin=_text(row["linkedin_url"]),
                why=_text(row["why_added"]),
                status=_text(row["network_status"]).lower(),
                notes=_text(row["notes"]),
                next_touch=next_touch,
                jobs=list(dict.fromkeys(linked)),
                extra_meta={"legacy_id": legacy_id, "email_status": _text(row["email_status"])},
            )
            if day(row["created_at"]):
                self.ws.set_meta(Path(person["path"]), {"added_on": day(row["created_at"])})

    def _discovered_contacts(self) -> None:
        groups: dict[str, tuple[str, set[str]]] = {}
        for row in self.data["contacts"]:
            name = _cell(row["name"])
            if _number(row["is_tracked"]) or not name:
                continue
            company = " ".join(_text(row["company"]).split())
            link = _cell(row["linkedin_url"]) or _cell(row["source_url"])
            line = f"- {name} | {_cell(row['role'])} | {link} | {_cell(row['email']) or 'no email'}"
            groups.setdefault(slugify(company, fallback="unknown"), (company or "Unknown", set()))[1].add(line)
        for slug, (company, lines) in sorted(groups.items()):
            path = self.ws.people_dir / "_discovered" / f"{slug}.md"
            current = path.read_text(encoding="utf-8").split("\n") if path.is_file() else []
            kept = {line.rstrip() for line in current if line.startswith("- ")}
            fresh = lines - kept
            self.counts["discovered_contacts"] += len(fresh)
            if not fresh or self.dry_run:
                continue
            title = current[0] if current and current[0].startswith("# ") else f"# Discovered contacts: {company}"
            atomic_write(path, title + "\n\n" + "\n".join(sorted(kept | fresh, key=str.lower)) + "\n")

    # -- leads -------------------------------------------------------------

    def _leads(self) -> None:
        current = self.ws.leads()
        existing = _legacy_ids(current)
        urls = {_text(item.get("url")).rstrip("/").lower() for item in current} - {""}
        rows = sorted(self.data["discovery_candidates"], key=lambda row: (_text(row["created_at"]), _text(row["id"])))
        for row in rows:
            status = (_text(row["status"]) or "new").lower().replace("-", "_").replace(" ", "_")
            found = next((day(row[column]) for column in _LEAD_DATE_COLUMNS if day(row[column])), "")
            try:
                fresh = bool(found) and (self.today - date.fromisoformat(found)).days <= self.lead_days
            except ValueError:
                fresh = False
            if _text(row["job_id"]) or status not in _LEAD_STATUSES or not fresh:
                self.skipped["leads_stale"] += 1
                continue
            legacy_id = _text(row["id"])
            url = _text(row["canonical_url"]) or _text(row["discovered_url"]) or _text(row["apply_url"])
            key = url.rstrip("/").lower()
            if (legacy_id and legacy_id in existing) or (key and key in urls):
                self.skipped["leads_existing"] += 1
                continue
            if key:
                urls.add(key)
            self.counts["leads"] += 1
            if self.dry_run:
                continue
            self.ws.create_lead(
                company=_text(row["company"]),
                title=_text(row["title"]),
                url=url,
                location=_text(row["location"]),
                posting=str(row["description"] or ""),
                source=_text(row["source_provider"]),
                found_on=found,
                status="shortlisted" if status == "approved" else "new",
                extra_meta={"legacy_id": legacy_id},
            )

    # -- summary -----------------------------------------------------------

    def _summary(self) -> str:
        def table(header: str, values: dict[str, int]) -> list[str]:
            rows = [f"| {key.replace('_', ' ').capitalize()} | {value} |" for key, value in values.items()]
            return [f"| {header} | Count |", "|---|---|", *rows]

        lines = [
            "# Migration from the legacy database",
            "",
            f"- Date: {self.today.isoformat()}",
            f"- Source: `{self.source}`",
            f"- Workspace: `{self.ws.root}`",
            "",
            "## Migrated",
            "",
            *table("Item", self.counts),
            "",
            "## Skipped",
            "",
            *table("Reason", self.skipped),
            "",
            "## Warnings",
            "",
            *([f"- {warning}" for warning in self.warnings] or ["None."]),
            "",
            "## Not migrated",
            "",
            _NOT_MIGRATED,
        ]
        return "\n".join(lines) + "\n"
