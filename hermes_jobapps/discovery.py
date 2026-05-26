"""Removable job discovery and ATS hydration helpers.

Discovery feeds candidate opportunities into JobApps. It does not submit,
message, or decide for the user. The app database remains the source of truth
once a candidate is promoted into the normal application workflow.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from .evaluator import evaluate_job
from .knowledge import normalize_space
from .repository import JobRepository


JsonFetcher = Callable[[str], dict[str, Any]]
JsonPoster = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class DiscoveryError(ValueError):
    """Raised when a discovery provider or hydrator cannot produce a candidate."""


class DiscoveryService:
    def __init__(
        self,
        repo: JobRepository,
        config: dict[str, Any],
        *,
        fetch_json: JsonFetcher | None = None,
        post_json: JsonPoster | None = None,
    ) -> None:
        self.repo = repo
        self.config = config
        self.fetch_json = fetch_json or http_get_json
        self.post_json = post_json or http_post_json

    def status(self) -> dict[str, Any]:
        discovery_config = self._config()
        exa_config = discovery_config.get("exa", {}) if isinstance(discovery_config.get("exa"), dict) else {}
        env_name = str(exa_config.get("api_key_env") or "EXA_API_KEY")
        return {
            "enabled": bool(discovery_config.get("enabled", True)),
            "providers": {
                "exa": {
                    "configured": bool(os.environ.get(env_name)),
                    "api_key_env": env_name,
                    "base_url": str(exa_config.get("base_url") or "https://api.exa.ai").rstrip("/"),
                    "mode": "search_api",
                    "include_domains": [str(item) for item in exa_config.get("include_domains", []) or []],
                },
                "ats": {
                    "hydrators": self._hydrators(),
                    "mode": "official_job_surfaces",
                },
            },
            "query_presets": _query_presets(discovery_config.get("query_presets")),
            "policy": {
                "external_actions": "disabled",
                "promote_requires_user_action": True,
                "unknown_sponsorship": "needs_review",
                "removable_boundary": "hermes_jobapps.discovery, discovery tables, discovery routes/tools, and the Find view",
            },
            "counts": self.repo.discovery_counts(),
        }

    def search_exa(self, query: str, *, limit: int = 8, hydrate: bool = True) -> dict[str, Any]:
        self._ensure_enabled()
        query = normalize_space(query)
        if not query:
            raise DiscoveryError("Search query is required.")
        discovery_config = self._config()
        exa_config = discovery_config.get("exa", {}) if isinstance(discovery_config.get("exa"), dict) else {}
        env_name = str(exa_config.get("api_key_env") or "EXA_API_KEY")
        api_key = os.environ.get(env_name)
        if not api_key:
            raise DiscoveryError(f"{env_name} is not set. Add it to the JobApps/Hermes environment before Exa search.")

        base_url = str(exa_config.get("base_url") or "https://api.exa.ai").rstrip("/")
        safe_limit = max(1, min(int(limit or exa_config.get("default_num_results") or 8), 25))
        payload = {
            "query": query,
            "numResults": safe_limit,
            "type": str(exa_config.get("type") or "auto"),
            "contents": {"highlights": True},
        }
        include_domains = exa_config.get("include_domains")
        if isinstance(include_domains, list) and include_domains:
            payload["includeDomains"] = [str(item) for item in include_domains if item]
        try:
            data = self.post_json(
                f"{base_url}/search",
                payload,
                {"x-api-key": api_key, "Content-Type": "application/json"},
            )
        except Exception as exc:
            raise DiscoveryError(f"Exa job search failed: {exc}") from exc

        candidates = []
        errors = []
        for result in data.get("results", []) or []:
            if not isinstance(result, dict):
                continue
            url = str(result.get("url") or "").strip()
            if not url:
                continue
            sighting = _sighting_from_search_result(result, query)
            if hydrate and detect_ats(url)["provider"] in self._hydrators():
                try:
                    candidates.append(self.hydrate_url(url, sighting=sighting))
                    continue
                except DiscoveryError as exc:
                    errors.append({"url": url, "error": str(exc)})
            candidates.append(self.repo.upsert_discovery_candidate(_candidate_from_search_result(result, query), sighting=sighting))

        return {
            "provider": "exa",
            "query": query,
            "count": len(candidates),
            "candidates": candidates,
            "errors": errors,
            "raw_request_id": data.get("requestId") or data.get("request_id") or "",
        }

    def hydrate_url(self, url: str, *, sighting: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_enabled()
        url = normalize_space(url)
        if not url:
            raise DiscoveryError("URL is required.")
        detected = detect_ats(url)
        provider = detected["provider"]
        if provider not in self._hydrators():
            candidate = _candidate_from_url(url)
            candidate["status"] = "needs_review"
            candidate["blocker_status"] = "unknown"
            return self.repo.upsert_discovery_candidate(candidate, sighting=sighting or {"discovered_url": url})
        if provider == "greenhouse":
            candidate = self._hydrate_greenhouse(url, detected)
        elif provider == "lever":
            candidate = self._hydrate_lever(url, detected)
        elif provider == "ashby":
            candidate = self._hydrate_ashby(url, detected)
        else:
            raise DiscoveryError(f"Unsupported ATS provider: {provider}")
        self._apply_preflight(candidate)
        return self.repo.upsert_discovery_candidate(candidate, sighting=sighting or {"discovered_url": url})

    def candidate_to_job(self, candidate: dict[str, Any]) -> dict[str, Any]:
        source_lines = [
            f"Discovery provider: {candidate.get('source_provider') or 'unknown'}",
            f"Canonical URL: {candidate.get('canonical_url') or candidate.get('discovered_url') or ''}",
        ]
        if candidate.get("posted_at"):
            source_lines.append(f"Posted: {candidate['posted_at']}")
        if candidate.get("compensation"):
            source_lines.append(f"Compensation: {candidate['compensation']}")
        if candidate.get("application_form_summary"):
            source_lines.append(f"Application form: {candidate['application_form_summary']}")
        description = candidate.get("description") or ""
        if candidate.get("application_form_summary"):
            description = f"{description}\n\nApplication form signals:\n{candidate['application_form_summary']}".strip()
        return {
            "title": candidate.get("title") or "Untitled role",
            "company": candidate.get("company") or "Unknown company",
            "location": candidate.get("location") or "",
            "url": candidate.get("canonical_url") or candidate.get("discovered_url") or "",
            "description": description,
            "user_notes": "\n".join(line for line in source_lines if line.split(": ", 1)[-1]),
        }

    def prepare_candidate(
        self,
        candidate_id: str,
        prepare_job: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        self._ensure_enabled()
        candidate = self.repo.get_discovery_candidate(candidate_id)
        if candidate.get("job_id"):
            try:
                return {
                    "candidate": candidate,
                    "job": self.repo.get_job(str(candidate["job_id"])),
                    "provenance": [],
                    "already_prepared": True,
                }
            except KeyError:
                pass
        if candidate.get("status") != "approved":
            raise ValueError("approve this discovery candidate from the shortlist before generating materials.")

        record = prepare_job(self.candidate_to_job(candidate))
        job_id = record["job"]["id"]
        linked = self.repo.link_discovery_candidate_job(candidate["id"], job_id)
        provenance = self.record_promotion_provenance(linked, job_id)
        prepared = self.repo.get_job(job_id)
        for key in ("run", "prompt_to_hermes", "tool_calls"):
            if key in record:
                prepared[key] = record[key]
        return {"candidate": linked, "job": prepared, "provenance": provenance, "already_prepared": False}

    def prepare_approved_candidates(
        self,
        prepare_job: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        limit: int = 3,
    ) -> dict[str, Any]:
        self._ensure_enabled()
        approved = self.repo.list_discovery_candidates(status="approved", limit=max(1, min(int(limit or 3), 10)))
        prepared = []
        errors = []
        for candidate in approved:
            try:
                prepared.append(self.prepare_candidate(candidate["id"], prepare_job))
            except Exception as exc:  # noqa: BLE001 - batch endpoint should return per-candidate failures.
                errors.append({"candidate_id": candidate.get("id"), "error": str(exc)})
        return {
            "prepared": prepared,
            "prepared_count": len(prepared),
            "errors": errors,
            "error_count": len(errors),
            "policy": "Only user-approved shortlist candidates are prepared.",
        }

    def record_promotion_provenance(self, candidate: dict[str, Any], job_id: str) -> dict[str, Any]:
        source_url = candidate.get("canonical_url") or candidate.get("discovered_url") or candidate.get("apply_url") or ""
        confidence = _coerce_confidence(candidate.get("source_confidence"), default=0.65)
        summary = _promotion_summary(candidate)
        note = self.repo.save_research_note(
            "Discovery source",
            summary,
            job_id=job_id,
            source_url=source_url,
            confidence=confidence,
        )
        signals = [
            self.repo.record_application_signal(
                job_id,
                "discovery_source",
                f"{candidate.get('source_provider') or 'unknown'} source",
                source_url or candidate.get("source_provider") or "unknown",
                evidence_text=summary,
                source="discovery",
                confidence=confidence,
                actionability="high",
                metadata={
                    "candidate_id": candidate.get("id"),
                    "source_type": candidate.get("source_type"),
                    "source_provider": candidate.get("source_provider"),
                    "discovered_url": candidate.get("discovered_url"),
                    "apply_url": candidate.get("apply_url"),
                    "retrieved_at": candidate.get("retrieved_at"),
                    "posted_at": candidate.get("posted_at"),
                    "remote_updated_at": candidate.get("remote_updated_at"),
                },
            )
        ]
        optional_signals = [
            ("compensation", "Compensation", candidate.get("compensation"), "high"),
            ("workplace_type", "Workplace", candidate.get("workplace_type"), "medium"),
            ("employment_type", "Employment", candidate.get("employment_type"), "medium"),
            ("application_form", "Application form", candidate.get("application_form_summary"), "high"),
            ("blocker_preflight", "Discovery preflight", candidate.get("blocker_status"), "high"),
        ]
        for signal_type, label, value, actionability in optional_signals:
            value = normalize_space(str(value or ""))
            if not value:
                continue
            signals.append(
                self.repo.record_application_signal(
                    job_id,
                    signal_type,
                    label,
                    value,
                    evidence_text=_signal_evidence(signal_type, candidate),
                    source="discovery",
                    confidence=confidence,
                    actionability=actionability,
                    metadata={"candidate_id": candidate.get("id"), "source_provider": candidate.get("source_provider")},
                )
            )
        return {"research_note": note, "signals": signals}

    def _hydrate_greenhouse(self, original_url: str, detected: dict[str, Any]) -> dict[str, Any]:
        board = detected.get("board")
        job_id = detected.get("job_id")
        if not board or not job_id:
            raise DiscoveryError("Greenhouse URL needs a board token and job id.")
        api_url = (
            f"https://boards-api.greenhouse.io/v1/boards/{quote(board)}/jobs/{quote(job_id)}"
            f"?{urlencode({'questions': 'true', 'pay_transparency': 'true'})}"
        )
        try:
            data = self.fetch_json(api_url)
        except Exception as exc:
            raise DiscoveryError(f"Greenhouse hydration failed: {exc}") from exc
        location = data.get("location", {})
        questions = data.get("questions") or []
        pay_ranges = data.get("pay_input_ranges") or data.get("pay_transparency") or []
        return {
            "dedupe_key": f"greenhouse:{board}:{job_id}",
            "source_type": "ats_api",
            "source_provider": "greenhouse",
            "status": "hydrated",
            "title": normalize_space(str(data.get("title") or "")),
            "company": _company_from_token(board),
            "location": normalize_space(str(location.get("name") if isinstance(location, dict) else location or "")),
            "canonical_url": normalize_url(str(data.get("absolute_url") or original_url)),
            "discovered_url": original_url,
            "apply_url": normalize_url(str(data.get("absolute_url") or original_url)),
            "posted_at": "",
            "remote_updated_at": str(data.get("updated_at") or ""),
            "retrieved_at": utc_now(),
            "workplace_type": "",
            "employment_type": "",
            "compensation": _summarize_compensation(pay_ranges),
            "description": truncate_text(strip_html(str(data.get("content") or ""))),
            "application_form_summary": _summarize_questions(questions),
            "source_confidence": 0.95,
            "discovery_query": "",
            "raw_payload": data,
        }

    def _hydrate_lever(self, original_url: str, detected: dict[str, Any]) -> dict[str, Any]:
        site = detected.get("site")
        posting_id = detected.get("posting_id")
        if not site or not posting_id:
            raise DiscoveryError("Lever URL needs a site and posting id.")
        api_url = f"https://api.lever.co/v0/postings/{quote(site)}/{quote(posting_id)}?mode=json"
        try:
            data = self.fetch_json(api_url)
        except Exception as exc:
            raise DiscoveryError(f"Lever hydration failed: {exc}") from exc
        categories = data.get("categories") if isinstance(data.get("categories"), dict) else {}
        urls = data.get("urls") if isinstance(data.get("urls"), dict) else {}
        description = _lever_description(data)
        salary = data.get("salaryDescription") or data.get("salaryRange") or ""
        return {
            "dedupe_key": f"lever:{site}:{posting_id}",
            "source_type": "ats_api",
            "source_provider": "lever",
            "status": "hydrated",
            "title": normalize_space(str(data.get("text") or data.get("title") or "")),
            "company": _company_from_token(site),
            "location": normalize_space(str(categories.get("location") or data.get("workplaceType") or "")),
            "canonical_url": normalize_url(str(urls.get("show") or original_url)),
            "discovered_url": original_url,
            "apply_url": normalize_url(str(urls.get("apply") or "")),
            "posted_at": str(data.get("createdAt") or ""),
            "remote_updated_at": str(data.get("updatedAt") or ""),
            "retrieved_at": utc_now(),
            "workplace_type": normalize_space(str(data.get("workplaceType") or "")),
            "employment_type": normalize_space(str(categories.get("commitment") or "")),
            "compensation": _summarize_compensation(salary),
            "description": truncate_text(description),
            "application_form_summary": "Lever public postings do not expose custom application questions; check apply page before final effort.",
            "source_confidence": 0.9,
            "discovery_query": "",
            "raw_payload": data,
        }

    def _hydrate_ashby(self, original_url: str, detected: dict[str, Any]) -> dict[str, Any]:
        board = detected.get("board")
        if not board:
            raise DiscoveryError("Ashby URL needs a job board name.")
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{quote(board)}?includeCompensation=true"
        try:
            data = self.fetch_json(api_url)
        except Exception as exc:
            raise DiscoveryError(f"Ashby hydration failed: {exc}") from exc
        jobs = [item for item in data.get("jobs", []) or [] if isinstance(item, dict)]
        job = _match_ashby_job(original_url, jobs)
        if not job:
            raise DiscoveryError("Ashby board was reachable, but no matching job posting was found.")
        job_key = _ashby_job_key(job)
        return {
            "dedupe_key": f"ashby:{board}:{job_key}",
            "source_type": "ats_api",
            "source_provider": "ashby",
            "status": "hydrated",
            "title": normalize_space(str(job.get("title") or "")),
            "company": _company_from_token(board),
            "location": normalize_space(str(job.get("location") or "")),
            "canonical_url": normalize_url(str(job.get("jobUrl") or original_url)),
            "discovered_url": original_url,
            "apply_url": normalize_url(str(job.get("applyUrl") or "")),
            "posted_at": str(job.get("publishedAt") or ""),
            "remote_updated_at": str(job.get("updatedAt") or job.get("publishedAt") or ""),
            "retrieved_at": utc_now(),
            "workplace_type": normalize_space(str(job.get("workplaceType") or ("Remote" if job.get("isRemote") else ""))),
            "employment_type": normalize_space(str(job.get("employmentType") or "")),
            "compensation": _summarize_compensation(job.get("compensation") or ""),
            "description": truncate_text(str(job.get("descriptionPlain") or strip_html(str(job.get("descriptionHtml") or "")))),
            "application_form_summary": "Ashby public postings do not include the richer application form spec without jobsRead API access.",
            "source_confidence": 0.92,
            "discovery_query": "",
            "raw_payload": job,
        }

    def _apply_preflight(self, candidate: dict[str, Any]) -> None:
        job = self.candidate_to_job(candidate)
        try:
            evaluation = evaluate_job(job, {}, self.config)
        except ValueError as exc:
            candidate["status"] = "needs_review"
            candidate["blocker_status"] = "unknown"
            candidate["blocker_reasons"] = [{"area": "description", "severity": "unknown", "evidence": str(exc)}]
            return
        flags = evaluation.get("blocker_flags") or []
        risks = evaluation.get("risks") or []
        if flags:
            candidate["status"] = "blocked"
            candidate["blocker_status"] = "hard_blocker"
        elif evaluation.get("sponsorship_risk") == "unknown":
            candidate["status"] = "needs_review"
            candidate["blocker_status"] = "unknown"
        else:
            candidate["status"] = "ready"
            candidate["blocker_status"] = "clear"
        candidate["blocker_reasons"] = flags or [
            {
                "area": "preflight",
                "severity": candidate["blocker_status"],
                "evidence": "; ".join(str(item) for item in risks[:3]),
            }
        ]

    def _config(self) -> dict[str, Any]:
        value = self.config.get("discovery")
        return value if isinstance(value, dict) else {}

    def _ensure_enabled(self) -> None:
        if not bool(self._config().get("enabled", True)):
            raise DiscoveryError("Discovery is disabled in JobApps config.")

    def _hydrators(self) -> list[str]:
        configured = self._config().get("hydrators") or ["greenhouse", "lever", "ashby"]
        return [str(item).strip().lower() for item in configured if str(item).strip()]


def detect_ats(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        board = parts[0]
        job_id = ""
        if "jobs" in parts:
            index = parts.index("jobs")
            if len(parts) > index + 1:
                job_id = parts[index + 1]
        job_id = job_id or (query.get("gh_jid") or [""])[0]
        return {"provider": "greenhouse", "board": board, "job_id": job_id}
    if host == "jobs.lever.co" and parts:
        return {"provider": "lever", "site": parts[0], "posting_id": parts[1] if len(parts) > 1 else ""}
    if host == "jobs.eu.lever.co" and parts:
        return {"provider": "lever", "site": parts[0], "posting_id": parts[1] if len(parts) > 1 else "", "region": "eu"}
    if host == "jobs.ashbyhq.com" and parts:
        return {"provider": "ashby", "board": parts[0], "path": parts[1:]}
    return {"provider": "unknown"}


def http_get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "HermesJobApps/0.1"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit user-requested public API fetches.
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"User-Agent": "HermesJobApps/0.1", **headers}, method="POST")
    with urlopen(request, timeout=30) as response:  # noqa: S310 - explicit user-requested API integration.
        return json.loads(response.read().decode("utf-8"))


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = urlparse(f"https://{url.strip()}")
    query = parse_qs(parsed.query)
    kept = []
    for key, values in sorted(query.items()):
        if key.lower().startswith(("utm_", "fbclid", "gclid")):
            continue
        for value in values:
            kept.append((key, value))
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=urlencode(kept, doseq=True),
        fragment="",
    )
    return urlunparse(normalized).rstrip("/")


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    return normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(value)))


def truncate_text(value: str, limit: int = 30000) -> str:
    value = normalize_space(value)
    return value if len(value) <= limit else value[:limit].rsplit(" ", 1)[0]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_from_url(url: str) -> dict[str, Any]:
    canonical = normalize_url(url)
    return {
        "dedupe_key": f"url:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20]}",
        "source_type": "manual",
        "source_provider": "url",
        "status": "new",
        "title": "",
        "company": "",
        "location": "",
        "canonical_url": canonical,
        "discovered_url": url,
        "retrieved_at": utc_now(),
        "source_confidence": 0.45,
        "raw_payload": {"url": url},
    }


def _candidate_from_search_result(result: dict[str, Any], query: str) -> dict[str, Any]:
    canonical = normalize_url(str(result.get("url") or ""))
    highlights = result.get("highlights") if isinstance(result.get("highlights"), list) else []
    text = "\n".join(str(item) for item in highlights if item)
    return {
        "dedupe_key": f"url:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20]}",
        "source_type": "search_api",
        "source_provider": "exa",
        "status": "new",
        "title": normalize_space(str(result.get("title") or "")),
        "company": "",
        "location": "",
        "canonical_url": canonical,
        "discovered_url": canonical,
        "retrieved_at": utc_now(),
        "description": truncate_text(text),
        "blocker_status": "unknown",
        "source_confidence": float(result.get("score") or 0.55),
        "discovery_query": query,
        "raw_payload": result,
    }


def _sighting_from_search_result(result: dict[str, Any], query: str) -> dict[str, Any]:
    highlights = result.get("highlights") if isinstance(result.get("highlights"), list) else []
    return {
        "source_type": "search_api",
        "source_provider": "exa",
        "discovered_url": str(result.get("url") or ""),
        "discovery_query": query,
        "title": str(result.get("title") or ""),
        "snippet": normalize_space(" ".join(str(item) for item in highlights[:3])),
        "raw_payload": result,
    }


def _query_presets(value: Any) -> list[dict[str, str]]:
    presets = []
    if not isinstance(value, list):
        return presets
    for item in value:
        if not isinstance(item, dict):
            continue
        query = normalize_space(str(item.get("query") or ""))
        if not query:
            continue
        presets.append(
            {
                "id": re.sub(r"[^a-z0-9_-]+", "-", str(item.get("id") or item.get("label") or "preset").lower()).strip("-")[:48] or "preset",
                "label": normalize_space(str(item.get("label") or "Preset"))[:40],
                "query": query,
            }
        )
    return presets[:12]


def _promotion_summary(candidate: dict[str, Any]) -> str:
    lines = [
        f"Candidate promoted from {candidate.get('source_provider') or 'unknown'} via {candidate.get('source_type') or 'discovery'}.",
        f"Canonical URL: {candidate.get('canonical_url') or ''}",
        f"Discovered URL: {candidate.get('discovered_url') or ''}",
        f"Apply URL: {candidate.get('apply_url') or ''}",
        f"Retrieved: {candidate.get('retrieved_at') or ''}",
        f"Posted: {candidate.get('posted_at') or ''}",
        f"Remote updated: {candidate.get('remote_updated_at') or ''}",
        f"Compensation: {candidate.get('compensation') or ''}",
        f"Workplace: {candidate.get('workplace_type') or ''}",
        f"Employment: {candidate.get('employment_type') or ''}",
        f"Application form: {candidate.get('application_form_summary') or ''}",
        f"Preflight: {candidate.get('blocker_status') or 'unknown'}",
    ]
    reasons = _format_blocker_reasons(candidate.get("blocker_reasons"))
    if reasons:
        lines.append(f"Preflight evidence: {reasons}")
    return "\n".join(line for line in lines if line.rsplit(": ", 1)[-1])


def _signal_evidence(signal_type: str, candidate: dict[str, Any]) -> str:
    if signal_type == "blocker_preflight":
        return _format_blocker_reasons(candidate.get("blocker_reasons")) or candidate.get("blocker_status") or ""
    if signal_type == "application_form":
        return candidate.get("application_form_summary") or ""
    return candidate.get("canonical_url") or candidate.get("discovered_url") or ""


def _format_blocker_reasons(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        label = normalize_space(str(item.get("area") or item.get("severity") or "preflight"))
        evidence = normalize_space(str(item.get("evidence") or item.get("action") or ""))
        parts.append(f"{label}: {evidence}" if evidence else label)
    return "; ".join(parts)


def _coerce_confidence(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(number, 1.0))


def _summarize_questions(questions: Any) -> str:
    if not isinstance(questions, list) or not questions:
        return ""
    labels = []
    for question in questions[:18]:
        if not isinstance(question, dict):
            continue
        label = strip_html(str(question.get("label") or question.get("description") or "question"))
        required = "required" if question.get("required") else "optional"
        fields = question.get("fields") if isinstance(question.get("fields"), list) else []
        field_types = sorted({str(field.get("type") or "") for field in fields if isinstance(field, dict) and field.get("type")})
        suffix = f" ({required}{', ' + ', '.join(field_types) if field_types else ''})"
        labels.append(f"{label}{suffix}")
    return "; ".join(labels)


def _summarize_compensation(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return normalize_space(value)
    if isinstance(value, dict):
        for key in ("compensationTierSummary", "scrapeableCompensationSalarySummary", "salaryDescription"):
            if value.get(key):
                return normalize_space(str(value[key]))
        return normalize_space(json.dumps(value, sort_keys=True))
    if isinstance(value, list):
        bits = []
        for item in value[:4]:
            if isinstance(item, dict):
                bits.append(item.get("label") or item.get("range") or item.get("value") or json.dumps(item, sort_keys=True))
            else:
                bits.append(str(item))
        return normalize_space("; ".join(str(item) for item in bits if item))
    return normalize_space(str(value))


def _company_from_token(token: str) -> str:
    words = re.sub(r"[-_]+", " ", token).strip()
    if not words:
        return "Unknown company"
    return " ".join(part[:1].upper() + part[1:] for part in re.findall(r"[A-Za-z0-9]+", words)) or words


def _lever_description(data: dict[str, Any]) -> str:
    parts = [
        strip_html(str(data.get("descriptionPlain") or data.get("description") or "")),
        strip_html(str(data.get("additionalPlain") or data.get("additional") or "")),
    ]
    for item in data.get("lists", []) or []:
        if not isinstance(item, dict):
            continue
        heading = strip_html(str(item.get("text") or ""))
        content = strip_html(str(item.get("content") or ""))
        parts.append(f"{heading}\n{content}".strip())
    return normalize_space("\n\n".join(part for part in parts if part))


def _match_ashby_job(original_url: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = normalize_url(original_url)
    for job in jobs:
        if normalized in {normalize_url(str(job.get("jobUrl") or "")), normalize_url(str(job.get("applyUrl") or ""))}:
            return job
    parsed_path = urlparse(normalized).path.strip("/")
    if parsed_path:
        tail = parsed_path.split("/")[-1].lower()
        for job in jobs:
            if tail and tail in normalize_url(str(job.get("jobUrl") or "")).lower():
                return job
    return jobs[0] if len(jobs) == 1 else None


def _ashby_job_key(job: dict[str, Any]) -> str:
    url = normalize_url(str(job.get("jobUrl") or job.get("applyUrl") or job.get("title") or ""))
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
