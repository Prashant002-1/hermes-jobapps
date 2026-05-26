"""Native Hermes slash-command bridge for the JobApps cockpit."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class HermesCommandError(RuntimeError):
    pass


class HermesSlashClient:
    """Execute native Hermes slash commands under the configured profile.

    Hermes slash commands live in the TUI gateway, not the OpenAI-compatible
    API server. The slash worker is the narrowest native bridge: plugin
    commands, skill commands, and built-in commands all go through the same
    command registry Hermes uses in its own chat surfaces.
    """

    def __init__(
        self,
        *,
        profile: str = "jobapps",
        model: str = "",
        timeout: float = 45.0,
        python_path: str = "",
    ) -> None:
        self.profile = profile or "jobapps"
        self.model = model
        self.timeout = timeout
        self.python_path = python_path or _default_hermes_python()

    def run(self, command: str) -> str:
        cleaned = command.strip()
        if not cleaned.startswith("/"):
            raise HermesCommandError("Hermes commands must start with '/'.")

        payload = json.dumps({"id": 1, "command": cleaned}) + "\n"
        argv = [
            self.python_path,
            "-m",
            "tui_gateway.slash_worker",
            "--session-key",
            "jobapps",
        ]
        if self.model:
            argv.extend(["--model", self.model])

        env = os.environ.copy()
        env["HERMES_HOME"] = str(_profile_home(self.profile))
        env.setdefault("HERMES_ENABLE_PROJECT_PLUGINS", "true")

        try:
            proc = subprocess.run(
                argv,
                input=payload,
                text=True,
                capture_output=True,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HermesCommandError(f"Hermes command timed out after {self.timeout:.0f}s.") from exc
        except OSError as exc:
            raise HermesCommandError(f"Could not start Hermes slash worker: {exc}") from exc

        if proc.returncode not in {0, None} and not proc.stdout.strip():
            detail = proc.stderr.strip() or f"exit code {proc.returncode}"
            raise HermesCommandError(f"Hermes command failed: {detail}")

        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                message: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") != 1:
                continue
            if not message.get("ok"):
                raise HermesCommandError(str(message.get("error") or "Hermes command failed."))
            return _clean_output(str(message.get("output") or ""))

        detail = proc.stderr.strip() or "No command response returned."
        raise HermesCommandError(f"Hermes command failed: {detail}")

    def catalog(self) -> dict[str, Any]:
        """Return the native Hermes command/skill catalog for command menus."""

        result = self._dispatch_tui_gateway("commands.catalog", {})
        if "error" in result:
            error = result.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise HermesCommandError(message or "Hermes command catalog failed.")
        catalog = result.get("result")
        if not isinstance(catalog, dict):
            raise HermesCommandError("Hermes command catalog returned an invalid response.")
        return catalog

    def model_options(self) -> dict[str, Any]:
        """Return the native Hermes model picker data used by the TUI."""

        result = self._dispatch_tui_gateway("model.options", {"session_id": "jobapps"})
        if "error" in result:
            error = result.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise HermesCommandError(message or "Hermes model options failed.")
        options = result.get("result")
        if not isinstance(options, dict):
            raise HermesCommandError("Hermes model options returned an invalid response.")
        return options

    def complete_slash(self, text: str) -> dict[str, Any]:
        """Return native Hermes slash completions for the current typed text."""

        result = self._dispatch_tui_gateway("complete.slash", {"text": text})
        if "error" in result:
            error = result.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise HermesCommandError(message or "Hermes slash completion failed.")
        completions = result.get("result")
        if not isinstance(completions, dict):
            raise HermesCommandError("Hermes slash completion returned an invalid response.")
        return completions

    def sessions(self, *, limit: int = 100) -> dict[str, Any]:
        """Return native Hermes sessions from the TUI session store."""

        result = self._dispatch_tui_gateway("session.list", {"limit": limit})
        if "error" in result:
            error = result.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise HermesCommandError(message or "Hermes session list failed.")
        sessions = result.get("result")
        if not isinstance(sessions, dict):
            raise HermesCommandError("Hermes session list returned an invalid response.")
        return sessions

    def resume_session(self, session_id: str) -> dict[str, Any]:
        """Hydrate a native Hermes session so the cockpit can continue it."""

        target = session_id.strip()
        if not target:
            raise HermesCommandError("session_id is required.")
        result = self._dispatch_tui_gateway("session.resume", {"session_id": target})
        if "error" in result:
            error = result.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise HermesCommandError(message or "Hermes session resume failed.")
        resumed = result.get("result")
        if not isinstance(resumed, dict):
            raise HermesCommandError("Hermes session resume returned an invalid response.")
        return resumed

    def _dispatch_tui_gateway(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        script = (
            "import json, sys\n"
            "from tui_gateway.server import dispatch\n"
            "req = json.loads(sys.stdin.read() or '{}')\n"
            "result = dispatch(req)\n"
            "print(json.dumps(result or {}))\n"
        )
        env = os.environ.copy()
        env["HERMES_HOME"] = str(_profile_home(self.profile))
        env.setdefault("HERMES_ENABLE_PROJECT_PLUGINS", "true")
        try:
            proc = subprocess.run(
                [self.python_path, "-c", script],
                input=json.dumps(request),
                text=True,
                capture_output=True,
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HermesCommandError(f"Hermes command catalog timed out after {self.timeout:.0f}s.") from exc
        except OSError as exc:
            raise HermesCommandError(f"Could not start Hermes command catalog: {exc}") from exc

        if proc.returncode not in {0, None}:
            detail = proc.stderr.strip() or f"exit code {proc.returncode}"
            raise HermesCommandError(f"Hermes command catalog failed: {detail}")
        for output in (proc.stdout, proc.stderr):
            for line in reversed(output.splitlines()):
                if not line.strip():
                    continue
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise HermesCommandError("Hermes command catalog returned invalid JSON.")


def _default_hermes_python() -> str:
    configured = os.environ.get("HERMES_SLASH_WORKER_PYTHON", "")
    if configured:
        return configured

    bundled = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"
    if bundled.exists():
        return str(bundled)

    return shutil.which("python3") or sys.executable


def _profile_home(profile: str) -> Path:
    if profile in {"", "default"}:
        return Path.home() / ".hermes"
    return Path.home() / ".hermes" / "profiles" / profile


def _clean_output(value: str) -> str:
    return ANSI_RE.sub("", value).strip()
