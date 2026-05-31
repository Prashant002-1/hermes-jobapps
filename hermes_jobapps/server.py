"""Local HTTP server for the Hermes JobApps cockpit."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .chat import ChatOrchestrator
from .config import PROJECT_ROOT, load_config, resolve_project_path, save_config_overlay
from .discovery import DiscoveryError, DiscoveryService
from .hermes_commands import HermesCommandError, HermesSlashClient
from .hermes_client import HermesAPIError, HermesClient
from .repository import JobRepository
from .runs import ACTIVE_STATUSES, HermesRunManager
from .tools import AgentToolbox
from .workflow import JobAppsWorkflow


WEB_ROOT = PROJECT_ROOT / "web"
DESIGN_ROOT = PROJECT_ROOT / "design-system"
COCKPIT_JOB_STATUSES = {
    "new": "Review the role and run blocker preflight.",
    "applied": "Record application details and watch for replies.",
    "skip": "Skip this role and preserve the reason.",
}
COCKPIT_STATUS_ALIASES = {
    "inbox": "new",
    "ready": "new",
    "ready_to_apply": "new",
    "preparing": "new",
    "waiting": "applied",
    "closed": "applied",
    "skipped": "skip",
    "not_interested": "skip",
    "not_needed": "skip",
}
ACTION_ITEM_STATUSES = {"open", "pending", "done", "dismissed", "not_needed", "canceled", "cancelled"}
ACTION_STATUS_ALIASES = {
    "complete": "done",
    "completed": "done",
    "mark_done": "done",
    "mark_complete": "done",
    "not needed": "not_needed",
    "not-needed": "not_needed",
    "skip": "not_needed",
    "cancel": "canceled",
}


class AppState:
    def __init__(self, config_path: str | None, db_path: str | None) -> None:
        self.config = load_config(config_path)
        configured_db = db_path or self.config.get("database_path") or "data/hermes-jobapps.sqlite3"
        self.repo = JobRepository(resolve_project_path(configured_db))
        self.toolbox = AgentToolbox(self.repo, self.config)
        self.discovery = DiscoveryService(self.repo, self.config)
        self.workflow = JobAppsWorkflow(self.repo, self.toolbox)
        hermes_config = self.config.get("hermes", {})
        self.hermes_session_key = hermes_config.get("session_key", "jobapps")
        self.hermes_profile = hermes_config.get("profile") or hermes_config.get("recommended_profile", "jobapps")
        self.hermes = HermesClient(
            base_url=hermes_config.get("api_base"),
            api_key=hermes_config.get("api_key"),
            model=hermes_config.get("model"),
        )
        self.slash = HermesSlashClient(
            profile=self.hermes_profile,
            model=hermes_config.get("slash_model") or "",
            timeout=float(hermes_config.get("slash_timeout_seconds", 45)),
            python_path=hermes_config.get("slash_python", ""),
        )
        self.runs = HermesRunManager(
            self.repo,
            self.toolbox,
            self.hermes,
            session_key=self.hermes_session_key,
        )
        self.chat = ChatOrchestrator(
            repo=self.repo,
            toolbox=self.toolbox,
            workflow=self.workflow,
            runs=self.runs,
            hermes=self.hermes,
            slash=self.slash,
            session_key=self.hermes_session_key,
        )
        self.command_catalog_cache: dict[str, Any] | None = None


def create_handler(state: AppState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "HermesJobApps/0.2"

        def do_GET(self) -> None:
            self._handle_read(head=False)

        def do_HEAD(self) -> None:
            self._handle_read(head=True)

        def _handle_read(self, *, head: bool) -> None:
            parsed = urlparse(self.path)
            request_path = parsed.path
            if request_path in {"/", "/index.html"}:
                self._serve_file(WEB_ROOT / "index.html", "text/html; charset=utf-8", head=head)
                return
            if request_path.startswith("/static/"):
                requested = request_path.removeprefix("/static/")
                self._serve_file(WEB_ROOT / requested, root=WEB_ROOT, head=head)
                return
            if request_path.startswith("/assets/"):
                requested = request_path.removeprefix("/assets/")
                self._serve_file(WEB_ROOT / "assets" / requested, root=WEB_ROOT / "assets", head=head)
                return
            if request_path.startswith("/design-system/"):
                requested = request_path.removeprefix("/design-system/")
                self._serve_file(DESIGN_ROOT / requested, root=DESIGN_ROOT, head=head)
                return
            if request_path == "/api/state":
                if head:
                    self._empty_json()
                    return
                dashboard = state.repo.dashboard()
                specs = state.toolbox.specs()
                criteria = state.config.get("criteria", {})
                self._json(dashboard | {"tool_specs": specs, "criteria": criteria})
                return
            if request_path == "/api/hermes/status":
                if head:
                    self._empty_json()
                    return
                self._json(self._hermes_status())
                return
            if request_path == "/api/hermes/commands":
                if head:
                    self._empty_json()
                    return
                try:
                    self._json(self._hermes_commands())
                except HermesCommandError as exc:
                    self._json({"error": str(exc), "commands": [], "categories": []}, HTTPStatus.BAD_GATEWAY)
                return
            if request_path == "/api/hermes/sessions":
                if head:
                    self._empty_json()
                    return
                try:
                    sessions = state.slash.sessions(limit=300)
                    self._json(
                        {
                            "profile": state.hermes_profile,
                            "sessions": sessions.get("sessions", []),
                        }
                    )
                except HermesCommandError as exc:
                    self._json({"error": str(exc), "sessions": []}, HTTPStatus.BAD_GATEWAY)
                return
            if request_path == "/api/criteria":
                if head:
                    self._empty_json()
                    return
                self._json(state.config.get("criteria", {}))
                return
            if request_path == "/api/discovery/status":
                if head:
                    self._empty_json()
                    return
                self._json(state.discovery.status())
                return
            if request_path == "/api/discovery/candidates":
                if head:
                    self._empty_json()
                    return
                query = parse_qs(parsed.query)
                limit = _read_limit((query.get("limit") or ["80"])[0], default=80, maximum=300)
                status = (query.get("status") or ["all"])[0]
                self._json(
                    {
                        "candidates": state.repo.list_discovery_candidates(status=status, limit=limit),
                        "counts": state.repo.discovery_counts(),
                    }
                )
                return
            match = re.fullmatch(r"/api/materials/([A-Za-z0-9_-]{1,64})", request_path)
            if match:
                if head:
                    self._empty_json()
                    return
                try:
                    self._json(state.repo.get_material(match.group(1)))
                except KeyError:
                    self._json({"error": "Material not found"}, HTTPStatus.NOT_FOUND)
                return
            match = re.fullmatch(r"/api/materials/([A-Za-z0-9_-]{1,64})/file", request_path)
            if match:
                try:
                    material = state.repo.get_material(match.group(1))
                    query = parse_qs(parsed.query)
                    target = (query.get("target") or ["source"])[0]
                    file_path = self._material_file_path(material, target)
                    self._serve_local_artifact(file_path, root=self._materials_root(), head=head)
                except KeyError:
                    self._json({"error": "Material not found"}, HTTPStatus.NOT_FOUND)
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})", request_path)
            if match:
                if head:
                    self._empty_json()
                    return
                try:
                    self._json(state.repo.get_job(match.group(1)))
                except KeyError:
                    self._json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
                return
            match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/hermes-run", request_path)
            if match:
                if head:
                    self._empty_json()
                    return
                try:
                    self._json(state.runs.refresh_for_job(match.group(1)))
                except KeyError:
                    self._json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def do_POST(self) -> None:
            if self.path == "/api/jobs/prepare":
                payload = self._read_json()
                try:
                    record = state.workflow.prepare_opportunity(payload)
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                self._json(record, HTTPStatus.CREATED)
                return

            if self.path == "/api/discovery/search":
                payload = self._read_json()
                try:
                    result = state.discovery.search_exa(
                        str(payload.get("query") or ""),
                        limit=_read_limit(payload.get("limit", 8), default=8, maximum=25),
                        hydrate=bool(payload.get("hydrate", True)),
                    )
                    self._json(result, HTTPStatus.CREATED)
                except DiscoveryError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            if self.path == "/api/discovery/hydrate":
                payload = self._read_json()
                try:
                    candidate = state.discovery.hydrate_url(str(payload.get("url") or ""))
                    self._json({"candidate": candidate}, HTTPStatus.CREATED)
                except DiscoveryError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            if self.path == "/api/discovery/candidates/prepare-approved":
                payload = self._read_json()
                try:
                    result = state.discovery.prepare_approved_candidates(
                        state.workflow.prepare_opportunity,
                        limit=_read_limit(payload.get("limit", 3), default=3, maximum=10),
                    )
                    self._json(result, HTTPStatus.CREATED)
                except DiscoveryError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            match = re.fullmatch(r"/api/discovery/candidates/([a-f0-9]{12})/prepare", self.path)
            if match:
                try:
                    result = state.discovery.prepare_candidate(match.group(1), state.workflow.prepare_opportunity)
                    self._json(result, HTTPStatus.CREATED)
                except KeyError:
                    self._json({"error": "Discovery candidate not found"}, HTTPStatus.NOT_FOUND)
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            match = re.fullmatch(r"/api/discovery/candidates/([a-f0-9]{12})/status", self.path)
            if match:
                payload = self._read_json()
                try:
                    candidate = state.repo.update_discovery_candidate(
                        match.group(1),
                        status=payload.get("status"),
                        note=str(payload.get("note") or ""),
                    )
                    self._json({"candidate": candidate})
                except KeyError:
                    self._json({"error": "Discovery candidate not found"}, HTTPStatus.NOT_FOUND)
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            if self.path == "/api/hermes/chat/stream":
                payload = self._read_json()
                message = str(payload.get("message") or "").strip()
                if not message:
                    self._json({"error": "Message is required."}, HTTPStatus.BAD_REQUEST)
                    return
                conversation_history = payload.get("conversation_history")
                if not isinstance(conversation_history, list):
                    conversation_history = None
                self._start_sse()
                try:
                    for event in state.chat.stream(
                        message,
                        conversation=str(payload.get("conversation") or "jobapps-cockpit"),
                        conversation_history=conversation_history,
                    ):
                        self._sse(str(event.get("type") or "message"), event)
                except (BrokenPipeError, ConnectionResetError):
                    return
                except (ValueError, HermesAPIError, HermesCommandError) as exc:
                    self._sse("error", {"type": "error", "message": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    self._sse("error", {"type": "error", "message": f"JobApps stream failed: {exc}"})
                return

            if self.path == "/api/hermes/chat":
                payload = self._read_json()
                message = str(payload.get("message") or "").strip()
                if not message:
                    self._json({"error": "Message is required."}, HTTPStatus.BAD_REQUEST)
                    return
                conversation_history = payload.get("conversation_history")
                if not isinstance(conversation_history, list):
                    conversation_history = None
                try:
                    result = state.chat.handle(
                        message,
                        conversation=str(payload.get("conversation") or "jobapps-cockpit"),
                        conversation_history=conversation_history,
                    )
                    self._json(result)
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                except HermesAPIError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return

            if self.path == "/api/hermes/sessions/resume":
                payload = self._read_json()
                session_id = str(payload.get("session_id") or "").strip()
                if not session_id:
                    self._json({"error": "session_id is required."}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    self._json(state.slash.resume_session(session_id))
                except HermesCommandError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return

            if self.path == "/api/jobs/hermes-runs":
                payload = self._read_json()
                raw_job_ids = payload.get("job_ids")
                if isinstance(raw_job_ids, list):
                    job_ids = [str(item) for item in raw_job_ids if re.fullmatch(r"[a-f0-9]{12}", str(item))]
                else:
                    job_ids = _pending_hermes_job_ids(state.repo.dashboard().get("jobs", []))
                result = state.runs.start_for_jobs(job_ids)
                dashboard = state.repo.dashboard()
                specs = state.toolbox.specs()
                criteria = state.config.get("criteria", {})
                self._json(result | {"state": dashboard | {"tool_specs": specs, "criteria": criteria}}, HTTPStatus.ACCEPTED)
                return

            match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/hermes-run", self.path)
            if match:
                job_id = match.group(1)
                try:
                    self._json(state.runs.start_for_job(job_id), HTTPStatus.ACCEPTED)
                except KeyError:
                    self._json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
                except HermesAPIError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return

            match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/status", self.path)
            if match:
                payload = self._read_json()
                status = _normalize_cockpit_status(payload.get("status"))
                if status not in COCKPIT_JOB_STATUSES:
                    self._json(
                        {
                            "error": "Status must be one of: "
                            + ", ".join(COCKPIT_JOB_STATUSES.keys()),
                        },
                        HTTPStatus.BAD_REQUEST,
                    )
                    return
                note = str(payload.get("note") or "Updated from JobApps cockpit.")
                try:
                    record = state.repo.record_event(
                        match.group(1),
                        "status_changed",
                        {
                            "status": status,
                            "note": note,
                            "next_action": COCKPIT_JOB_STATUSES[status],
                            "source": "cockpit",
                        },
                    )
                    self._json({"job": record, "state": state.repo.dashboard()})
                except KeyError:
                    self._json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
                return

            match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/events", self.path)
            if match:
                payload = self._read_json()
                event_type = str(payload.get("event_type") or "note")
                saved = state.repo.record_event(match.group(1), event_type, payload)
                self._json(saved)
                return

            match = re.fullmatch(r"/api/progress-items/([a-f0-9]{12})/disposition", self.path)
            if match:
                payload = self._read_json()
                status = _normalize_action_item_status(payload.get("status") or payload.get("disposition"))
                if status not in ACTION_ITEM_STATUSES:
                    self._json({"error": "Status must be open, pending, done, dismissed, not_needed, or canceled."}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    item = state.repo.update_progress_item(
                        match.group(1),
                        status,
                        notes=str(payload.get("note") or "") if "note" in payload else None,
                        due_date=str(payload.get("due_date") or "") if "due_date" in payload else None,
                    )
                    self._json({"progress_item": item, "state": state.repo.dashboard()})
                except KeyError:
                    self._json({"error": "Progress item not found"}, HTTPStatus.NOT_FOUND)
                return

            match = re.fullmatch(r"/api/followups/([a-f0-9]{12})/disposition", self.path)
            if match:
                payload = self._read_json()
                status = _normalize_action_item_status(payload.get("status") or payload.get("disposition"))
                if status not in ACTION_ITEM_STATUSES:
                    self._json({"error": "Status must be open, pending, done, dismissed, not_needed, or canceled."}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    followup = state.repo.update_followup(
                        match.group(1),
                        status,
                        due_date=str(payload.get("due_date") or "") if "due_date" in payload else None,
                        reason=str(payload.get("reason") or "") if "reason" in payload else None,
                    )
                    self._json({"followup": followup, "state": state.repo.dashboard()})
                except KeyError:
                    self._json({"error": "Follow-up not found"}, HTTPStatus.NOT_FOUND)
                return

            match = re.fullmatch(r"/api/approvals/([a-f0-9]{12})/disposition", self.path)
            if match:
                payload = self._read_json()
                action = str(payload.get("action") or payload.get("disposition") or "").strip().lower()
                if action not in {"approve", "reject"}:
                    self._json({"error": "Approval action must be approve or reject."}, HTTPStatus.BAD_REQUEST)
                    return
                status = "approved" if action == "approve" else "rejected"
                try:
                    approval = state.repo.update_approval(
                        match.group(1),
                        status,
                        payload={"note": payload.get("note", ""), "acted_via": "actions"},
                    )
                    if approval.get("job_id"):
                        state.repo.record_event(
                            approval["job_id"],
                            "approval_updated",
                            {"approval_id": match.group(1), "status": status, "note": payload.get("note", "")},
                        )
                    self._json({"approval": approval, "state": state.repo.dashboard()})
                except KeyError:
                    self._json({"error": "Approval not found"}, HTTPStatus.NOT_FOUND)
                return

            match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/approvals/([a-f0-9]{12})", self.path)
            if match:
                payload = self._read_json()
                action = str(payload.get("action") or "").strip().lower()
                if action not in {"approve", "reject"}:
                    self._json({"error": "Approval action must be approve or reject."}, HTTPStatus.BAD_REQUEST)
                    return
                status = "approved" if action == "approve" else "rejected"
                try:
                    approval = state.repo.update_approval(
                        match.group(2),
                        status,
                        payload={"note": payload.get("note", ""), "acted_via": "cockpit"},
                    )
                    state.repo.record_event(
                        match.group(1),
                        "approval_updated",
                        {"approval_id": match.group(2), "status": status, "note": payload.get("note", "")},
                    )
                    self._json({"approval": approval, "state": state.repo.dashboard()})
                except KeyError:
                    self._json({"error": "Approval not found"}, HTTPStatus.NOT_FOUND)
                return

            match = re.fullmatch(r"/api/tools/([a-zA-Z0-9_]+)", self.path)
            if match:
                payload = self._read_json()
                try:
                    result = state.toolbox.execute(match.group(1), payload)
                    self._json(result)
                except KeyError:
                    self._json({"error": "Unknown tool"}, HTTPStatus.NOT_FOUND)
                except Exception as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            if self.path == "/api/criteria":
                payload = self._read_json()
                try:
                    save_config_overlay({"criteria": payload})
                    state.config = load_config()
                    state.discovery = DiscoveryService(state.repo, state.config)
                    self._json({"criteria": state.config.get("criteria", {}), "saved": True})
                except Exception as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def log_message(self, format: str, *args: Any) -> None:
            print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw or "{}")

        def _hermes_status(self) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "profile": state.hermes_profile,
                "session_key": state.hermes_session_key,
                "api_base": state.hermes.base_url,
                "model": state.hermes.model,
                "status": "unknown",
                "features": {},
                "commands": {"available": state.slash is not None},
            }
            try:
                health = state.hermes.health()
                capabilities = state.hermes.capabilities()
                payload["status"] = health.get("status", "ok")
                payload["health"] = health
                payload["features"] = capabilities.get("features", {})
                payload["advertised_model"] = capabilities.get("model") or payload["model"]
            except HermesAPIError as exc:
                payload["status"] = "offline"
                payload["error"] = str(exc)
            return payload

        def _hermes_commands(self) -> dict[str, Any]:
            if state.command_catalog_cache is None:
                catalog = state.slash.catalog()
                commands_by_name: dict[str, dict[str, str]] = {}
                categorized: set[str] = set()
                categories = []
                for category in catalog.get("categories", []):
                    if not isinstance(category, dict):
                        continue
                    pairs = category.get("pairs", [])
                    category_commands = []
                    category_name = str(category.get("name") or "Commands")
                    for pair in pairs:
                        if not isinstance(pair, list) or len(pair) < 2:
                            continue
                        command = str(pair[0])
                        description = str(pair[1])
                        categorized.add(command)
                        item = {"command": command, "description": description, "category": category_name}
                        commands_by_name.setdefault(command, item)
                        category_commands.append(item)
                    if category_commands:
                        categories.append({"name": category_name, "commands": category_commands})

                uncategorized_commands = []
                for pair in catalog.get("pairs", []):
                    if not isinstance(pair, list) or len(pair) < 2:
                        continue
                    command = str(pair[0])
                    description = str(pair[1])
                    if command in commands_by_name:
                        continue
                    category_name = "Skills" if command not in categorized else "Commands"
                    item = {"command": command, "description": description, "category": category_name}
                    commands_by_name[command] = item
                    uncategorized_commands.append(item)
                if uncategorized_commands:
                    categories.append({"name": "Skills", "commands": uncategorized_commands})

                state.command_catalog_cache = {
                    "commands": list(commands_by_name.values()),
                    "categories": categories,
                    "canon": catalog.get("canon", {}),
                    "subcommands": catalog.get("sub", {}),
                    "skill_count": catalog.get("skill_count", 0),
                    "warning": catalog.get("warning", ""),
                }
            return state.command_catalog_cache

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _start_sse(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

        def _sse(self, event_name: str, payload: dict[str, Any]) -> None:
            safe_name = re.sub(r"[^a-zA-Z0-9_.-]", ".", event_name) or "message"
            data = json.dumps(payload, separators=(",", ":"))
            self.wfile.write(f"event: {safe_name}\ndata: {data}\n\n".encode("utf-8"))
            self.wfile.flush()

        def _empty_json(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _materials_root(self) -> Path:
            return resolve_project_path(state.config.get("materials_path", "data/materials")).expanduser()

        def _material_file_path(self, material: dict[str, Any], target: str) -> Path:
            metadata = material.get("metadata") if isinstance(material.get("metadata"), dict) else {}
            compile_info = metadata.get("compile") if isinstance(metadata.get("compile"), dict) else {}
            if target == "pdf":
                candidates = [compile_info.get("pdf_path"), metadata.get("pdf_path")]
                source_path = Path(str(material.get("file_path") or "")).expanduser()
                if source_path.suffix.lower() in {".tex", ".ltx"}:
                    candidates.append(str(source_path.with_suffix(".pdf")))
                for candidate in candidates:
                    if not candidate:
                        continue
                    path = Path(str(candidate)).expanduser()
                    if path.exists() and path.is_file():
                        return path
                file_path = candidates[0] if candidates else ""
            elif target == "log":
                file_path = compile_info.get("log_path")
            else:
                file_path = material.get("file_path")
            if not file_path:
                raise ValueError(f"No {target or 'source'} file is available for this material.")
            return Path(str(file_path)).expanduser()

        def _serve_local_artifact(self, path: Path, *, root: Path, head: bool = False) -> None:
            content_type = mimetypes.guess_type(path.name)[0] or "text/plain"
            if path.suffix.lower() in {".tex", ".ltx", ".md", ".txt", ".log"}:
                content_type = "text/plain; charset=utf-8"
            self._serve_file(path, content_type, root=root, head=head, inline_name=path.name)

        def _serve_file(
            self,
            path: Path,
            content_type: str | None = None,
            *,
            root: Path = WEB_ROOT,
            head: bool = False,
            inline_name: str | None = None,
        ) -> None:
            try:
                resolved = path.resolve()
                resolved.relative_to(root.resolve())
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            if not resolved.exists() or not resolved.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            data = resolved.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or mimetypes.guess_type(resolved.name)[0] or "text/plain")
            self.send_header("Content-Length", str(len(data)))
            if inline_name:
                safe_name = re.sub(r'["\r\n]', "_", inline_name)
                self.send_header("Content-Disposition", f'inline; filename="{safe_name}"')
            self.end_headers()
            if not head:
                self.wfile.write(data)

    return Handler


def _normalize_cockpit_status(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return COCKPIT_STATUS_ALIASES.get(normalized, normalized)


def _normalize_action_item_status(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return ACTION_STATUS_ALIASES.get(normalized, normalized)


def _pending_hermes_job_ids(jobs: list[dict[str, Any]]) -> list[str]:
    blocked_statuses = {"applied", "waiting", "closed", "rejected", "declined", "archived", "hermes_completed", "skip", "skipped", "not_interested", "not_needed"}
    output: list[str] = []
    for job in jobs:
        job_id = str(job.get("id") or "")
        if not re.fullmatch(r"[a-f0-9]{12}", job_id):
            continue
        decision = str(job.get("decision") or job.get("evaluation", {}).get("decision") or "pending").lower()
        status = str(job.get("status") or "").lower()
        active_run = job.get("active_run") or {}
        if decision == "skip" or status in blocked_statuses:
            continue
        if active_run.get("status") in ACTIVE_STATUSES:
            continue
        output.append(job_id)
    return output


def _read_limit(value: Any, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Hermes JobApps local cockpit.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", default=None)
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    state = AppState(args.config, args.db)
    server = ThreadingHTTPServer((args.host, args.port), create_handler(state))
    print(f"Hermes JobApps running at http://{args.host}:{args.port}")
    print(f"App database: {state.repo.path}")
    print(f"Hermes API: {state.hermes.base_url}")
    print(f"Hermes profile: {state.hermes_profile}")
    server.serve_forever()


if __name__ == "__main__":
    main()
