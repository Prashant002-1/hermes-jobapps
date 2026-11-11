"""Command line for the JobApps workspace: python -m hermes_jobapps <command>."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .workspace import Workspace


def _workspace(args: argparse.Namespace) -> Workspace:
    return Workspace(args.workspace) if args.workspace else Workspace()


def cmd_init(args: argparse.Namespace) -> int:
    ws = _workspace(args)
    created = ws.init(name=args.name or "")
    print(f"Workspace: {ws.root}")
    for item in created:
        print(f"  created {item}")
    if not created:
        print("  already set up; nothing was overwritten")
    print("Next: fill profile/profile.md and add one file per experience under evidence/.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from .plugin import render_overview
    from .tracking import overview

    ws = _workspace(args)
    result = overview(ws, view=args.view, query=" ".join(args.query))
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render_overview(result))
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    from .migrate import migrate_legacy

    ws = _workspace(args)
    report = migrate_legacy(
        args.source,
        ws,
        materials_root=args.materials or None,
        lead_days=args.lead_days,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from .check import check_material

    result = check_material(_workspace(args), args.path, kind=args.kind or "", job=args.job or "")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "pass" else 1


def cmd_ui(args: argparse.Namespace) -> int:
    from .server import serve

    serve(_workspace(args), port=args.port, open_browser=not args.no_open)
    return 0


def doctor_report(ws: Workspace) -> dict[str, Any]:
    settings = ws.settings() if ws.exists() else {}
    paths = os.pathsep.join(
        [
            os.environ.get("PATH", ""),
            *settings.get("typst", {}).get("compiler_paths", []),
            *settings.get("latex", {}).get("compiler_paths", []),
        ]
    )
    exa_env = settings.get("discovery", {}).get("exa", {}).get("api_key_env", "EXA_API_KEY")
    gog = settings.get("networking", {}).get("gog_path", "gog")
    tools = {
        "typst": "Builds resumes and letters written in Typst.",
        "tectonic": "Builds TeX letters.",
        "pdftotext": "Reads PDF text and layout for the resume check (poppler).",
        "pdfinfo": "Counts PDF pages (poppler).",
    }
    report: dict[str, Any] = {
        "version": __version__,
        "workspace": {
            "path": str(ws.root),
            "exists": ws.exists(),
            "jobs": len(ws.jobs()) if ws.exists() else 0,
            "evidence_files": len(ws.evidence()) if ws.exists() else 0,
            "people": len(ws.people()) if ws.exists() else 0,
            "profile_name": bool(ws.profile_meta().get("name")) if ws.exists() else False,
        },
        "tools": {
            name: {"found": shutil.which(name, path=paths) or "", "purpose": purpose} for name, purpose in tools.items()
        },
        "optional": {
            "job_and_people_search": {"env": exa_env, "set": bool(os.environ.get(exa_env))},
            "gmail_drafts": {"command": gog, "found": shutil.which(gog, path=paths) or ""},
        },
    }
    return report


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor_report(_workspace(args))
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    space = report["workspace"]
    print(f"JobApps {report['version']}")
    print(f"Workspace: {space['path']} ({'ready' if space['exists'] else 'not created; run init'})")
    if space["exists"]:
        print(f"  {space['jobs']} jobs, {space['evidence_files']} evidence files, {space['people']} people")
        if not space["profile_name"]:
            print("  profile/profile.md has no name yet")
    for name, info in report["tools"].items():
        print(f"  {'ok     ' if info['found'] else 'missing'} {name}: {info['purpose']}")
    search = report["optional"]["job_and_people_search"]
    print(f"  {'ok     ' if search['set'] else 'off    '} search: set {search['env']} to enable job and people search")
    drafts = report["optional"]["gmail_drafts"]
    print(f"  {'ok     ' if drafts['found'] else 'off    '} Gmail drafts: needs the {drafts['command']} command")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobapps", description="Plain-file job-search workspace.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", help="Workspace folder. Default: JOBAPPS_HOME or ~/JobApps.")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create the workspace folders and starter files.")
    init.add_argument("--name", help="Your name, for profile/profile.md.")
    init.set_defaults(run=cmd_init)

    status = commands.add_parser("status", help="Show what needs attention.")
    status.add_argument("view", nargs="?", default="today", choices=["today", "jobs", "people", "leads", "stats"])
    status.add_argument("query", nargs="*", help="Words to search for.")
    status.add_argument("--json", action="store_true")
    status.set_defaults(run=cmd_status)

    migrate = commands.add_parser("migrate", help="Copy a legacy JobApps SQLite database into the workspace.")
    migrate.add_argument("source", help="Path to the legacy hermes-jobapps.sqlite3 file. It is opened read-only.")
    migrate.add_argument("--materials", help="Legacy materials folder. Default: materials/ next to the database.")
    migrate.add_argument("--lead-days", type=int, default=45, help="Keep discovery candidates newer than this.")
    migrate.add_argument("--dry-run", action="store_true", help="Report what would be written without writing.")
    migrate.set_defaults(run=cmd_migrate)

    check = commands.add_parser("check", help="Build and check one document.")
    check.add_argument("path")
    check.add_argument("--job")
    check.add_argument("--kind", choices=["resume", "cover_letter", "application_answers", "outreach"])
    check.set_defaults(run=cmd_check)

    ui = commands.add_parser("ui", help="Open the local cockpit in a browser.")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-open", action="store_true")
    ui.set_defaults(run=cmd_ui)

    doctor = commands.add_parser("doctor", help="Check the workspace and the optional tools.")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(run=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.run(args) or 0)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc.args[0] if isinstance(exc, KeyError) and exc.args else exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
