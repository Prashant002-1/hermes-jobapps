"""Local cockpit host.

Serves the browser UI from dashboard/dist and the cockpit API from
`api.handle`. It binds to 127.0.0.1 only and refuses requests that were not
addressed to this computer.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from . import api
from .workspace import Workspace, clip


DIST = Path(__file__).resolve().parents[1] / "dashboard" / "dist"
MAX_BODY_BYTES = 2 * 1024 * 1024
DRAIN_LIMIT_BYTES = 16 * 1024 * 1024
GZIP_MIN_BYTES = 1024

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}
_LONG_CACHED = {".woff2"}
_COMPRESSIBLE = {".html", ".js", ".css", ".json", ".svg"}
_TEXT_SUFFIXES = {".md", ".typ", ".tex", ".txt", ".json"}
_FILE_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_LOCAL = r"(?:127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?"
_LOCAL_HOST = re.compile(_LOCAL, re.IGNORECASE)
_LOCAL_ORIGIN = re.compile(rf"https?://{_LOCAL}", re.IGNORECASE)


def file_content_type(path: Path) -> str:
    """Content type for a workspace file. Source text is always sent as plain text."""
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return "text/plain; charset=utf-8"
    return _FILE_TYPES.get(suffix, "application/octet-stream")


def _accepts_gzip(header: str) -> bool:
    for part in header.split(","):
        name, _, params = part.strip().partition(";")
        if name.strip().lower() not in ("gzip", "x-gzip", "*"):
            continue
        quality = params.replace(" ", "").lower()
        if quality.startswith("q="):
            try:
                return float(quality[2:]) > 0
            except ValueError:
                return False
        return True
    return False


def create_handler(ws: Workspace) -> type[BaseHTTPRequestHandler]:
    write_lock = threading.Lock()

    class CockpitHandler(BaseHTTPRequestHandler):
        server_version = "JobApps"
        sys_version = ""
        protocol_version = "HTTP/1.1"
        timeout = 30

        def version_string(self) -> str:
            return self.server_version

        def log_message(self, format: str, *args: Any) -> None:
            if os.environ.get("JOBAPPS_DEBUG"):
                super().log_message(format, *args)

        def do_GET(self) -> None:
            self._dispatch()

        do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_GET

        # -- request ---------------------------------------------------------

        def _dispatch(self) -> None:
            self._started = False
            try:
                self._respond()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
            except Exception as exc:  # one bad request must never stop the server
                if os.environ.get("JOBAPPS_DEBUG"):
                    traceback.print_exc()
                self.close_connection = True
                if not self._started:
                    message = clip(f"{type(exc).__name__}: {exc}", 200)
                    try:
                        self._json(500, {"error": f"The cockpit hit an internal error. {message}"})
                    except OSError:
                        pass

        def _respond(self) -> None:
            method = self.command
            length = self._content_length()
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            query = dict(parse_qsl(parts.query, keep_blank_values=True))

            if not _LOCAL_HOST.fullmatch(self.headers.get("Host", "").strip()):
                return self._reject(403, "This cockpit only answers requests addressed to this computer.", length)
            if method == "POST":
                return self._post(path, query, length)
            if method not in ("GET", "HEAD"):
                return self._reject(405, "Use GET or POST.", length)
            if length is None:
                self.close_connection = True
            elif length:
                self._drain(length)
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/") :])
            if path.startswith("/api/"):
                return self._api("GET", path[len("/api") :], query, None)
            return self._json(404, {"error": f"Not found: {clip(path, 120)}"})

        def _post(self, path: str, query: dict[str, str], length: int | None) -> None:
            origin = self.headers.get("Origin")
            if origin is not None and not _LOCAL_ORIGIN.fullmatch(origin.strip()):
                return self._reject(403, "Requests from other sites are not accepted.", length)
            if not path.startswith("/api/"):
                return self._reject(404, f"Not found: {clip(path, 120)}", length)
            content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type != "application/json":
                return self._reject(415, "Send the request body as application/json.", length)
            if length is None:
                return self._reject(400, "The request needs a valid Content-Length.", 0, close=True)
            if length > MAX_BODY_BYTES:
                return self._reject(413, "The request body is larger than 2 MiB.", length)
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except ValueError:
                return self._json(400, {"error": "The request body is not valid JSON."})
            if not isinstance(body, dict):
                return self._json(400, {"error": "The request body must be a JSON object."})
            self._api("POST", path[len("/api") :], query, body)

        def _content_length(self) -> int | None:
            if self.headers.get("Transfer-Encoding"):
                return None
            raw = self.headers.get("Content-Length")
            if raw is None:
                return 0
            return int(raw) if raw.strip().isdigit() else None

        def _drain(self, length: int) -> None:
            """Read and discard a request body so the reply is not lost to a reset."""
            remaining = min(length, DRAIN_LIMIT_BYTES)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            if length > DRAIN_LIMIT_BYTES:
                self.close_connection = True

        def _reject(self, status: int, message: str, length: int | None, *, close: bool = False) -> None:
            if length is None or close:
                self.close_connection = True
            elif length:
                self._drain(length)
            self._json(status, {"error": message})

        # -- responses -------------------------------------------------------

        def _api(self, method: str, route: str, query: dict[str, str], body: dict[str, Any] | None) -> None:
            if method == "POST":
                with write_lock:
                    status, payload = api.handle(ws, method, route, query, body)
            else:
                status, payload = api.handle(ws, method, route, query, body)
            if isinstance(payload, api.FileResult):
                return self._file(payload.path)
            self._json(status, payload)

        def _send(self, status: int, body: bytes, headers: list[tuple[str, str]]) -> None:
            self._started = True
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _compressed(self, body: bytes, headers: list[tuple[str, str]]) -> bytes:
            headers.append(("Vary", "Accept-Encoding"))
            if len(body) > GZIP_MIN_BYTES and _accepts_gzip(self.headers.get("Accept-Encoding", "")):
                headers.append(("Content-Encoding", "gzip"))
                return gzip.compress(body, compresslevel=6, mtime=0)
            return body

        def _json(self, status: int, payload: Any) -> None:
            headers = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")]
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
            self._send(status, self._compressed(body, headers), headers)

        def _static(self, name: str) -> None:
            root = DIST.resolve()
            try:
                target = (root / name).resolve()
                target.relative_to(root)
            except (OSError, ValueError):
                target = None
            content_type = STATIC_TYPES.get(target.suffix.lower()) if target else None
            if (
                target is None
                or content_type is None
                or not target.is_file()
                or any(part.startswith(".") for part in target.relative_to(root).parts)
            ):
                return self._json(404, {"error": f"Not found: {clip(name, 120)}"})
            cache = "public, max-age=31536000, immutable" if target.suffix.lower() in _LONG_CACHED else "no-cache"
            headers = [("Content-Type", content_type), ("Cache-Control", cache)]
            body = target.read_bytes()
            if target.suffix.lower() in _COMPRESSIBLE:
                body = self._compressed(body, headers)
            self._send(200, body, headers)

        def _file(self, path: Path) -> None:
            with path.open("rb") as stream:
                remaining = os.fstat(stream.fileno()).st_size
                self._started = True
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type", file_content_type(path))
                self.send_header("Content-Length", str(remaining))
                self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(path.name, safe='')}")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while remaining > 0 and self.command != "HEAD":
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    return CockpitHandler


def serve(ws: Workspace, *, port: int = 8765, open_browser: bool = True) -> None:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), create_handler(ws))
    except OSError as exc:
        raise ValueError(
            f"Could not start the cockpit on port {port}: {exc.strerror or exc}. Pick another port with --port."
        ) from exc
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"JobApps cockpit: {url}", flush=True)
    print(f"Workspace: {ws.root}  (Ctrl-C to stop)", flush=True)
    if open_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hermes_jobapps.server", description="Local JobApps cockpit.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace", help="Workspace folder. Default: JOBAPPS_HOME or ~/JobApps.")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser window.")
    args = parser.parse_args(argv)
    try:
        serve(Workspace(args.workspace) if args.workspace else Workspace(), port=args.port, open_browser=not args.no_open)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
