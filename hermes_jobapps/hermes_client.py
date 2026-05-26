"""Small stdlib client for Hermes API Server."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any


class HermesAPIError(RuntimeError):
    pass


class HermesClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("HERMES_API_BASE") or "http://127.0.0.1:8642/v1").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("HERMES_API_KEY", "")
        self.model = model or os.environ.get("HERMES_API_MODEL", "hermes-agent")
        self.timeout = timeout

    def configured(self) -> bool:
        return bool(self.base_url)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/capabilities")

    def start_run(
        self,
        prompt: str,
        *,
        instructions: str = "",
        session_id: str = "",
        session_key: str = "jobapps",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }
        if instructions:
            payload["instructions"] = instructions
        if session_id:
            payload["session_id"] = session_id
        headers = {"X-Hermes-Session-Key": session_key}
        return self._request("POST", "/runs", payload, headers=headers, expected=(200, 202))

    def get_run(self, run_id: str) -> dict[str, Any]:
        quoted = urllib.parse.quote(run_id, safe="")
        return self._request("GET", f"/runs/{quoted}")

    def get_run_events(self, run_id: str) -> dict[str, Any]:
        quoted = urllib.parse.quote(run_id, safe="")
        return self._request("GET", f"/runs/{quoted}/events")

    def chat(
        self,
        message: str,
        *,
        instructions: str = "",
        conversation: str = "jobapps-cockpit",
        conversation_history: list[dict[str, Any]] | None = None,
        session_key: str = "jobapps",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": message,
            "conversation": conversation,
            "store": True,
        }
        if instructions:
            payload["instructions"] = instructions
        if conversation_history:
            payload["conversation_history"] = conversation_history
        result = self._request("POST", "/responses", payload, headers={"X-Hermes-Session-Key": session_key})
        result.setdefault("output_text", _extract_output_text(result))
        result.setdefault("run_id", result.get("id", ""))
        result.setdefault("session_id", result.get("session_id") or result.get("conversation") or "")
        return result

    def stream_chat(
        self,
        message: str,
        *,
        instructions: str = "",
        conversation: str = "jobapps-cockpit",
        conversation_history: list[dict[str, Any]] | None = None,
        session_key: str = "jobapps",
    ) -> Iterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": message,
            "conversation": conversation,
            "store": True,
            "stream": True,
        }
        if instructions:
            payload["instructions"] = instructions
        if conversation_history:
            payload["conversation_history"] = conversation_history
        yield from self._request_sse(
            "POST",
            "/responses",
            payload,
            headers={"X-Hermes-Session-Key": session_key},
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {
            "Content-Type": "application/json",
            **(headers or {}),
        }
        if self.api_key:
            request_headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = response.read().decode("utf-8")
                if response.status not in expected:
                    raise HermesAPIError(f"Hermes returned HTTP {response.status}: {data}")
                return json.loads(data or "{}")
        except urllib.error.HTTPError as exc:
            data = exc.read().decode("utf-8", errors="replace")
            raise HermesAPIError(f"Hermes returned HTTP {exc.code}: {data}") from exc
        except urllib.error.URLError as exc:
            raise HermesAPIError(f"Hermes API server unavailable at {url}: {exc.reason}") from exc

    def _request_sse(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        url = f"{self.base_url}{path}"
        request_headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            **(headers or {}),
        }
        if self.api_key:
            request_headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=max(self.timeout, 300.0)) as response:
                event_type = "message"
                data_lines: list[str] = []
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        if data_lines:
                            data = "\n".join(data_lines)
                            if data == "[DONE]":
                                yield {"event": event_type, "data": {"done": True}}
                            else:
                                try:
                                    parsed: Any = json.loads(data)
                                except json.JSONDecodeError:
                                    parsed = data
                                yield {"event": event_type, "data": parsed}
                        event_type = "message"
                        data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip() or "message"
                    elif line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].lstrip())
                if data_lines:
                    data = "\n".join(data_lines)
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        parsed = data
                    yield {"event": event_type, "data": parsed}
        except urllib.error.HTTPError as exc:
            data = exc.read().decode("utf-8", errors="replace")
            raise HermesAPIError(f"Hermes returned HTTP {exc.code}: {data}") from exc
        except urllib.error.URLError as exc:
            raise HermesAPIError(f"Hermes API server unavailable at {url}: {exc.reason}") from exc


def extract_output_text(result: dict[str, Any]) -> str:
    if isinstance(result.get("output_text"), str):
        return result["output_text"]
    if isinstance(result.get("output"), str):
        return result["output"]
    output = result.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str):
                    chunks.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            chunks.append(part["text"])
        if chunks:
            return "\n".join(chunks)
    message = result.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        content = choices[0].get("message", {}).get("content") if isinstance(choices[0], dict) else None
        if isinstance(content, str):
            return content
    return ""


_extract_output_text = extract_output_text
