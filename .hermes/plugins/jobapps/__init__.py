"""Hermes plugin bridge for the JobApps cockpit.

This lets a native Hermes TUI/API session read and update the same SQLite
database used by the local web cockpit. The database remains the application
source of truth; Hermes memory stays focused on durable preferences and lessons.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PLUGIN_DIR.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hermes_jobapps.config import load_config, resolve_project_path  # noqa: E402
from hermes_jobapps.repository import JobRepository  # noqa: E402
from hermes_jobapps.tools import AgentToolbox, TOOL_SPECS  # noqa: E402


_REPO: JobRepository | None = None
_TOOLBOX: AgentToolbox | None = None


def _toolbox() -> AgentToolbox:
    global _REPO, _TOOLBOX
    if _TOOLBOX is None:
        config = load_config()
        db_path = config.get("database_path") or "data/hermes-jobapps.sqlite3"
        _REPO = JobRepository(resolve_project_path(db_path))
        _TOOLBOX = AgentToolbox(_REPO, config)
    return _TOOLBOX


def _make_handler(name: str):
    def handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            result = _toolbox().execute(name, args or {})
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, indent=2)

    return handler


def _schema(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "description": spec["description"],
        "parameters": spec.get("input_schema", {"type": "object", "properties": {}}),
    }


def _inject_jobapps_context(user_message: str = "", is_first_turn: bool = False, **kwargs: Any) -> dict[str, str] | None:
    query = (user_message or "").lower()
    trigger_terms = (
        "jobapps",
        "job",
        "application",
        "resume",
        "cover letter",
        "company",
        "networking",
        "follow-up",
        "followup",
        "outreach",
    )
    triggered = any(term in query for term in trigger_terms)
    boundary = (
        "Use native Hermes file/search/patch/terminal tools for material writing, editing, diffing, "
        "Typst/TeX compilation, and QA. Use JobApps tools only for targeted retrieval and durable "
        "app-state ledger records such as jobs, proof points, material links/provenance, contacts, "
        "follow-ups, status, and external-action approvals."
    )
    if not triggered:
        if is_first_turn:
            return {"context": f"JobApps SQLite context is available through targeted tools. {boundary}"}
        return None

    try:
        repo = _toolbox().repo
        dashboard = repo.dashboard()
        recent_jobs = dashboard.get("jobs", [])[:3]
        context_counts = dashboard.get("context_counts", {})
        discovery_counts = dashboard.get("discovery", {}).get("counts", {})
        lines = [
            "JobApps app context is available. Treat the JobApps SQLite database as source of truth.",
            boundary,
            f"Profile facts: {context_counts.get('profile_facts', 0)}; active proof points: {context_counts.get('proof_points', 0)}; application signals: {context_counts.get('application_signals', 0)}.",
            f"Career-brain entities: {context_counts.get('brain_entities', 0)}; career-brain events: {context_counts.get('brain_events', 0)}.",
            f"Discovery candidates: {discovery_counts.get('total', 0)}; ready={discovery_counts.get('ready', 0)}; needs_review={discovery_counts.get('needs_review', 0)}.",
            f"Cached contacts: {context_counts.get('contacts', 0)}.",
        ]
        if recent_jobs:
            lines.append("Recent opportunities:")
            for job in recent_jobs:
                title = job.get("title") or "Untitled role"
                company = job.get("company") or "Unknown company"
                status = job.get("status") or "saved"
                decision = job.get("decision") or "review"
                lines.append(f"- {job.get('id')}: {title} at {company}; status={status}; decision={decision}")
        lines.append("Use jobapps_prepare_opportunity for intake/evaluation only; it does not author candidate-facing materials. Use jobapps_start_material_prep only when the applicant wants background Hermes material-prep runs for existing jobs. Discovery candidates must be promoted before tailoring. For networking, use jobapps_find_people to cache public contacts and jobapps_create_gmail_draft only for drafts; never send email.")
        return {"context": "\n".join(lines)}
    except Exception as exc:
        return {"context": f"JobApps context bridge failed: {exc}"}


def _jobapps_command(argstr: str = "", **kwargs: Any) -> str:
    try:
        result = _toolbox().repo.dashboard()
        summary = {
            "jobs": len(result.get("jobs", [])),
            "open_followups": len(result.get("followups", [])),
            "open_progress_items": len(result.get("progress_items", [])),
            "pending_approvals": len(result.get("approvals", [])),
            "discovery_candidates": result.get("discovery", {}).get("counts", {}),
            "database_health": result.get("database_health", {}).get("status", "unknown"),
            "context_counts": result.get("context_counts", {}),
        }
        return json.dumps(summary, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, indent=2)


def register(ctx: Any) -> None:
    for spec in TOOL_SPECS:
        ctx.register_tool(
            name=spec["name"],
            toolset="jobapps",
            schema=_schema(spec),
            handler=_make_handler(spec["name"]),
        )

    ctx.register_hook("pre_llm_call", _inject_jobapps_context)
    ctx.register_command(
        "jobapps",
        _jobapps_command,
        description="Show a compact JobApps dashboard summary",
    )

    skills_dir = PLUGIN_DIR / "skills"
    if not skills_dir.exists():
        return
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            ctx.register_skill(child.name, skill_md)
