"""Hermes run orchestration for JobApps opportunities."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any

from .hermes_client import HermesAPIError, HermesClient
from .prompts import build_chat_instructions, build_opportunity_prompt
from .repository import JobRepository
from .tools import AgentToolbox


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "canceled", "expired"}
ACTIVE_STATUSES = {"queued", "starting", "running", "requires_action", "in_progress"}


class HermesRunManager:
    def __init__(
        self,
        repo: JobRepository,
        toolbox: AgentToolbox,
        hermes: HermesClient,
        *,
        session_key: str = "jobapps",
    ) -> None:
        self.repo = repo
        self.toolbox = toolbox
        self.hermes = hermes
        self.session_key = session_key
        self._job_locks: dict[str, threading.Lock] = {}
        self._job_locks_guard = threading.Lock()

    def start_for_job(self, job_id: str) -> dict[str, Any]:
        with self._job_lock(job_id):
            active = self.repo.get_active_hermes_run_for_job(job_id)
            if active:
                record = self.repo.get_job(job_id)
                active_run = self.repo.get_agent_run(active["id"])
                active_run["existing"] = True
                record["active_run"] = active_run
                return record

            record = self.repo.get_job(job_id)
            prompt = build_opportunity_prompt(record["job"], self.repo.career_context(), record["evaluation"])
            prompt_record = self.repo.save_prompt_build(
                "opportunity_research_tailor",
                prompt,
                job_id=job_id,
                context_snapshot={"evaluation": record["evaluation"]},
                status="sent_to_hermes",
            )
            app_run, created = self.repo.create_hermes_run_unless_active(
                "Hermes research, tailoring, database updates, and follow-up planning.",
                job_id=job_id,
                prompt_id=prompt_record["id"],
                status="queued",
                metadata={
                    "prompt_id": prompt_record["id"],
                    "launch_mode": "background_thread",
                    "session_id": f"jobapps-{job_id}",
                },
            )
            if not created:
                record = self.repo.get_job(job_id)
                active_run = self.repo.get_agent_run(app_run["id"])
                active_run["existing"] = True
                record["active_run"] = active_run
                return record
            self.repo.record_agent_run_event(app_run["id"], "prompt_built", {"prompt_id": prompt_record["id"]})
            updated = self.repo.record_event(
                job_id,
                "hermes_run_queued",
                {
                    "status": "hermes_queued",
                    "prompt_id": prompt_record["id"],
                    "app_run_id": app_run["id"],
                },
            )
            active_run = self.repo.get_agent_run(app_run["id"])
            active_run["existing"] = False

        self._launch_in_background(job_id, app_run["id"], prompt, prompt_record["id"])
        updated["active_run"] = active_run
        return updated

    def start_for_jobs(self, job_ids: list[str]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        queued_count = 0
        existing_count = 0
        failed_count = 0
        for job_id in _unique_job_ids(job_ids):
            try:
                record = self.start_for_job(job_id)
                active_run = record.get("active_run") or {}
                if active_run.get("existing"):
                    existing_count += 1
                else:
                    queued_count += 1
                results.append(
                    {
                        "job_id": job_id,
                        "app_run_id": active_run.get("id", ""),
                        "status": active_run.get("status", ""),
                        "hermes_run_id": active_run.get("hermes_run_id", ""),
                        "existing": bool(active_run.get("existing")),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - batch launch reports per-job failures.
                failed_count += 1
                results.append({"job_id": job_id, "status": "failed", "error": str(exc)})
        return {
            "requested_count": len(_unique_job_ids(job_ids)),
            "queued_count": queued_count,
            "existing_count": existing_count,
            "failed_count": failed_count,
            "results": results,
        }

    def _job_lock(self, job_id: str) -> threading.Lock:
        with self._job_locks_guard:
            if job_id not in self._job_locks:
                self._job_locks[job_id] = threading.Lock()
            return self._job_locks[job_id]

    def _launch_in_background(self, job_id: str, app_run_id: str, prompt: str, prompt_id: str) -> None:
        thread = threading.Thread(
            target=self._launch_run,
            args=(job_id, app_run_id, prompt, prompt_id),
            name=f"jobapps-hermes-run-{app_run_id}",
            daemon=True,
        )
        thread.start()

    def _launch_run(self, job_id: str, app_run_id: str, prompt: str, prompt_id: str) -> None:
        session_id = f"jobapps-{job_id}"
        try:
            self.repo.update_agent_run(app_run_id, status="starting")
            self.repo.record_agent_run_event(app_run_id, "hermes_run_starting", {"session_id": session_id})
            response = self.hermes.start_run(
                prompt,
                instructions=build_chat_instructions(self.repo.instruction_summary(), self.toolbox.specs()),
                session_id=session_id,
                session_key=self.session_key,
            )
        except HermesAPIError as exc:
            self._record_launch_failure(job_id, app_run_id, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - background thread must mark the app run visibly.
            self._record_launch_failure(job_id, app_run_id, f"{type(exc).__name__}: {exc}")
            return

        hermes_run_id = _extract_identifier(response, "run_id", "id")
        hermes_session_id = _extract_identifier(response, "session_id", "conversation_id")
        status = _accepted_run_status(response)

        self.repo.update_agent_run(
            app_run_id,
            status=status,
            hermes_run_id=hermes_run_id,
            hermes_session_id=hermes_session_id,
            metadata={
                "start_response": _compact_payload(response),
                "last_snapshot_fingerprint": _fingerprint(response),
            },
        )
        self.repo.record_agent_run_event(
            app_run_id,
            "hermes_run_started",
            {
                "status": status,
                "hermes_run_id": hermes_run_id,
                "hermes_session_id": hermes_session_id,
            },
        )
        self.repo.record_event(
            job_id,
            "hermes_run_started",
            {
                "status": "hermes_running" if status not in TERMINAL_STATUSES else f"hermes_{status}",
                "hermes_run_id": hermes_run_id,
                "hermes_session_id": hermes_session_id,
                "prompt_id": prompt_id,
                "app_run_id": app_run_id,
            },
        )
        if status in TERMINAL_STATUSES:
            self._record_snapshot(app_run_id, response)

    def _record_launch_failure(self, job_id: str, app_run_id: str, error: str) -> None:
        self.repo.update_agent_run(app_run_id, status="failed", error=error)
        self.repo.record_agent_run_event(app_run_id, "hermes_run_failed", {"error": error})
        self.repo.record_event(job_id, "hermes_run_failed", {"status": "hermes_failed", "error": error})

    def refresh_for_job(self, job_id: str) -> dict[str, Any]:
        run = self.repo.get_active_hermes_run_for_job(job_id)
        if run is None:
            hermes_runs = [
                item for item in self.repo.list_agent_runs(job_id=job_id)
                if item.get("kind") == "hermes_run"
            ]
            if not hermes_runs:
                record = self.repo.get_job(job_id)
                record["active_run"] = None
                return record
            run = hermes_runs[0]

        if not run.get("hermes_run_id"):
            record = self.repo.get_job(job_id)
            record["active_run"] = self.repo.get_agent_run(run["id"])
            return record

        try:
            snapshot = self.hermes.get_run(run["hermes_run_id"])
        except HermesAPIError as exc:
            self.repo.update_agent_run(run["id"], status="failed", error=str(exc))
            self.repo.record_agent_run_event(run["id"], "hermes_poll_failed", {"error": str(exc)})
            updated = self.repo.record_event(
                job_id,
                "hermes_run_failed",
                {
                    "status": "hermes_failed",
                    "hermes_run_id": run.get("hermes_run_id", ""),
                    "error": str(exc),
                },
            )
            updated["active_run"] = self.repo.get_agent_run(run["id"])
            return updated

        return self._record_snapshot(run["id"], snapshot)

    def _record_snapshot(
        self,
        app_run_id: str,
        snapshot: dict[str, Any],
        event_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        app_run = self.repo.get_agent_run(app_run_id)
        job_id = app_run["job_id"]
        if not job_id:
            raise KeyError("Hermes run is not tied to a job.")

        status = _normalize_status(_extract_status(snapshot) or app_run["status"])
        output_text = _extract_text(snapshot)
        fingerprint = _fingerprint({"snapshot": snapshot, "events": event_payload or {}})
        metadata = {
            "last_snapshot_fingerprint": fingerprint,
            "last_raw_status": _extract_status(snapshot) or app_run["status"],
        }
        if event_payload:
            metadata["last_event_count"] = _count_events(event_payload)

        if app_run["metadata"].get("last_snapshot_fingerprint") != fingerprint:
            self.repo.record_agent_run_event(
                app_run_id,
                "hermes_snapshot",
                {
                    "status": status,
                    "output_preview": output_text[:600],
                    "event_count": _count_events(event_payload or {}),
                },
            )

        self.repo.update_agent_run(
            app_run_id,
            status=status,
            output=output_text or None,
            metadata=metadata,
        )

        if status in TERMINAL_STATUSES:
            self._ingest_final_output(job_id, app_run_id, output_text, snapshot)
            if not app_run["metadata"].get("terminal_event_recorded"):
                event_type = "hermes_run_failed" if status == "failed" else "hermes_run_completed"
                job_status = "hermes_failed" if status == "failed" else "hermes_completed"
                updated = self.repo.record_event(
                    job_id,
                    event_type,
                    {
                        "status": job_status,
                        "hermes_status": status,
                        "hermes_run_id": app_run.get("hermes_run_id", ""),
                        "app_run_id": app_run_id,
                    },
                )
                self.repo.update_agent_run(app_run_id, metadata={"terminal_event_recorded": True})
            else:
                updated = self.repo.get_job(job_id)
        else:
            updated = self.repo.get_job(job_id)

        updated["active_run"] = self.repo.get_agent_run(app_run_id)
        return updated

    def _ingest_final_output(
        self,
        job_id: str,
        app_run_id: str,
        output_text: str,
        snapshot: dict[str, Any],
    ) -> None:
        app_run = self.repo.get_agent_run(app_run_id)
        output_fingerprint = _fingerprint(output_text)
        if app_run["metadata"].get("ingested_output_fingerprint") == output_fingerprint:
            return

        if output_text and not _has_material_for_run(self.repo.get_job(job_id), "hermes_run_output", app_run_id):
            self.toolbox.execute(
                "jobapps_save_material",
                {
                    "job_id": job_id,
                    "kind": "hermes_run_output",
                    "format": "text",
                    "content": output_text,
                    "rationale": "Final Hermes run output.",
                    "source": "hermes",
                    "metadata": {"app_run_id": app_run_id},
                },
                run_id=app_run_id,
            )

        records = _extract_jobapps_records(snapshot) or _extract_jobapps_records(output_text)
        if records:
            self._apply_records(job_id, app_run_id, records)
            self.repo.record_agent_run_event(
                app_run_id,
                "jobapps_records_ingested",
                {"keys": sorted(records.keys())},
            )
        self.repo.update_agent_run(
            app_run_id,
            metadata={"ingested_output_fingerprint": output_fingerprint},
        )

    def _apply_records(self, job_id: str, app_run_id: str, records: dict[str, Any]) -> None:
        for entity in _list(records.get("brain_entities")):
            self.toolbox.execute("jobapps_upsert_brain_entity", entity, run_id=app_run_id)

        for event in _list(records.get("brain_events")):
            payload = {**event}
            payload.setdefault("job_id", job_id)
            self.toolbox.execute("jobapps_record_brain_event", payload, run_id=app_run_id)

        for note in _list(records.get("research_notes")):
            payload = {**note, "job_id": job_id}
            self.toolbox.execute("jobapps_record_research_note", payload, run_id=app_run_id)

        for material in _list(records.get("materials")):
            payload = {
                **material,
                "job_id": job_id,
                "source": material.get("source", "hermes"),
                "metadata": {"app_run_id": app_run_id, **material.get("metadata", {})},
            }
            self.toolbox.execute("jobapps_save_material", payload, run_id=app_run_id)

        for change in _list(records.get("application_changes")):
            payload = {**change, "job_id": job_id}
            self.toolbox.execute("jobapps_record_application_change", payload, run_id=app_run_id)

        for requirement in _list(records.get("tailoring_requirements")):
            payload = {**requirement, "job_id": job_id}
            self.toolbox.execute("jobapps_record_tailoring_requirement", payload, run_id=app_run_id)

        for decision in _list(records.get("portrayal_decisions")):
            payload = {**decision, "job_id": job_id}
            self.toolbox.execute("jobapps_record_portrayal_decision", payload, run_id=app_run_id)

        for pattern in _list(records.get("learning_patterns")):
            self.toolbox.execute("jobapps_record_learning_pattern", pattern, run_id=app_run_id)

        for item in _list(records.get("progress_items")):
            payload = {**item, "job_id": job_id}
            try:
                self.toolbox.execute("jobapps_create_progress_item", payload, run_id=app_run_id)
            except ValueError as exc:
                if "not a dashboard Action" not in str(exc):
                    raise

        for followup in _list(records.get("followups")):
            payload = {**followup, "job_id": job_id}
            self.toolbox.execute("jobapps_create_followup", payload, run_id=app_run_id)

        for approval in _list(records.get("approvals")):
            payload = {**approval, "job_id": job_id}
            try:
                self.toolbox.execute("jobapps_request_approval", payload, run_id=app_run_id)
            except ValueError as exc:
                if "not dashboard Actions" not in str(exc):
                    raise

        status = records.get("status")
        if isinstance(status, str) and status:
            self.toolbox.execute(
                "jobapps_update_status",
                {"job_id": job_id, "status": status, "note": "Status returned by Hermes run."},
                run_id=app_run_id,
            )


def _extract_identifier(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    for parent_key in ("run", "response", "data"):
        parent = payload.get(parent_key)
        if isinstance(parent, dict):
            found = _extract_identifier(parent, *keys)
            if found:
                return found
    return ""


def _extract_status(payload: dict[str, Any]) -> str:
    for key in ("status", "state", "run_status"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    for parent_key in ("run", "response", "data"):
        parent = payload.get(parent_key)
        if isinstance(parent, dict):
            status = _extract_status(parent)
            if status:
                return status
    return ""


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"succeeded", "success", "done"}:
        return "completed"
    if normalized in {"canceled", "cancelled"}:
        return "cancelled"
    if normalized in {"queued", "starting", "running", "in_progress", "requires_action", "failed", "completed", "expired"}:
        return normalized
    return "running"


def _accepted_run_status(response: dict[str, Any]) -> str:
    status = _normalize_status(_extract_status(response) or "running")
    if status in TERMINAL_STATUSES or status == "requires_action":
        return status
    return "running"


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    for key in ("output_text", "final_output", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    output = payload.get("output")
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            text = _extract_text(item)
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)
    for parent_key in ("run", "response", "result", "data"):
        value = payload.get(parent_key)
        text = _extract_text(value)
        if text:
            return text
    return ""


def _extract_jobapps_records(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        value = payload.get("jobapps_records") or payload.get("JOBAPPS_RECORDS")
        if isinstance(value, dict):
            return value
        text = _extract_text(payload)
        if text:
            return _extract_jobapps_records(text)
        return {}
    if not isinstance(payload, str):
        return {}

    marker = payload.find("JOBAPPS_RECORDS")
    if marker >= 0:
        start = payload.find("{", marker)
        if start >= 0:
            try:
                value, _ = json.JSONDecoder().raw_decode(payload[start:])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
    stripped = _strip_code_fence(payload.strip())
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _strip_code_fence(value: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL)
    return match.group(1) if match else value


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "run_id", "status", "state", "session_id", "conversation_id", "created_at")
    compact = {key: payload[key] for key in keys if key in payload}
    text = _extract_text(payload)
    if text:
        compact["output_preview"] = text[:600]
    return compact or {"preview": json.dumps(payload, default=str)[:900]}


def _fingerprint(value: Any) -> str:
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _count_events(payload: dict[str, Any]) -> int:
    for key in ("events", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _has_material_for_run(record: dict[str, Any], kind: str, app_run_id: str) -> bool:
    for material in record.get("materials", []):
        if material.get("kind") != kind:
            continue
        if material.get("metadata", {}).get("app_run_id") == app_run_id:
            return True
    return False


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_job_ids(job_ids: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for job_id in job_ids:
        normalized = str(job_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output
