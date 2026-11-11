"""JobApps cockpit API inside the Hermes dashboard, mounted at /api/plugins/jobapps/.

Every request goes to `hermes_jobapps.api.handle`, the same functions the
standalone cockpit serves. The endpoint is a plain `def`, so FastAPI runs it in
a worker thread and file work never blocks the dashboard's event loop.
"""

import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse, JSONResponse

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from hermes_jobapps import api  # noqa: E402
from hermes_jobapps.server import file_content_type  # noqa: E402
from hermes_jobapps.workspace import Workspace, default_root  # noqa: E402


router = APIRouter()

_lock = threading.Lock()
_write_lock = threading.Lock()
_workspaces: Dict[str, Workspace] = {}


def _configured_root() -> str:
    """The plugin's `workspace` setting, where the plugin's own ctx.get_config reads it."""
    try:
        from hermes_cli.config import load_config_readonly

        plugins = (load_config_readonly() or {}).get("plugins")
        entries = plugins.get("entries") if isinstance(plugins, dict) else None
        for plugin_id in (PLUGIN_ROOT.name, "jobapps"):
            entry = entries.get(plugin_id) if isinstance(entries, dict) else None
            for subtree in ("settings", "config"):
                values = entry.get(subtree) if isinstance(entry, dict) else None
                if isinstance(values, dict) and values.get("workspace"):
                    return str(values["workspace"])
    except Exception:  # Hermes internals are optional here: fall back to JOBAPPS_HOME, then the default
        return ""
    return ""


def workspace() -> Workspace:
    """Same order as the plugin: its workspace setting, then JOBAPPS_HOME, then ~/JobApps."""
    root = _configured_root() or os.environ.get("JOBAPPS_HOME", "").strip() or str(default_root())
    key = str(Path(root).expanduser())
    with _lock:
        if key not in _workspaces:
            _workspaces[key] = Workspace(key)
        return _workspaces[key]


@router.api_route("/{route:path}", methods=["GET", "POST"])
def cockpit(route: str, request: Request, body: Optional[Dict[str, Any]] = Body(default=None)):
    query = dict(request.query_params)
    if request.method == "POST":
        with _write_lock:
            status, payload = api.handle(workspace(), "POST", "/" + route, query, body)
    else:
        status, payload = api.handle(workspace(), "GET", "/" + route, query, None)
    if isinstance(payload, api.FileResult):
        return FileResponse(
            payload.path,
            media_type=file_content_type(payload.path),
            filename=payload.path.name,
            content_disposition_type="inline",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )
    return JSONResponse(payload, status_code=status)
