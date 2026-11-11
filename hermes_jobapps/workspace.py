"""Plain-file JobApps workspace.

The workspace folder is the source of truth. Every record is a Markdown file
with a flat frontmatter block that people and agents can read and edit
directly. Nothing here needs a database: tracking views are computed by
scanning the files.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


STAGES = ("new", "ready", "applied", "interviewing", "offer", "rejected", "closed", "skipped")
OPEN_STAGES = ("new", "ready", "applied", "interviewing", "offer")
PERSON_STATUSES = ("to_contact", "contacted", "follow_up", "replied", "paused")
LEAD_STATUSES = ("new", "shortlisted", "dismissed", "promoted")
EVIDENCE_STATUSES = ("active", "needs_review", "retired")

MATERIAL_SOURCE_EXTENSIONS = (".typ", ".tex", ".md", ".txt", ".docx")
DEFAULTS_PATH = Path(__file__).resolve().parent / "resources" / "defaults.json"

_STAGE_ALIASES = {
    "": "new",
    "lead": "new",
    "pending": "new",
    "evaluated": "new",
    "preparing": "new",
    "in_progress": "new",
    "materials_ready": "ready",
    "materials_ready_for_review": "ready",
    "ready_to_apply": "ready",
    "submitted": "applied",
    "waiting": "applied",
    "follow_up": "applied",
    "phone_screen": "interviewing",
    "interview": "interviewing",
    "onsite": "interviewing",
    "declined": "rejected",
    "archived": "closed",
    "withdrawn": "closed",
    "expired": "closed",
    "skip": "skipped",
    "not_interested": "skipped",
    "not_needed": "skipped",
}

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-]*):(?:\s+(.*)|\s*)$")
_INT_RE = re.compile(r"^-?\d{1,15}$")
_BARE_SAFE_RE = re.compile(r"^[A-Za-z0-9(/.+~$€£][^\n]*$")


def normalize_stage(value: Any) -> str:
    """Map any stored status, including legacy ones, onto STAGES."""
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in STAGES:
        return key
    if key in _STAGE_ALIASES:
        return _STAGE_ALIASES[key]
    if key.startswith("closed"):
        return "closed"
    return "new"


def slugify(value: Any, *, limit: int = 48, fallback: str = "item") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    if len(text) > limit:
        text = text[:limit].rsplit("-", 1)[0] or text[:limit]
    return text.strip("-") or fallback


def today_iso() -> str:
    return date.today().isoformat()


def day(value: Any) -> str:
    """First ten characters of an ISO date or timestamp, or an empty string."""
    text = str(value or "").strip()
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"


# ---------------------------------------------------------------------------
# Frontmatter: a strict, flat subset of YAML that round-trips untouched keys.
# ---------------------------------------------------------------------------


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return ""
    if text[0] == '"' and text.endswith('"') and len(text) >= 2:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text[1:-1]
    if text[0] == "'" and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text[0] == "[" and text.endswith("]"):
        return [_parse_scalar(item) for item in _split_inline_list(text[1:-1])]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if _INT_RE.match(text):
        return int(text)
    return text


def _split_inline_list(inner: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote = ""
    escaped = False
    for char in inner:
        if quote:
            current.append(char)
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = ""
            escaped = False
            continue
        if char in "\"'":
            quote = char
            current.append(char)
        elif char == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return [item for item in (part.strip() for part in items) if item]


def _render_scalar(value: Any, *, in_list: bool = False) -> str:
    if value is None:
        return "null" if in_list else ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""' if in_list else ""
    reparsed_differently = _parse_scalar(text) != text
    unsafe = (
        reparsed_differently
        or not _BARE_SAFE_RE.match(text)
        or text != text.strip()
        or ": " in text
        or " #" in text
        or text.endswith(":")
        or (in_list and any(char in text for char in ",[]"))
    )
    return json.dumps(text, ensure_ascii=False) if unsafe else text


def _render_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_render_scalar(item, in_list=True) for item in value) + "]"
    return _render_scalar(value)


@dataclass
class _Entry:
    key: str
    value: Any
    raw: list[str] | None


def _parse_entries(lines: list[str]) -> list[_Entry]:
    entries: list[_Entry] = []
    for line in lines:
        match = _KEY_RE.match(line)
        if match:
            entries.append(_Entry(match.group(1), _parse_scalar(match.group(2) or ""), [line]))
            continue
        if not entries:
            continue
        entry = entries[-1]
        entry.raw = (entry.raw or []) + [line]
        stripped = line.strip()
        if stripped.startswith("- ") or stripped == "-":
            item = _parse_scalar(stripped[1:].strip())
            if isinstance(entry.value, list):
                entry.value.append(item)
            elif entry.value in ("", None):
                entry.value = [item]
    return entries


def split_frontmatter(text: str) -> tuple[list[str], str]:
    """Return (frontmatter lines, body). Files without frontmatter return ([], text)."""
    if not text.startswith("---"):
        return [], text
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return [], text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            body = "\n".join(lines[index + 1 :])
            return lines[1:index], body.lstrip("\n")
    return [], text


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines, body = split_frontmatter(text)
    return {entry.key: entry.value for entry in _parse_entries(lines)}, body


def render_document(meta: dict[str, Any], body: str) -> str:
    lines = [f"{key}: {_render_value(value)}".rstrip() for key, value in meta.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body.strip("\n") + "\n"


def update_frontmatter(text: str, changes: dict[str, Any]) -> str:
    """Apply changes while leaving every untouched line exactly as written."""
    lines, body = split_frontmatter(text)
    entries = _parse_entries(lines)
    by_key = {entry.key: entry for entry in entries}
    for key, value in changes.items():
        if key in by_key:
            if by_key[key].value != value or by_key[key].raw is None:
                by_key[key].value = value
                by_key[key].raw = None
        else:
            entry = _Entry(key, value, None)
            entries.append(entry)
            by_key[key] = entry
    rendered: list[str] = []
    for entry in entries:
        if entry.raw is not None:
            rendered.extend(entry.raw)
        else:
            rendered.append(f"{entry.key}: {_render_value(entry.value)}".rstrip())
    return "---\n" + "\n".join(rendered) + "\n---\n\n" + body.strip("\n") + "\n"


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


def section(body: str, heading: str) -> str:
    """Return the text under a `## heading`, without the heading line."""
    pattern = re.compile(rf"^##[ \t]+{re.escape(heading)}[ \t]*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return ""
    rest = body[match.end() :]
    nxt = re.search(r"^##\s+\S", rest, re.MULTILINE)
    return (rest[: nxt.start()] if nxt else rest).strip("\n")


def set_section(body: str, heading: str, content: str) -> str:
    """Replace the text under `## heading`, creating the section when missing."""
    pattern = re.compile(rf"^##[ \t]+{re.escape(heading)}[ \t]*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(body)
    block = content.strip("\n")
    if not match:
        return body.rstrip("\n") + f"\n\n## {heading}\n\n{block}\n"
    rest = body[match.end() :]
    nxt = re.search(r"^##\s+\S", rest, re.MULTILINE)
    tail = rest[nxt.start() :] if nxt else ""
    head = body[: match.end()]
    return head + "\n\n" + block + "\n" + ("\n" + tail if tail else "")


def append_to_section(body: str, heading: str, line: str) -> str:
    existing = section(body, heading)
    return set_section(body, heading, (existing + "\n" + line).strip("\n"))


def plain_posting(text: str) -> str:
    """Turn Markdown headings inside pasted text into bold lines.

    A posting that carries its own `## Notes` heading would otherwise be read
    as one of the record's sections.
    """
    return re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t#]*$", r"**\1**", text)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp_name, path)
    except BaseException:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_root() -> Path:
    configured = os.environ.get("JOBAPPS_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / "JobApps"


def material_kind(name: str) -> str:
    lowered = name.lower()
    if "cover" in lowered or "letter" in lowered:
        return "cover_letter"
    if "resume" in lowered or re.search(r"\bcv\b", lowered):
        return "resume"
    if "answer" in lowered or "question" in lowered:
        return "application_answers"
    if any(term in lowered for term in ("outreach", "email", "message", "referral", "linkedin")):
        return "outreach"
    if "interview" in lowered:
        return "interview"
    return "other"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def qa_report_path(source: Path) -> Path:
    return source.parent / "qa" / f"{source.name}.json"


def qa_state(source: Path) -> dict[str, Any]:
    """Summarize the saved check for a material file.

    state is none (never checked), stale (file changed since the check),
    or the saved status: pass, review or fail.
    """
    report_path = qa_report_path(source)
    if not report_path.is_file() or not source.is_file():
        return {"state": "none"}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "none"}
    if not isinstance(report, dict):
        return {"state": "none"}
    summary = {"checked_at": str(report.get("checked_at") or "")}
    if report.get("source_sha256") != sha256_file(source):
        return {"state": "stale", **summary}
    status = str(report.get("status") or "")
    return {"state": status if status in {"pass", "review", "fail"} else "none", **summary}


class AmbiguousReference(LookupError):
    def __init__(self, kind: str, ref: str, matches: list[dict[str, Any]]) -> None:
        self.kind = kind
        self.ref = ref
        self.matches = matches
        names = "; ".join(f"{item['id']}" for item in matches[:5])
        super().__init__(f"{len(matches)} {kind} match {ref!r}: {names}. Use the exact id.")


@dataclass
class Doc:
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""


class Workspace:
    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root).expanduser() if root else default_root()
        self.profile_dir = self.root / "profile"
        self.evidence_dir = self.root / "evidence"
        self.jobs_dir = self.root / "jobs"
        self.people_dir = self.root / "people"
        self.leads_dir = self.root / "leads"
        self.templates_dir = self.root / "templates"
        self.settings_path = self.root / "settings.json"
        self._cache: dict[Path, tuple[tuple[int, int], Doc]] = {}

    # -- setup -------------------------------------------------------------

    def exists(self) -> bool:
        return self.profile_dir.is_dir() or self.jobs_dir.is_dir()

    def init(self, *, name: str = "") -> list[str]:
        """Create the folder skeleton. Never overwrites an existing file."""
        from .scaffold import starter_files

        created: list[str] = []
        for folder in (
            self.profile_dir,
            self.evidence_dir,
            self.jobs_dir,
            self.people_dir,
            self.leads_dir,
            self.templates_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        has_templates = any(path.is_file() for path in self.templates_dir.iterdir())
        for relative, text in starter_files(name=name).items():
            if has_templates and relative.startswith("templates/"):
                continue
            target = self.root / relative
            if not target.exists():
                atomic_write(target, text)
                created.append(relative)
        return created

    def settings(self) -> dict[str, Any]:
        defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8")) if DEFAULTS_PATH.exists() else {}
        if self.settings_path.exists():
            try:
                overlay = json.loads(self.settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{self.settings_path} is not valid JSON: {exc}") from exc
            if isinstance(overlay, dict):
                defaults = deep_merge(defaults, overlay)
        defaults["workspace_path"] = str(self.root)
        return defaults

    def save_settings(self, overlay: dict[str, Any]) -> None:
        current: dict[str, Any] = {}
        if self.settings_path.exists():
            current = json.loads(self.settings_path.read_text(encoding="utf-8"))
        atomic_write(self.settings_path, json.dumps(deep_merge(current, overlay), indent=2) + "\n")

    # -- documents ---------------------------------------------------------

    def relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(path)

    def inside(self, path: str | os.PathLike[str]) -> Path:
        """Resolve a user-supplied path and require it to stay in the workspace."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError(f"Path must stay inside the workspace {self.root}: {path}") from exc
        return resolved

    def read(self, path: Path) -> Doc:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(path)
        if cached and cached[0] == stamp:
            return Doc(path, copy.deepcopy(cached[1].meta), cached[1].body)
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        self._cache[path] = (stamp, Doc(path, meta, body))
        return Doc(path, copy.deepcopy(meta), body)

    def write(self, path: Path, meta: dict[str, Any], body: str) -> Path:
        atomic_write(path, render_document(meta, body))
        return path

    def set_meta(self, path: Path, changes: dict[str, Any]) -> Doc:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            text = render_document({}, text)
        atomic_write(path, update_frontmatter(text, changes))
        return self.read(path)

    def set_body(self, path: Path, body: str) -> None:
        text = path.read_text(encoding="utf-8")
        lines, _ = split_frontmatter(text)
        atomic_write(path, "---\n" + "\n".join(lines) + "\n---\n\n" + body.strip("\n") + "\n")

    def _docs(self, folder: Path, pattern: str) -> Iterable[Doc]:
        if not folder.is_dir():
            return
        for path in sorted(folder.glob(pattern)):
            if path.name.startswith((".", "_")) or any(part.startswith(".") for part in path.parts[-2:]):
                continue
            try:
                yield self.read(path)
            except OSError:
                continue

    @staticmethod
    def _match(ref: str, items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
        needle = ref.strip().lower()
        if not needle:
            return []
        exact = [item for item in items if needle in {str(item.get(key, "")).lower() for key in ("id", "legacy_id")}]
        if exact:
            return exact
        words = needle.split()
        return [
            item
            for item in items
            if all(word in " ".join(str(item.get(key, "")) for key in fields).lower() for word in words)
        ]

    def _resolve(self, kind: str, ref: str, items: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
        matches = self._match(ref, items, fields)
        if not matches:
            raise KeyError(f"Nothing in {kind} matches {ref!r}.")
        if len(matches) > 1:
            raise AmbiguousReference(kind, ref, matches)
        return matches[0]

    # -- jobs --------------------------------------------------------------

    def jobs(self) -> list[dict[str, Any]]:
        records = []
        for doc in self._docs(self.jobs_dir, "*/job.md"):
            record = dict(doc.meta)
            record["id"] = doc.path.parent.name
            record["path"] = str(doc.path)
            record["stage"] = normalize_stage(record.get("status"))
            record["updated_on"] = day(record.get("updated_on")) or datetime.fromtimestamp(
                doc.path.stat().st_mtime
            ).date().isoformat()
            records.append(record)
        records.sort(key=lambda item: (item["updated_on"], item["id"]), reverse=True)
        return records

    def find_jobs(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        return self._match(query, self.jobs(), ("id", "company", "title"))[:limit]

    def resolve_job(self, ref: str) -> dict[str, Any]:
        return self._resolve("jobs", ref, self.jobs(), ("id", "company", "title"))

    def job_dir(self, job_id: str) -> Path:
        path = self.jobs_dir / job_id
        if not (path / "job.md").is_file():
            raise KeyError(f"No job folder named {job_id!r}.")
        return path

    def job_doc(self, job_id: str) -> Doc:
        return self.read(self.job_dir(job_id) / "job.md")

    def create_job(
        self,
        *,
        company: str,
        title: str,
        location: str = "",
        url: str = "",
        posting: str = "",
        source: str = "",
        notes: str = "",
        status: str = "new",
        created_on: str = "",
        extra_meta: dict[str, Any] | None = None,
        body_sections: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        created = day(created_on) or today_iso()
        base = f"{created[:7]}-{slugify(company, limit=28, fallback='company')}-{slugify(title, limit=36, fallback='role')}"
        job_id = base
        counter = 2
        while (self.jobs_dir / job_id).exists():
            job_id = f"{base}-{counter}"
            counter += 1
        meta: dict[str, Any] = {
            "company": company.strip() or "Unknown company",
            "title": title.strip() or "Untitled role",
            "status": normalize_stage(status),
            "location": location.strip(),
            "url": url.strip(),
            "source": source.strip(),
            "created_on": created,
            "updated_on": created,
            "applied_on": "",
            "next_action": "",
            "next_action_due": "",
        }
        meta.update(extra_meta or {})
        sections = {"Posting": plain_posting(posting.strip()) or "_Paste the full job description here._"}
        sections.update(body_sections or {})
        sections.setdefault("Notes", notes.strip())
        sections.setdefault("Log", f"- {created}: Added.")
        body = f"# {meta['title']} at {meta['company']}\n" + "".join(
            f"\n## {heading}\n\n{text.strip()}\n" for heading, text in sections.items()
        )
        path = self.jobs_dir / job_id / "job.md"
        self.write(path, meta, body)
        return {"id": job_id, "path": str(path), **meta, "stage": meta["status"]}

    def update_job(self, job_id: str, changes: dict[str, Any], *, log: str = "") -> Doc:
        path = self.job_dir(job_id) / "job.md"
        stamped = dict(changes)
        if "status" in stamped:
            stamped["status"] = normalize_stage(stamped["status"])
        stamped["updated_on"] = today_iso()
        doc = self.set_meta(path, stamped)
        if log:
            self.set_body(path, append_to_section(doc.body, "Log", f"- {today_iso()}: {clip(log, 400)}"))
            doc = self.read(path)
        return doc

    def materials(self, job_id: str) -> list[dict[str, Any]]:
        folder = self.job_dir(job_id)
        items = []
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.name == "job.md" or path.name.startswith("."):
                continue
            if path.suffix.lower() not in MATERIAL_SOURCE_EXTENSIONS:
                continue
            item: dict[str, Any] = {
                "name": path.name,
                "kind": material_kind(path.name),
                "format": path.suffix.lower().lstrip("."),
                "path": str(path),
                "updated_on": datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(),
            }
            pdf = path.with_suffix(".pdf")
            if pdf.is_file():
                item["pdf"] = str(pdf)
            if qa_report_path(path).is_file():
                item["qa_report"] = str(qa_report_path(path))
            item["qa"] = qa_state(path)["state"]
            items.append(item)
        sourced = {Path(item["path"]).stem for item in items}
        for path in sorted(folder.glob("*.pdf")):
            if path.stem not in sourced:
                items.append(
                    {
                        "name": path.name,
                        "kind": material_kind(path.name),
                        "format": "pdf",
                        "path": str(path),
                        "pdf": str(path),
                        "updated_on": datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(),
                    }
                )
        return items

    # -- people ------------------------------------------------------------

    def people(self) -> list[dict[str, Any]]:
        records = []
        for doc in self._docs(self.people_dir, "*.md"):
            record = dict(doc.meta)
            record["id"] = doc.path.stem
            record["path"] = str(doc.path)
            record["name"] = str(record.get("name") or "").strip() or doc.path.stem.replace("-", " ").title()
            status = str(record.get("status") or "to_contact").strip().lower()
            record["status"] = status if status in PERSON_STATUSES else "to_contact"
            records.append(record)
        records.sort(key=lambda item: str(item.get("name", "")).lower())
        return records

    def resolve_person(self, ref: str) -> dict[str, Any]:
        return self._resolve("people", ref, self.people(), ("id", "name", "company"))

    def create_person(
        self,
        *,
        name: str,
        company: str = "",
        role: str = "",
        email: str = "",
        linkedin: str = "",
        why: str = "",
        status: str = "to_contact",
        next_touch: str = "",
        jobs: list[str] | None = None,
        notes: str = "",
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("A person needs a name.")
        person_id = slugify(name, limit=40, fallback="person")
        base = person_id
        counter = 2
        while (self.people_dir / f"{person_id}.md").exists():
            person_id = f"{base}-{counter}"
            counter += 1
        meta: dict[str, Any] = {
            "name": name.strip(),
            "company": company.strip(),
            "role": role.strip(),
            "email": email.strip(),
            "linkedin": linkedin.strip(),
            "status": status if status in PERSON_STATUSES else "to_contact",
            "next_touch": day(next_touch),
            "jobs": list(jobs or []),
            "added_on": today_iso(),
        }
        meta.update(extra_meta or {})
        body = (
            f"# {meta['name']}\n\n## Why\n\n{why.strip() or '_Why this person matters to the search._'}\n\n"
            f"## Notes\n\n{notes.strip()}\n\n## Log\n\n- {today_iso()}: Added.\n"
        )
        path = self.people_dir / f"{person_id}.md"
        self.write(path, meta, body)
        return {"id": person_id, "path": str(path), **meta}

    def update_person(self, person_id: str, changes: dict[str, Any], *, log: str = "") -> Doc:
        path = self.people_dir / f"{person_id}.md"
        if not path.is_file():
            raise KeyError(f"No person file named {person_id!r}.")
        doc = self.set_meta(path, changes) if changes else self.read(path)
        if log:
            self.set_body(path, append_to_section(doc.body, "Log", f"- {today_iso()}: {clip(log, 400)}"))
            doc = self.read(path)
        return doc

    # -- leads -------------------------------------------------------------

    def leads(self) -> list[dict[str, Any]]:
        records = []
        for doc in self._docs(self.leads_dir, "*.md"):
            record = dict(doc.meta)
            record["id"] = doc.path.stem
            record["path"] = str(doc.path)
            status = str(record.get("status") or "new").strip().lower()
            record["status"] = status if status in LEAD_STATUSES else "new"
            records.append(record)
        records.sort(key=lambda item: (day(item.get("found_on")), item["id"]), reverse=True)
        return records

    def resolve_lead(self, ref: str) -> dict[str, Any]:
        return self._resolve("leads", ref, self.leads(), ("id", "company", "title"))

    def create_lead(
        self,
        *,
        company: str,
        title: str,
        url: str = "",
        location: str = "",
        posting: str = "",
        source: str = "",
        found_on: str = "",
        status: str = "new",
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_url = url.strip().rstrip("/").lower()
        if normalized_url:
            for lead in self.leads():
                if str(lead.get("url", "")).strip().rstrip("/").lower() == normalized_url:
                    return {**lead, "duplicate": True}
        lead_id = f"{slugify(company, limit=28, fallback='company')}-{slugify(title, limit=36, fallback='role')}"
        base = lead_id
        counter = 2
        while (self.leads_dir / f"{lead_id}.md").exists():
            lead_id = f"{base}-{counter}"
            counter += 1
        meta: dict[str, Any] = {
            "company": company.strip() or "Unknown company",
            "title": title.strip() or "Untitled role",
            "status": status if status in LEAD_STATUSES else "new",
            "location": location.strip(),
            "url": url.strip(),
            "source": source.strip(),
            "found_on": day(found_on) or today_iso(),
        }
        meta.update(extra_meta or {})
        body = f"# {meta['title']} at {meta['company']}\n\n## Posting\n\n{plain_posting(posting.strip())}\n"
        path = self.leads_dir / f"{lead_id}.md"
        self.write(path, meta, body)
        return {"id": lead_id, "path": str(path), **meta}

    # -- evidence and profile ---------------------------------------------

    def evidence(self, *, include_retired: bool = False) -> list[dict[str, Any]]:
        records = []
        for doc in self._docs(self.evidence_dir, "*.md"):
            status = str(doc.meta.get("status") or "active").strip().lower()
            if status not in EVIDENCE_STATUSES:
                status = "active"
            if status == "retired" and not include_retired:
                continue
            record = dict(doc.meta)
            record["id"] = doc.path.stem
            record["path"] = str(doc.path)
            record["status"] = status
            record["body"] = doc.body
            record.setdefault("title", doc.path.stem.replace("-", " ").title())
            records.append(record)
        return records

    def profile_text(self, name: str) -> str:
        """Body of profile/<name>.md, or an empty string when the file is absent."""
        path = self.profile_dir / f"{name}.md"
        if not path.is_file():
            return ""
        return self.read(path).body.strip()

    def profile_meta(self) -> dict[str, Any]:
        path = self.profile_dir / "profile.md"
        return self.read(path).meta if path.is_file() else {}
