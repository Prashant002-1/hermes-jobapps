"""Hermes plugin entry point for JobApps.

The workspace folder holds all state as plain files, so this plugin stays
thin: a handful of tools for what files cannot do, the bundled skills, one
slash command and a two-line system prompt pointer.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .workspace import AmbiguousReference, Workspace, default_root, parse_frontmatter


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PLUGIN_ROOT / "skills"
TOOLSET = "jobapps"

_STAGES = ["new", "ready", "applied", "interviewing", "offer", "rejected", "closed", "skipped"]
_PURPOSES = ["resume", "cover_letter", "application_answers", "outreach", "interview", "general"]
_KINDS = ["resume", "cover_letter", "application_answers", "outreach"]
_PERSON_STATUSES = ["to_contact", "contacted", "follow_up", "replied", "paused"]

_lock = threading.Lock()
_workspaces: dict[str, Workspace] = {}
_configured_root: Callable[[], str] = lambda: ""


def workspace() -> Workspace:
    root = _configured_root() or os.environ.get("JOBAPPS_HOME", "") or str(default_root())
    key = str(Path(root).expanduser())
    with _lock:
        if key not in _workspaces:
            _workspaces[key] = Workspace(key)
        return _workspaces[key]


def _overview(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .tracking import overview

    return overview(
        ws,
        view=str(args.get("view") or "today"),
        stage=str(args.get("stage") or ""),
        query=str(args.get("query") or ""),
        limit=_int(args.get("limit"), 8),
    )


def _brief(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .tracking import brief

    return brief(
        ws,
        _required(args, "job"),
        purpose=str(args.get("purpose") or "resume"),
        evidence=args.get("evidence") is not False,
    )


def _add_job(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .intake import add_job

    return add_job(ws, **_strings(args, "url", "text", "company", "title", "location", "notes", "lead"))


def _track(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .tracking import track_job

    return track_job(
        ws,
        _required(args, "job"),
        status=_optional(args, "status"),
        next_action=_optional(args, "next_action"),
        due=_optional(args, "due"),
        note=str(args.get("note") or ""),
        applied_on=_optional(args, "applied_on"),
        force=args.get("force") is True,
        priority=_optional(args, "priority"),
        referral=_optional(args, "referral"),
    )


def _check(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .check import check_material

    max_chars = args.get("max_chars")
    return check_material(
        ws,
        _required(args, "path"),
        kind=str(args.get("kind") or ""),
        job=str(args.get("job") or ""),
        max_chars=_int(max_chars, 0) or None,
    )


def _find_jobs(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .intake import find_jobs

    return find_jobs(ws, _required(args, "query"), limit=_int(args.get("limit"), 8))


def _find_people(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .intake import find_people

    return find_people(ws, limit=_int(args.get("limit"), 6), **_strings(args, "company", "query", "job"))


def _person(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .tracking import save_person

    return save_person(
        ws,
        status=_optional(args, "status"),
        next_touch=_optional(args, "next_touch"),
        **_strings(args, "person", "name", "company", "role", "email", "linkedin", "why", "job", "note"),
    )


def _gmail_draft(ws: Workspace, args: dict[str, Any]) -> dict[str, Any]:
    from .intake import gmail_draft

    return gmail_draft(ws, **_strings(args, "to", "subject", "body", "account", "person"))


def _required(args: dict[str, Any], name: str) -> str:
    value = str(args.get(name) or "").strip()
    if not value:
        raise ValueError(f"Missing required argument: {name}.")
    return value


def _optional(args: dict[str, Any], name: str) -> str | None:
    return None if args.get(name) is None else str(args[name])


def _strings(args: dict[str, Any], *names: str) -> dict[str, str]:
    return {name: str(args.get(name) or "") for name in names}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _props(**properties: Any) -> dict[str, Any]:
    return properties


def _text(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "jobapps_overview",
        "handler": _overview,
        "description": (
            "Job-search tracking computed from the workspace files: counts by stage and what needs attention "
            "(due actions, quiet applications, ready to apply, interviews, people to reach, fresh leads). "
            "Also lists or searches jobs, people and leads. Use it to find a job id."
        ),
        "properties": _props(
            view={
                "type": "string",
                "enum": ["today", "jobs", "people", "leads", "stats"],
                "description": "Default today. stats gives the application funnel by month and role family.",
            },
            stage={"type": "string", "enum": _STAGES, "description": "Filter jobs by stage."},
            query=_text("Words that must appear in the company, title, name or id."),
            limit={"type": "integer", "description": "Items per list, default 8. Totals are always exact."},
        ),
        "required": [],
    },
    {
        "name": "jobapps_brief",
        "handler": _brief,
        "description": (
            "Everything needed to write for one job in a single call: posting, blocker assessment, requirements, "
            "notes, existing files, profile, voice, the playbook rules for this document type and the evidence files. "
            "Call once before writing. Evidence left out to fit the budget is listed by path and is not missing experience."
        ),
        "properties": _props(
            job=_text("Job id, or words that identify exactly one job."),
            purpose={"type": "string", "enum": _PURPOSES, "description": "Document being written. Default resume."},
            evidence={
                "type": "boolean",
                "description": "Pass false when an earlier brief in this conversation already gave you the evidence files.",
            },
        ),
        "required": ["job"],
    },
    {
        "name": "jobapps_add_job",
        "handler": _add_job,
        "description": (
            "Create a job folder from a posting and run the configured hard-blocker check (apply, pending or skip; never a score). "
            "Give url for Greenhouse, Lever or Ashby pages. For any other page fetch it yourself and pass text with company and title. "
            "Give lead to promote a saved lead. Detects duplicates. Does not write any application document."
        ),
        "properties": _props(
            url=_text("Posting URL."),
            text=_text("Full posting text, verbatim."),
            company=_text("Employer name. Required with text."),
            title=_text("Role title. Required with text."),
            location=_text("Location, if known."),
            notes=_text("What the user said about this role."),
            lead=_text("Lead id to promote instead of url or text."),
        ),
        "required": [],
    },
    {
        "name": "jobapps_track",
        "handler": _track,
        "description": (
            "Record progress on a job: stage, the one next action and its due date, priority, referral, a log note. "
            "applied stamps the date and schedules a check-in. ready is refused while a resume is unchecked, stale or failing. "
            "Read the reminders it returns: they name what would still strengthen the application."
        ),
        "properties": _props(
            job=_text("Job id, or words that identify exactly one job."),
            status={"type": "string", "enum": _STAGES},
            next_action=_text("The single next step. Empty string clears it."),
            due=_text("Due date for the next action, YYYY-MM-DD. Empty string clears it."),
            note=_text("What happened, for the job log."),
            applied_on=_text("Application date, YYYY-MM-DD. Defaults to today when marking applied."),
            priority={"type": "string", "enum": ["high", "normal", "low"], "description": "How much this role matters to the user."},
            referral=_text("Name of the person referring the user. Empty string clears it."),
            force={"type": "boolean", "description": "Mark ready despite check problems. Only when the user explicitly accepts that."},
        ),
        "required": ["job"],
    },
    {
        "name": "jobapps_check",
        "handler": _check,
        "description": (
            "Build and check one document file: compiles Typst or TeX to PDF, measures resume layout "
            "(one page, collisions, spacing, bottom whitespace) and lints the content (weak or generic bullets, "
            "missing consequence, leaked notes, numbers absent from evidence, posting coverage). "
            "Returns pass, review or fail with exact repairs. Run after every edit; the result goes stale when the file changes."
        ),
        "properties": _props(
            path=_text("Source file (.typ, .tex, .md, .txt): workspace-relative path, or a file name when job is given."),
            job=_text("Job id the file belongs to, when path is only a file name."),
            kind={"type": "string", "enum": _KINDS, "description": "Only when the file name does not say what it is."},
            max_chars={"type": "integer", "description": "Character limit of the form field, for application answers."},
        ),
        "required": ["path"],
    },
    {
        "name": "jobapps_find_jobs",
        "handler": _find_jobs,
        "description": (
            "Search current postings and save new ones as leads with a blocker check. Nothing is applied to. "
            "Shortlist or dismiss by editing the lead file's status; promote with jobapps_add_job(lead)."
        ),
        "properties": _props(
            query=_text("Role, skills, location and other terms."),
            limit={"type": "integer", "description": "Results, default 8."},
        ),
        "required": ["query"],
    },
    {
        "name": "jobapps_find_people",
        "handler": _find_people,
        "description": (
            "Search public profiles for people at a company and list anyone already tracked there. "
            "Saves nothing and never guesses email addresses. Verify identity before using a result."
        ),
        "properties": _props(
            company=_text("Company name."),
            job=_text("Job id to take the company from."),
            query=_text("Role or team to look for, for example engineering manager payments."),
            limit={"type": "integer", "description": "Results, default 6."},
        ),
        "required": [],
    },
    {
        "name": "jobapps_person",
        "handler": _person,
        "description": (
            "Add or update a person the user chose to track, and log each touch. "
            "New people need name and why. contacted schedules the next touch. Use only when the user asks to track someone."
        ),
        "properties": _props(
            person=_text("Existing person id or name."),
            name=_text("Full name, for a new person."),
            why=_text("Why this person matters to the search. Required for a new person."),
            company=_text("Company."),
            role=_text("Role or title."),
            email=_text("Email, only if known for certain."),
            linkedin=_text("LinkedIn URL."),
            status={"type": "string", "enum": _PERSON_STATUSES},
            next_touch=_text("Next contact date, YYYY-MM-DD. Empty string clears it."),
            job=_text("Job id to link this person to."),
            note=_text("What happened, for the person's log."),
        ),
        "required": [],
    },
    {
        "name": "jobapps_gmail_draft",
        "handler": _gmail_draft,
        "description": "Create a Gmail draft. It cannot send. Use only when the user asks for a draft in Gmail.",
        "properties": _props(
            subject=_text("Subject line."),
            body=_text("Plain-text body."),
            to=_text("Recipient address."),
            person=_text("Tracked person id to take the address from."),
            account=_text("Gmail account, when more than one is configured."),
        ),
        "required": ["subject", "body"],
    },
]


def tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool["description"],
        "parameters": {
            "type": "object",
            "properties": tool["properties"],
            "required": tool["required"],
            "additionalProperties": False,
        },
    }


def run_tool(name: str, args: dict[str, Any] | None, *, ws: Workspace | None = None) -> str:
    """Execute a tool and return the JSON string Hermes expects."""
    tool = next((item for item in TOOLS if item["name"] == name), None)
    if tool is None:
        return _dump({"error": f"Unknown tool: {name}"})
    try:
        result = tool["handler"](ws or workspace(), args if isinstance(args, dict) else {})
    except AmbiguousReference as exc:
        result = {
            "error": str(exc),
            "matches": [
                {key: item.get(key) for key in ("id", "company", "title", "name", "status") if item.get(key)}
                for item in exc.matches[:5]
            ],
        }
    except KeyError as exc:
        result = {"error": str(exc.args[0]) if exc.args else "Not found."}
    except ValueError as exc:
        result = {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a tool must always answer
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return _dump(result)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _handler(name: str) -> Callable[..., str]:
    def handle(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
        return run_tool(name, args)

    return handle


def render_overview(result: dict[str, Any]) -> str:
    """Plain-text overview for the slash command and the CLI."""
    counts = result.get("counts", {})
    stages = "  ".join(f"{stage} {counts.get(stage, 0)}" for stage in _STAGES if counts.get(stage))
    lines = [f"JobApps  {result.get('as_of', '')}  {result.get('workspace', '')}", stages or "No jobs yet."]
    for note in result.get("setup", []):
        lines.append(f"Setup: {note}")
    stats = result.get("stats")
    if stats:
        lines.append("")
        lines.append(
            f"Sent {stats.get('applied', 0)}: {stats.get('interviews', 0)} reached an interview, "
            f"{stats.get('rejected', 0)} rejected, {stats.get('no_reply', 0)} no reply yet"
        )
        for row in stats.get("by_channel", []):
            lines.append(f"  {row['channel']}: sent {row['applied']}, interviews {row['interviews']}")
        for row in stats.get("by_month", []):
            lines.append(f"  {row['month']}  sent {row['applied']}  interviews {row['interviews']}  rejected {row['rejected']}")
        for row in stats.get("by_role_family", []):
            lines.append(f"  {row['role_family']}: sent {row['applied']}, interviews {row['interviews']}")
    labels = {
        "due": "Due",
        "applied_quiet": "Applied, worth a follow-up",
        "applied_stale": "Applied long ago, no reply",
        "ready": "Ready to apply",
        "interviewing": "Interviewing",
        "in_progress": "In progress",
        "people": "People to reach",
        "leads": "New leads",
        "jobs": "Jobs",
    }
    sources = dict(result.get("attention", {}))
    for key in ("jobs", "people", "leads"):
        if key in result:
            sources[key] = result[key]
            sources[f"{key}_total"] = result.get(f"{key}_total", len(result[key]))
    for key, label in labels.items():
        items = sources.get(key)
        if not items:
            continue
        total = sources.get(f"{key}_total", len(items))
        lines.append("")
        lines.append(f"{label} ({total})")
        for item in items:
            lines.append("  " + _overview_line(item))
    return "\n".join(lines)


def _overview_line(item: dict[str, Any]) -> str:
    if item.get("name"):
        parts = [item["name"], item.get("role", ""), item.get("company", ""), item.get("status", "")]
        if item.get("next_touch"):
            parts.append(f"next {item['next_touch']}")
    else:
        parts = [f"{item.get('company', '')}: {item.get('title', '')}"]
        if item.get("priority"):
            parts.append(f"{item['priority']} priority")
        if item.get("next_action"):
            parts.append(item["next_action"])
        if item.get("due"):
            parts.append(f"due {item['due']}")
        if item.get("days") is not None:
            parts.append(f"{item['days']} days since applying")
        if item.get("materials"):
            parts.append(", ".join(f"{m.get('kind')} {m.get('qa')}" for m in item["materials"]))
        if item.get("found_on"):
            parts.append(f"found {item['found_on']}")
        identifier = item.get("job") or item.get("lead")
        if identifier:
            parts.append(f"[{identifier}]")
    return " · ".join(str(part) for part in parts if part)


def slash_command(raw_args: str = "", **kwargs: Any) -> str:
    words = (raw_args or "").split()
    view = words[0].lower() if words and words[0].lower() in {"today", "jobs", "people", "leads", "stats"} else "today"
    query = " ".join(words[1:] if words and words[0].lower() == view else words)
    try:
        from .tracking import overview

        return render_overview(overview(workspace(), view=view, query=query))
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return f"JobApps could not read the workspace: {exc}"


def _prompt_section(context: Any = None) -> str:
    return (
        f"JobApps: the user's job search lives as plain files in {workspace().root}. "
        "For any job search, application, resume, cover letter, networking or interview task, "
        "load the skill jobapps:jobapps first."
    )


def _register_skills(ctx: Any) -> None:
    if not SKILLS_DIR.is_dir():
        return
    for child in sorted(SKILLS_DIR.iterdir()):
        skill_file = child / "SKILL.md"
        if not skill_file.is_file():
            continue
        meta, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        description = str(meta.get("description") or "")
        try:
            ctx.register_skill(child.name, skill_file, description=description, frontmatter={"description": description})
        except TypeError:
            ctx.register_skill(child.name, skill_file)


def register(ctx: Any) -> None:
    global _configured_root
    if hasattr(ctx, "get_config"):
        _configured_root = lambda: str(ctx.get_config("workspace", "") or "")

    for tool in TOOLS:
        ctx.register_tool(
            name=tool["name"],
            toolset=TOOLSET,
            schema=tool_schema(tool),
            handler=_handler(tool["name"]),
            description=tool["description"],
            emoji="💼",
        )
    ctx.register_command(
        "jobapps",
        slash_command,
        description="Job search overview: what is due, quiet, ready and new",
        args_hint="[today|jobs|people|leads|stats] [search words]",
    )
    _register_skills(ctx)
    if hasattr(ctx, "register_system_prompt_section"):
        ctx.register_system_prompt_section("jobapps.workspace", _prompt_section)
    if hasattr(ctx, "register_automation_blueprint"):
        for blueprint in BLUEPRINTS:
            ctx.register_automation_blueprint(**blueprint)


_TIME_SLOT = {"name": "time", "type": "time", "label": "What time?", "default": "08:30"}
_DELIVER_SLOT = {
    "name": "deliver",
    "type": "enum",
    "label": "Where?",
    "default": "origin",
    "options": ["origin", "local"],
    "strict": False,
}

BLUEPRINTS: list[dict[str, Any]] = [
    {
        "key": "daily-brief",
        "title": "Job search: daily brief",
        "description": "Each weekday, what is due, which applications have gone quiet, and who to reach.",
        "category": "daily",
        "schedule_template": "{minute} {hour} * * 1-5",
        "prompt_template": (
            "Call jobapps_overview. In at most eight short lines tell the user what is due or overdue, "
            "which applications have been quiet long enough to follow up, what is ready to send, any "
            "interviews, and people to reach. Lead with the single most useful action for today. "
            "Recommend only: change nothing and send nothing. If nothing needs attention, respond with [SILENT]."
        ),
        "slots": [_TIME_SLOT, _DELIVER_SLOT],
        "skills": ["jobapps:jobapps"],
        "tags": ["career", "daily"],
    },
    {
        "key": "lead-scan",
        "title": "Job search: new postings",
        "description": "Each weekday, search for fresh postings and report only new ones worth a look.",
        "category": "daily",
        "schedule_template": "{minute} {hour} * * 1-5",
        "prompt_template": (
            "Call jobapps_find_jobs once for each of these searches: {searches}. Report only leads that are new "
            "and whose blocker check is apply or pending, newest first, at most eight, with company, title, "
            "location and link. Fresh postings matter: say which were posted in the last three days. "
            "Apply to nothing and promote nothing. If there are no new leads, respond with [SILENT]."
        ),
        "slots": [
            {
                "name": "searches",
                "type": "text",
                "label": "Which searches? Separate with semicolons.",
                "default": "software engineer new grad remote; data engineer entry level",
            },
            {**_TIME_SLOT, "default": "07:30"},
            _DELIVER_SLOT,
        ],
        "skills": ["jobapps:job-search"],
        "tags": ["career", "daily", "search"],
    },
    {
        "key": "weekly-review",
        "title": "Job search: weekly review",
        "description": "Once a week, the funnel, what stalled, leads worth promoting and a plan for next week.",
        "category": "weekly",
        "schedule_template": "{minute} {hour} * * {dow}",
        "prompt_template": (
            "Run the weekly review from the jobapps:job-search skill: call jobapps_overview with view today and "
            "view stats, name what stalled and why, list leads worth promoting, and propose a short plan for "
            "next week with at most five actions. Recommend only: change nothing and send nothing."
        ),
        "slots": [
            {**_TIME_SLOT, "default": "17:00"},
            {
                "name": "day",
                "type": "enum",
                "label": "Which day?",
                "default": "sunday",
                "options": ["sunday", "monday", "friday", "saturday"],
            },
            _DELIVER_SLOT,
        ],
        "skills": ["jobapps:job-search"],
        "tags": ["career", "weekly"],
    },
]


__all__ = ["TOOLS", "register", "render_overview", "run_tool", "slash_command", "tool_schema", "workspace", "__version__"]
