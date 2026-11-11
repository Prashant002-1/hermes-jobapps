"""Turn postings into workspace records: blocker preflight, jobs, leads, people lookups and drafts."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from . import sources
from .sources import SourceError
from .workspace import Workspace, clip, day, normalize_stage, section


MIN_POSTING_CHARS = 200
MAX_REQUIREMENTS = 10
MAX_TRACKED = 20
SETTABLE_LEAD_STATUSES = ("new", "shortlisted", "dismissed")
INACTIVE_STAGES = ("rejected", "closed", "skipped")
CRITERIA_TYPES = ("pattern", "title", "years")
CRITERIA_SEVERITIES = ("blocker", "flag", "clear")

SPONSORSHIP_ACTION = "Skip unless the user confirms work authorization is not a problem for this role."
NEXT_AFTER_BLOCKER = "A configured blocker matched. Tell the user and ask whether to skip or proceed."
NEXT_AFTER_ADD = "Call jobapps_brief for this job, then write the requested document."

_FACT_LABELS = {
    "years_required": "Years required",
    "workplace": "Workplace",
    "employment_type": "Employment type",
    "salary": "Salary",
    "sponsorship": "Sponsorship",
}


def _phrases(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern.replace(" ", r"\s+"), re.IGNORECASE) for pattern in patterns)


_SPONSOR_KIND = r"(?:visa |work |employment |immigration |h-?1b )?"
_SPONSORSHIP_DENIED = _phrases(
    rf"no {_SPONSOR_KIND}sponsorship",
    rf"(?:unable|not able|not in a position) to (?:offer |provide )?{_SPONSOR_KIND}sponsor",
    rf"(?:cannot|can not|can't|will not|won't|does not|do not|doesn't|don't|not) (?:currently )?(?:offer |provide )?{_SPONSOR_KIND}sponsor",
    r"without (?:[\w'-]+ ){0,4}?sponsorship",
    r"sponsorship (?:is |will )?(?:not|unavailable)",
    r"must be (?:a |an )?u\.?s\.? citizen",
    r"u\.?s\.? citizenship (?:is )?required",
    r"(?:u\.?s\.?|united states) citizens? only",
    r"green card (?:holder|required)",
    r"(?<!no\s)security clearance(?!\s(?:is\s)?not\s(?:required|needed))",
)
_SPONSORSHIP_OFFERED = _phrases(
    rf"{_SPONSOR_KIND}sponsorship (?:is |may be )?(?:available|offered|provided|possible)",
    r"will sponsor",
    r"open to sponsor",
    r"happy to sponsor",
    rf"(?<!un)(?<!not\s)able to (?:offer |provide )?{_SPONSOR_KIND}sponsor",
    rf"(?:offers?|provides?|offering|providing) {_SPONSOR_KIND}sponsorship",
)

_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])[ \t]+(?=[^a-z\s])|\s*\n\s*")
_YEARS_RE = re.compile(
    r"(?<![\w.,$])(\d{1,2})\s*\+?\s*(?:(?:-|–|—|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b(?!\s+(?:ago|old)\b)",
    re.IGNORECASE,
)
_YEARS_NOISE_RE = re.compile(
    r"\b(?:(?:past|last|next|every|first)\s+(?:the\s+)?|for\s+(?:over|more\s+than|nearly|almost|the)\s+)$",
    re.IGNORECASE,
)

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{2,3}(?:\.\d+)?\s?[kK]\b|\d{2,3}(?:\.\d{1,2})?"
_SALARY_RE = re.compile(
    rf"[$€£]\s?(?P<low>{_NUMBER})(?P<high>\s*(?:-|–|—|to)\s*[$€£]?\s?(?:{_NUMBER}))?"
    r"(?P<unit>\s*(?:per|/|an?)\s*(?:year|yr|annum|hour|hr|month)\b)?"
)
_SALARY_CONTEXT_RE = re.compile(r"salary|compensation|\bpay\b|\bbase\b|\brange\b|\bote\b|wage|earn|annual", re.IGNORECASE)

_BULLET_RE = re.compile(r"^\s*(?:[-*•·–—▪◦‣●○]|\d{1,2}[.)])\s+")
_HEADING_TAIL = r"(?:\s+(?:for|at|in)\s+[^.]{1,30})?"
_QUALIFICATION_HEADING_RE = re.compile(
    r"(?:(?:(?:minimum|basic|required|preferred|desired|key|job|core|technical|additional|bonus)\s+)?"
    r"(?:requirements?|qualifications?|skills|skills\s+(?:and|&)\s+(?:experience|qualifications)|experience\s+(?:and|&)\s+skills"
    r"|must[- ]haves?|nice[- ]to[- ]haves?)"
    r"|what\s+(?:we(?:'re|\s+are)\s+looking\s+for|we\s+look\s+for|you(?:'ll|\s+will)?\s+(?:bring|need|have))"
    r"|we(?:'re|\s+are)\s+looking\s+for(?:\s+someone\s+who)?"
    r"|who\s+you\s+are|about\s+you|you(?:'ll|\s+will)\s+(?:need|have|bring)"
    r"|you\s+(?:have|bring|are|might\s+be|should\s+have))" + _HEADING_TAIL,
    re.IGNORECASE,
)
_DUTY_HEADING_RE = re.compile(
    r"(?:(?:(?:key|core|job|your|primary|main)\s+)?(?:responsibilities|duties)"
    r"|what\s+you(?:'ll|\s+will)\s+(?:do|be\s+doing|work\s+on|own|build)"
    r"|in\s+this\s+role,?\s+you(?:'ll|\s+will)|you\s+will|you'll|your\s+impact|day[- ]to[- ]day)" + _HEADING_TAIL,
    re.IGNORECASE,
)
_OTHER_HEADING_RE = re.compile(
    r"^(?:benefits|perks|compensation|salary|pay\b|about\b|who\s+we\s+are|what\s+we\s+offer|why\s+|our\s+|the\s+team"
    r"|equal\s+opportunity|eeo\b|how\s+to\s+apply|interview\s+process|location|life\s+at|logistics)",
    re.IGNORECASE,
)
_FALLBACK_TERMS = ("experience", "must", "required", "proficien")


def _line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _key(value: Any) -> str:
    return _line(value).casefold()


def _url_key(url: Any) -> str:
    return re.sub(r"^https?://(?:www\.)?", "", sources.normalize_url(str(url or "")).lower())


def _compact(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if value not in ("", None, [], {})}


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _sentence_at(text: str, start: int, end: int) -> str:
    left = 0
    for match in _SENTENCE_BREAK_RE.finditer(text):
        if match.end() > start:
            break
        left = match.end()
    following = _SENTENCE_BREAK_RE.search(text, end)
    right = following.start() if following else len(text)
    sentence = _BULLET_RE.sub("", text[left:right].strip())
    if len(" ".join(sentence.split())) > 240 and start - left > 120:
        sentence = "…" + text[start - 100 : right].strip()
    return clip(sentence, 240)


def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        words = str(pattern or "").split()
        if not words:
            continue
        match = re.search(r"\s+".join(re.escape(word) for word in words), text, re.IGNORECASE)
        if match:
            return _sentence_at(text, match.start(), match.end())
    return ""


def _criteria(settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _mapping(settings.get("criteria")).get("blockers") or []
    if not isinstance(raw, list):
        raise ValueError("settings.json criteria.blockers must be a list.")
    criteria = []
    for index, item in enumerate(raw):
        where = f"settings.json criteria.blockers[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where} must be an object.")
        kind = str(item.get("type") or "pattern").strip().lower()
        severity = str(item.get("severity") or "blocker").strip().lower()
        if kind not in CRITERIA_TYPES:
            raise ValueError(f"{where} has unknown type {kind!r}. Use one of: {', '.join(CRITERIA_TYPES)}.")
        if severity not in CRITERIA_SEVERITIES:
            raise ValueError(f"{where} has unknown severity {severity!r}. Use one of: {', '.join(CRITERIA_SEVERITIES)}.")
        patterns = item.get("patterns") or []
        if isinstance(patterns, str):
            patterns = [patterns]
        threshold = item.get("threshold")
        if kind == "years" and (isinstance(threshold, bool) or not isinstance(threshold, int)):
            raise ValueError(f"{where} needs a whole-number threshold.")
        if kind != "years" and not (isinstance(patterns, list) and any(str(entry or "").strip() for entry in patterns)):
            raise ValueError(f"{where} needs at least one pattern.")
        criteria.append(
            {
                "area": _line(item.get("area")) or kind,
                "type": kind,
                "severity": severity,
                "patterns": [str(entry) for entry in patterns] if isinstance(patterns, list) else [],
                "threshold": threshold,
                "action": _line(item.get("action")),
            }
        )
    return criteria


def _years_required(text: str) -> tuple[int | None, str]:
    best: tuple[int, int, int] | None = None
    for match in _YEARS_RE.finditer(text):
        years = int(match.group(1))
        if not 1 <= years <= 25 or _YEARS_NOISE_RE.search(text[max(0, match.start() - 24) : match.start()]):
            continue
        if best is None or years > best[0]:
            best = (years, match.start(), match.end())
    if best is None:
        return None, ""
    return best[0], _sentence_at(text, best[1], best[2])


def _sponsorship(text: str) -> tuple[str, str]:
    haystack = text.replace("’", "'")
    for status, patterns in (("denied", _SPONSORSHIP_DENIED), ("offered", _SPONSORSHIP_OFFERED)):
        for pattern in patterns:
            match = pattern.search(haystack)
            if match:
                return status, _sentence_at(text, match.start(), match.end())
    return "unstated", ""


def _workplace(location: str, description: str) -> str:
    place = location.lower()
    if "hybrid" in place:
        return "hybrid"
    if "remote" in place:
        return "remote"
    if re.search(r"\bon-?site\b|\bin[- ]office\b|\bin[- ]person\b", place):
        return "onsite"
    text = description.lower()
    if re.search(r"\bhybrid (?:role|position|work|schedule|model|environment)\b|\bthis is a hybrid\b|\bdays (?:per|a|each) week in (?:the |our )?office\b", text):
        return "hybrid"
    if re.search(r"\b(?:fully|100%) remote\b|\bremote[- ]first\b|\bremote (?:role|position|opportunity)\b|\bthis is a remote\b|\bwork remotely\b", text):
        return "remote"
    if re.search(r"\b(?:fully |100% )?(?:on-?site|in-office|in-person) (?:role|position|work)\b|\bthis is an (?:on-?site|in-office|in-person)\b", text):
        return "onsite"
    return ""


def _employment_type(title: str, description: str) -> str:
    heading = title.lower()
    if re.search(r"\bintern(?:ship)?\b|\bco-?op\b", heading):
        return "internship"
    if re.search(r"\bcontract(?:or)?\b", heading):
        return "contract"
    if re.search(r"\bpart[- ]time\b", heading):
        return "part-time"
    text = description.lower()
    for label, pattern in (
        ("full-time", r"\bfull[- ]time\b"),
        ("part-time", r"\bpart[- ]time\b"),
        ("internship", r"\binternship (?:role|position|program|opportunity)\b|\bthis (?:is an )?internship\b"),
        ("contract", r"\bcontract(?:-to-hire| role| position)\b|\b\d{1,2}[- ]month contract\b"),
        ("temporary", r"\btemporary (?:role|position)\b"),
    ):
        if re.search(pattern, text):
            return label
    return ""


def _salary(text: str) -> str:
    for match in _SALARY_RE.finditer(text):
        low = match.group("low")
        unit = (match.group("unit") or "").lower()
        hourly = "hour" in unit or "hr" in unit
        if low.count(",") > 1 or re.match(r"\s?(?:m|mm|b|bn|million|billion)\b|,?\d", text[match.end() :], re.IGNORECASE):
            continue
        if not ("," in low or low.lower().endswith("k") or hourly):
            continue
        if match.group("high") or unit or _SALARY_CONTEXT_RE.search(text[max(0, match.start() - 80) : match.start()]):
            return clip(match.group(0), 80)
    return ""


def _heading_kind(line: str) -> str:
    text = re.sub(r"^[#>\s]+", "", line.strip().replace("’", "'")).strip("*_ \t").rstrip(":").strip("*_ \t")
    if not text or len(text) > 60:
        return ""
    if _QUALIFICATION_HEADING_RE.fullmatch(text):
        return "qualification"
    if _DUTY_HEADING_RE.fullmatch(text):
        return "duty"
    return ""


def _ends_section(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) > 60 or stripped[-1:] in ".!?;,":
        return False
    marked = stripped.startswith("#") or stripped.endswith(":") or (stripped.startswith("**") and stripped.endswith("**"))
    return marked or bool(_OTHER_HEADING_RE.match(stripped))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _clean_item(text: str) -> str:
    return _line(_BULLET_RE.sub("", text).replace("**", "").replace("__", ""))


def extract_requirements(description: str, limit: int = MAX_REQUIREMENTS) -> list[str]:
    buckets: dict[str, list[str]] = {"qualification": [], "duty": []}
    loose: list[str] = []
    current = ""
    bulleted = False
    for raw in str(description or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        kind = _heading_kind(line)
        rest = ""
        if not kind and ":" in line and not _BULLET_RE.match(line):
            head, _, tail = line.partition(":")
            if tail.strip() and _heading_kind(head):
                kind, rest = _heading_kind(head), tail.strip()
        if kind:
            current, bulleted = kind, False
            if not rest:
                continue
            line = rest
        is_bullet = bool(_BULLET_RE.match(line))
        if current and not kind and not is_bullet and (bulleted or _ends_section(line)):
            current = ""
        bulleted = bulleted or (is_bullet and bool(current))
        pieces = [_clean_item(line)] if is_bullet else [_clean_item(part) for part in _sentences(line)]
        for piece in pieces:
            bucket = current
            if not is_bullet and ":" in piece:
                head, _, tail = piece.partition(":")
                if tail.strip() and _heading_kind(head):
                    bucket, piece = _heading_kind(head), tail.strip()
            if len(piece) < 12 or piece.endswith(":"):
                continue
            if bucket:
                buckets[bucket].append(piece)
            elif len(piece) >= 20 and any(term in piece.lower() for term in _FALLBACK_TERMS):
                loose.append(piece)
    found = buckets["qualification"] + buckets["duty"]
    if len(found) < 3:
        found += loose
    unique: list[str] = []
    seen: set[str] = set()
    for item in found:
        if item.casefold() not in seen:
            seen.add(item.casefold())
            unique.append(clip(item, 300))
    return unique[:limit]


def preflight(job: dict, settings: dict) -> dict:
    """Check a posting against configured hard blockers. This is never a fit score."""
    title = _line(job.get("title"))
    location = _line(job.get("location"))
    description = str(job.get("description") or "")
    combined = "\n".join(part for part in (title, location, description) if part)
    rules = _mapping(settings.get("rules"))

    years, years_evidence = _years_required("\n".join(part for part in (title, description) if part))
    facts: dict[str, Any] = {
        "years_required": years,
        "workplace": _line(job.get("workplace")) or _workplace(location, description),
        "employment_type": _line(job.get("employment_type")) or _employment_type(title, description),
        "salary": clip(job.get("salary"), 80) or _salary(description),
    }

    blockers: list[dict[str, str]] = []
    clear: list[dict[str, str]] = []

    def record(area: str, severity: str, evidence: str, action: str) -> None:
        if severity == "clear":
            item = {"area": area, "evidence": evidence}
            if item not in clear:
                clear.append(item)
            return
        item = {"area": area, "severity": severity, "evidence": evidence, "action": action}
        if not any((seen["area"], seen["severity"], seen["evidence"]) == (area, severity, evidence) for seen in blockers):
            blockers.append(item)

    needs_sponsorship = rules.get("needs_sponsorship")
    if needs_sponsorship is not False:
        status, evidence = _sponsorship(combined)
        facts["sponsorship"] = status
        if needs_sponsorship is True and status == "denied":
            record("sponsorship", "blocker", evidence, SPONSORSHIP_ACTION)
        elif needs_sponsorship is True and status == "offered":
            record("sponsorship", "clear", evidence, "")

    for criterion in _criteria(settings):
        if criterion["type"] == "years":
            matched = years_evidence if years is not None and years >= criterion["threshold"] else ""
        else:
            matched = _first_match(title if criterion["type"] == "title" else combined, criterion["patterns"])
        if matched:
            record(criterion["area"], criterion["severity"], matched, criterion["action"])

    if any(item["severity"] == "blocker" for item in blockers):
        decision = "skip"
    elif blockers:
        decision = "pending"
    else:
        intent = str(rules.get("pasted_job_intent") or "apply").strip().lower()
        decision = "apply" if intent == "apply" else "pending"

    return {
        "decision": decision,
        "blockers": blockers,
        "clear": clear,
        "facts": {key: value for key, value in facts.items() if value not in ("", None)},
        "requirements": extract_requirements(description),
    }


def _render_assessment(result: dict[str, Any]) -> str:
    lines = [f"- Decision: {result['decision']}"]
    for item in result["blockers"]:
        label = "Blocker" if item["severity"] == "blocker" else "Flag"
        action = f" Action: {item['action']}" if item.get("action") else ""
        lines.append(f"- {label} ({item['area']}): {item['evidence']}{action}")
    lines.extend(f"- Clear ({item['area']}): {item['evidence']}" for item in result["clear"])
    lines.extend(f"- {_FACT_LABELS.get(key, key)}: {value}" for key, value in result["facts"].items())
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Jobs and leads
# ---------------------------------------------------------------------------


def _hydrate(settings: Mapping[str, Any], url: str, fetch_json: Callable[[str], dict[str, Any]] | None) -> dict[str, Any]:
    provider = sources.detect_ats(url)["provider"]
    enabled = _mapping(settings.get("discovery")).get("hydrators")
    if provider and isinstance(enabled, list) and provider not in {str(item).strip().lower() for item in enabled}:
        raise SourceError(f"{provider} postings are turned off in settings (discovery.hydrators).")
    return sources.hydrate_posting(url, fetch_json=fetch_json or sources.http_get_json)


def _hints(hydrated: Mapping[str, Any]) -> dict[str, Any]:
    return _compact(
        {
            "workplace": hydrated.get("workplace"),
            "employment_type": hydrated.get("employment_type"),
            "salary": hydrated.get("compensation"),
        }
    )


def _header(job: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(str(job["path"]))
    return {
        "job": job["id"],
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "location": job.get("location") or "",
        "stage": job.get("stage") or normalize_stage(job.get("status")),
        "folder": str(path.parent),
        "path": str(path),
    }


def _find_duplicate(jobs: list[dict[str, Any]], *, url: str = "", company: str = "", title: str = "") -> dict[str, Any] | None:
    url_key = _url_key(url)
    if url_key:
        for job in jobs:
            if _url_key(job.get("url")) == url_key:
                return job
    if company and title:
        wanted = (_key(company), _key(title))
        for job in jobs:
            if job.get("stage") not in INACTIVE_STAGES and (_key(job.get("company")), _key(job.get("title"))) == wanted:
                return job
    return None


def _duplicate(job: Mapping[str, Any]) -> dict[str, Any]:
    return {"ok": True, "duplicate": True, "job": _header(job), "hint": "This job already exists. Continue with it."}


def _question_lines(summary: str) -> str:
    return "\n".join(f"- {item.strip()}" for item in summary.split("; ") if item.strip())


def add_job(
    ws: Workspace,
    *,
    url: str = "",
    text: str = "",
    company: str = "",
    title: str = "",
    location: str = "",
    notes: str = "",
    lead: str = "",
    fetch_json: Callable[[str], dict[str, Any]] | None = None,
    today: Any = None,
) -> dict:
    url, company, title, location, lead = (_line(value) for value in (url, company, title, location, lead))
    posting = str(text or "").strip()
    settings = ws.settings()
    jobs = ws.jobs()
    lead_record: dict[str, Any] | None = None
    hydrated: dict[str, Any] = {}
    source = "pasted"

    if lead:
        if url or posting:
            raise ValueError("Give one source: a lead, a url, or the posting text.")
        lead_record = ws.resolve_lead(lead)
        promoted = next((job for job in jobs if job["id"] == str(lead_record.get("job") or "")), None)
        if promoted:
            return _duplicate(promoted)
        posting = section(ws.read(Path(lead_record["path"])).body, "Posting").strip()
        company = company or _line(lead_record.get("company"))
        title = title or _line(lead_record.get("title"))
        location = location or _line(lead_record.get("location"))
        url = _line(lead_record.get("url"))
        source = "lead"
        if len(posting) < MIN_POSTING_CHARS and url:
            try:
                hydrated = _hydrate(settings, url, fetch_json)
            except SourceError:
                hydrated = {}
            posting = str(hydrated.get("description") or posting)
            location = location or _line(hydrated.get("location"))
    elif posting:
        if not company or not title:
            return {"ok": False, "needs": ["company", "title"], "hint": "Read them from the posting and call again."}
    elif url:
        existing = _find_duplicate(jobs, url=url)
        if existing:
            return _duplicate(existing)
        try:
            hydrated = _hydrate(settings, url, fetch_json)
        except SourceError as exc:
            result: dict[str, Any] = {
                "ok": False,
                "needs": "posting_text",
                "hint": "This URL is not a supported ATS page. Fetch the posting with your web tool, then call again with text, company and title (keep url).",
            }
            if sources.detect_ats(url)["provider"]:
                result["error"] = clip(str(exc), 240)
            return result
        posting = str(hydrated.get("description") or "")
        company = company or _line(hydrated.get("company"))
        title = title or _line(hydrated.get("title"))
        location = location or _line(hydrated.get("location"))
        url = _line(hydrated.get("url")) or url
        source = str(hydrated.get("provider") or "pasted")
    else:
        return {"ok": False, "needs": "posting_text", "hint": "Provide a posting url, the posting text, or a lead."}

    existing = _find_duplicate(jobs, url=url, company=company, title=title)
    if existing:
        return _duplicate(existing)
    if not company or not title:
        return {"ok": False, "needs": ["company", "title"], "hint": "Read them from the posting and call again."}
    if len(posting) < MIN_POSTING_CHARS:
        return {"ok": False, "needs": "posting_text", "hint": "Provide the full job description."}

    result = preflight({"title": title, "company": company, "location": location, "description": posting, **_hints(hydrated)}, settings)
    sections = {"Assessment": _render_assessment(result)}
    if result["requirements"]:
        sections["Requirements"] = "\n".join(f"- {item}" for item in result["requirements"])
    if hydrated.get("questions"):
        sections["Application questions"] = _question_lines(str(hydrated["questions"]))
    job = ws.create_job(
        company=company,
        title=title,
        location=location,
        url=url,
        posting=posting,
        source=source,
        notes=str(notes or "").strip(),
        created_on=str(today or ""),
        extra_meta={"decision": result["decision"], "posted_on": _posted_day(hydrated, lead_record), "priority": "normal"},
        body_sections=sections,
    )

    if lead_record:
        ws.set_meta(Path(lead_record["path"]), {"status": "promoted", "job": job["id"]})
    elif _url_key(url):
        for other in ws.leads():
            if other["status"] != "promoted" and _url_key(other.get("url")) == _url_key(url):
                ws.set_meta(Path(other["path"]), {"status": "promoted", "job": job["id"]})

    return {
        "ok": True,
        "job": _header(job),
        "preflight": {
            "decision": result["decision"],
            "blockers": result["blockers"],
            "facts": result["facts"],
            "requirements_count": len(result["requirements"]),
        },
        "next": NEXT_AFTER_BLOCKER if result["decision"] == "skip" else NEXT_AFTER_ADD,
    }


def find_jobs(
    ws: Workspace,
    query: str,
    *,
    limit: int = 8,
    post_json: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]] | None = None,
    fetch_json: Callable[[str], dict[str, Any]] | None = None,
    env: Mapping[str, str] | None = None,
    today: Any = None,
) -> dict:
    settings = ws.settings()
    try:
        results = sources.search_jobs(
            query,
            settings,
            limit=limit,
            post_json=post_json or sources.http_post_json,
            env=os.environ if env is None else env,
        )
    except SourceError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "hint": "Search with your web tool instead and add postings with jobapps_add_job.",
        }

    known_keys = {_url_key(item.get("url")) for item in [*ws.jobs(), *ws.leads()]} - {""}
    known = 0
    leads: list[dict[str, Any]] = []
    for found in results:
        search_key = _url_key(found["url"])
        if search_key in known_keys:
            known += 1
            continue
        try:
            hydrated = _hydrate(settings, found["url"], fetch_json)
        except SourceError:
            hydrated = {}
        url = _line(hydrated.get("url")) or found["url"]
        canonical_key = _url_key(url)
        already_known = canonical_key in known_keys
        known_keys.update({search_key, canonical_key})
        if already_known:
            known += 1
            continue
        company = _line(hydrated.get("company")) or found["company"]
        title = _line(hydrated.get("title")) or found["title"]
        location = _line(hydrated.get("location")) or found["location"]
        posting = str(hydrated.get("description") or found["snippet"])
        result = preflight({"title": title, "company": company, "location": location, "description": posting, **_hints(hydrated)}, settings)
        areas = list(dict.fromkeys(item["area"] for item in result["blockers"]))
        record = ws.create_lead(
            company=company,
            title=title,
            url=url,
            location=location,
            posting=posting,
            source=str(hydrated.get("provider") or "exa"),
            found_on=str(today or ""),
            extra_meta={
                "preflight": result["decision"],
                "blockers": areas,
                "posted_on": day(hydrated.get("posted_at") or found.get("published")),
            },
        )
        if record.get("duplicate"):
            known += 1
            continue
        leads.append(
            _compact(
                {
                    "lead": record["id"],
                    "company": record["company"],
                    "title": record["title"],
                    "location": location,
                    "url": url,
                    "preflight": result["decision"],
                    "blockers": areas,
                }
            )
        )
    return {"ok": True, "query": _line(query), "found": len(results), "new": len(leads), "known": known, "leads": leads}


def _posted_day(hydrated: dict[str, Any], lead_record: dict[str, Any] | None) -> str:
    return day(hydrated.get("posted_at")) or day((lead_record or {}).get("posted_on"))


def set_lead_status(ws: Workspace, lead_ref: str, status: str) -> dict:
    wanted = str(status or "").strip().lower()
    if wanted not in SETTABLE_LEAD_STATUSES:
        raise ValueError(f"Lead status must be one of: {', '.join(SETTABLE_LEAD_STATUSES)}.")
    lead = ws.resolve_lead(lead_ref)
    ws.set_meta(Path(lead["path"]), {"status": wanted})
    return {"ok": True, "lead": lead["id"], "status": wanted}


# ---------------------------------------------------------------------------
# People and drafts
# ---------------------------------------------------------------------------


def _same_company(left: Any, right: Any) -> bool:
    a, b = _key(left), _key(right)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))


def find_people(
    ws: Workspace,
    *,
    company: str = "",
    query: str = "",
    job: str = "",
    limit: int = 6,
    post_json: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict:
    employer = _line(company)
    if job and not employer:
        employer = _line(ws.resolve_job(job).get("company"))
    try:
        found = sources.search_people(
            company=employer,
            query=_line(query),
            settings=ws.settings(),
            limit=limit,
            post_json=post_json or sources.http_post_json,
            env=os.environ if env is None else env,
        )
    except SourceError as exc:
        return {"ok": False, "error": str(exc), "hint": "Use your web search tool to find people instead."}
    tracked = [
        {"person": person["id"], "name": person.get("name", ""), "role": person.get("role") or "", "status": person["status"]}
        for person in ws.people()
        if _same_company(person.get("company"), employer)
    ]
    result: dict[str, Any] = {"ok": True, "company": employer, "tracked": tracked[:MAX_TRACKED]}
    if len(tracked) > MAX_TRACKED:
        result["tracked_total"] = len(tracked)
    result["found"] = found
    result["note"] = (
        "Nothing was saved. Save a person only when the user asks, with jobapps_person. "
        "Verify identity and never guess an email address."
    )
    return result


def gmail_draft(
    ws: Workspace,
    *,
    to: str = "",
    subject: str = "",
    body: str = "",
    account: str = "",
    person: str = "",
    run: Callable[[list[str], str, float], Any] | None = None,
) -> dict:
    if not _line(subject) or not str(body or "").strip():
        return {"ok": False, "error": "A draft needs a subject and a body."}
    recipient = str(to or "").strip()
    tracked: dict[str, Any] | None = None
    if _line(person):
        tracked = ws.resolve_person(person)
        if not recipient:
            recipient = str(tracked.get("email") or "").strip()
            if not recipient:
                return {"ok": False, "error": f"No email on file for {tracked.get('name') or tracked['id']}. Ask the user; never guess."}
    try:
        draft = sources.create_gmail_draft(
            to=recipient,
            subject=subject,
            body=body,
            account=account,
            settings=ws.settings(),
            run=run,
        )
    except SourceError as exc:
        return {"ok": False, "error": str(exc)}
    if tracked:
        ws.update_person(tracked["id"], {}, log=f"Gmail draft created: {clip(subject, 80)}")
    return {"ok": True, "draft_id": draft["draft_id"], "to": draft["to"], "note": "Draft only. Nothing was sent."}
