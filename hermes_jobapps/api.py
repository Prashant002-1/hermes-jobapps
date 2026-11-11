"""Cockpit API as plain functions.

Both hosts (the standalone local server and the Hermes dashboard tab) call
`handle` so the cockpit behaves the same wherever it is opened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .workspace import AmbiguousReference, Workspace, clip, section, set_section


JOB_SECTIONS = ("Posting", "Assessment", "Strategy", "Requirements", "Application questions", "Research", "Notes", "Log")
VIEWABLE_SUFFIXES = {".md", ".typ", ".tex", ".txt", ".json", ".pdf", ".docx", ".png", ".jpg", ".jpeg"}
_ID = r"[A-Za-z0-9][A-Za-z0-9._\-]*"


@dataclass
class FileResult:
    path: Path


def handle(ws: Workspace, method: str, path: str, query: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    """Route one request. Returns (HTTP status, JSON-ready payload or FileResult)."""
    query = query or {}
    body = body if isinstance(body, dict) else {}
    route = "/" + path.strip("/")
    try:
        return _route(ws, method.upper(), route, query, body)
    except AmbiguousReference as exc:
        return 409, {"error": str(exc)}
    except KeyError as exc:
        return 404, {"error": str(exc.args[0]) if exc.args else "Not found."}
    except (ValueError, FileNotFoundError) as exc:
        return 400, {"error": str(exc)}


def _route(ws: Workspace, method: str, route: str, query: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
    from . import intake, tracking

    if method == "GET":
        if route == "/state":
            return 200, state(ws)
        if route == "/stats":
            return 200, tracking.overview(ws, view="stats")
        if route == "/evidence":
            return 200, {"evidence": evidence_index(ws)}
        if route == "/doc":
            return 200, document(ws, query.get("path", ""))
        if route == "/file":
            return 200, FileResult(_viewable(ws, query.get("path", "")))
        match = re.fullmatch(rf"/jobs/({_ID})", route)
        if match:
            return 200, job_detail(ws, match.group(1))
        return 404, {"error": f"Unknown route: {route}"}

    if method != "POST":
        return 405, {"error": "Use GET or POST."}

    if route == "/jobs/close-stale":
        return 200, tracking.close_stale(ws)
    if route == "/jobs":
        fields = {key: str(body.get(key) or "") for key in ("url", "text", "company", "title", "location", "notes", "lead")}
        return 200, intake.add_job(ws, **fields)
    match = re.fullmatch(rf"/jobs/({_ID})/track", route)
    if match:
        return 200, tracking.track_job(
            ws,
            match.group(1),
            status=_optional(body, "status"),
            next_action=_optional(body, "next_action"),
            due=_optional(body, "due"),
            note=str(body.get("note") or ""),
            applied_on=_optional(body, "applied_on"),
            force=body.get("force") is True,
            priority=_optional(body, "priority"),
            referral=_optional(body, "referral"),
        )
    match = re.fullmatch(rf"/jobs/({_ID})/notes", route)
    if match:
        doc = ws.job_doc(match.group(1))
        ws.set_body(doc.path, set_section(doc.body, "Notes", _notes_text(body.get("text"))))
        ws.update_job(match.group(1), {})
        return 200, {"ok": True}
    if route == "/people":
        fields = {
            key: str(body.get(key) or "")
            for key in ("person", "name", "company", "role", "email", "linkedin", "why", "job", "note")
        }
        return 200, tracking.save_person(
            ws, status=_optional(body, "status"), next_touch=_optional(body, "next_touch"), **fields
        )
    match = re.fullmatch(rf"/leads/({_ID})", route)
    if match:
        status = str(body.get("status") or "")
        if status == "promote":
            return 200, intake.add_job(ws, lead=match.group(1))
        return 200, intake.set_lead_status(ws, match.group(1), status)
    if route == "/check":
        from .check import check_material

        return 200, check_material(ws, str(body.get("path") or ""), kind=str(body.get("kind") or ""), job=str(body.get("job") or ""))
    return 404, {"error": f"Unknown route: {route}"}


def _optional(body: dict[str, Any], name: str) -> str | None:
    return None if body.get(name) is None else str(body[name])


def _notes_text(value: Any) -> str:
    """Notes are one `##` section of job.md: a `##` line inside them would start another."""
    return re.sub(r"(?m)^##(?=\s|$)", "###", str(value or ""))


def _viewable(ws: Workspace, relative: str) -> Path:
    if not relative:
        raise ValueError("Missing path.")
    path = ws.inside(relative)
    if not path.is_file():
        raise KeyError(f"No such file: {relative}")
    if path.suffix.lower() not in VIEWABLE_SUFFIXES or path.name == "settings.json":
        raise ValueError("This file type cannot be opened from the cockpit.")
    return path


def state(ws: Workspace) -> dict[str, Any]:
    from .tracking import job_header, overview

    today = overview(ws, view="today", limit=50)
    jobs = []
    for record in ws.jobs():
        item = job_header(record)
        for key in ("decision", "created_on", "source"):
            if record.get(key):
                item[key] = record[key]
        jobs.append(item)
    settings = ws.settings()
    return {
        "version": __version__,
        "workspace": str(ws.root),
        "ready": ws.exists(),
        "as_of": today.get("as_of"),
        "counts": today.get("counts", {}),
        "attention": today.get("attention", {}),
        "setup": today.get("setup", []),
        "jobs": jobs,
        "people": _all(ws, "people"),
        "leads": _all(ws, "leads"),
        "followups": settings.get("followups", {}),
    }


def _all(ws: Workspace, view: str) -> list[dict[str, Any]]:
    """Every person or lead, in the compact shape the tracking view uses."""
    from .tracking import MAX_LIMIT, _lead_item, _person_item, _PERSON_ALL, OPEN_LEAD_STATUSES

    if view == "people":
        return [_person_item(person, _PERSON_ALL) for person in ws.people()]
    leads = [lead for lead in ws.leads() if lead["status"] in OPEN_LEAD_STATUSES]
    leads.sort(key=lambda lead: lead["status"] != "shortlisted")
    return [_lead_item(lead) for lead in leads][: MAX_LIMIT * 10]


def job_detail(ws: Workspace, job_id: str) -> dict[str, Any]:
    from .tracking import job_header

    record = next((item for item in ws.jobs() if item["id"] == job_id), None)
    if record is None:
        raise KeyError(f"No job folder named {job_id!r}.")
    doc = ws.job_doc(job_id)
    materials = []
    for item in ws.materials(job_id):
        entry = {
            "name": item["name"],
            "kind": item["kind"],
            "format": item["format"],
            "qa": item.get("qa", "none"),
            "updated_on": item.get("updated_on", ""),
            "path": ws.relative(Path(item["path"])),
        }
        if item.get("pdf"):
            entry["pdf"] = ws.relative(Path(item["pdf"]))
        if item.get("qa_report"):
            entry["qa_report"] = ws.relative(Path(item["qa_report"]))
        materials.append(entry)
    company = str(record.get("company") or "").strip().lower()
    people = [
        {key: person.get(key) for key in ("id", "name", "role", "status", "next_touch", "email", "linkedin") if person.get(key)}
        for person in ws.people()
        if (company and str(person.get("company") or "").strip().lower() == company)
        or job_id in (person.get("jobs") or [])
    ]
    header = job_header(record)
    header.update(
        {
            key: record[key]
            for key in ("decision", "created_on", "source", "role_family")
            if record.get(key)
        }
    )
    return {
        "job": header,
        "folder": str(ws.job_dir(job_id)),
        "path": ws.relative(doc.path),
        "sections": {name.lower().replace(" ", "_"): text for name in JOB_SECTIONS if (text := section(doc.body, name))},
        "materials": materials,
        "people": people,
    }


def evidence_index(ws: Workspace) -> list[dict[str, Any]]:
    items = []
    for record in ws.evidence(include_retired=True):
        item = {
            "id": record["id"],
            "title": record.get("title", ""),
            "type": record.get("type", ""),
            "status": record["status"],
            "tags": record.get("tags") or [],
            "path": ws.relative(Path(record["path"])),
            "summary": clip(re.sub(r"^#.*$", "", record.get("body", ""), flags=re.MULTILINE), 180),
        }
        items.append({key: value for key, value in item.items() if value not in ("", [], None)})
    return items


def document(ws: Workspace, relative: str) -> dict[str, Any]:
    path = _viewable(ws, relative)
    if path.suffix.lower() not in {".md", ".typ", ".tex", ".txt", ".json"}:
        raise ValueError("Only text files can be read as a document.")
    doc = ws.read(path)
    return {"path": ws.relative(path), "meta": doc.meta, "body": doc.body}


__all__ = ["FileResult", "document", "evidence_index", "handle", "job_detail", "state"]
