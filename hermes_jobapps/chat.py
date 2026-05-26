"""Chat-first orchestration for the JobApps harness.

The web UI is intentionally only a chat composer plus structured state viewer.
This module handles the small set of app-owned transitions that should happen
locally before falling back to Hermes conversation: pasted opportunity prep and
run launch for the latest/current job.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from .hermes_commands import HermesCommandError
from .hermes_client import HermesAPIError, extract_output_text
from .knowledge import normalize_space
from .prompts import build_chat_instructions

URL_RE = re.compile(r"https?://\S+")
TITLE_AT_COMPANY_RE = re.compile(r"^(.{2,90}?)\s+(?:at|@)\s+(.{2,90}?)(?:\s*[-|].*)?$", re.IGNORECASE)
FIELD_RE = re.compile(r"^(title|role|position|company|location|url)\s*:\s*(.+)$", re.IGNORECASE)


class ChatOrchestrator:
    """Route chat messages into JobApps transitions or Hermes chat.

    This is not a replacement for Hermes tool calling. It is the practical
    harness layer that makes the first workflow work even when the Hermes API
    chat endpoint is only conversational.
    """

    def __init__(
        self,
        *,
        repo: Any,
        toolbox: Any,
        workflow: Any,
        runs: Any | None = None,
        hermes: Any | None = None,
        slash: Any | None = None,
        session_key: str = "jobapps",
    ) -> None:
        self.repo = repo
        self.toolbox = toolbox
        self.workflow = workflow
        self.runs = runs
        self.hermes = hermes
        self.slash = slash
        self.session_key = session_key

    def handle(
        self,
        message: str,
        *,
        conversation: str = "jobapps-cockpit",
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        text = normalize_space(message)
        if not text:
            raise ValueError("Message is required.")
        self._remember_conversation("user", message, conversation)

        if _is_hermes_command(text):
            result = self._run_hermes_command(text)
            self._remember_conversation("assistant", result.get("output_text", ""), conversation, {"action": result.get("action")})
            return result

        if _is_start_run_intent(text):
            result = self._start_latest_run(text)
            self._remember_conversation("assistant", result.get("output_text", ""), conversation, {"action": result.get("action")})
            return result

        if looks_like_opportunity(text):
            job = parse_job_from_message(message)
            record = self.workflow.prepare_opportunity(job)
            job_data = record["job"]
            evaluation = record.get("evaluation") or {}
            run = record.get("run") or {}
            result = {
                "action": "prepared_opportunity",
                "output_text": _prepared_summary(job_data, evaluation),
                "job_id": job_data["id"],
                "app_run_id": run.get("id", ""),
                "tool_calls": _tool_call_summary(record.get("tool_calls", [])),
                "state": self.repo.dashboard(),
            }
            self._remember_conversation(
                "assistant",
                result["output_text"],
                conversation,
                {"action": "prepared_opportunity", "job_id": job_data["id"]},
            )
            return result

        if self.hermes is None:
            result = {
                "action": "no_op",
                "output_text": (
                    "I can prepare pasted job descriptions, start a Hermes run for the latest role, "
                    "or show current state. Paste a fuller job description when you want me to evaluate it."
                ),
                "state": self.repo.dashboard(),
            }
            self._remember_conversation("assistant", result["output_text"], conversation, {"action": "no_op"})
            return result

        result = self.hermes.chat(
            message,
            instructions=build_chat_instructions(self.repo.dashboard(), self.toolbox.specs()),
            conversation=conversation,
            conversation_history=conversation_history,
            session_key=self.session_key,
        )
        if isinstance(result, dict):
            result.setdefault("action", "hermes_chat")
            result.setdefault("state", self.repo.dashboard())
            self._remember_conversation(
                "assistant",
                result.get("output_text") or extract_output_text(result),
                conversation,
                {"action": result.get("action")},
            )
        return result

    def stream(
        self,
        message: str,
        *,
        conversation: str = "jobapps-cockpit",
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        text = normalize_space(message)
        if not text:
            raise ValueError("Message is required.")
        self._remember_conversation("user", message, conversation)

        if _is_hermes_command(text):
            yield from self._stream_hermes_command(text, conversation=conversation)
            return

        if _is_start_run_intent(text):
            yield {"type": "status", "label": "run", "message": "Starting Hermes run"}
            result = self._start_latest_run(text)
            self._remember_conversation("assistant", result.get("output_text", ""), conversation, {"action": result.get("action")})
            yield {"type": "message.delta", "text": result.get("output_text", "")}
            yield {"type": "state", "state": result.get("state") or self.repo.dashboard()}
            yield {"type": "done", "result": result}
            return

        if looks_like_opportunity(text):
            yield {"type": "status", "label": "preflight", "message": "Preparing opportunity"}
            job = parse_job_from_message(message)
            record = self.workflow.prepare_opportunity(job)
            job_data = record["job"]
            evaluation = record.get("evaluation") or {}
            tool_calls = _tool_call_summary(record.get("tool_calls", []))
            for tool_call in tool_calls:
                yield {
                    "type": "tool",
                    "name": tool_call.get("name", ""),
                    "status": "completed" if tool_call.get("ok", True) else "failed",
                    "ok": tool_call.get("ok", True),
                }
            result = {
                "action": "prepared_opportunity",
                "output_text": _prepared_summary(job_data, evaluation),
                "job_id": job_data["id"],
                "app_run_id": (record.get("run") or {}).get("id", ""),
                "tool_calls": tool_calls,
                "state": self.repo.dashboard(),
            }
            self._remember_conversation(
                "assistant",
                result["output_text"],
                conversation,
                {"action": "prepared_opportunity", "job_id": job_data["id"]},
            )
            yield {"type": "message.delta", "text": result["output_text"]}
            yield {"type": "state", "state": result["state"]}
            yield {"type": "done", "result": result}
            return

        if self.hermes is None:
            result = {
                "action": "no_op",
                "output_text": (
                    "I can prepare pasted job descriptions, start a Hermes run for the latest role, "
                    "or show current state. Paste a fuller job description when you want me to evaluate it."
                ),
                "state": self.repo.dashboard(),
            }
            self._remember_conversation("assistant", result["output_text"], conversation, {"action": "no_op"})
            yield {"type": "message.delta", "text": result.get("output_text", "")}
            yield {"type": "state", "state": result.get("state") or self.repo.dashboard()}
            yield {"type": "done", "result": result}
            return

        yield {"type": "status", "label": "hermes", "message": "Connected to Hermes"}
        final_result: dict[str, Any] = {"action": "hermes_chat"}
        for raw in self.hermes.stream_chat(
            message,
            instructions=build_chat_instructions(self.repo.dashboard(), self.toolbox.specs()),
            conversation=conversation,
            conversation_history=conversation_history,
            session_key=self.session_key,
        ):
            yield from _map_hermes_sse_event(raw)
            if raw.get("event") == "response.completed" and isinstance(raw.get("data"), dict):
                response = raw["data"].get("response", raw["data"])
                if isinstance(response, dict):
                    final_result = dict(response)
                    final_result["action"] = "hermes_chat"
                    final_result.setdefault("output_text", extract_output_text(final_result))

        final_result.setdefault("state", self.repo.dashboard())
        self._remember_conversation(
            "assistant",
            final_result.get("output_text") or extract_output_text(final_result),
            conversation,
            {"action": final_result.get("action", "hermes_chat")},
        )
        yield {"type": "state", "state": final_result["state"]}
        yield {"type": "done", "result": final_result}

    def _remember_conversation(
        self,
        role: str,
        content: str,
        conversation: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not content:
            return
        try:
            personal_signal = _looks_like_personal_signal(content)
            self.repo.record_brain_event(
                "conversation_signal" if role == "user" and personal_signal else f"conversation_{role}",
                f"{role} message",
                str(content),
                entity_type="conversation",
                entity_name=conversation,
                source="chat",
                confidence=0.65 if role == "user" else 0.55,
                importance=0.68 if personal_signal else 0.34,
                metadata={"conversation": conversation, "role": role, **(metadata or {})},
            )
        except Exception:
            # Conversation capture should never block the cockpit.
            return

    def _run_hermes_command(self, text: str) -> dict[str, Any]:
        if self.slash is None:
            return {
                "action": "hermes_command_unavailable",
                "output_text": "Hermes slash commands are not available in this process.",
                "state": self.repo.dashboard(),
            }

        try:
            if _is_bare_model_command(text) and hasattr(self.slash, "model_options"):
                options = self.slash.model_options()
                return {
                    "action": "hermes_command_menu",
                    "output_text": _format_model_options(options),
                    "menu": {"type": "model_options", "options": options},
                    "state": self.repo.dashboard(),
                }
            output = self.slash.run(text)
        except HermesCommandError as exc:
            return {
                "action": "hermes_command_failed",
                "output_text": str(exc),
                "state": self.repo.dashboard(),
            }

        return {
            "action": "hermes_command",
            "output_text": output or f"Ran {text.split()[0]}.",
            "state": self.repo.dashboard(),
        }

    def _stream_hermes_command(self, text: str, *, conversation: str = "jobapps-cockpit") -> Iterator[dict[str, Any]]:
        yield {"type": "command", "command": text, "status": "running"}
        result = self._run_hermes_command(text)
        status = "failed" if str(result.get("action", "")).endswith("_failed") else "completed"
        yield {"type": "command", "command": text, "status": status}
        if result.get("menu"):
            yield {"type": "menu", "menu": result["menu"]}
        self._remember_conversation("assistant", result.get("output_text", ""), conversation, {"action": result.get("action")})
        yield {"type": "message.delta", "text": result.get("output_text", "")}
        yield {"type": "state", "state": result.get("state") or self.repo.dashboard()}
        yield {"type": "done", "result": result}

    def _start_latest_run(self, text: str) -> dict[str, Any]:
        if self.runs is None:
            return {
                "action": "run_unavailable",
                "output_text": "Hermes run manager is not available in this process.",
                "state": self.repo.dashboard(),
            }

        job_id = _extract_job_id(text) or _latest_job_id(self.repo.dashboard())
        if not job_id:
            return {
                "action": "missing_job",
                "output_text": "No prepared opportunity exists yet. Paste a job description first.",
                "state": self.repo.dashboard(),
            }

        record = self.runs.start_for_job(job_id)
        active_run = record.get("active_run") or {}
        hermes_run_id = active_run.get("hermes_run_id") or record.get("job", {}).get("hermes_run_id", "")
        hermes_session_id = active_run.get("hermes_session_id") or record.get("job", {}).get("hermes_session_id", "")
        return {
            "action": "started_hermes_run",
            "output_text": f"Started Hermes run for {record['job'].get('title', 'the role')} at {record['job'].get('company', 'the company')}.",
            "job_id": job_id,
            "run_id": hermes_run_id,
            "session_id": hermes_session_id,
            "app_run_id": active_run.get("id", ""),
            "state": self.repo.dashboard(),
        }


def parse_job_from_message(message: str) -> dict[str, Any]:
    """Extract a useful job payload from a pasted chat message.

    The parser is intentionally conservative. It supports common pasted shapes
    without pretending to be a crawler or a full extraction model.
    """

    raw_lines = [line.strip() for line in message.splitlines()]
    lines = [line for line in raw_lines if line]
    fields: dict[str, str] = {}
    description_lines: list[str] = []
    url = ""

    for line in lines:
        url_match = URL_RE.search(line)
        if url_match and not url:
            url = url_match.group(0).rstrip(").,]")
        field = FIELD_RE.match(line)
        if field:
            key = field.group(1).lower()
            if key in {"role", "position"}:
                key = "title"
            fields[key] = field.group(2).strip()
            continue
        if URL_RE.fullmatch(line):
            continue
        description_lines.append(line)

    if url and "url" not in fields:
        fields["url"] = url

    title = fields.get("title", "")
    company = fields.get("company", "")
    if (not title or not company) and lines:
        match = TITLE_AT_COMPANY_RE.match(lines[0])
        if match:
            title = title or match.group(1).strip()
            company = company or match.group(2).strip()
            if description_lines and description_lines[0] == lines[0]:
                description_lines = description_lines[1:]

    if not title:
        title = _guess_title(description_lines)
    if not company:
        company = "Unknown company"

    description = normalize_space("\n".join(description_lines))
    return {
        "title": title,
        "company": company,
        "location": fields.get("location", ""),
        "url": fields.get("url", ""),
        "description": description,
        "user_notes": "Prepared from chat message.",
    }


def looks_like_opportunity(message: str) -> bool:
    lowered = message.lower()
    has_role_header = bool(TITLE_AT_COMPANY_RE.match(message.split("\n", 1)[0].strip()))
    has_job_language = any(
        term in lowered
        for term in (
            "requirements",
            "responsibilities",
            "visa sponsorship",
            "sponsorship is available",
            "entry level",
            "engineer",
            "developer",
            "analyst",
            "intern",
        )
    )
    has_work_verbs = any(term in lowered for term in ("build", "develop", "design", "maintain", "work with"))
    return len(message.strip()) >= 140 and has_job_language and (has_role_header or has_work_verbs)


def _guess_title(lines: list[str]) -> str:
    for line in lines[:4]:
        cleaned = normalize_space(line)
        if 3 <= len(cleaned) <= 90 and any(term in cleaned.lower() for term in ("engineer", "developer", "analyst", "intern", "scientist")):
            return cleaned
    return "Untitled role"


def _is_start_run_intent(text: str) -> bool:
    lowered = text.lower()
    return "hermes" in lowered and "run" in lowered and any(term in lowered for term in ("start", "launch", "run", "research"))


def _is_hermes_command(text: str) -> bool:
    if not text.startswith("/"):
        return False
    command = text.split(maxsplit=1)[0]
    return "/" not in command[1:] and len(command) > 1


def _is_bare_model_command(text: str) -> bool:
    return text.strip().lower() == "/model"


def _looks_like_personal_signal(text: str) -> bool:
    normalized = text.lower()
    triggers = (
        "remember",
        "i prefer",
        "i like",
        "i don't like",
        "i hate",
        "i want",
        "i don't want",
        "my constraint",
        "my decision",
        "we decided",
        "don't say",
        "do not say",
        "sounds like me",
        "doesn't sound like me",
        "not my voice",
        "proof point",
        "networking",
        "follow up",
        "follow-up",
        "sponsorship",
        "opt",
        "h1b",
    )
    return any(trigger in normalized for trigger in triggers)


def _extract_job_id(text: str) -> str:
    match = re.search(r"\b[a-f0-9]{12}\b", text)
    return match.group(0) if match else ""


def _latest_job_id(state: dict[str, Any]) -> str:
    jobs = state.get("jobs") or []
    if not jobs:
        return ""
    return str(jobs[0].get("id") or "")


def _format_model_options(options: dict[str, Any]) -> str:
    current = options.get("model") or "unknown"
    provider = options.get("provider") or "unknown"
    lines = [f"Current model: {current}", f"Provider: {provider}", "", "Available providers:"]
    providers = options.get("providers")
    if isinstance(providers, list):
        for item in providers[:12]:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("slug") or "provider"
            slug = item.get("slug") or ""
            models = item.get("models") if isinstance(item.get("models"), list) else []
            model_count = item.get("total_models") or len(models)
            marker = "*" if item.get("is_current") else "-"
            if item.get("authenticated"):
                sample_parts = []
                for model in models[:3]:
                    if isinstance(model, dict):
                        sample_parts.append(str(model.get("id") or model.get("name") or "model"))
                    else:
                        sample_parts.append(str(model))
                sample = ", ".join(sample_parts)
                suffix = f"{model_count} models" if model_count else "configured"
                if sample:
                    suffix = f"{suffix}: {sample}"
            else:
                suffix = str(item.get("warning") or "not configured")
            lines.append(f"{marker} {name} ({slug}): {suffix}")
    lines.extend(["", "Switch with /model <provider>/<model> or /model <alias>."])
    return "\n".join(lines).strip()


def _map_hermes_sse_event(raw: dict[str, Any]) -> Iterator[dict[str, Any]]:
    event_name = str(raw.get("event") or "")
    data = raw.get("data")
    if not isinstance(data, dict):
        return

    if event_name == "response.output_text.delta":
        delta = data.get("delta")
        if isinstance(delta, str) and delta:
            yield {"type": "message.delta", "text": delta}
        return

    if event_name == "response.created":
        response = data.get("response") if isinstance(data.get("response"), dict) else {}
        yield {
            "type": "status",
            "label": "response",
            "message": response.get("status", "in_progress") or "in_progress",
            "response_id": response.get("id", ""),
        }
        return

    if event_name in {"response.output_item.added", "response.output_item.done"}:
        item = data.get("item") if isinstance(data.get("item"), dict) else {}
        item_type = item.get("type")
        if item_type == "function_call":
            status = item.get("status") or ("completed" if event_name.endswith(".done") else "running")
            yield {
                "type": "tool",
                "name": item.get("name", ""),
                "status": status,
                "call_id": item.get("call_id", ""),
                "arguments": item.get("arguments", ""),
            }
        elif item_type == "function_call_output":
            yield {
                "type": "tool",
                "name": item.get("call_id", "tool_result"),
                "status": item.get("status", "completed"),
                "call_id": item.get("call_id", ""),
                "output": _tool_output_preview(item.get("output")),
            }
        elif item_type == "reasoning":
            yield {"type": "reasoning", "text": _item_text(item)}
        return

    if "reasoning" in event_name:
        text = data.get("text") or data.get("delta") or data.get("summary")
        if isinstance(text, str) and text:
            yield {"type": "reasoning", "text": text}
        return

    if event_name == "response.failed":
        error = data.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        yield {"type": "error", "message": message or "Hermes response failed"}
        return

    if event_name == "response.completed":
        response = data.get("response") if isinstance(data.get("response"), dict) else data
        usage = response.get("usage") if isinstance(response, dict) else None
        yield {
            "type": "status",
            "label": "response",
            "message": response.get("status", "completed") if isinstance(response, dict) else "completed",
            "response_id": response.get("id", "") if isinstance(response, dict) else "",
        }
        if isinstance(usage, dict):
            yield {
                "type": "usage",
                "usage": _normalize_usage(usage),
                "response_id": response.get("id", "") if isinstance(response, dict) else "",
                "model": response.get("model", "") if isinstance(response, dict) else "",
            }


def _tool_output_preview(output: Any) -> str:
    if isinstance(output, str):
        return output[:500]
    if isinstance(output, list):
        chunks: list[str] = []
        for part in output:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content") or ""
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)[:500]
    if output is None:
        return ""
    return str(output)[:500]


def _item_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text") or part.get("content") or "")
            for part in content
            if isinstance(part, dict)
        ).strip()
    return str(item.get("text") or "")


def _normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    input_tokens = _int_usage(usage.get("input_tokens", usage.get("prompt_tokens")))
    output_tokens = _int_usage(usage.get("output_tokens", usage.get("completion_tokens")))
    total_tokens = _int_usage(usage.get("total_tokens"))
    if not total_tokens:
        total_tokens = input_tokens + output_tokens
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
        "cache_read": _int_usage(usage.get("cache_read_tokens") or usage.get("cache_read")),
        "cache_write": _int_usage(usage.get("cache_write_tokens") or usage.get("cache_write")),
        "reasoning": _int_usage(usage.get("reasoning_tokens") or usage.get("reasoning")),
        "raw": usage,
    }


def _int_usage(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _prepared_summary(job: dict[str, Any], evaluation: dict[str, Any]) -> str:
    title = job.get("title") or "Untitled role"
    company = job.get("company") or "Unknown company"
    decision = evaluation.get("decision") or job.get("decision") or "review"
    score = evaluation.get("score_0_to_5") or job.get("score")
    next_action = evaluation.get("next_action") or job.get("next_action") or "Review the generated material."
    score_text = f" Score: {score:.2f}/5." if isinstance(score, (int, float)) else ""
    return f"Prepared {title} at {company}. Decision: {decision}.{score_text} Next: {next_action}"


def _tool_call_summary(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for call in tool_calls:
        output.append(
            {
                "name": call.get("tool_name") or call.get("name") or "tool",
                "status": "ok" if call.get("status") == "completed" else call.get("status", "ok"),
            }
        )
    return output
