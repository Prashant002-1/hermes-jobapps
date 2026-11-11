"""External lookups: ATS postings, Exa search and Gmail drafts.

Nothing here reads or writes the workspace. Every network and subprocess
entry point takes an injectable callable so callers and tests stay offline.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from .workspace import clip, day


JsonFetcher = Callable[[str], dict[str, Any]]
JsonPoster = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
CommandRunner = Callable[[list[str], str, float], Any]

USER_AGENT = "HermesJobApps/1.0"
MAX_DESCRIPTION_CHARS = 30000

_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
_LEVER_HOSTS = {"jobs.lever.co": "", "jobs.eu.lever.co": "eu"}
_TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "gh_src", "lever-source", "lever-origin")
_EMAIL_RE = re.compile(r"[A-Za-z0-9][\w.+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_BLOCK_TAG_RE = re.compile(
    r"(?i)<br\s*/?>|</?(?:p|div|ul|ol|li|h[1-6]|tr|table|section|article|header|footer|blockquote)\b[^>]*>"
)
_TITLE_SEPARATOR_RE = re.compile(r"\s+[-–—]\s+")


class SourceError(ValueError):
    """An external lookup could not produce a usable result."""


# ---------------------------------------------------------------------------
# Text and URL helpers
# ---------------------------------------------------------------------------


def _squash(value: Any) -> str:
    return " ".join(str(value or "").split())


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _with_scheme(url: str) -> str:
    text = str(url or "").strip()
    if text and not re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://", text):
        text = f"https://{text}"
    return text


def normalize_url(url: str) -> str:
    text = _with_scheme(url)
    if not text:
        return ""
    parsed = urlparse(text)
    kept = [
        (key, value)
        for key, values in sorted(parse_qs(parsed.query).items())
        if not key.lower().startswith(_TRACKING_PARAMS)
        for value in values
    ]
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/"),
        query=urlencode(kept, doseq=True),
        fragment="",
    )
    return urlunparse(normalized)


def _tidy_lines(text: str) -> str:
    """Collapse spacing while keeping paragraphs and bullet lists readable."""
    lines: list[str] = []
    pending_bullet = False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        if line == "-":
            pending_bullet = True
            continue
        if pending_bullet and not line.startswith("- "):
            line = f"- {line}"
        pending_bullet = False
        lines.append(line)
    blocks: list[str] = []
    for line in lines:
        bullet = line.startswith("- ")
        if blocks and not (bullet and blocks[-1].startswith("- ")):
            blocks.append("")
        blocks.append(line)
    return "\n".join(blocks)


def strip_html(value: str) -> str:
    text = str(value or "")
    if "<" not in text and "&lt;" in text:
        text = html.unescape(text)
    text = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1\s*>", " ", text)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?i)<li\b[^>]*>", "\n- ", text)
    text = _BLOCK_TAG_RE.sub("\n", text)
    return _tidy_lines(html.unescape(re.sub(r"<[^>]+>", " ", text)))


def _truncate(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(None, 1)[0].rstrip()


def _company_from_token(token: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in re.findall(r"[A-Za-z0-9]+", str(token or "")))


def _date(value: Any) -> str:
    if isinstance(value, bool) or value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    return day(value)


def _workplace(value: Any) -> str:
    key = re.sub(r"[^a-z]", "", str(value or "").lower())
    return {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "inoffice": "onsite"}.get(key, "")


def _employment_type(value: Any) -> str:
    key = re.sub(r"[^a-z]", "", str(value or "").lower())
    return {
        "fulltime": "full-time",
        "parttime": "part-time",
        "contract": "contract",
        "contractor": "contract",
        "intern": "internship",
        "internship": "internship",
        "temporary": "temporary",
        "temp": "temporary",
    }.get(key, "")


def _amount(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return ""


def _compensation(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return clip(strip_html(value), 200)
    if isinstance(value, list):
        return clip("; ".join(item for item in (_compensation(entry) for entry in value[:4]) if item), 200)
    if not isinstance(value, dict):
        return ""
    for key in ("compensationTierSummary", "scrapeableCompensationSalarySummary", "salaryDescription", "summary"):
        if value.get(key):
            return clip(strip_html(str(value[key])), 200)
    low = high = ""
    for low_key, high_key, divisor in (("min_cents", "max_cents", 100), ("min_value", "max_value", 1), ("min", "max", 1)):
        if value.get(low_key) is not None or value.get(high_key) is not None:
            try:
                low = _amount(float(value[low_key]) / divisor) if value.get(low_key) is not None else ""
                high = _amount(float(value[high_key]) / divisor) if value.get(high_key) is not None else ""
            except (TypeError, ValueError):
                low = high = ""
            break
    span = " - ".join(part for part in (low, high) if part)
    if not span:
        return ""
    label = _squash(value.get("title") or value.get("label"))
    unit = " ".join(
        part for part in (_squash(value.get("currency_type") or value.get("currency")), _squash(value.get("interval"))) if part
    )
    return clip(f"{label + ': ' if label else ''}{span}{' ' + unit if unit else ''}", 200)


def _questions(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    labels = []
    for question in value[:18]:
        if not isinstance(question, dict):
            continue
        label = _squash(strip_html(str(question.get("label") or question.get("description") or "")))
        if not label:
            continue
        fields = question.get("fields") if isinstance(question.get("fields"), list) else []
        kinds = sorted({str(item.get("type")) for item in fields if isinstance(item, dict) and item.get("type")})
        detail = ", ".join(["required" if question.get("required") else "optional", *kinds])
        labels.append(f"{label} ({detail})")
    return "; ".join(labels)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _read_json(request: Request, timeout: float) -> dict[str, Any]:
    if urlparse(request.full_url).scheme not in {"http", "https"}:
        raise SourceError(f"Only http and https URLs can be fetched: {request.full_url}")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked above.
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceError(f"{request.get_method()} {request.full_url} failed: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceError(f"{request.full_url} did not return a JSON object.")
    return data


def http_get_json(url: str, headers: dict | None = None, timeout: float = 20) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT, **(headers or {})})
    return _read_json(request, timeout)


def http_post_json(url: str, payload: dict, headers: dict, timeout: float = 30) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})},
        method="POST",
    )
    return _read_json(request, timeout)


# ---------------------------------------------------------------------------
# ATS postings
# ---------------------------------------------------------------------------


def detect_ats(url: str) -> dict:
    parsed = urlparse(_with_scheme(url))
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)
    if host in _GREENHOUSE_HOSTS and parts:
        if parts[0] == "embed":
            return {
                "provider": "greenhouse",
                "board": (query.get("for") or [""])[0],
                "job_id": (query.get("token") or [""])[0],
            }
        job_id = ""
        if "jobs" in parts and len(parts) > parts.index("jobs") + 1:
            job_id = parts[parts.index("jobs") + 1]
        return {"provider": "greenhouse", "board": parts[0], "job_id": job_id or (query.get("gh_jid") or [""])[0]}
    if host in _LEVER_HOSTS and parts:
        detected = {"provider": "lever", "site": parts[0], "posting_id": parts[1] if len(parts) > 1 else ""}
        if _LEVER_HOSTS[host]:
            detected["region"] = _LEVER_HOSTS[host]
        return detected
    if host == "jobs.ashbyhq.com" and parts:
        return {"provider": "ashby", "board": parts[0], "job_id": parts[1] if len(parts) > 1 else ""}
    return {"provider": ""}


def _unsupported(url: str, reason: str) -> SourceError:
    return SourceError(f"{url or 'An empty URL'} is not a supported ATS URL: {reason}")


def _fetch(label: str, api_url: str, fetch_json: JsonFetcher) -> dict[str, Any]:
    try:
        data = fetch_json(api_url)
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes one visible error.
        raise SourceError(f"{label} hydration failed: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceError(f"{label} hydration failed: unexpected response.")
    return data


def _hydrate_greenhouse(url: str, ats: dict[str, Any], fetch_json: JsonFetcher) -> dict[str, Any]:
    board, job_id = ats.get("board"), ats.get("job_id")
    if not board or not job_id:
        raise _unsupported(url, "a Greenhouse link needs a board and a job id.")
    api_url = (
        f"https://boards-api.greenhouse.io/v1/boards/{quote(board, safe='')}/jobs/{quote(job_id, safe='')}"
        f"?{urlencode({'questions': 'true', 'pay_transparency': 'true'})}"
    )
    data = _fetch("Greenhouse", api_url, fetch_json)
    location = data.get("location")
    canonical = normalize_url(str(data.get("absolute_url") or url))
    return {
        "provider": "greenhouse",
        "title": _squash(data.get("title")),
        "company": _squash(data.get("company_name")) or _company_from_token(board),
        "location": _squash(location.get("name") if isinstance(location, dict) else location),
        "url": canonical,
        "apply_url": canonical,
        "description": _truncate(strip_html(str(data.get("content") or ""))),
        "posted_at": _date(data.get("first_published")),
        "compensation": _compensation(data.get("pay_input_ranges") or data.get("pay_transparency")),
        "questions": _questions(data.get("questions")),
    }


def _lever_description(data: dict[str, Any]) -> str:
    def block(plain_key: str, html_key: str) -> str:
        if data.get(plain_key):
            return _tidy_lines(str(data[plain_key]))
        return strip_html(str(data.get(html_key) or ""))

    parts = [block("descriptionPlain", "description")]
    for item in data.get("lists") or []:
        if isinstance(item, dict):
            parts.append("\n\n".join(part for part in (strip_html(str(item.get("text") or "")), strip_html(str(item.get("content") or ""))) if part))
    parts.append(block("additionalPlain", "additional"))
    return "\n\n".join(part for part in parts if part)


def _hydrate_lever(url: str, ats: dict[str, Any], fetch_json: JsonFetcher) -> dict[str, Any]:
    site, posting_id = ats.get("site"), ats.get("posting_id")
    if not site or not posting_id:
        raise _unsupported(url, "a Lever link needs a site and a posting id.")
    host = "api.eu.lever.co" if ats.get("region") == "eu" else "api.lever.co"
    data = _fetch("Lever", f"https://{host}/v0/postings/{quote(site, safe='')}/{quote(posting_id, safe='')}?mode=json", fetch_json)
    categories = _mapping(data.get("categories"))
    urls = _mapping(data.get("urls"))
    return {
        "provider": "lever",
        "title": _squash(data.get("text") or data.get("title")),
        "company": _company_from_token(site),
        "location": _squash(categories.get("location")),
        "url": normalize_url(str(urls.get("show") or data.get("hostedUrl") or url)),
        "apply_url": normalize_url(str(urls.get("apply") or data.get("applyUrl") or "")),
        "description": _truncate(_lever_description(data)),
        "posted_at": _date(data.get("createdAt")),
        "compensation": _compensation(data.get("salaryDescriptionPlain") or data.get("salaryDescription") or data.get("salaryRange")),
        "workplace": _workplace(data.get("workplaceType")),
        "employment_type": _employment_type(categories.get("commitment")),
    }


def _match_ashby_job(url: str, job_id: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = normalize_url(url).lower()
    for job in jobs:
        if target in {normalize_url(str(job.get(key) or "")).lower() for key in ("jobUrl", "applyUrl")}:
            return job
    needle = job_id.lower()
    for job in jobs:
        if needle and (str(job.get("id") or "").lower() == needle or needle in str(job.get("jobUrl") or "").lower()):
            return job
    return None


def _hydrate_ashby(url: str, ats: dict[str, Any], fetch_json: JsonFetcher) -> dict[str, Any]:
    board, job_id = ats.get("board"), ats.get("job_id")
    if not board or not job_id:
        raise _unsupported(url, "an Ashby link needs a board and a job id.")
    data = _fetch("Ashby", f"https://api.ashbyhq.com/posting-api/job-board/{quote(board, safe='')}?includeCompensation=true", fetch_json)
    job = _match_ashby_job(url, job_id, [item for item in data.get("jobs") or [] if isinstance(item, dict)])
    if not job:
        raise SourceError("Ashby hydration failed: the board has no posting that matches this URL.")
    description = _tidy_lines(str(job.get("descriptionPlain") or "")) or strip_html(str(job.get("descriptionHtml") or ""))
    return {
        "provider": "ashby",
        "title": _squash(job.get("title")),
        "company": _company_from_token(board),
        "location": _squash(job.get("location")),
        "url": normalize_url(str(job.get("jobUrl") or url)),
        "apply_url": normalize_url(str(job.get("applyUrl") or "")),
        "description": _truncate(description),
        "posted_at": _date(job.get("publishedAt")),
        "compensation": _compensation(job.get("compensation")),
        "workplace": _workplace(job.get("workplaceType")) or ("remote" if job.get("isRemote") is True else ""),
        "employment_type": _employment_type(job.get("employmentType")),
    }


_HYDRATORS = {"greenhouse": _hydrate_greenhouse, "lever": _hydrate_lever, "ashby": _hydrate_ashby}


def hydrate_posting(url: str, *, fetch_json: JsonFetcher = http_get_json) -> dict:
    """Read one posting from a public ATS API. Raises SourceError for anything else."""
    target = _squash(url)
    ats = detect_ats(target)
    hydrator = _HYDRATORS.get(ats["provider"])
    if hydrator is None:
        raise _unsupported(target, "only Greenhouse, Lever and Ashby job pages can be read directly.")
    return {key: value for key, value in hydrator(target, ats, fetch_json).items() if value}


# ---------------------------------------------------------------------------
# Exa search
# ---------------------------------------------------------------------------


def _exa_access(exa: dict[str, Any], fallback: dict[str, Any], env: Mapping[str, str]) -> tuple[str, str]:
    env_name = str(exa.get("api_key_env") or fallback.get("api_key_env") or "EXA_API_KEY")
    api_key = str(env.get(env_name) or "").strip()
    if not api_key:
        raise SourceError(f"{env_name} is not set. Add it to the environment to use Exa search.")
    base_url = str(exa.get("base_url") or fallback.get("base_url") or "https://api.exa.ai").rstrip("/")
    return api_key, base_url


def _bounded(value: Any, default: int, maximum: int) -> int:
    try:
        number = int(value or default)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def _exa_search(label: str, post_json: JsonPoster, base_url: str, payload: dict[str, Any], api_key: str) -> list[dict[str, Any]]:
    try:
        data = post_json(f"{base_url}/search", payload, {"x-api-key": api_key, "Content-Type": "application/json"})
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes one visible error.
        raise SourceError(f"{label} failed: {exc}") from exc
    results = data.get("results") if isinstance(data, dict) else None
    return [item for item in results or [] if isinstance(item, dict)]


def _result_text(result: dict[str, Any]) -> str:
    highlights = result.get("highlights") if isinstance(result.get("highlights"), list) else []
    text = " ".join(str(item) for item in highlights if item)
    return _squash(text or result.get("summary") or result.get("text"))


def _add_domains(payload: dict[str, Any], exa: dict[str, Any]) -> None:
    domains = exa.get("include_domains")
    if isinstance(domains, list) and any(domains):
        payload["includeDomains"] = [str(item) for item in domains if item]


def _same_name(left: str, right: str) -> bool:
    a, b = (re.sub(r"[^a-z0-9]", "", value.lower()) for value in (left, right))
    return bool(a) and a == b


def _parse_job_title(raw: str, board_company: str) -> tuple[str, str]:
    text = re.sub(r"(?i)^job application for\s+", "", _squash(raw))
    prefixed = text != _squash(raw)
    bar_parts = [part for part in (item.strip() for item in text.split(" | ")) if part]
    dash_parts = [part for part in _TITLE_SEPARATOR_RE.split(text) if part.strip()]
    for parts, joiner in ((bar_parts, " | "), (dash_parts, " - ")):
        if board_company and len(parts) > 1:
            for index, part in enumerate(parts):
                if _same_name(part, board_company):
                    return joiner.join(parts[:index] + parts[index + 1 :]), part
    lead = text if prefixed or (len(bar_parts) < 2 and len(dash_parts) < 2) else (bar_parts if len(bar_parts) > 1 else dash_parts)[0]
    at = re.match(r"^(.{2,120})\s+(?:at|@)\s+(.{2,80})$", lead, re.IGNORECASE)
    if at:
        return at.group(1).strip(), at.group(2).strip()
    if len(bar_parts) > 1:
        return bar_parts[1], bar_parts[0]
    if len(dash_parts) > 1:
        return " - ".join(dash_parts[:-1]), dash_parts[-1].strip()
    return text, board_company


def search_jobs(
    query: str,
    settings: dict,
    *,
    limit: int = 8,
    post_json: JsonPoster = http_post_json,
    env: Mapping[str, str] = os.environ,
) -> list[dict]:
    config = _mapping(settings.get("discovery"))
    if config.get("enabled") is False:
        raise SourceError("Job search is turned off in settings (discovery.enabled).")
    text = _squash(query)
    if not text:
        raise SourceError("A search query is required.")
    exa = _mapping(config.get("exa"))
    api_key, base_url = _exa_access(exa, {}, env)
    payload: dict[str, Any] = {
        "query": text,
        "numResults": _bounded(limit or exa.get("default_num_results"), 8, 25),
        "type": str(exa.get("type") or "auto"),
        "contents": {"highlights": True},
    }
    _add_domains(payload, exa)
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in _exa_search("Exa job search", post_json, base_url, payload, api_key):
        url = normalize_url(str(result.get("url") or ""))
        if not url or url.lower() in seen:
            continue
        seen.add(url.lower())
        ats = detect_ats(url)
        board_company = _company_from_token(ats.get("board") or ats.get("site") or "")
        title, company = _parse_job_title(str(result.get("title") or ""), board_company)
        snippet = _result_text(result)
        located = re.search(r"\bLocation:\s*([^.;|\n]{2,60})", snippet)
        jobs.append(
            {
                "title": title,
                "company": company or board_company,
                "url": url,
                "location": located.group(1).strip() if located else "",
                "snippet": clip(snippet, 600),
                "published": _date(result.get("publishedDate")),
            }
        )
    return jobs


def _parse_person_title(raw: str, default_company: str) -> tuple[str, str, str]:
    text = re.sub(r"(?i)\s*[|\-–—]\s*LinkedIn.*$", "", _squash(raw))
    parts = [part.strip() for part in re.split(r"\s+[-–—]\s+|\s+\|\s+", text) if part.strip()]
    name = parts[0] if parts else text
    role = parts[1] if len(parts) > 1 else ""
    company = parts[2] if len(parts) > 2 else ""
    if not role and "," in name:
        name, role = (piece.strip() for piece in name.split(",", 1))
    if role and not company:
        placed = re.match(r"^(.+?)\s+(?:at|@)\s+(.+)$", role, re.IGNORECASE)
        if placed:
            role, company = placed.group(1).strip(), placed.group(2).strip()
    return name[:160], role[:220], (company or default_company)[:160]


def search_people(
    *,
    company: str = "",
    query: str = "",
    settings: dict,
    limit: int = 6,
    post_json: JsonPoster = http_post_json,
    env: Mapping[str, str] = os.environ,
) -> list[dict]:
    config = _mapping(settings.get("networking"))
    if config.get("enabled") is False:
        raise SourceError("People search is turned off in settings (networking.enabled).")
    employer = _squash(company)
    text = _squash(query)
    if not employer and not text:
        raise SourceError("People search needs a company or a query.")
    if not text:
        template = str(config.get("people_query") or "{company} recruiter hiring manager")
        text = _squash(template.replace("{company}", employer))
    elif employer and employer.lower() not in text.lower():
        text = f"{employer} {text}"
    exa = _mapping(config.get("exa"))
    api_key, base_url = _exa_access(exa, _mapping(_mapping(settings.get("discovery")).get("exa")), env)
    payload: dict[str, Any] = {
        "query": text,
        "numResults": _bounded(limit or exa.get("default_num_results"), 6, 15),
        "type": str(exa.get("type") or "auto"),
        "category": str(exa.get("category") or "people"),
        "contents": {
            "highlights": {"query": f"{text} role company email contact", "numSentences": 2, "highlightsPerUrl": 2}
        },
    }
    _add_domains(payload, exa)
    people: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in _exa_search("Exa people search", post_json, base_url, payload, api_key):
        url = _squash(result.get("url"))
        title = _squash(result.get("title") or result.get("author"))
        name, role, employer_name = _parse_person_title(title, employer)
        if not name:
            continue
        linkedin = url if "linkedin.com/in/" in url.lower() else ""
        key = (linkedin or url).rstrip("/").lower()
        if key and key in seen:
            continue
        seen.add(key)
        snippet = _result_text(result)
        person = {
            "name": name,
            "role": role,
            "company": employer_name,
            "linkedin": linkedin,
            "source_url": url,
            "snippet": clip(snippet, 240),
        }
        email = _EMAIL_RE.search(f"{title} {snippet}")
        if email:
            person["email"] = email.group(0).lower()
        people.append(person)
    return people


# ---------------------------------------------------------------------------
# Gmail drafts (draft only)
# ---------------------------------------------------------------------------


def _run_command(command: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=stdin, text=True, capture_output=True, timeout=timeout, check=False)


def _draft_id(stdout: Any) -> str:
    try:
        data = json.loads(str(stdout or "").strip())
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    for holder in (data, data.get("draft")):
        if isinstance(holder, dict):
            for key in ("draftId", "draft_id", "id"):
                if holder.get(key):
                    return str(holder[key])
    return ""


def create_gmail_draft(
    *,
    to: str = "",
    subject: str,
    body: str,
    account: str = "",
    settings: dict,
    run: CommandRunner | None = None,
) -> dict:
    """Create a Gmail draft through gog. There is no code path here that sends mail."""
    config = _mapping(settings.get("networking"))
    if config.get("enabled") is False:
        raise SourceError("Gmail drafts are turned off in settings (networking.enabled).")
    subject_text = _squash(subject)
    body_text = str(body or "").strip()
    if not subject_text:
        raise SourceError("A draft needs a subject.")
    if not body_text:
        raise SourceError("A draft needs a body.")
    recipient = str(to or "").strip()
    if recipient and not _EMAIL_RE.fullmatch(recipient):
        raise SourceError(f"Not a valid email address: {recipient}")
    sender = str(account or "").strip()
    if sender.startswith("-") or any(char.isspace() for char in sender):
        raise SourceError(f"Not a valid Gmail account: {sender}")
    gog = str(config.get("gog_path") or "gog")
    if run is None and not shutil.which(gog):
        raise SourceError(f"gog command not found: {gog}")
    command = [gog]
    if sender:
        command += ["--account", sender]
    command += ["--gmail-no-send", "--json", "--no-input", "gmail", "drafts", "create", "--subject", subject_text, "--body-file", "-"]
    if recipient:
        command += ["--to", recipient]
    try:
        timeout = float(config.get("gog_timeout_seconds") or 30)
    except (TypeError, ValueError):
        timeout = 30.0
    try:
        result = (run or _run_command)(command, body_text, timeout)
    except FileNotFoundError as exc:
        raise SourceError(f"gog command not found: {gog}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SourceError("gog draft creation timed out.") from exc
    except OSError as exc:
        raise SourceError(f"gog could not be started: {exc}") from exc
    if result.returncode != 0:
        detail = str(result.stderr or result.stdout or "").strip()[-400:]
        raise SourceError(f"gog draft creation failed: {detail or 'unknown error'}")
    return {"ok": True, "draft_id": _draft_id(result.stdout), "to": recipient}
