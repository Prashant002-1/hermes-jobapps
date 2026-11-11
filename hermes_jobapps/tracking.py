"""Tracking views and updates computed from the plain-file workspace."""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from .workspace import (
    OPEN_STAGES,
    PERSON_STATUSES,
    STAGES,
    _STAGE_ALIASES,
    AmbiguousReference,
    Workspace,
    clip,
    day,
    normalize_stage,
    section,
    set_section,
)


VIEWS = ("today", "jobs", "people", "leads", "stats")
PURPOSES = ("resume", "cover_letter", "application_answers", "outreach", "interview", "general")
RESEARCH_PURPOSES = ("cover_letter", "outreach", "interview", "general")
PLAYBOOK_SECTIONS = {
    "resume": "Resume",
    "cover_letter": "Cover letter",
    "application_answers": "Application answers",
    "outreach": "Outreach",
    "interview": "Interview",
}
OPEN_LEAD_STATUSES = ("new", "shortlisted")
CLOSING_STAGES = ("rejected", "closed", "skipped")
RESUME_SOURCE_FORMATS = ("typ", "tex")
PASSING_QA = ("pass", "review")

DUE_HORIZON_DAYS = 3
IN_PROGRESS_DAYS = 21
MAX_LIMIT = 50
MAX_MATCHES = 5
MAX_NESTED = 6
MAX_STALE_SHOWN = 5
MAX_BRIEF_LIST = 20
MIN_RANKED_FILES = 3
POSTING_CHARS = 14000

POSTING_CUT = "\n[posting truncated: read job.md for the rest]"
SECTION_CUT = "\n[truncated: read job.md for the rest]"
EVIDENCE_NOTE = (
    "Some evidence files were left out to fit the budget. Absence here does not mean absence of "
    "experience; open the listed paths when a requirement is not covered."
)
READY_HINT = (
    "Run jobapps_check on these files, fix what it reports, then mark ready. "
    "Use force only when the user explicitly accepts the risk."
)

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "the and for with you your our are will that this from have has not but all can who what when "
    "how their they them its into about more other such use using work working role team job "
    "ability strong including must may also etc any each well able new years".split()
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _line(value: Any) -> str:
    return " ".join(_text(value).split())


def _compact(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value not in ("", None, [], {})}


def _date(value: Any) -> date | None:
    text = day(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _iso_arg(value: Any, label: str) -> str:
    text = _text(value)
    try:
        if not _ISO_RE.match(text):
            raise ValueError(text)
        date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{label} must be a date written as YYYY-MM-DD, got {value!r}.") from None
    return text


def _as_list(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else [value]
    return [text for text in (_text(item) for item in values) if text]


def _matches(query: str, record: dict[str, Any], fields: tuple[str, ...]) -> bool:
    haystack = " ".join(_text(record.get(key)) for key in fields).lower()
    return all(word in haystack for word in query.lower().split())


def _cut(text: str, limit: int, marker: str = SECTION_CUT) -> str:
    text = text.strip("\n")
    return text if len(text) <= limit else text[:limit].rstrip() + marker


def _meaningful(text: str) -> bool:
    for raw in text.splitlines():
        line = raw.strip()
        if line and not (len(line) > 1 and line.startswith("_") and line.endswith("_")):
            return True
    return False


def _followup_days(ws: Workspace, key: str, default: int) -> int:
    value = (ws.settings().get("followups") or {}).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default


def _put(
    target: dict[str, Any],
    name: str,
    records: list[Any],
    limit: int,
    render: Callable[[Any], dict[str, Any]],
    *,
    keep_empty: bool = False,
) -> None:
    if records or keep_empty:
        target[name] = [render(record) for record in records[:limit]]
        target[f"{name}_total"] = len(records)


def job_header(record: dict[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "job": _text(record.get("id")),
            "company": _text(record.get("company")),
            "title": _text(record.get("title")),
            "stage": record.get("stage") or normalize_stage(record.get("status")),
            "location": _text(record.get("location")),
            "url": _text(record.get("url")),
            "applied_on": day(record.get("applied_on")),
            "next_action": clip(record.get("next_action"), 160),
            "due": day(record.get("next_action_due")),
            "updated_on": day(record.get("updated_on")),
            "priority": _priority(record.get("priority")) if _priority(record.get("priority")) != "normal" else "",
            "referral": _text(record.get("referral")),
        }
    )


PRIORITIES = ("high", "normal", "low")
_PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
POSTING_STALE_DAYS = 21
MAX_REMINDERS = 4


def _priority(value: Any) -> str:
    key = _text(value).lower()
    return key if key in PRIORITIES else "normal"


def _reminders(ws: Workspace, job: dict[str, Any], stage: str, now: date) -> list[str]:
    """What still separates this application from the strongest one, at the moment it matters."""
    job_id = job["id"]
    company = _text(job.get("company"))
    body = ws.job_doc(job_id).body
    kinds = {item["kind"] for item in ws.materials(job_id)}
    people = [
        person
        for person in ws.people()
        if (company and _text(person.get("company")).lower() == company.lower())
        or job_id in _as_list(person.get("jobs"))
    ]
    notes: list[str] = []
    if not people and not _text(job.get("referral")):
        notes.append(
            f"No one at {company or 'this company'} is tracked. A referral or a short note to the hiring manager "
            "is the strongest lever: find someone there and reach out before or right after applying."
        )
    elif stage == "applied":
        waiting = [_text(person.get("name")) for person in people if person["status"] == "to_contact"]
        if waiting:
            notes.append(f"Tell {', '.join(waiting[:3])} that the application is in.")
    if stage == "ready":
        if _meaningful(section(body, "Application questions")) and "application_answers" not in kinds:
            notes.append("The posting lists application questions and there is no answers file yet.")
        if _priority(job.get("priority")) == "high" and "cover_letter" not in kinds:
            notes.append("High-priority role without a cover letter.")
        if not _meaningful(section(body, "Strategy")):
            notes.append("job.md has no Strategy section: the positioning thesis keeps every document telling one story.")
        seen = _date(job.get("posted_on")) or _date(job.get("created_on"))
        if seen and (now - seen).days > POSTING_STALE_DAYS:
            notes.append(f"The posting is {(now - seen).days} days old. Confirm it is still open before submitting.")
    return notes[:MAX_REMINDERS]


def _person_item(record: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    full = {
        "person": _text(record.get("id")),
        "name": _text(record.get("name")),
        "company": _text(record.get("company")),
        "role": _text(record.get("role")),
        "email": _text(record.get("email")),
        "linkedin": _text(record.get("linkedin")),
        "status": _text(record.get("status")),
        "next_touch": day(record.get("next_touch")),
        "jobs": _as_list(record.get("jobs")),
        "path": _text(record.get("path")),
    }
    return _compact({key: full[key] for key in keys})


_PERSON_ALL = ("person", "name", "company", "role", "email", "linkedin", "status", "next_touch", "jobs")
_PERSON_SAVED = _PERSON_ALL + ("path",)
_PERSON_ATTENTION = ("person", "name", "company", "role", "status", "next_touch")
_PERSON_BRIEF = ("person", "name", "role", "status", "email", "linkedin")


def _lead_item(record: dict[str, Any]) -> dict[str, Any]:
    preflight = record.get("preflight")
    if isinstance(preflight, (list, tuple)):
        preflight = "; ".join(_as_list(preflight))
    return _compact(
        {
            "lead": _text(record.get("id")),
            "company": _text(record.get("company")),
            "title": _text(record.get("title")),
            "location": _text(record.get("location")),
            "url": _text(record.get("url")),
            "found_on": day(record.get("found_on")),
            "status": _text(record.get("status")),
            "preflight": clip(preflight, 160),
        }
    )


def _material_items(ws: Workspace, job_id: str, keys: tuple[str, ...], limit: int) -> dict[str, Any]:
    materials = ws.materials(job_id)
    result: dict[str, Any] = {
        "materials": [_compact({key: item.get(key) for key in keys}) for item in materials[:limit]]
    }
    if len(materials) > limit:
        result["materials_total"] = len(materials)
    return result


def _ambiguous_jobs(exc: AmbiguousReference) -> dict[str, Any]:
    return {
        "ambiguous": True,
        "matches": [job_header(match) for match in exc.matches[:MAX_MATCHES]],
        "matches_total": len(exc.matches),
        "hint": "Call again with the exact job id.",
    }


def _ambiguous_people(matches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ambiguous": True,
        "matches": [_person_item(match, _PERSON_ATTENTION) for match in matches[:MAX_MATCHES]],
        "matches_total": len(matches),
        "hint": "Call again with the exact person id.",
    }


# ---------------------------------------------------------------------------
# overview
# ---------------------------------------------------------------------------


def overview(
    ws: Workspace,
    *,
    view: str = "today",
    stage: str = "",
    query: str = "",
    limit: int = 12,
    today: date | None = None,
) -> dict[str, Any]:
    now = today or date.today()
    view = _text(view).lower() or "today"
    if view not in VIEWS:
        raise ValueError(f"view must be one of: {', '.join(VIEWS)}.")
    stage = _text(stage).lower()
    query = _text(query)
    if view == "today" and (stage or query):
        view = "jobs"
    if view == "jobs" and stage and stage not in STAGES:
        raise ValueError(f"stage must be one of: {', '.join(STAGES)}.")
    try:
        limit = max(1, min(MAX_LIMIT, int(limit)))
    except (TypeError, ValueError):
        limit = 12

    jobs = ws.jobs()
    people = ws.people()
    leads = [lead for lead in ws.leads() if lead["status"] in OPEN_LEAD_STATUSES]
    leads.sort(key=lambda lead: lead["status"] != "shortlisted")

    counts = {name: 0 for name in STAGES}
    for job in jobs:
        counts[job["stage"]] += 1
    counts.update(total=len(jobs), people=len(people), leads=len(leads))
    result: dict[str, Any] = {"as_of": now.isoformat(), "workspace": str(ws.root), "counts": counts}

    if view == "jobs":
        rows = [
            job
            for job in jobs
            if (not stage or job["stage"] == stage) and _matches(query, job, ("id", "company", "title"))
        ]
        _put(result, "jobs", rows, limit, job_header, keep_empty=True)
        result["filter"] = _compact({"stage": stage, "query": query})
        return result
    if view == "people":
        rows = [person for person in people if _matches(query, person, ("id", "name", "company", "role"))]
        _put(result, "people", rows, limit, lambda person: _person_item(person, _PERSON_ALL), keep_empty=True)
        return result
    if view == "leads":
        rows = [lead for lead in leads if _matches(query, lead, ("id", "company", "title"))]
        _put(result, "leads", rows, limit, _lead_item, keep_empty=True)
        return result

    if view == "stats":
        result["stats"] = _stats(ws, jobs)
        return result

    result["attention"] = _attention(ws, jobs, people, leads, limit, now)
    setup = []
    if not _text(ws.profile_meta().get("name")):
        setup.append("Add your name and contact details to profile/profile.md.")
    if not any(item["status"] == "active" for item in ws.evidence()):
        setup.append("Add evidence files under evidence/: one per role, project or degree.")
    if not jobs:
        setup.append("No jobs yet: paste a posting to start the first one.")
    if setup:
        result["setup"] = setup
    return result


_INTERVIEW_LOG_RE = re.compile(r"Status:.*\b(interview\w*|phone_screen|onsite|offer)\b", re.IGNORECASE)


def _stats(ws: Workspace, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Funnel facts for applications that were actually sent. Observations, not scores."""
    months: dict[str, dict[str, int]] = {}
    families: dict[str, dict[str, int]] = {}
    channels: dict[str, dict[str, int]] = {}
    totals = {"applied": 0, "interviews": 0, "offers": 0, "rejected": 0, "no_reply": 0}
    waits: list[int] = []
    for job in jobs:
        applied = _date(job.get("applied_on"))
        stage = job["stage"]
        if applied is None and stage not in ("applied", "interviewing", "offer"):
            continue
        interviewed = stage in ("interviewing", "offer")
        if not interviewed and stage in ("rejected", "closed"):
            interviewed = bool(_INTERVIEW_LOG_RE.search(section(ws.job_doc(job["id"]).body, "Log")))
        outcome = "interviews" if interviewed else "rejected" if stage == "rejected" else "no_reply" if stage == "applied" else ""
        totals["applied"] += 1
        if stage == "offer":
            totals["offers"] += 1
        if outcome:
            totals[outcome] += 1
        month = applied.isoformat()[:7] if applied else "undated"
        family = _text(job.get("role_family")) or "unlabelled"
        channel = "referral" if _text(job.get("referral")) else "cold"
        for table, key in ((months, month), (families, family), (channels, channel)):
            row = table.setdefault(key, {"applied": 0, "interviews": 0, "rejected": 0, "no_reply": 0})
            row["applied"] += 1
            if outcome:
                row[outcome] += 1
        updated = _date(job.get("updated_on"))
        if applied and updated and outcome in ("interviews", "rejected"):
            waits.append(max(0, (updated - applied).days))
    result: dict[str, Any] = dict(totals)
    if totals["applied"]:
        result["interview_rate"] = f"{totals['interviews']} of {totals['applied']}"
    if waits:
        waits.sort()
        result["median_days_to_outcome"] = waits[len(waits) // 2]
    result["by_channel"] = [{"channel": key, **channels[key]} for key in sorted(channels)]
    result["by_month"] = [{"month": key, **months[key]} for key in sorted(months)][-12:]
    ranked = sorted(families.items(), key=lambda pair: (-pair[1]["applied"], pair[0]))[:8]
    result["by_role_family"] = [{"role_family": key, **row} for key, row in ranked]
    return result


_PRECEDENT_KINDS = {
    "resume": "resume",
    "cover_letter": "cover_letter",
    "application_answers": "application_answers",
    "outreach": "outreach",
    "interview": "interview",
    "general": "resume",
}
_PRECEDENT_STAGES = ("ready", "applied", "interviewing", "offer", "rejected")
_SOURCE_SUFFIXES = (".typ", ".tex", ".md", ".txt")
MAX_PRECEDENTS = 3
PRECEDENT_NOTE = (
    "Earlier documents written for similar roles, strongest match first. Start from the closest one "
    "instead of a blank page, then re-check every claim against the evidence."
)


def _precedents(ws: Workspace, job: dict[str, Any], job_text: str, purpose: str) -> list[dict[str, Any]]:
    from .workspace import material_kind

    wanted_kind = _PRECEDENT_KINDS[purpose]
    title_tokens = _tokens(_text(job.get("title")))
    text_tokens = _tokens(job_text)
    family = _text(job.get("role_family")).lower()
    scored: list[tuple[int, str, dict[str, Any], str]] = []
    for other in ws.jobs():
        if other["id"] == job["id"] or other["stage"] not in _PRECEDENT_STAGES:
            continue
        folder = ws.jobs_dir / other["id"]
        files = sorted(
            path
            for path in folder.iterdir()
            if path.is_file()
            and path.name != "job.md"
            and path.suffix.lower() in _SOURCE_SUFFIXES
            and material_kind(path.name) == wanted_kind
        )
        if not files:
            continue
        other_title = _tokens(_text(other.get("title")))
        other_text = _tokens(section(ws.job_doc(other["id"]).body, "Requirements"))
        score = 4 * len(title_tokens & other_title) + len(text_tokens & (other_title | other_text))
        if family and _text(other.get("role_family")).lower() == family:
            score += 3
        if score <= 0:
            continue
        if other["stage"] in ("interviewing", "offer"):
            score += 6
        newest = max(files, key=lambda path: path.stat().st_mtime)
        scored.append((score, other["updated_on"], other, str(newest)))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        _compact(
            {
                "job": other["id"],
                "company": _text(other.get("company")),
                "title": _text(other.get("title")),
                "stage": other["stage"],
                "file": path,
            }
        )
        for _, _, other, path in scored[:MAX_PRECEDENTS]
    ]


def _attention(
    ws: Workspace,
    jobs: list[dict[str, Any]],
    people: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    limit: int,
    now: date,
) -> dict[str, Any]:
    horizon = now + timedelta(days=DUE_HORIZON_DAYS)
    attention: dict[str, Any] = {}

    due = [
        (due_on, job)
        for job in jobs
        if job["stage"] in OPEN_STAGES
        for due_on in [_date(job.get("next_action_due"))]
        if due_on and due_on <= horizon
    ]
    due.sort(key=lambda pair: (_PRIORITY_ORDER[_priority(pair[1].get("priority"))], pair[0], pair[1]["id"]))
    _put(attention, "due", due, limit, lambda pair: {**job_header(pair[1]), "days_overdue": (now - pair[0]).days})

    quiet_after = _followup_days(ws, "application_check_after_days", 10)
    stale_after = max(quiet_after + 1, _followup_days(ws, "application_stale_after_days", 45))
    quiet = []
    stale = []
    for job in jobs:
        applied = _date(job.get("applied_on"))
        if job["stage"] != "applied" or not applied or (now - applied).days < quiet_after:
            continue
        due_on = _date(job.get("next_action_due"))
        if due_on and due_on >= now:
            continue
        (stale if (now - applied).days >= stale_after else quiet).append((applied, job))

    def applied_item(pair: tuple[date, dict[str, Any]]) -> dict[str, Any]:
        return _compact(
            {
                "job": pair[1]["id"],
                "company": _text(pair[1].get("company")),
                "title": _text(pair[1].get("title")),
                "applied_on": pair[0].isoformat(),
                "days": (now - pair[0]).days,
            }
        )

    for rows in (quiet, stale):
        rows.sort(key=lambda pair: pair[1]["id"])
        rows.sort(key=lambda pair: pair[0], reverse=True)
    _put(attention, "applied_quiet", quiet, limit, applied_item)
    _put(attention, "applied_stale", stale, min(limit, MAX_STALE_SHOWN), applied_item)
    if stale:
        attention["applied_stale_hint"] = (
            f"No reply for {stale_after} days or more. Follow up once through a person, or close them "
            "so the pipeline shows what is live."
        )

    by_priority = lambda job: _PRIORITY_ORDER[_priority(job.get("priority"))]  # noqa: E731
    _put(
        attention,
        "ready",
        sorted((job for job in jobs if job["stage"] == "ready"), key=by_priority),
        limit,
        lambda job: _compact(
            {**job_header(job), **_material_items(ws, job["id"], ("name", "kind", "qa"), MAX_NESTED)}
        ),
    )
    _put(attention, "interviewing", [job for job in jobs if job["stage"] in ("interviewing", "offer")], limit, job_header)

    in_progress = []
    for job in jobs:
        updated = _date(job.get("updated_on"))
        if (
            job["stage"] == "new"
            and _text(job.get("decision")).lower() != "skip"
            and updated
            and (now - updated).days <= IN_PROGRESS_DAYS
        ):
            in_progress.append(job)
    in_progress.sort(key=by_priority)
    _put(attention, "in_progress", in_progress, limit, job_header)

    touch = []
    for person in people:
        next_touch = _date(person.get("next_touch"))
        if person["status"] in ("follow_up", "to_contact") or (next_touch and next_touch <= horizon):
            touch.append(person)
    touch.sort(
        key=lambda person: (
            person["status"] != "follow_up",
            not day(person.get("next_touch")),
            day(person.get("next_touch")),
            _text(person.get("name")).lower(),
        )
    )
    _put(attention, "people", touch, limit, lambda person: _person_item(person, _PERSON_ATTENTION))

    fresh_days = _followup_days(ws, "lead_fresh_days", 30)
    fresh = [
        lead
        for lead in leads
        for found in [_date(lead.get("found_on"))]
        if found and (now - found).days <= fresh_days
    ]
    _put(attention, "leads", fresh, limit, _lead_item)
    return attention


# ---------------------------------------------------------------------------
# brief
# ---------------------------------------------------------------------------


def brief(
    ws: Workspace,
    job_ref: str,
    *,
    purpose: str = "resume",
    max_chars: int | None = None,
    evidence: bool = True,
) -> dict[str, Any]:
    purpose = _text(purpose).lower() or "resume"
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of: {', '.join(PURPOSES)}.")
    try:
        job = ws.resolve_job(job_ref)
    except AmbiguousReference as exc:
        return _ambiguous_jobs(exc)
    job_id = job["id"]
    folder = os.path.abspath(ws.job_dir(job_id))
    body = ws.job_doc(job_id).body
    posting = section(body, "Posting")
    requirements = section(body, "Requirements")
    company = _text(job.get("company")).lower()
    people = [
        person
        for person in ws.people()
        if (company and _text(person.get("company")).lower() == company) or job_id in _as_list(person.get("jobs"))
    ]
    budget = max_chars or (ws.settings().get("brief") or {}).get("max_chars") or 60000

    result: dict[str, Any] = {
        "job": _compact({**job_header(job), "folder": folder, "decision": _text(job.get("decision"))}),
        "posting": _cut(posting, POSTING_CHARS, POSTING_CUT),
        "assessment": _cut(section(body, "Assessment"), 3000),
        "strategy": _cut(section(body, "Strategy"), 3000) if _meaningful(section(body, "Strategy")) else "",
        "requirements": _cut(requirements, 3000),
        "application_questions": _cut(section(body, "Application questions"), 2500)
        if purpose in ("application_answers", "general")
        else "",
        "notes": _cut(section(body, "Notes"), 2000),
        "research": _cut(section(body, "Research"), 3000) if purpose in RESEARCH_PURPOSES else "",
        **_material_items(ws, job_id, ("name", "kind", "qa", "path"), MAX_BRIEF_LIST),
        "profile": _compact({"contact": _compact(dict(ws.profile_meta())), "text": ws.profile_text("profile")}),
        "voice": ws.profile_text("voice"),
        "playbook": _playbook(ws.profile_text("playbook"), purpose),
        **(
            _evidence(ws, " ".join((_text(job.get("title")), posting, requirements)), int(budget))
            if evidence
            else _evidence_index(ws)
        ),
    }
    _put(result, "people", people, MAX_BRIEF_LIST, lambda person: _person_item(person, _PERSON_BRIEF))
    if len(people) <= MAX_BRIEF_LIST:
        result.pop("people_total", None)
    precedents = _precedents(ws, job, " ".join((_text(job.get("title")), requirements)), purpose)
    if precedents:
        result["precedents"] = precedents
        result["precedents_note"] = PRECEDENT_NOTE
    result["write_to"] = folder
    if purpose != "general" and not _meaningful(section(body, "Strategy")):
        result["next"] = (
            "First add a short Strategy section to job.md (thesis, proof for each key requirement, gaps, way in), "
            "then write the document in the job folder and run jobapps_check on it."
        )
    else:
        result["next"] = "Write the document in the job folder, then run jobapps_check on it."
    return _compact(result)


def _playbook(body: str, purpose: str) -> str:
    headings = list(_HEADING_RE.finditer(body))
    if not headings:
        rules = "\n".join(line for line in body.splitlines() if not line.startswith("# ")).strip()
        return rules if _meaningful(rules) else ""
    wanted = None if purpose == "general" else {"all documents", PLAYBOOK_SECTIONS[purpose].lower()}
    blocks = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        heading = match.group(1)
        text = body[match.end() : end].strip("\n")
        if (wanted is None or heading.lower() in wanted) and _meaningful(text):
            blocks.append(f"## {heading}\n\n{text}")
    return "\n\n".join(blocks)


def _tokens(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if len(word) >= 3 and word not in _STOPWORDS}


def _evidence_index(ws: Workspace) -> dict[str, Any]:
    files = [
        _compact({"id": record["id"], "title": _text(record.get("title")), "path": record["path"]})
        for record in ws.evidence()
    ]
    return {"evidence": {"mode": "index", "files": files}} if files else {}


def _evidence(ws: Workspace, job_text: str, budget: int) -> dict[str, Any]:
    files = [(record, _text(record.get("body"))) for record in ws.evidence()]
    if not files:
        return {}
    included = files
    omitted: list[tuple[dict[str, Any], str]] = []
    mode = "full"
    if sum(len(text) for _, text in files) > budget:
        mode = "ranked"
        wanted = _tokens(job_text)

        def score(pair: tuple[dict[str, Any], str]) -> int:
            record, text = pair
            own = " ".join((_text(record.get("title")), " ".join(_as_list(record.get("tags"))), text))
            return len(_tokens(own) & wanted)

        included = []
        used = 0
        for pair in sorted(files, key=score, reverse=True):
            if len(included) < MIN_RANKED_FILES or used + len(pair[1]) <= budget:
                included.append(pair)
                used += len(pair[1])
            else:
                omitted.append(pair)

    evidence: dict[str, Any] = {
        "mode": mode,
        "files": [
            _compact(
                {
                    "id": record["id"],
                    "title": _text(record.get("title")),
                    "status": record["status"] if record["status"] == "needs_review" else "",
                    "path": record["path"],
                    "meta": _compact(
                        {key: record.get(key) for key in ("type", "organization", "role", "start", "end")}
                    ),
                    "text": text,
                }
            )
            for record, text in included
        ],
    }
    if not omitted:
        return {"evidence": evidence}
    evidence["omitted"] = [
        _compact(
            {
                "id": record["id"],
                "title": _text(record.get("title")),
                "tags": _as_list(record.get("tags"))[:8],
                "path": record["path"],
            }
        )
        for record, _ in omitted
    ]
    return {"evidence": evidence, "evidence_note": EVIDENCE_NOTE}


# ---------------------------------------------------------------------------
# track_job
# ---------------------------------------------------------------------------


def _stage_arg(status: Any) -> str | None:
    raw = _text(status)
    if not raw:
        return None
    key = raw.lower().replace("-", "_").replace(" ", "_")
    stage = normalize_stage(raw)
    if stage == "new" and key != "new" and key not in _STAGE_ALIASES:
        raise ValueError(f"status must be one of: {', '.join(STAGES)}.")
    return stage


def _next_line(action: str, due: str) -> str:
    if not action:
        return f"Due {due}." if due else "Next action cleared."
    return f"Next: {clip(action, 160)}" + (f" (due {due})." if due else ".")


def track_job(
    ws: Workspace,
    job_ref: str,
    *,
    status: str | None = None,
    next_action: str | None = None,
    due: str | None = None,
    note: str = "",
    applied_on: str | None = None,
    force: bool = False,
    priority: str | None = None,
    referral: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    now = today or date.today()
    new_stage = _stage_arg(status)
    new_priority = None
    if _text(priority):
        new_priority = _text(priority).lower()
        if new_priority not in PRIORITIES:
            raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}.")
    due_day = None if due is None else (_iso_arg(due, "due") if _text(due) else "")
    applied_day = None if applied_on is None else _iso_arg(applied_on, "applied_on")
    action = None if next_action is None else _line(next_action)
    if action == "" and due_day:
        raise ValueError("due cannot be set while next_action is being cleared.")
    note = _line(note)

    try:
        job = ws.resolve_job(job_ref)
    except AmbiguousReference as exc:
        return _ambiguous_jobs(exc)
    job_id = job["id"]
    old_stage = job["stage"]
    moving = new_stage is not None and new_stage != old_stage

    current = {
        "next_action": _text(job.get("next_action")),
        "next_action_due": day(job.get("next_action_due")),
        "applied_on": day(job.get("applied_on")),
        "priority": _priority(job.get("priority")),
        "referral": _text(job.get("referral")),
    }
    target = dict(current)
    if new_priority is not None:
        target["priority"] = new_priority
    if referral is not None:
        target["referral"] = _line(referral)
    if action is not None:
        target["next_action"] = action
        if not action:
            target["next_action_due"] = ""
    if due_day is not None:
        target["next_action_due"] = due_day
    if applied_day is not None:
        target["applied_on"] = applied_day

    forced: list[dict[str, Any]] = []
    if moving and new_stage == "applied":
        target["applied_on"] = target["applied_on"] or now.isoformat()
        upcoming = _date(target["next_action_due"])
        if action is None and not (upcoming and upcoming >= now):
            check_after = _followup_days(ws, "application_check_after_days", 10)
            target["next_action"] = "Check on the application"
            target["next_action_due"] = (now + timedelta(days=check_after)).isoformat()
    elif moving and new_stage == "ready":
        unchecked = [
            {"name": item["name"], "qa": item.get("qa", "none")}
            for item in ws.materials(job_id)
            if item["format"] in RESUME_SOURCE_FORMATS
            and (
                (item["kind"] == "resume" and item.get("qa") not in PASSING_QA)
                or (item["kind"] != "resume" and item.get("qa") == "fail")
            )
        ]
        if unchecked and not force:
            return {"ok": False, "blocked": unchecked, "hint": READY_HINT}
        forced = unchecked
    elif moving and new_stage in CLOSING_STAGES and action is None and due_day is None:
        target["next_action"] = ""
        target["next_action_due"] = ""

    changes: dict[str, Any] = {"status": new_stage} if moving else {}
    changes.update({key: value for key, value in target.items() if value != current[key]})

    if moving:
        log = f"Status: {old_stage} -> {new_stage}."
        if forced:
            names = ", ".join(f"{item['name']} ({item['qa']})" for item in forced[:MAX_NESTED])
            log += f" Forced past the resume check: {names}."
        log = f"{log} {note}".strip()
    elif note:
        log = note
    elif "next_action" in changes or "next_action_due" in changes:
        log = _next_line(target["next_action"], target["next_action_due"])
    elif "applied_on" in changes:
        log = f"Applied on {target['applied_on']}."
    elif "priority" in changes:
        log = f"Priority: {target['priority']}."
    elif "referral" in changes:
        log = f"Referral: {target['referral'] or 'cleared'}."
    else:
        log = ""

    if not changes and not log:
        return {"ok": True, "unchanged": True, "job": job_header(job)}
    doc = ws.update_job(job_id, changes, log=log)
    after = {**doc.meta, "id": job_id}
    result: dict[str, Any] = {"ok": True, "job": job_header(after), "changed": list(changes)}
    if moving and new_stage in ("ready", "applied"):
        reminders = _reminders(ws, after, new_stage, now)
        if reminders:
            result["reminders"] = reminders
    return result


def close_stale(ws: Workspace, *, today: date | None = None) -> dict[str, Any]:
    """Close every application that has been silent past the stale threshold."""
    now = today or date.today()
    quiet_after = _followup_days(ws, "application_check_after_days", 10)
    stale_after = max(quiet_after + 1, _followup_days(ws, "application_stale_after_days", 45))
    closed = []
    for job in ws.jobs():
        applied = _date(job.get("applied_on"))
        due_on = _date(job.get("next_action_due"))
        if job["stage"] != "applied" or not applied or (now - applied).days < stale_after:
            continue
        if due_on and due_on >= now:
            continue
        ws.update_job(
            job["id"],
            {"status": "closed", "next_action": "", "next_action_due": ""},
            log=f"Status: applied -> closed. No reply {(now - applied).days} days after applying.",
        )
        closed.append(job["id"])
    return {"ok": True, "closed": len(closed), "jobs": closed[:MAX_LIMIT]}


# ---------------------------------------------------------------------------
# save_person
# ---------------------------------------------------------------------------


def save_person(
    ws: Workspace,
    *,
    person: str = "",
    name: str = "",
    company: str = "",
    role: str = "",
    email: str = "",
    linkedin: str = "",
    why: str = "",
    status: str | None = None,
    next_touch: str | None = None,
    job: str = "",
    note: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    now = today or date.today()
    fields = {
        "name": _line(name),
        "company": _line(company),
        "role": _line(role),
        "email": _line(email),
        "linkedin": _line(linkedin),
    }
    why = _text(why)
    note = _line(note)
    new_status = _text(status).lower().replace("-", "_").replace(" ", "_") or None
    if new_status and new_status not in PERSON_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(PERSON_STATUSES)}.")
    if fields["email"] and "@" not in fields["email"]:
        raise ValueError("email must be an address containing @. Leave it empty when it is not known.")
    touch = None if next_touch is None else (_iso_arg(next_touch, "next_touch") if _text(next_touch) else "")

    job_id = ""
    if _text(job):
        try:
            job_id = ws.resolve_job(job)["id"]
        except AmbiguousReference as exc:
            return _ambiguous_jobs(exc)

    existing: dict[str, Any] | None = None
    if _text(person):
        try:
            existing = ws.resolve_person(person)
        except AmbiguousReference as exc:
            return _ambiguous_people(exc.matches)
    elif fields["name"]:
        same = [item for item in ws.people() if _line(item.get("name")).lower() == fields["name"].lower()]
        if len(same) > 1:
            return _ambiguous_people(same)
        existing = same[0] if same else None
        if existing:
            fields["name"] = ""

    follow_up_on = (now + timedelta(days=_followup_days(ws, "networking_after_days", 5))).isoformat()

    if existing is None:
        if not fields["name"] or not why:
            raise ValueError("Saving a new person needs a name and why they matter.")
        new_status = new_status or "to_contact"
        if touch is None:
            touch = follow_up_on if new_status == "contacted" else ""
        created = ws.create_person(
            **fields,
            why=why,
            status=new_status,
            next_touch=touch,
            jobs=[job_id] if job_id else [],
        )
        if note:
            ws.update_person(created["id"], {}, log=note)
        return {"ok": True, "created": True, "person": _person_item(created, _PERSON_SAVED)}

    person_id = existing["id"]
    path = Path(existing["path"])
    old_status = existing["status"]
    status_changed = new_status is not None and new_status != old_status
    changes: dict[str, Any] = {
        key: value for key, value in fields.items() if value and value != _text(existing.get(key))
    }
    if status_changed:
        changes["status"] = new_status

    old_touch = day(existing.get("next_touch"))
    new_touch = old_touch
    if touch is not None:
        new_touch = touch
    elif status_changed and new_status == "contacted":
        new_touch = follow_up_on
    elif status_changed and new_status in ("replied", "paused"):
        new_touch = ""
    if new_touch != old_touch:
        changes["next_touch"] = new_touch

    linked = _as_list(existing.get("jobs"))
    if job_id and job_id not in linked:
        changes["jobs"] = linked + [job_id]

    body = ws.read(path).body
    old_why = section(body, "Why").strip()
    why_changed = bool(why) and why != old_why

    parts = []
    if status_changed:
        parts.append(f"Status: {old_status} -> {new_status}.")
    if note:
        parts.append(note)
    if why_changed and _meaningful(old_why):
        parts.append(f"Why replaced; it was: {clip(old_why, 160)}")
    log = " ".join(parts)

    if not changes and not log and not why_changed:
        return {"ok": True, "created": False, "unchanged": True, "person": _person_item(existing, _PERSON_SAVED)}
    if why_changed:
        ws.set_body(path, set_section(body, "Why", why))
    doc = ws.update_person(person_id, changes, log=log)
    saved = {**existing, **doc.meta, "id": person_id, "path": str(path)}
    if saved.get("status") not in PERSON_STATUSES:
        saved["status"] = old_status
    return {"ok": True, "created": False, "person": _person_item(saved, _PERSON_SAVED)}
