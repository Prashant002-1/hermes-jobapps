from __future__ import annotations

import contextlib
import gzip
import http.client
import importlib.util
import inspect
import io
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from hermes_jobapps import api, server
from hermes_jobapps.server import MAX_BODY_BYTES, create_handler
from hermes_jobapps.workspace import Workspace


REPO = Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard"
DIST = DASHBOARD / "dist"
JSON_HEADERS = {"Content-Type": "application/json"}
PDF_BYTES = b"%PDF-1.4\n% invented sample\n" + bytes(range(256)) * 8
ODD_NAME = "Jordan Example \u2013 R\u00e9sum\u00e9.pdf"


def seed(root: Path) -> tuple[Workspace, str]:
    ws = Workspace(root)
    ws.init(name="Jordan Example")
    posting = "Northstar is hiring a product designer to shape the planning tools.\n" * 8
    job_id = ws.create_job(company="Northstar", title="Product Designer", posting=posting)["id"]
    for index in range(6):
        ws.create_job(company=f"Fieldwork {index}", title="Design Engineer", status="applied", posting=posting)
    folder = ws.job_dir(job_id)
    (folder / "resume.typ").write_text("= Jordan Example\n<script>alert(1)</script>\n", encoding="utf-8")
    (folder / "resume.pdf").write_bytes(PDF_BYTES)
    (folder / ODD_NAME).write_bytes(PDF_BYTES)
    return ws, job_id


class ServerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws, self.job = seed(Path(self.tmp.name) / "ws")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.ws))
        self.port = self.httpd.server_address[1]
        thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def send(self, conn: http.client.HTTPConnection, method: str, path: str, *, body=None, headers=None, host=...):
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        if host is ...:
            host = f"127.0.0.1:{self.port}"
        if host is not None:
            conn.putheader("Host", host)
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            conn.putheader("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        conn.endheaders(data)
        response = conn.getresponse()
        return response.status, response, response.read()

    def request(self, method: str, path: str, **kwargs):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            return self.send(conn, method, path, **kwargs)
        finally:
            conn.close()

    def get_json(self, path: str, **kwargs):
        status, response, raw = self.request("GET", path, **kwargs)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        return status, json.loads(raw)

    def post_json(self, path: str, body, **kwargs):
        kwargs.setdefault("headers", JSON_HEADERS)
        status, response, raw = self.request("POST", path, body=body, **kwargs)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        return status, json.loads(raw)

    def stage(self) -> str:
        return str(self.ws.job_doc(self.job).meta["status"])


class StaticTests(ServerCase):
    def test_index_is_served_at_both_paths(self) -> None:
        for path in ("/", "/index.html", "/?from=bookmark"):
            status, response, raw = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertEqual(response.getheader("Content-Type"), "text/html; charset=utf-8")
            self.assertEqual(response.getheader("Cache-Control"), "no-cache")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertEqual(raw, (DIST / "index.html").read_bytes())
        self.assertIn(b'id="jobapps-root"', raw)
        self.assertIn(b"/static/index.js", raw)
        self.assertIn(b"/static/style.css", raw)

    def test_static_files_have_content_types(self) -> None:
        for name, content_type in (("index.js", "text/javascript; charset=utf-8"), ("style.css", "text/css; charset=utf-8")):
            status, response, raw = self.request("GET", f"/static/{name}")
            self.assertEqual(status, 200, name)
            self.assertEqual(response.getheader("Content-Type"), content_type)
            self.assertEqual(response.getheader("Cache-Control"), "no-cache")
            self.assertIsNone(response.getheader("Content-Encoding"))
            self.assertEqual(raw, (DIST / name).read_bytes())

    def test_fonts_in_a_subfolder_are_served_with_a_long_cache(self) -> None:
        font = DIST / "fonts" / "hanken-grotesk-latin.woff2"
        status, response, raw = self.request("GET", "/static/fonts/hanken-grotesk-latin.woff2", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(status, 200)
        self.assertEqual(response.getheader("Content-Type"), "font/woff2")
        self.assertEqual(response.getheader("Cache-Control"), "public, max-age=31536000, immutable")
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertIsNone(response.getheader("Content-Encoding"))
        self.assertEqual(raw, font.read_bytes())

    def test_subfolders_cannot_be_used_to_leave_dist(self) -> None:
        attempts = (
            "/static/fonts/../../manifest.json",
            "/static/fonts/..%2f..%2fplugin_api.py",
            "/static/fonts/%2e%2e/%2e%2e/manifest.json",
            "/static/fonts/../../../hermes_jobapps/server.py",
            "/static/fonts/",
            "/static/fonts",
            "/static/fonts/OFL.txt",
            "/static/fonts/missing.woff2",
            "/static/fonts/.hidden.woff2",
        )
        for path in attempts:
            status, payload = self.get_json(path)
            self.assertEqual(status, 404, path)
            self.assertIn("error", payload)
        self.assertEqual(self.request("GET", "/static/fonts/../index.js")[0], 200, "a path that stays inside dist is fine")

    def test_static_is_gzipped_on_request(self) -> None:
        status, response, raw = self.request("GET", "/static/index.js", headers={"Accept-Encoding": "gzip, deflate"})
        self.assertEqual(status, 200)
        self.assertEqual(response.getheader("Content-Encoding"), "gzip")
        self.assertEqual(response.getheader("Vary"), "Accept-Encoding")
        self.assertEqual(gzip.decompress(raw), (DIST / "index.js").read_bytes())

    def test_static_traversal_and_unknown_files_are_404(self) -> None:
        attempts = (
            "/static/../manifest.json",
            "/static/../plugin_api.py",
            "/static/%2e%2e/manifest.json",
            "/static/..%2f..%2fhermes_jobapps%2fserver.py",
            "/static/%2e%2e%2f%2e%2e%2fREADME.md",
            "/static//etc/hosts",
            "/static/index.js%00.css",
            "/static/nope.js",
            "/static/",
            "/static",
        )
        for path in attempts:
            status, payload = self.get_json(path)
            self.assertEqual(status, 404, path)
            self.assertIn("error", payload)

    def test_head_sends_headers_only(self) -> None:
        status, response, raw = self.request("HEAD", "/static/style.css")
        self.assertEqual(status, 200)
        self.assertEqual(int(response.getheader("Content-Length")), (DIST / "style.css").stat().st_size)
        self.assertEqual(raw, b"")


class ApiTests(ServerCase):
    def test_get_is_compact_json(self) -> None:
        status, response, raw = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertIsNone(response.getheader("Content-Encoding"))
        payload = json.loads(raw)
        self.assertEqual(payload["counts"]["total"], 7)
        self.assertEqual(raw, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def test_post_round_trip(self) -> None:
        status, result = self.post_json(f"/api/jobs/{self.job}/track", {"status": "applied", "note": "Sent it."})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(self.stage(), "applied")
        status, detail = self.get_json(f"/api/jobs/{self.job}")
        self.assertEqual((status, detail["job"]["stage"]), (200, "applied"))
        self.assertIn("Sent it.", detail["sections"]["log"])

    def test_query_and_encoded_paths_reach_the_api(self) -> None:
        status, doc = self.get_json("/api/doc?path=profile%2Fprofile.md")
        self.assertEqual((status, doc["meta"]["name"]), (200, "Jordan Example"))
        status, payload = self.get_json("/api/doc?path=..%2F..%2Fetc%2Fhosts")
        self.assertEqual(status, 400)
        status, payload = self.post_json(f"/api/jobs/{quote(self.job)}/notes", {"text": "Ask about the team."})
        self.assertEqual((status, payload), (200, {"ok": True}))

    def test_charset_on_the_content_type_is_accepted(self) -> None:
        headers = {"Content-Type": "Application/JSON; charset=utf-8"}
        status, result = self.post_json(f"/api/jobs/{self.job}/track", {"note": "Caf\u00e9 chat."}, headers=headers)
        self.assertEqual((status, result["ok"]), (200, True))

    def test_gzip_when_accepted_and_large(self) -> None:
        plain = self.request("GET", "/api/state")[2]
        self.assertGreater(len(plain), 1024)
        status, response, raw = self.request("GET", "/api/state", headers={"Accept-Encoding": "br, gzip"})
        self.assertEqual(status, 200)
        self.assertEqual(response.getheader("Content-Encoding"), "gzip")
        self.assertEqual(response.getheader("Vary"), "Accept-Encoding")
        self.assertEqual(int(response.getheader("Content-Length")), len(raw))
        self.assertLess(len(raw), len(plain))
        self.assertEqual(json.loads(gzip.decompress(raw))["counts"]["total"], 7)

    def test_no_gzip_when_small_or_refused(self) -> None:
        status, response, raw = self.request("GET", "/api/nope", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(status, 404)
        self.assertIsNone(response.getheader("Content-Encoding"))
        self.assertEqual(json.loads(raw), {"error": "Unknown route: /nope"})
        for value in ("identity", "gzip;q=0", "deflate"):
            response = self.request("GET", "/api/state", headers={"Accept-Encoding": value})[1]
            self.assertIsNone(response.getheader("Content-Encoding"), value)

    def test_unknown_paths_are_json_404(self) -> None:
        for path in ("/nope", "/api", "/api/nope", "/favicon.ico", "/web/app.js"):
            status, payload = self.get_json(path)
            self.assertEqual(status, 404, path)
            self.assertIn("error", payload)
        self.assertEqual(self.post_json("/nope", {})[0], 404)
        self.assertEqual(self.post_json("/api/nope", {})[0], 404)

    def test_other_methods_are_405(self) -> None:
        for method in ("PUT", "DELETE", "PATCH", "OPTIONS"):
            status, response, raw = self.request(method, f"/api/jobs/{self.job}/track", body={"status": "applied"}, headers=JSON_HEADERS)
            self.assertEqual(status, 405, method)
            self.assertIn("error", json.loads(raw))
        self.assertEqual(self.stage(), "new")

    def test_keep_alive_survives_a_rejected_post(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        self.assertEqual(self.send(conn, "GET", "/api/state")[0], 200)
        self.assertEqual(self.send(conn, "POST", "/api/people", body=b"name=x", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.send(conn, "POST", f"/api/jobs/{self.job}/track", body={"note": "Still here."}, headers=JSON_HEADERS)[0], 200)
        self.assertEqual(self.send(conn, "GET", "/")[0], 200)


class HardeningTests(ServerCase):
    def test_foreign_host_is_403(self) -> None:
        for host in ("evil.example", "127.0.0.1.evil.example", f"localhost.evil.example:{self.port}", "10.0.0.5:8765", "", None):
            status, payload = self.get_json("/api/state", host=host)
            self.assertEqual(status, 403, host)
            self.assertIn("error", payload)
            self.assertEqual(self.request("GET", "/", host=host)[0], 403, host)
            status, payload = self.post_json(f"/api/jobs/{self.job}/track", {"status": "applied"}, host=host)
            self.assertEqual(status, 403, host)
        self.assertEqual(self.stage(), "new")

    def test_local_hosts_are_accepted(self) -> None:
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}", f"[::1]:{self.port}", "127.0.0.1", "LOCALHOST", "[::1]"):
            self.assertEqual(self.get_json("/api/state", host=host)[0], 200, host)

    def test_foreign_origin_is_403_on_post(self) -> None:
        for origin in ("https://evil.example", "http://127.0.0.1.evil.example", "http://localhost.evil.example:8765", "null", "file://"):
            headers = {**JSON_HEADERS, "Origin": origin}
            status, payload = self.post_json(f"/api/jobs/{self.job}/track", {"status": "applied"}, headers=headers)
            self.assertEqual(status, 403, origin)
            self.assertIn("error", payload)
        self.assertEqual(self.stage(), "new")

    def test_local_origin_is_accepted(self) -> None:
        for origin in (f"http://127.0.0.1:{self.port}", "http://localhost:3000", "http://[::1]:8765", "https://localhost"):
            headers = {**JSON_HEADERS, "Origin": origin}
            status, result = self.post_json(f"/api/jobs/{self.job}/track", {"note": f"From {origin}"}, headers=headers)
            self.assertEqual((status, result["ok"]), (200, True), origin)

    def test_wrong_content_type_is_415(self) -> None:
        body = json.dumps({"status": "applied"}).encode("utf-8")
        for content_type in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data", "application/jsonx", None):
            headers = {"Content-Type": content_type} if content_type else {}
            status, response, raw = self.request("POST", f"/api/jobs/{self.job}/track", body=body, headers=headers)
            self.assertEqual(status, 415, content_type)
            self.assertIn("application/json", json.loads(raw)["error"])
        self.assertEqual(self.stage(), "new")

    def test_oversized_body_is_413(self) -> None:
        body = b'{"note":"' + b"a" * (MAX_BODY_BYTES - 10) + b'"}'
        self.assertEqual(len(body), MAX_BODY_BYTES + 1)
        status, payload = self.post_json(f"/api/jobs/{self.job}/track", body)
        self.assertEqual(status, 413)
        self.assertIn("2 MiB", payload["error"])
        self.assertEqual(self.get_json("/api/state")[0], 200)

    def test_body_at_the_limit_is_read(self) -> None:
        body = b'{"text":"' + b"a" * (MAX_BODY_BYTES - 11) + b'"}'
        self.assertEqual(len(body), MAX_BODY_BYTES)
        status, payload = self.post_json(f"/api/jobs/{self.job}/notes", body)
        self.assertEqual((status, payload), (200, {"ok": True}))

    def test_bad_json_is_400(self) -> None:
        for body in (b"{not json", b"", b"[1, 2]", b'"text"', b"null", b"\xff\xfe"):
            status, payload = self.post_json(f"/api/jobs/{self.job}/track", body)
            self.assertEqual(status, 400, body)
            self.assertIn("error", payload)
        self.assertEqual(self.stage(), "new")

    def test_bad_content_length_is_400(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        conn.putrequest("POST", f"/api/jobs/{self.job}/track", skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"127.0.0.1:{self.port}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "-5")
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        self.assertIn("Content-Length", json.loads(response.read())["error"])

    def test_requests_are_not_logged_unless_debugging(self) -> None:
        with mock.patch.dict(os.environ), mock.patch.object(sys, "stderr", io.StringIO()) as quiet:
            os.environ.pop("JOBAPPS_DEBUG", None)
            self.get_json("/api/state")
            self.get_json("/api/nope")
        self.assertEqual(quiet.getvalue(), "")
        with mock.patch.dict(os.environ, {"JOBAPPS_DEBUG": "1"}), mock.patch.object(sys, "stderr", io.StringIO()) as loud:
            self.get_json("/api/state")
        self.assertIn("/api/state", loud.getvalue())


class FileTests(ServerCase):
    def test_pdf_is_streamed_inline(self) -> None:
        status, response, raw = self.request("GET", f"/api/file?path=jobs/{self.job}/resume.pdf", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/pdf")
        self.assertEqual(response.getheader("Content-Disposition"), "inline; filename*=UTF-8''resume.pdf")
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(int(response.getheader("Content-Length")), len(PDF_BYTES))
        self.assertIsNone(response.getheader("Content-Encoding"))
        self.assertEqual(raw, PDF_BYTES)

    def test_file_name_is_percent_encoded(self) -> None:
        path = quote(f"jobs/{self.job}/{ODD_NAME}", safe="")
        status, response, raw = self.request("GET", f"/api/file?path={path}")
        self.assertEqual(status, 200)
        self.assertEqual(
            response.getheader("Content-Disposition"),
            "inline; filename*=UTF-8''Jordan%20Example%20%E2%80%93%20R%C3%A9sum%C3%A9.pdf",
        )
        self.assertEqual(raw, PDF_BYTES)

    def test_source_text_is_plain_text(self) -> None:
        for name in ("resume.typ", "job.md"):
            status, response, raw = self.request("GET", f"/api/file?path=jobs/{self.job}/{name}")
            self.assertEqual(status, 200, name)
            self.assertEqual(response.getheader("Content-Type"), "text/plain; charset=utf-8")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertEqual(response.getheader("Content-Disposition"), f"inline; filename*=UTF-8''{name}")
        status, response, raw = self.request("GET", f"/api/file?path=jobs/{self.job}/resume.typ")
        self.assertIn(b"<script>", raw)

    def test_image_content_types(self) -> None:
        folder = self.ws.job_dir(self.job)
        (folder / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (folder / "photo.JPG").write_bytes(b"\xff\xd8\xff")
        for name, content_type in (("shot.png", "image/png"), ("photo.JPG", "image/jpeg")):
            response = self.request("GET", f"/api/file?path=jobs/{self.job}/{name}")[1]
            self.assertEqual((response.status, response.getheader("Content-Type")), (200, content_type))

    def test_refused_files(self) -> None:
        self.assertEqual(self.get_json("/api/file?path=settings.json")[0], 400)
        self.assertEqual(self.get_json("/api/file?path=..%2Foutside.pdf")[0], 400)
        self.assertEqual(self.get_json(f"/api/file?path=jobs/{self.job}/missing.pdf")[0], 404)


class ContainmentTests(ServerCase):
    def test_api_exception_becomes_500_and_the_server_keeps_serving(self) -> None:
        with mock.patch.object(api, "handle", side_effect=RuntimeError("boom")), mock.patch.object(sys, "stderr", io.StringIO()) as err:
            status, payload = self.get_json("/api/state")
            self.assertEqual(status, 500)
            self.assertIn("RuntimeError: boom", payload["error"])
            self.assertLess(len(payload["error"]), 300)
            status, payload = self.post_json(f"/api/jobs/{self.job}/track", {"status": "applied"})
            self.assertEqual(status, 500)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(self.get_json("/api/state")[0], 200)
        self.assertEqual(self.request("GET", "/")[0], 200)

    def test_unserializable_payload_does_not_crash(self) -> None:
        with mock.patch.object(api, "handle", return_value=(200, {"path": Path("/tmp/example"), "bad": object()})):
            status, payload = self.get_json("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(payload["path"], "/tmp/example")
        self.assertEqual(self.get_json("/api/state")[0], 200)


class ServeTests(unittest.TestCase):
    def serve(self, **kwargs):
        instances = []

        class FakeServer:
            def __init__(self, address, handler) -> None:
                self.address = address
                self.handler = handler
                self.server_address = (address[0], address[1] or 54321)
                self.closed = False
                instances.append(self)

            def serve_forever(self) -> None:
                raise KeyboardInterrupt

            def server_close(self) -> None:
                self.closed = True

        class InlineThread:
            def __init__(self, target, args=(), daemon=None) -> None:
                self.run = lambda: target(*args)

            def start(self) -> None:
                self.run()

        opened = []
        out = io.StringIO()
        with (
            mock.patch.object(server, "ThreadingHTTPServer", FakeServer),
            mock.patch.object(server.threading, "Thread", InlineThread),
            mock.patch.object(server.webbrowser, "open", opened.append),
            contextlib.redirect_stdout(out),
            tempfile.TemporaryDirectory() as tmp,
        ):
            server.serve(Workspace(Path(tmp) / "ws"), **kwargs)
        return instances[0], opened, out.getvalue()

    def test_serve_binds_loopback_prints_the_url_and_stops_cleanly(self) -> None:
        fake, opened, printed = self.serve(port=8791, open_browser=False)
        self.assertEqual(fake.address, ("127.0.0.1", 8791))
        self.assertTrue(fake.closed)
        self.assertEqual(opened, [])
        self.assertIn("http://127.0.0.1:8791/", printed)

    def test_serve_opens_the_browser_by_default(self) -> None:
        fake, opened, printed = self.serve()
        self.assertEqual(fake.address, ("127.0.0.1", 8765))
        self.assertEqual(opened, ["http://127.0.0.1:8765/"])

    def test_main_parses_arguments(self) -> None:
        with mock.patch.object(server, "serve") as serve, tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(server.main(["--port", "9001", "--workspace", tmp, "--no-open"]), 0)
            ws = serve.call_args.args[0]
            self.assertEqual(ws.root, Path(tmp))
            self.assertEqual(serve.call_args.kwargs, {"port": 9001, "open_browser": False})
            with mock.patch.dict(os.environ, {"JOBAPPS_HOME": tmp}):
                self.assertEqual(server.main([]), 0)
            self.assertEqual(serve.call_args.args[0].root, Path(tmp))
            self.assertEqual(serve.call_args.kwargs, {"port": 8765, "open_browser": True})

    def test_busy_port_is_reported_not_raised(self) -> None:
        busy = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(Workspace(Path(tempfile.gettempdir()) / "jobapps-none")))
        self.addCleanup(busy.server_close)
        port = busy.server_address[1]
        err = io.StringIO()
        with contextlib.redirect_stderr(err), tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(server.main(["--port", str(port), "--workspace", tmp, "--no-open"]), 2)
        self.assertIn(f"port {port}", err.getvalue())


class FakeResponse:
    def __init__(self, content=None, status_code: int = 200, **kwargs) -> None:
        self.content = content
        self.status_code = status_code
        self.kwargs = kwargs


class FakeRouter:
    def __init__(self) -> None:
        self.routes: list[tuple[str, list[str], object]] = []

    def api_route(self, path: str, methods: list[str]):
        def register(endpoint):
            self.routes.append((path, methods, endpoint))
            return endpoint

        return register


class FakeRequest:
    def __init__(self, method: str, query: dict[str, str] | None = None) -> None:
        self.method = method
        self.query_params = query or {}


class DashboardHostTests(unittest.TestCase):
    """dashboard/plugin_api.py with stand-ins for FastAPI, which only exists inside Hermes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws, self.job = seed(Path(self.tmp.name) / "ws")
        fastapi = types.ModuleType("fastapi")
        fastapi.APIRouter = FakeRouter
        fastapi.Request = FakeRequest
        fastapi.Body = lambda default=None, **_: default
        responses = types.ModuleType("fastapi.responses")
        responses.JSONResponse = type("JSONResponse", (FakeResponse,), {})
        responses.FileResponse = type("FileResponse", (FakeResponse,), {})
        fastapi.responses = responses
        self.responses = responses
        modules = mock.patch.dict(sys.modules, {"fastapi": fastapi, "fastapi.responses": responses})
        modules.start()
        self.addCleanup(modules.stop)
        environ = mock.patch.dict(os.environ, {"JOBAPPS_HOME": str(self.ws.root)})
        environ.start()
        self.addCleanup(environ.stop)
        path = mock.patch.object(sys, "path", list(sys.path))
        path.start()
        self.addCleanup(path.stop)
        spec = importlib.util.spec_from_file_location("jobapps_dashboard_plugin_api_under_test", DASHBOARD / "plugin_api.py")
        self.plugin_api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.plugin_api)

    def call(self, method: str, route: str, query: dict[str, str] | None = None, body=None):
        return self.plugin_api.cockpit(route, FakeRequest(method, query), body)

    def test_one_sync_catch_all_route(self) -> None:
        self.assertIsInstance(self.plugin_api.router, FakeRouter)
        self.assertEqual(len(self.plugin_api.router.routes), 1)
        path, methods, endpoint = self.plugin_api.router.routes[0]
        self.assertEqual((path, sorted(methods)), ("/{route:path}", ["GET", "POST"]))
        self.assertFalse(inspect.iscoroutinefunction(endpoint))
        self.assertIn(str(REPO), sys.path)

    def test_get_post_and_status_pass_through(self) -> None:
        response = self.call("GET", "state", {"profile": "default"})
        self.assertIsInstance(response, self.responses.JSONResponse)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content["counts"]["total"], 7)
        self.assertEqual(response.content["workspace"], str(self.ws.root))

        response = self.call("POST", f"jobs/{self.job}/track", body={"status": "applied"})
        self.assertEqual((response.status_code, response.content["ok"]), (200, True))
        self.assertEqual(self.ws.job_doc(self.job).meta["status"], "applied")

        self.assertEqual(self.call("POST", f"jobs/{self.job}/track", body=None).content["unchanged"], True)
        self.assertEqual(self.call("GET", "nope").status_code, 404)
        self.assertEqual(self.call("GET", "doc", {"path": "../outside.md"}).status_code, 400)
        self.assertEqual(self.call("GET", "doc", {"path": "profile/profile.md"}).content["meta"]["name"], "Jordan Example")

    def test_file_result_becomes_an_inline_file_response(self) -> None:
        response = self.call("GET", "file", {"path": f"jobs/{self.job}/resume.pdf"})
        self.assertIsInstance(response, self.responses.FileResponse)
        self.assertEqual(response.content, (self.ws.job_dir(self.job) / "resume.pdf").resolve())
        self.assertEqual(response.kwargs["content_disposition_type"], "inline")
        self.assertEqual(response.kwargs["media_type"], "application/pdf")
        self.assertEqual(response.kwargs["filename"], "resume.pdf")
        self.assertEqual(response.kwargs["headers"]["X-Content-Type-Options"], "nosniff")
        text = self.call("GET", "file", {"path": f"jobs/{self.job}/resume.typ"})
        self.assertEqual(text.kwargs["media_type"], "text/plain; charset=utf-8")

    def test_workspace_follows_the_plugin_order(self) -> None:
        self.assertEqual(self.plugin_api.workspace().root, self.ws.root)
        self.assertIs(self.plugin_api.workspace(), self.plugin_api.workspace())
        configured = Path(self.tmp.name) / "configured"
        config = types.ModuleType("hermes_cli.config")
        config.load_config_readonly = lambda: {"plugins": {"entries": {"jobapps": {"settings": {"workspace": str(configured)}}}}}
        package = types.ModuleType("hermes_cli")
        package.config = config
        with mock.patch.dict(sys.modules, {"hermes_cli": package, "hermes_cli.config": config}):
            self.assertEqual(self.plugin_api.workspace().root, configured)
            config.load_config_readonly = lambda: {"plugins": {"entries": {"jobapps": {"settings": {"workspace": ""}}}}}
            self.assertEqual(self.plugin_api.workspace().root, self.ws.root)
            config.load_config_readonly = mock.Mock(side_effect=RuntimeError("broken config"))
            self.assertEqual(self.plugin_api.workspace().root, self.ws.root)
        with mock.patch.dict(os.environ):
            os.environ.pop("JOBAPPS_HOME")
            self.assertEqual(self.plugin_api.workspace().root, Path.home() / "JobApps")

    def test_manifest(self) -> None:
        manifest = json.loads((DASHBOARD / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {key: manifest[key] for key in ("name", "label", "version", "entry", "css", "api")},
            {
                "name": "jobapps",
                "label": "JobApps",
                "version": "1.0.0",
                "entry": "dist/index.js",
                "css": "dist/style.css",
                "api": "plugin_api.py",
            },
        )
        self.assertEqual(manifest["tab"]["path"], "/jobapps")
        self.assertTrue(manifest["icon"])
        self.assertTrue(manifest["description"])
        for key in ("entry", "css", "api"):
            self.assertTrue((DASHBOARD / manifest[key]).is_file(), key)


if __name__ == "__main__":
    unittest.main()
