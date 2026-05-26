"""Networking operator helpers for JobApps.

This module is deliberately narrow: find public people, cache contacts, and
create Gmail drafts. It never sends email.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .discovery import http_post_json
from .knowledge import normalize_space
from .repository import JobRepository


JsonPoster = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
JsonGetter = Callable[[str, dict[str, str]], dict[str, Any]]
CommandRunner = Callable[[list[str], str, int], subprocess.CompletedProcess[str]]


class NetworkingError(ValueError):
    """Raised when people search or draft creation cannot complete."""


class NetworkingService:
    def __init__(
        self,
        repo: JobRepository,
        config: dict[str, Any],
        *,
        post_json: JsonPoster | None = None,
        get_json: JsonGetter | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.repo = repo
        self.config = config
        self.post_json = post_json or http_post_json
        self.get_json = get_json or http_get_json
        self.command_runner = command_runner or _run_command

    def status(self) -> dict[str, Any]:
        config = self._config()
        exa = config.get("exa", {}) if isinstance(config.get("exa"), dict) else {}
        discovery_config = self.config.get("discovery", {}) if isinstance(self.config.get("discovery"), dict) else {}
        discovery_exa = discovery_config.get("exa", {}) if isinstance(discovery_config.get("exa"), dict) else {}
        env_name = str(exa.get("api_key_env") or discovery_exa.get("api_key_env") or "EXA_API_KEY")
        gog_path = str(config.get("gog_path") or "gog")
        return {
            "enabled": bool(config.get("enabled", True)),
            "people_search": {
                "provider": str(config.get("people_provider") or "exa_search"),
                "configured": bool(os.environ.get(env_name)),
                "api_key_env": env_name,
                "category": str(exa.get("category") or "people"),
            },
            "websets": {
                "provider": "exa_websets",
                "configured": bool(os.environ.get(env_name)),
                "mode": "explicit_or_missing_email_fallback",
                "default": False,
            },
            "drafts": {
                "provider": "gog",
                "available": bool(shutil.which(gog_path)),
                "command": gog_path,
                "policy": "draft_only_no_send",
            },
        }

    def search_people(
        self,
        *,
        query: str = "",
        company: str = "",
        job_id: str = "",
        limit: int = 6,
        provider: str = "",
        use_websets_fallback: bool = False,
    ) -> dict[str, Any]:
        self._ensure_enabled()
        if job_id and not company:
            try:
                company = self.repo.get_job(job_id)["job"].get("company") or ""
            except KeyError as exc:
                raise NetworkingError(f"Job not found: {job_id}") from exc
        query = normalize_space(query or _default_people_query(company))
        if not query:
            raise NetworkingError("People search needs a query or company.")
        provider = normalize_space(provider or str(self._config().get("people_provider") or "search")).lower()
        if provider in {"websets", "exa_websets"}:
            return self._search_people_websets(query=query, company=company, job_id=job_id, limit=limit)
        if provider not in {"search", "exa", "exa_search", "auto"}:
            raise NetworkingError(f"Unsupported people search provider: {provider}")
        result = self._search_people_search(query=query, company=company, job_id=job_id, limit=limit)
        if (use_websets_fallback or provider == "auto") and not _has_verified_email(result["contacts"]):
            websets = self._search_people_websets(query=query, company=company, job_id=job_id, limit=min(int(limit or 1), 3))
            contacts = _dedupe_contacts([*result["contacts"], *websets["contacts"]])
            return {
                **result,
                "provider": "exa_search+websets",
                "count": len(contacts),
                "contacts": contacts,
                "research_notes": [*result.get("research_notes", []), *websets.get("research_notes", [])],
                "fallback_reason": "missing_verified_email",
                "websets": {
                    "webset": websets.get("webset"),
                    "count": websets.get("count"),
                    "provider": websets.get("provider"),
                },
            }
        return result

    def _search_people_search(self, *, query: str, company: str, job_id: str, limit: int) -> dict[str, Any]:
        config = self._config()
        exa = config.get("exa", {}) if isinstance(config.get("exa"), dict) else {}
        discovery_config = self.config.get("discovery", {}) if isinstance(self.config.get("discovery"), dict) else {}
        discovery_exa = discovery_config.get("exa", {}) if isinstance(discovery_config.get("exa"), dict) else {}
        env_name = str(exa.get("api_key_env") or discovery_exa.get("api_key_env") or "EXA_API_KEY")
        api_key = os.environ.get(env_name)
        if not api_key:
            raise NetworkingError(f"{env_name} is not set. People search cannot run.")
        safe_limit = max(1, min(int(limit or 6), 15))
        payload: dict[str, Any] = {
            "query": query,
            "numResults": safe_limit,
            "type": str(exa.get("type") or "auto"),
            "category": str(exa.get("category") or "people"),
            "contents": {
                "highlights": {
                    "query": f"{query} role company email contact",
                    "numSentences": 2,
                    "highlightsPerUrl": 2,
                }
            },
        }
        include_domains = exa.get("include_domains")
        if isinstance(include_domains, list) and include_domains:
            payload["includeDomains"] = [str(item) for item in include_domains if item]
        base_url = str(exa.get("base_url") or discovery_exa.get("base_url") or "https://api.exa.ai").rstrip("/")
        try:
            data = self.post_json(f"{base_url}/search", payload, {"x-api-key": api_key, "Content-Type": "application/json"})
        except Exception as exc:
            raise NetworkingError(f"Exa people search failed: {exc}") from exc
        contacts = []
        notes = []
        for result in data.get("results", []) or []:
            if not isinstance(result, dict):
                continue
            contact = _contact_from_exa_result(result, company)
            if not contact.get("name"):
                continue
            cached = self.repo.upsert_contact(**contact)
            contacts.append(cached)
            if job_id:
                note = self.repo.save_research_note(
                    "Networking contact",
                    _contact_summary(cached, query),
                    job_id=job_id,
                    source_url=cached.get("source_url") or cached.get("linkedin_url") or "",
                    confidence=float(cached.get("source_confidence") or 0.6),
                )
                notes.append(note)
        return {
            "provider": "exa_search",
            "query": query,
            "count": len(contacts),
            "contacts": contacts,
            "research_notes": notes,
            "raw_request_id": data.get("requestId") or data.get("request_id") or "",
        }

    def _search_people_websets(self, *, query: str, company: str, job_id: str, limit: int) -> dict[str, Any]:
        config = self._config()
        websets = config.get("websets", {}) if isinstance(config.get("websets"), dict) else {}
        if websets.get("enabled") is False:
            raise NetworkingError("Exa Websets contact enrichment is disabled.")
        exa = config.get("exa", {}) if isinstance(config.get("exa"), dict) else {}
        env_name = str(websets.get("api_key_env") or exa.get("api_key_env") or "EXA_API_KEY")
        api_key = os.environ.get(env_name)
        if not api_key:
            raise NetworkingError(f"{env_name} is not set. Exa Websets cannot run.")
        safe_limit = max(1, min(int(limit or websets.get("default_num_results") or 3), 5))
        base_url = str(websets.get("base_url") or "https://api.exa.ai/websets/v0").rstrip("/")
        headers = {"x-api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "title": f"JobApps contacts: {company or query[:80]}",
            "search": {
                "query": query,
                "count": safe_limit,
                "entity": {"type": "person"},
                "criteria": _webset_people_criteria(company),
            },
            "enrichments": [
                {
                    "description": "Find this person's publicly available professional email address. Return only a verified email address with public source support; leave blank if none is found.",
                    "format": "email",
                }
            ],
            "metadata": {"source": "jobapps", "company": company, "cost_mode": "fallback"},
        }
        try:
            webset = self.post_json(f"{base_url}/websets", payload, headers)
        except Exception as exc:
            raise NetworkingError(f"Exa Websets contact enrichment failed: {exc}") from exc
        webset_id = str(webset.get("id") or "")
        if not webset_id:
            raise NetworkingError("Exa Websets did not return a webset id.")
        webset = self._wait_for_webset(base_url, webset_id, api_key, webset)
        items = self._list_webset_items(base_url, webset_id, api_key, safe_limit)
        contacts = []
        notes = []
        for item in items:
            if not isinstance(item, dict):
                continue
            contact = _contact_from_webset_item(item, company)
            if not contact.get("name"):
                continue
            cached = self.repo.upsert_contact(**contact)
            contacts.append(cached)
            if job_id:
                note = self.repo.save_research_note(
                    "Networking contact",
                    _contact_summary(cached, query),
                    job_id=job_id,
                    source_url=cached.get("source_url") or cached.get("linkedin_url") or "",
                    confidence=float(cached.get("source_confidence") or 0.7),
                )
                notes.append(note)
        return {
            "provider": "exa_websets",
            "query": query,
            "count": len(contacts),
            "contacts": contacts,
            "research_notes": notes,
            "webset": {
                "id": webset_id,
                "status": webset.get("status") or "",
                "dashboard_url": webset.get("dashboardUrl") or webset.get("dashboard_url") or "",
                "cost_mode": "fallback",
            },
        }

    def _wait_for_webset(self, base_url: str, webset_id: str, api_key: str, initial: dict[str, Any]) -> dict[str, Any]:
        websets = self._config().get("websets", {}) if isinstance(self._config().get("websets"), dict) else {}
        max_wait = max(0, min(int(websets.get("max_wait_seconds") or 45), 180))
        poll_seconds = max(1, min(float(websets.get("poll_seconds") or 3), 15))
        if max_wait == 0:
            return initial
        deadline = time.monotonic() + max_wait
        latest = initial
        while time.monotonic() < deadline:
            latest = self.get_json(f"{base_url}/websets/{webset_id}", {"x-api-key": api_key})
            if str(latest.get("status") or "").lower() == "idle":
                return latest
            time.sleep(poll_seconds)
        return latest

    def _list_webset_items(self, base_url: str, webset_id: str, api_key: str, limit: int) -> list[dict[str, Any]]:
        query = urlencode({"limit": max(1, min(limit, 100))})
        data = self.get_json(f"{base_url}/websets/{webset_id}/items?{query}", {"x-api-key": api_key})
        return [item for item in data.get("data", []) or [] if isinstance(item, dict)]

    def create_gmail_draft(
        self,
        *,
        subject: str,
        body: str,
        job_id: str = "",
        contact_id: str = "",
        to_email: str = "",
        account: str = "",
    ) -> dict[str, Any]:
        self._ensure_enabled()
        subject = normalize_space(subject)
        body = str(body or "").strip()
        if not subject:
            raise NetworkingError("Draft subject is required.")
        if not body:
            raise NetworkingError("Draft body is required.")
        contact = None
        if contact_id:
            try:
                contact = self.repo.get_contact(contact_id)
            except KeyError as exc:
                raise NetworkingError(f"Contact not found: {contact_id}") from exc
            if not to_email and contact.get("email_status") == "found":
                to_email = contact.get("email") or ""
        command = self._draft_command(subject=subject, to_email=to_email, account=account)
        try:
            result = self.command_runner(command, body, int(self._config().get("gog_timeout_seconds") or 30))
        except subprocess.TimeoutExpired as exc:
            raise NetworkingError("gog draft creation timed out.") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise NetworkingError(f"gog draft creation failed: {detail or 'unknown error'}")
        draft = _normalize_gog_draft(_parse_gog_json(result.stdout))
        material = None
        approval = None
        if job_id:
            material = self.repo.save_material(
                job_id,
                "outreach_draft",
                body,
                rationale="Networking draft only. No send action is available from JobApps.",
                format="text",
                source="gog_draft",
                metadata={
                    "subject": subject,
                    "to_email": to_email,
                    "contact_id": contact_id,
                    "contact_email_status": contact.get("email_status") if contact else "",
                    "gmail_draft": draft,
                    "policy": "draft_only_no_send",
                },
            )
            approval = self.repo.create_approval(
                "review_outreach_draft",
                job_id=job_id,
                payload={
                    "material_id": material["id"],
                    "contact_id": contact_id,
                    "subject": subject,
                    "policy": "Draft created only. JobApps has no email-send tool.",
                },
            )
        return {
            "provider": "gog",
            "policy": "draft_only_no_send",
            "command_scope": "gmail.drafts.create",
            "to_email": to_email,
            "recipient_policy": "verified_contact_email_only",
            "contact_email_status": contact.get("email_status") if contact else "",
            "contact": contact,
            "draft": draft,
            "material": material,
            "approval": approval,
        }

    def _draft_command(self, *, subject: str, to_email: str, account: str) -> list[str]:
        gog_path = str(self._config().get("gog_path") or "gog")
        if not shutil.which(gog_path):
            raise NetworkingError(f"gog command not found: {gog_path}")
        command = [
            gog_path,
            "--gmail-no-send",
            "--json",
            "--no-input",
            "gmail",
            "drafts",
            "create",
            "--subject",
            subject,
            "--body-file",
            "-",
        ]
        if account:
            command[1:1] = ["--account", account]
        if to_email:
            command.extend(["--to", to_email])
        return command

    def _config(self) -> dict[str, Any]:
        value = self.config.get("networking")
        return value if isinstance(value, dict) else {}

    def _ensure_enabled(self) -> None:
        if not bool(self._config().get("enabled", True)):
            raise NetworkingError("Networking is disabled in JobApps config.")


def _contact_from_exa_result(result: dict[str, Any], default_company: str) -> dict[str, Any]:
    url = normalize_space(str(result.get("url") or ""))
    title = normalize_space(str(result.get("title") or ""))
    highlights = result.get("highlights") or []
    highlight_text = " ".join(str(item) for item in highlights if item)
    email = _extract_email(f"{title} {highlight_text}")
    name, role, company = _parse_person_title(title, default_company)
    linkedin_url = url if "linkedin.com/in/" in url.lower() else ""
    return {
        "name": name,
        "company": company,
        "role": role,
        "email": email,
        "email_status": "found" if email else "missing",
        "linkedin_url": linkedin_url,
        "source_url": url,
        "source_provider": "exa",
        "source_confidence": 0.72 if linkedin_url else 0.58,
        "channel": "email" if email else ("linkedin" if linkedin_url else "web"),
        "relationship": "prospect",
        "notes": normalize_space(highlight_text)[:1200],
        "raw_payload": result,
    }


def _contact_from_webset_item(item: dict[str, Any], default_company: str) -> dict[str, Any]:
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    person = properties.get("person") if isinstance(properties.get("person"), dict) else {}
    company_data = person.get("company") if isinstance(person.get("company"), dict) else {}
    url = normalize_space(str(properties.get("url") or ""))
    email = _email_from_webset_item(item)
    linkedin_url = _linkedin_from_webset_item(item) or (url if "linkedin.com/in/" in url.lower() else "")
    name = normalize_space(str(person.get("name") or properties.get("title") or ""))
    role = normalize_space(str(person.get("position") or ""))
    company = normalize_space(str(company_data.get("name") or default_company))
    description = normalize_space(str(properties.get("description") or ""))
    return {
        "name": name[:160],
        "company": company[:160],
        "role": role[:220],
        "email": email,
        "email_status": "found" if email else "missing",
        "linkedin_url": linkedin_url,
        "source_url": url or linkedin_url,
        "source_provider": "exa_websets",
        "source_confidence": 0.86 if email else 0.74,
        "channel": "email" if email else ("linkedin" if linkedin_url else "web"),
        "relationship": "prospect",
        "notes": description[:1200],
        "raw_payload": item,
    }


def _parse_person_title(title: str, default_company: str) -> tuple[str, str, str]:
    clean = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.I)
    parts = [normalize_space(part) for part in re.split(r"\s+-\s+|\s+\|\s+", clean) if normalize_space(part)]
    name = parts[0] if parts else clean
    role = parts[1] if len(parts) > 1 else ""
    company = parts[2] if len(parts) > 2 else default_company
    if not role and "," in name:
        pieces = [normalize_space(part) for part in name.split(",", 1)]
        name = pieces[0]
        role = pieces[1] if len(pieces) > 1 else ""
    return name[:160], role[:220], company[:160]


def _extract_email(text: str) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text or "")
    return match.group(0).lower() if match else ""


def _email_from_webset_item(item: dict[str, Any]) -> str:
    for enrichment in item.get("enrichments", []) or []:
        if not isinstance(enrichment, dict):
            continue
        if str(enrichment.get("format") or "").lower() != "email":
            continue
        email = _extract_email(_stringify_enrichment_result(enrichment.get("result")))
        if email:
            return email
    return _extract_email(json.dumps(item.get("enrichments") or [], default=str))


def _linkedin_from_webset_item(item: dict[str, Any]) -> str:
    candidates = [str((item.get("properties") or {}).get("url") or "")]
    for enrichment in item.get("enrichments", []) or []:
        if not isinstance(enrichment, dict):
            continue
        candidates.append(_stringify_enrichment_result(enrichment.get("result")))
        for reference in enrichment.get("references", []) or []:
            if isinstance(reference, dict):
                candidates.append(str(reference.get("url") or ""))
    for candidate in candidates:
        match = re.search(r"https?://(?:www\.)?linkedin\.com/in/[^\s\"'<>),]+", candidate, flags=re.I)
        if match:
            return match.group(0).rstrip("/")
    return ""


def _stringify_enrichment_result(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_stringify_enrichment_result(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_stringify_enrichment_result(item) for item in value.values())
    return str(value)


def _default_people_query(company: str) -> str:
    company = normalize_space(company)
    if not company:
        return ""
    return f'{company} engineering recruiter hiring manager AI ML "LinkedIn"'


def _contact_summary(contact: dict[str, Any], query: str) -> str:
    lines = [
        f"Found through Exa people search: {query}",
        f"Name: {contact.get('name') or ''}",
        f"Role: {contact.get('role') or ''}",
        f"Company: {contact.get('company') or ''}",
        f"Email: {contact.get('email') or ''}",
        f"Email status: {contact.get('email_status') or ''}",
        f"LinkedIn: {contact.get('linkedin_url') or ''}",
        f"Source: {contact.get('source_url') or ''}",
        f"Notes: {contact.get('notes') or ''}",
    ]
    return "\n".join(line for line in lines if line.rsplit(": ", 1)[-1])


def _webset_people_criteria(company: str) -> list[dict[str, str]]:
    criteria = [{"description": "Person is relevant to recruiting, talent, hiring, engineering leadership, AI, ML, or applied engineering hiring."}]
    if company:
        criteria.append({"description": f"Person works at or publicly represents {company}."})
    return criteria


def _has_verified_email(contacts: list[dict[str, Any]]) -> bool:
    return any(contact.get("email") and contact.get("email_status") == "found" for contact in contacts)


def _dedupe_contacts(contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positions: dict[str, int] = {}
    deduped: list[dict[str, Any]] = []
    for contact in contacts:
        key = str(contact.get("id") or contact.get("email") or contact.get("source_url") or contact.get("name") or "")
        if not key:
            continue
        if key in positions:
            deduped[positions[key]] = contact
        else:
            positions[key] = len(deduped)
            deduped.append(contact)
    return deduped


def _run_command(command: list[str], stdin: str, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=stdin, text=True, capture_output=True, timeout=timeout_seconds, check=False)


def http_get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "HermesJobApps/0.1", **headers})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - explicit user-requested public API fetches.
        return json.loads(response.read().decode("utf-8"))


def _parse_gog_json(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _normalize_gog_draft(draft: dict[str, Any]) -> dict[str, Any]:
    draft_id = draft.get("id") or draft.get("draftId")
    if not draft_id and isinstance(draft.get("draft"), dict):
        nested = draft["draft"]
        draft_id = nested.get("id") or nested.get("draftId")
    if not draft_id:
        return draft
    normalized = dict(draft)
    normalized.setdefault("id", draft_id)
    normalized.setdefault("draftId", draft_id)
    return normalized
