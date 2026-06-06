"""Tool handlers for JobApps database transitions.

These handlers are used by the local app and by the Hermes plugin wrapper.
Hermes-facing tool names use underscores because model tool schemas generally
expect simple function identifiers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .config import resolve_project_path
from .discovery import DiscoveryService
from .evaluator import evaluate_job
from .latex import compile_tex_to_pdf, job_material_filename, write_material_artifact
from .typst import compile_typst_to_pdf, build_full_resume_typst
from .materials import (
    build_full_cover_letter_tex,
    patch_text,
    text_diff,
)
from .networking import NetworkingService
from .repository import (
    ACTIVE_HERMES_RUN_STATUSES,
    JobRepository,
    TOOL_CALL_INLINE_LIMIT_BYTES,
    normalize_material_format_for_db,
    normalize_material_kind_for_db,
)
from .writers import draft_materials


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "jobapps_read_context",
        "description": "Read JobApps profile facts, proof points, recent applications, progress, follow-ups, approvals, and health.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "writes": False,
    },
    {
        "name": "jobapps_database_health",
        "description": "Inspect JobApps database counts and stale or unattached records before real workflow use.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "writes": False,
    },
    {
        "name": "jobapps_tool_call_retention",
        "description": "Preview or archive old inline tool-call audit payloads without deleting core workflow state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "retain_days": {"type": "integer"},
                "limit": {"type": "integer"},
                "min_bytes": {"type": "integer"},
                "apply": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "writes": True,
    },
    {
        "name": "jobapps_brain_context",
        "description": "Read the compact JobApps career brain: personal/job-search memory counts, recent events, and optional search results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
        "writes": False,
    },
    {
        "name": "jobapps_search_brain",
        "description": "Search the JobApps career brain for remembered conversations, decisions, people, companies, constraints, preferences, proof points, projects, and job-search patterns.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "entity_type": {"type": "string"},
                "event_type": {"type": "string"},
                "job_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
        "writes": False,
    },
    {
        "name": "jobapps_upsert_brain_entity",
        "description": "Create or update a canonical personal brain entity such as a person, company, project, constraint, decision theme, proof point, or preference.",
        "input_schema": {
            "type": "object",
            "required": ["entity_type", "title"],
            "properties": {
                "entity_type": {"type": "string"},
                "title": {"type": "string"},
                "slug": {"type": "string"},
                "summary": {"type": "string"},
                "status": {"type": "string"},
                "privacy": {"type": "string"},
                "source": {"type": "string"},
                "confidence": {"type": "number"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_record_brain_event",
        "description": "Record a sourced career-brain event for a conversation, correction, decision, revision, preference, person, company, project, networking move, daily note, or application step.",
        "input_schema": {
            "type": "object",
            "required": ["event_type", "title", "content"],
            "properties": {
                "event_type": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "entity_type": {"type": "string"},
                "entity_name": {"type": "string"},
                "entity_slug": {"type": "string"},
                "entity_id": {"type": "string"},
                "job_id": {"type": "string"},
                "source": {"type": "string"},
                "evidence_text": {"type": "string"},
                "confidence": {"type": "number"},
                "importance": {"type": "number"},
                "occurred_at": {"type": "string"},
                "hermes_session_id": {"type": "string"},
                "hermes_run_id": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_upsert_profile_fact",
        "description": "Create or update one durable profile fact in the JobApps database.",
        "input_schema": {
            "type": "object",
            "required": ["fact_key", "value"],
            "properties": {
                "fact_key": {"type": "string"},
                "value": {"type": "string"},
                "category": {"type": "string"},
                "source": {"type": "string"},
                "confidence": {"type": "number"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_upsert_proof_point",
        "description": "Create or update a truthful experience proof point used for matching jobs.",
        "input_schema": {
            "type": "object",
            "required": ["label", "summary", "evidence"],
            "properties": {
                "id": {"type": "string"},
                "label": {"type": "string"},
                "summary": {"type": "string"},
                "evidence": {"type": "string"},
                "role_family": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string"},
                "confidence": {"type": "number"},
                "status": {"type": "string"},
                "user_confirmed": {"type": "boolean"},
                "narrative_version": {"type": "string"},
                "allowed_uses": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string"},
                "valid_from": {"type": "string"},
                "valid_to": {"type": "string"},
                "superseded_by": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_search_evidence",
        "description": "Search app-owned evidence with lifecycle filters before ranking. Defaults to active, user-confirmed proof usable for the requested material.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "role_family": {"type": "string"},
                "use": {"type": "string"},
                "limit": {"type": "integer"},
                "include_inactive": {"type": "boolean"},
            },
        },
        "writes": False,
    },
    {
        "name": "jobapps_retrieve_for_job",
        "description": "Retrieve eligible current evidence for a stored job and report excluded stale, retired, superseded, or unconfirmed evidence.",
        "input_schema": {
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {"type": "string"},
                "use": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_discovery_status",
        "description": "Inspect the removable discovery layer: Exa key readiness, official ATS hydrators, and candidate counts.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "writes": False,
    },
    {
        "name": "jobapps_discover_jobs",
        "description": "Search for current candidate jobs through configured discovery providers. Exa uses EXA_API_KEY and stores candidates, but never applies.",
        "input_schema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "hydrate": {"type": "boolean"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_hydrate_job_url",
        "description": "Hydrate one job URL through official ATS surfaces when available and store it as a discovery candidate.",
        "input_schema": {
            "type": "object",
            "required": ["url"],
            "properties": {"url": {"type": "string"}},
        },
        "writes": True,
    },
    {
        "name": "jobapps_prepare_discovered_job",
        "description": "Promote a stored discovery candidate into the normal JobApps opportunity workflow for blocker preflight, materials, and tracking.",
        "input_schema": {
            "type": "object",
            "required": ["candidate_id"],
            "properties": {"candidate_id": {"type": "string"}},
        },
        "writes": True,
    },
    {
        "name": "jobapps_networking_status",
        "description": "Inspect networking operator readiness: Exa people search and draft-only Gmail via gog.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "writes": False,
    },
    {
        "name": "jobapps_find_people",
        "description": "Search public people profiles with cheap Exa Search by default and cache contacts. Use Websets only as an explicit/missing-email fallback. This never contacts anyone or guesses private emails.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "company": {"type": "string"},
                "job_id": {"type": "string"},
                "limit": {"type": "integer"},
                "provider": {"type": "string", "description": "search (default), auto (search then Websets if no verified email), or websets (expensive explicit enrichment)."},
                "use_websets_fallback": {"type": "boolean", "description": "Run expensive Websets contact enrichment only if normal search finds no verified email."},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_create_gmail_draft",
        "description": "Create a Gmail draft through gog with --gmail-no-send. This tool cannot send email and only auto-fills a contact recipient when email_status is found.",
        "input_schema": {
            "type": "object",
            "required": ["subject", "body"],
            "properties": {
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "job_id": {"type": "string"},
                "contact_id": {"type": "string"},
                "to_email": {"type": "string"},
                "account": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_record_application_signal",
        "description": "Record one reusable signal extracted from a job description or application event.",
        "input_schema": {
            "type": "object",
            "required": ["job_id", "signal_type", "label", "value"],
            "properties": {
                "job_id": {"type": "string"},
                "signal_type": {"type": "string"},
                "label": {"type": "string"},
                "value": {"type": "string"},
                "evidence_text": {"type": "string"},
                "source": {"type": "string"},
                "confidence": {"type": "number"},
                "actionability": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_record_tailoring_requirement",
        "description": "Persist one JD-grounded tailoring requirement that generated materials must address.",
        "input_schema": {
            "type": "object",
            "required": ["job_id", "requirement"],
            "properties": {
                "job_id": {"type": "string"},
                "requirement": {"type": "string"},
                "source_text": {"type": "string"},
                "category": {"type": "string"},
                "priority": {"type": "number"},
                "status": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_record_portrayal_decision",
        "description": "Persist how a JD requirement changed material framing, with requirement/material/proof provenance.",
        "input_schema": {
            "type": "object",
            "required": ["job_id", "target", "after_text", "rationale"],
            "properties": {
                "job_id": {"type": "string"},
                "requirement_id": {"type": "string"},
                "material_id": {"type": "string"},
                "proof_id": {"type": "string"},
                "decision_type": {"type": "string"},
                "target": {"type": "string"},
                "before_text": {"type": "string"},
                "after_text": {"type": "string"},
                "rationale": {"type": "string"},
                "source": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_update_proof_lifecycle",
        "description": "Change whether a proof point can be used: active, candidate, needs_review, superseded, retired, forbidden, or archived.",
        "input_schema": {
            "type": "object",
            "required": ["proof_id"],
            "properties": {
                "proof_id": {"type": "string"},
                "status": {"type": "string"},
                "user_confirmed": {"type": "boolean"},
                "narrative_version": {"type": "string"},
                "allowed_uses": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string"},
                "valid_from": {"type": "string"},
                "valid_to": {"type": "string"},
                "superseded_by": {"type": "string"},
                "reason": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_evaluate_job",
        "description": "Create a structured local evaluation from a job and current JobApps database context.",
        "input_schema": {
            "type": "object",
            "required": ["job"],
            "properties": {"job": {"type": "object"}, "context": {"type": "object"}},
        },
        "writes": False,
    },
    {
        "name": "jobapps_prepare_opportunity",
        "description": "Parse/persist an opportunity and record blocker preflight, signals, tailoring targets, and prompt handoff. Does not author materials.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "message": {"type": "string"},
                "job": {"type": "object"},
                "title": {"type": "string"},
                "company": {"type": "string"},
                "location": {"type": "string"},
                "url": {"type": "string"},
                "description": {"type": "string"},
                "user_notes": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_start_material_prep",
        "description": "Queue background Hermes material-prep runs for one job, selected jobs, or all pending apply-intent jobs. Returns immediately and deduplicates active same-job runs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "job_ids": {"type": "array", "items": {"type": "string"}},
                "scope": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_draft_materials",
        "description": "Specialist/legacy deterministic draft helper. Prefer native Hermes writing tools for candidate-facing materials.",
        "input_schema": {
            "type": "object",
            "required": ["job", "evaluation"],
            "properties": {"job": {"type": "object"}, "evaluation": {"type": "object"}, "context": {"type": "object"}},
        },
        "writes": False,
    },
    {
        "name": "jobapps_record_job",
        "description": "Persist a job and its evaluation in the JobApps database.",
        "input_schema": {
            "type": "object",
            "required": ["job", "evaluation"],
            "properties": {"job_id": {"type": "string"}, "job": {"type": "object"}, "evaluation": {"type": "object"}},
        },
        "writes": True,
    },
    {
        "name": "jobapps_save_material",
        "description": "Record/link an already-created material artifact in JobApps state. Use Hermes-native file tools for writing/editing content first.",
        "input_schema": {
            "type": "object",
            "required": ["job_id", "kind", "content"],
            "properties": {
                "job_id": {"type": "string"},
                "kind": {"type": "string"},
                "content": {},
                "rationale": {"type": "string"},
                "format": {"type": "string"},
                "file_path": {"type": "string"},
                "source": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_create_resume_typst",
        "description": "Specialist/legacy authoring helper. Prefer Hermes-native file tools for resume creation, then jobapps_save_material for state linkage.",
        "input_schema": {
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {"type": "string"},
                "name": {"type": "string"},
                "headline": {"type": "string"},
                "sections": {"type": "array", "items": {"type": "object"}},
                "rationale": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_create_resume_tex",
        "description": "Legacy alias for resume creation. Prefer Hermes-native file tools for resume creation, then jobapps_save_material for state linkage.",
        "input_schema": {
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {"type": "string"},
                "name": {"type": "string"},
                "headline": {"type": "string"},
                "sections": {"type": "array", "items": {"type": "object"}},
                "rationale": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_create_cover_letter_tex",
        "description": "Specialist/legacy authoring helper. Prefer Hermes-native file tools for cover-letter creation, then jobapps_save_material for state linkage.",
        "input_schema": {
            "type": "object",
            "required": ["job_id", "body"],
            "properties": {
                "job_id": {"type": "string"},
                "body": {"type": "string"},
                "company": {"type": "string"},
                "role_title": {"type": "string"},
                "name": {"type": "string"},
                "rationale": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_patch_material",
        "description": "Specialist provenance patch helper. Prefer Hermes-native patch/file tools for edits, then record important changes in JobApps state.",
        "input_schema": {
            "type": "object",
            "required": ["material_id", "old_string", "new_string", "reason"],
            "properties": {
                "material_id": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
                "reason": {"type": "string"},
                "requirement": {"type": "string"},
                "proof_id": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_diff_material",
        "description": "Specialist material diff helper. Prefer Hermes-native diff/patch inspection unless JobApps material metadata is required.",
        "input_schema": {
            "type": "object",
            "required": ["material_id"],
            "properties": {
                "material_id": {"type": "string"},
                "proposed_content": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
        },
        "writes": False,
    },
    {
        "name": "jobapps_compile_material_pdf",
        "description": "Specialist compile helper for app-owned material records. Prefer Hermes-native terminal compilation when editing local files directly.",
        "input_schema": {
            "type": "object",
            "required": ["material_id"],
            "properties": {"material_id": {"type": "string"}},
        },
        "writes": True,
    },
    {
        "name": "jobapps_mark_material_ready_for_review",
        "description": "Mark one or more materials ready for human review without creating a dashboard Action.",
        "input_schema": {
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {"type": "string"},
                "material_ids": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_save_prompt",
        "description": "Save a prompt build so Hermes and the app can reproduce a workflow run.",
        "input_schema": {
            "type": "object",
            "required": ["prompt_type", "prompt"],
            "properties": {
                "job_id": {"type": "string"},
                "prompt_type": {"type": "string"},
                "prompt": {"type": "string"},
                "context_snapshot": {"type": "object"},
                "status": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_record_research_note",
        "description": "Record company, job, sponsorship, or networking research with source and confidence.",
        "input_schema": {
            "type": "object",
            "required": ["subject", "summary"],
            "properties": {
                "job_id": {"type": "string"},
                "subject": {"type": "string"},
                "source_url": {"type": "string"},
                "summary": {"type": "string"},
                "confidence": {"type": "number"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_record_application_change",
        "description": "Record why a resume, cover letter, or answer changed for a role.",
        "input_schema": {
            "type": "object",
            "required": ["job_id", "change_type", "target", "after_text", "reason"],
            "properties": {
                "job_id": {"type": "string"},
                "material_id": {"type": "string"},
                "change_type": {"type": "string"},
                "target": {"type": "string"},
                "before_text": {"type": "string"},
                "after_text": {"type": "string"},
                "reason": {"type": "string"},
                "requirement": {"type": "string"},
                "proof_id": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_record_learning_pattern",
        "description": "Persist a reusable user correction or portrayal preference so future job materials follow it.",
        "input_schema": {
            "type": "object",
            "required": ["pattern_type", "trigger", "preference"],
            "properties": {
                "pattern_type": {"type": "string"},
                "trigger": {"type": "string"},
                "preference": {"type": "string"},
                "source": {"type": "string"},
                "confidence": {"type": "number"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_create_progress_item",
        "description": "Create a purposeful progress item for real user work such as a networking send or follow-up; do not use this for review materials, research, generic apply/submit reminders, or other obvious workflow steps.",
        "input_schema": {
            "type": "object",
            "required": ["title"],
            "properties": {
                "job_id": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"type": "string"},
                "status": {"type": "string"},
                "due_date": {"type": "string"},
                "notes": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_create_followup",
        "description": "Create a follow-up reminder tied to a job or contact.",
        "input_schema": {
            "type": "object",
            "required": ["due_date", "reason"],
            "properties": {
                "job_id": {"type": "string"},
                "contact_id": {"type": "string"},
                "due_date": {"type": "string"},
                "reason": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_update_status",
        "description": "Record an application status transition.",
        "input_schema": {
            "type": "object",
            "required": ["job_id", "status"],
            "properties": {
                "job_id": {"type": "string"},
                "status": {"type": "string"},
                "note": {"type": "string"},
                "hermes_run_id": {"type": "string"},
                "hermes_session_id": {"type": "string"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_request_approval",
        "description": "Create a pending human approval gate for an external action. Do not use approvals for ordinary material review.",
        "input_schema": {
            "type": "object",
            "required": ["action"],
            "properties": {
                "job_id": {"type": "string"},
                "action": {"type": "string"},
                "status": {"type": "string"},
                "payload": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_update_approval",
        "description": "Update a human approval gate after explicit user review.",
        "input_schema": {
            "type": "object",
            "required": ["approval_id", "status"],
            "properties": {
                "approval_id": {"type": "string"},
                "status": {"type": "string"},
                "payload": {"type": "object"},
            },
        },
        "writes": True,
    },
]


DEFAULT_TOOL_NAMES = frozenset(
    {
        # Compact retrieval: use these instead of broad dashboard/context dumps.
        "jobapps_brain_context",
        "jobapps_search_brain",
        "jobapps_upsert_brain_entity",
        "jobapps_upsert_profile_fact",
        "jobapps_upsert_proof_point",
        "jobapps_search_evidence",
        "jobapps_retrieve_for_job",
        "jobapps_update_proof_lifecycle",
        "jobapps_evaluate_job",
        # Opportunity intake, discovery, and run orchestration.
        "jobapps_discover_jobs",
        "jobapps_hydrate_job_url",
        "jobapps_prepare_discovered_job",
        "jobapps_prepare_opportunity",
        "jobapps_start_material_prep",
        # App-state ledger writes. Hermes-native tools should create/edit files first.
        "jobapps_record_job",
        "jobapps_save_material",
        "jobapps_mark_material_ready_for_review",
        "jobapps_record_research_note",
        "jobapps_record_application_signal",
        "jobapps_record_tailoring_requirement",
        "jobapps_record_portrayal_decision",
        "jobapps_record_application_change",
        "jobapps_record_learning_pattern",
        "jobapps_record_brain_event",
        "jobapps_update_status",
        # Networking state and draft-only communication support.
        "jobapps_find_people",
        "jobapps_create_gmail_draft",
        "jobapps_create_progress_item",
        "jobapps_create_followup",
        "jobapps_request_approval",
        "jobapps_update_approval",
    }
)

SPECIALIST_TOOL_NAMES = frozenset(
    {
        # App-owned authoring helpers retained for dashboard/internal automation.
        # Native Hermes file/patch/terminal tools should handle normal writing,
        # editing, diffing, and compilation work in Hermes sessions.
        "jobapps_draft_materials",
        "jobapps_create_resume_typst",
        "jobapps_create_resume_tex",
        "jobapps_create_cover_letter_tex",
        "jobapps_patch_material",
        "jobapps_diff_material",
        "jobapps_compile_material_pdf",
    }
)

DEBUG_TOOL_NAMES = frozenset(
    {
        "jobapps_read_context",
        "jobapps_database_health",
        "jobapps_tool_call_retention",
        "jobapps_discovery_status",
        "jobapps_networking_status",
        "jobapps_save_prompt",
    }
)


def _tool_exposure(name: str) -> str:
    if name in DEFAULT_TOOL_NAMES:
        return "default"
    if name in DEBUG_TOOL_NAMES:
        return "debug"
    return "specialist"


def _with_tool_routing_metadata(spec: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(spec)
    exposure = _tool_exposure(str(enriched.get("name") or ""))
    enriched["exposure"] = exposure
    if exposure == "default":
        enriched["tool_boundary"] = "JobApps retrieval/state ledger; use Hermes-native tools for general writing, file edits, patching, and compilation."
    elif exposure == "debug":
        enriched["tool_boundary"] = "Debug/audit only; do not expose in normal material-generation context."
    else:
        enriched["tool_boundary"] = "Specialist/internal helper; use only when app-owned state semantics are required and Hermes-native tools are not enough."
    return enriched


ALL_TOOL_SPECS: tuple[dict[str, Any], ...] = tuple(_with_tool_routing_metadata(spec) for spec in TOOL_SPECS)
TOOL_SPECS = [spec for spec in ALL_TOOL_SPECS if spec["exposure"] == "default"]


def specs_for_exposure(exposure: str = "default") -> list[dict[str, Any]]:
    normalized = (exposure or "default").lower()
    if normalized in {"all", "full"}:
        return [dict(spec) for spec in ALL_TOOL_SPECS]
    if normalized in {"default", "normal", "visible"}:
        return [dict(spec) for spec in TOOL_SPECS]
    return [dict(spec) for spec in ALL_TOOL_SPECS if spec["exposure"] == normalized]


class AgentToolbox:
    def __init__(
        self,
        repo: JobRepository,
        config: dict[str, Any],
        *,
        hermes_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.repo = repo
        self.config = config
        self._hermes_factory = hermes_factory
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "jobapps_read_context": self._read_context,
            "jobapps_database_health": self._database_health,
            "jobapps_tool_call_retention": self._tool_call_retention,
            "jobapps_brain_context": self._brain_context,
            "jobapps_search_brain": self._search_brain,
            "jobapps_upsert_brain_entity": self._upsert_brain_entity,
            "jobapps_record_brain_event": self._record_brain_event,
            "jobapps_upsert_profile_fact": self._upsert_profile_fact,
            "jobapps_upsert_proof_point": self._upsert_proof_point,
            "jobapps_search_evidence": self._search_evidence,
            "jobapps_retrieve_for_job": self._retrieve_for_job,
            "jobapps_discovery_status": self._discovery_status,
            "jobapps_discover_jobs": self._discover_jobs,
            "jobapps_hydrate_job_url": self._hydrate_job_url,
            "jobapps_prepare_discovered_job": self._prepare_discovered_job,
            "jobapps_networking_status": self._networking_status,
            "jobapps_find_people": self._find_people,
            "jobapps_create_gmail_draft": self._create_gmail_draft,
            "jobapps_record_application_signal": self._record_application_signal,
            "jobapps_record_tailoring_requirement": self._record_tailoring_requirement,
            "jobapps_record_portrayal_decision": self._record_portrayal_decision,
            "jobapps_update_proof_lifecycle": self._update_proof_lifecycle,
            "jobapps_evaluate_job": self._evaluate_job,
            "jobapps_prepare_opportunity": self._prepare_opportunity,
            "jobapps_start_material_prep": self._start_material_prep,
            "jobapps_draft_materials": self._draft_materials,
            "jobapps_record_job": self._record_job,
            "jobapps_save_material": self._save_material,
            "jobapps_create_resume_typst": self._create_resume_typst,
            "jobapps_create_resume_tex": self._create_resume_tex,
            "jobapps_create_cover_letter_tex": self._create_cover_letter_tex,
            "jobapps_patch_material": self._patch_material,
            "jobapps_diff_material": self._diff_material,
            "jobapps_compile_material_pdf": self._compile_material_pdf,
            "jobapps_mark_material_ready_for_review": self._mark_material_ready_for_review,
            "jobapps_save_prompt": self._save_prompt,
            "jobapps_record_research_note": self._record_research_note,
            "jobapps_record_application_change": self._record_application_change,
            "jobapps_record_learning_pattern": self._record_learning_pattern,
            "jobapps_create_progress_item": self._create_progress_item,
            "jobapps_create_followup": self._create_followup,
            "jobapps_update_status": self._update_status,
            "jobapps_request_approval": self._request_approval,
            "jobapps_update_approval": self._update_approval,
        }

    def specs(self, exposure: str = "default") -> list[dict[str, Any]]:
        """Return JobApps tool schemas for a given exposure tier.

        Default exposure is intentionally state/retrieval oriented. Authoring,
        patching, diffing, compilation, broad context dumps, and audit helpers
        remain executable by name for the dashboard/internal workflows, but are
        not advertised to normal Hermes runs where native Hermes tools are the
        right workbench.
        """
        return specs_for_exposure(exposure)

    def execute(self, name: str, payload: dict[str, Any], run_id: str | None = None) -> dict[str, Any]:
        if name not in self._handlers:
            raise KeyError(f"Unknown tool: {name}")
        try:
            output = self._handlers[name](payload)
            status = "completed"
        except Exception as exc:
            output = {"error": str(exc)}
            status = "failed"
            self.repo.record_tool_call(name, payload, output, status=status, run_id=run_id)
            raise
        self.repo.record_tool_call(name, payload, output, status=status, run_id=run_id)
        return output

    def _read_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.dashboard() | {"career_context": self.repo.career_context()}

    def _database_health(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.database_health()

    def _tool_call_retention(self, payload: dict[str, Any]) -> dict[str, Any]:
        retain_days = parse_limit(payload.get("retain_days", 30), default=30, maximum=3650)
        limit = parse_limit(payload.get("limit", 100), default=100, maximum=2000)
        min_bytes = parse_limit(
            payload.get("min_bytes", TOOL_CALL_INLINE_LIMIT_BYTES),
            default=TOOL_CALL_INLINE_LIMIT_BYTES,
            maximum=1_000_000_000,
        )
        apply_changes = parse_bool(payload.get("apply", False), "apply", default=False)
        if apply_changes:
            return self.repo.archive_old_tool_calls(
                retain_days=retain_days,
                limit=limit,
                min_bytes=min_bytes,
                dry_run=False,
            )
        report = self.repo.tool_call_retention_report(retain_days=retain_days, limit=min(limit, 100))
        preview = self.repo.archive_old_tool_calls(
            retain_days=retain_days,
            limit=limit,
            min_bytes=min_bytes,
            dry_run=True,
        )
        return report | {"cleanup_preview": preview}

    def _brain_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.brain_context(
            query=payload.get("query", ""),
            limit=parse_limit(payload.get("limit", 12), default=12, maximum=80),
        )

    def _search_brain(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.search_brain(
            payload["query"],
            entity_type=payload.get("entity_type"),
            event_type=payload.get("event_type"),
            job_id=payload.get("job_id"),
            limit=parse_limit(payload.get("limit", 12), default=12, maximum=80),
        )

    def _upsert_brain_entity(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.upsert_brain_entity(
            payload["entity_type"],
            payload["title"],
            slug=payload.get("slug", ""),
            summary=payload.get("summary", ""),
            status=payload.get("status", "active"),
            privacy=payload.get("privacy", "private"),
            source=payload.get("source", "agent"),
            confidence=float(payload.get("confidence", 0.8)),
            metadata=payload.get("metadata", {}),
        )

    def _record_brain_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.record_brain_event(
            payload["event_type"],
            payload["title"],
            payload["content"],
            entity_type=payload.get("entity_type", "job_search"),
            entity_name=payload.get("entity_name", ""),
            entity_slug=payload.get("entity_slug", ""),
            entity_id=payload.get("entity_id"),
            job_id=payload.get("job_id"),
            source=payload.get("source", "agent"),
            evidence_text=payload.get("evidence_text", ""),
            confidence=float(payload.get("confidence", 0.8)),
            importance=float(payload.get("importance", 0.5)),
            occurred_at=payload.get("occurred_at"),
            hermes_session_id=payload.get("hermes_session_id"),
            hermes_run_id=payload.get("hermes_run_id"),
            metadata=payload.get("metadata", {}),
        )

    def _upsert_profile_fact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.upsert_profile_fact(
            payload["fact_key"],
            payload["value"],
            payload.get("category", "profile"),
            payload.get("source", "agent"),
            float(payload.get("confidence", 1.0)),
        )

    def _upsert_proof_point(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.upsert_proof_point(
            label=payload["label"],
            summary=payload["summary"],
            evidence=payload["evidence"],
            role_family=payload.get("role_family", "other"),
            tags=payload.get("tags", []),
            source=payload.get("source", "agent"),
            confidence=float(payload.get("confidence", 1.0)),
            proof_id=payload.get("id"),
            status=payload.get("status", "active"),
            user_confirmed=parse_bool(payload.get("user_confirmed", True), "user_confirmed", default=True),
            narrative_version=payload.get("narrative_version", "current"),
            allowed_uses=payload.get("allowed_uses"),
            risk_level=payload.get("risk_level", "safe"),
            valid_from=payload.get("valid_from"),
            valid_to=payload.get("valid_to"),
            superseded_by=payload.get("superseded_by"),
        )

    def _search_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.search_evidence(
            payload["query"],
            role_family=payload.get("role_family"),
            use=payload.get("use", "resume"),
            limit=parse_limit(payload.get("limit", 8), default=8),
            include_inactive=parse_bool(payload.get("include_inactive", False), "include_inactive", default=False),
        )

    def _retrieve_for_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.retrieve_for_job(
            payload["job_id"],
            use=payload.get("use", "resume"),
            limit=parse_limit(payload.get("limit", 8), default=8),
        )

    def _discovery_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        return DiscoveryService(self.repo, self.config).status()

    def _discover_jobs(self, payload: dict[str, Any]) -> dict[str, Any]:
        return DiscoveryService(self.repo, self.config).search_exa(
            payload["query"],
            limit=parse_limit(payload.get("limit", 8), default=8, maximum=25),
            hydrate=parse_bool(payload.get("hydrate", True), "hydrate", default=True),
        )

    def _hydrate_job_url(self, payload: dict[str, Any]) -> dict[str, Any]:
        return DiscoveryService(self.repo, self.config).hydrate_url(payload["url"])

    def _prepare_discovered_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        from .workflow import JobAppsWorkflow

        service = DiscoveryService(self.repo, self.config)
        workflow = JobAppsWorkflow(self.repo, self)
        return service.prepare_candidate(payload["candidate_id"], workflow.prepare_opportunity)

    def _networking_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        return NetworkingService(self.repo, self.config).status()

    def _find_people(self, payload: dict[str, Any]) -> dict[str, Any]:
        return NetworkingService(self.repo, self.config).search_people(
            query=payload.get("query", ""),
            company=payload.get("company", ""),
            job_id=payload.get("job_id", ""),
            limit=parse_limit(payload.get("limit", 6), default=6, maximum=15),
            provider=payload.get("provider", ""),
            use_websets_fallback=parse_bool(payload.get("use_websets_fallback"), "use_websets_fallback", default=False),
        )

    def _create_gmail_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        return NetworkingService(self.repo, self.config).create_gmail_draft(
            subject=payload["subject"],
            body=payload["body"],
            job_id=payload.get("job_id", ""),
            contact_id=payload.get("contact_id", ""),
            to_email=payload.get("to_email", ""),
            account=payload.get("account", ""),
        )

    def _record_application_signal(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.record_application_signal(
            payload["job_id"],
            payload["signal_type"],
            payload["label"],
            payload["value"],
            evidence_text=payload.get("evidence_text", ""),
            source=payload.get("source", "agent"),
            confidence=float(payload.get("confidence", 0.7)),
            actionability=payload.get("actionability", "medium"),
            metadata=payload.get("metadata", {}),
        )

    def _record_tailoring_requirement(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.record_tailoring_requirement(
            payload["job_id"],
            payload["requirement"],
            source_text=payload.get("source_text", ""),
            category=payload.get("category", "general"),
            priority=float(payload.get("priority", 0.5)),
            status=payload.get("status", "targeted"),
            metadata=payload.get("metadata", {}),
        )

    def _record_portrayal_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.record_portrayal_decision(
            payload["job_id"],
            payload["target"],
            payload["after_text"],
            payload["rationale"],
            requirement_id=payload.get("requirement_id"),
            material_id=payload.get("material_id"),
            proof_id=payload.get("proof_id"),
            before_text=payload.get("before_text", ""),
            decision_type=payload.get("decision_type", "resume_tailoring"),
            source=payload.get("source", "agent"),
            metadata=payload.get("metadata", {}),
        )

    def _update_proof_lifecycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.update_proof_point_lifecycle(
            payload["proof_id"],
            status=payload.get("status"),
            user_confirmed=parse_optional_bool(payload, "user_confirmed"),
            narrative_version=payload.get("narrative_version"),
            allowed_uses=payload.get("allowed_uses"),
            risk_level=payload.get("risk_level"),
            valid_from=payload.get("valid_from"),
            valid_to=payload.get("valid_to"),
            superseded_by=payload.get("superseded_by"),
            reason=payload.get("reason", ""),
        )

    def _evaluate_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = payload.get("context") or self.repo.career_context()
        return evaluate_job(payload["job"], context, self.config)

    def _prepare_opportunity(self, payload: dict[str, Any]) -> dict[str, Any]:
        from .chat import parse_job_from_message
        from .workflow import JobAppsWorkflow

        if isinstance(payload.get("job"), dict):
            job = dict(payload["job"])
        elif payload.get("text") or payload.get("message"):
            job = parse_job_from_message(str(payload.get("text") or payload.get("message") or ""))
        else:
            job = {
                "title": payload.get("title", ""),
                "company": payload.get("company", ""),
                "location": payload.get("location", ""),
                "url": payload.get("url", ""),
                "description": payload.get("description", ""),
                "user_notes": payload.get("user_notes", ""),
            }
        workflow = JobAppsWorkflow(self.repo, self)
        return workflow.prepare_opportunity(job)

    def _start_material_prep(self, payload: dict[str, Any]) -> dict[str, Any]:
        from .runs import HermesRunManager

        job_ids = _material_prep_job_ids(payload, self.repo.dashboard())
        if not job_ids:
            return {
                "requested_count": 0,
                "queued_count": 0,
                "existing_count": 0,
                "failed_count": 0,
                "results": [],
            }
        hermes_config = self.config.get("hermes", {})
        manager = HermesRunManager(
            self.repo,
            self,
            self._make_hermes_client(),
            session_key=hermes_config.get("session_key", "jobapps"),
        )
        return manager.start_for_jobs(job_ids)

    def _make_hermes_client(self) -> Any:
        if self._hermes_factory:
            return self._hermes_factory(self.config)
        from .hermes_client import HermesClient

        hermes_config = self.config.get("hermes", {})
        return HermesClient(
            base_url=hermes_config.get("api_base"),
            api_key=hermes_config.get("api_key"),
            model=hermes_config.get("model"),
        )

    def _draft_materials(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = payload.get("context") or self.repo.career_context()
        return draft_materials(payload["job"], payload["evaluation"], context, self.config)

    def _record_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = dict(payload["job"])
        if payload.get("job_id") and not job.get("id"):
            job["id"] = payload["job_id"]
        return self.repo.create_job(job, payload["evaluation"])

    def _save_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = payload["content"]
        material_format = normalize_material_format(payload.get("format", "text"))
        material_kind = normalize_material_kind_for_db(
            payload["kind"],
            format=material_format,
            file_path=str(payload.get("file_path", "")),
            content=content,
        )
        metadata = dict(payload.get("metadata", {}) or {})
        if isinstance(content, dict):
            for key in ("pdf_path", "source_path", "source_format", "template", "display_name", "filename", "name"):
                if content.get(key) and not metadata.get(key):
                    metadata[key] = content[key]
        file_path = payload.get("file_path", "")
        if file_path:
            file_path = str(_validate_material_path(self.config, file_path))
        elif material_format == "pdf" and isinstance(content, dict) and content.get("pdf_path"):
            file_path = str(_validate_material_path(self.config, content["pdf_path"]))
        if material_format in {"tex", "typ"} and not file_path:
            job = self.repo.get_job(payload["job_id"])["job"]
            filename = job_material_filename(job, material_kind, material_format)
            root = self.config.get("materials_path", "data/materials")
            file_path = write_material_artifact(payload["job_id"], filename, str(content), root=root)
        return self.repo.save_material(
            payload["job_id"],
            material_kind,
            content,
            payload.get("rationale", ""),
            format=material_format,
            file_path=file_path,
            source=payload.get("source", "agent"),
            metadata=metadata,
        )

    def _create_resume_typst(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = self.repo.get_job(payload["job_id"])["job"]
        context = self.repo.career_context()
        name = payload.get("name") or _profile_value(context, "name", "Prashant Shah")
        headline = payload.get("headline") or f"AI Engineer focused on agentic systems for {job.get('title') or 'target roles'}"
        typst = build_full_resume_typst(name=name, headline=headline, sections=payload.get("sections") or [])
        filename = job_material_filename(job, "resume", "typ")
        file_path = write_material_artifact(payload["job_id"], filename, typst, root=self.config.get("materials_path", "data/materials"))
        return self.repo.save_material(
            payload["job_id"],
            "resume",
            typst,
            payload.get("rationale", "Full resume Typst artifact for this application."),
            format="typ",
            file_path=file_path,
            source="agent",
            metadata={
                "artifact_role": "full_resume",
                "renderer": "typst",
                "template": "@preview/simple-technical-resume:0.1.1",
                "provenance": {
                    "job_title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "fact_policy": "user_confirmed_only",
                },
            },
        )

    def _create_resume_tex(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible tool name; resumes are Typst-first now."""

        return self._create_resume_typst(payload)

    def _create_cover_letter_tex(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = self.repo.get_job(payload["job_id"])["job"]
        context = self.repo.career_context()
        tex = build_full_cover_letter_tex(
            body=payload["body"],
            company=payload.get("company") or job.get("company") or "Hiring Team",
            role_title=payload.get("role_title") or job.get("title") or "Target Role",
            name=payload.get("name") or _profile_value(context, "name", "Prashant Shah"),
        )
        filename = job_material_filename(job, "cover_letter", "tex")
        file_path = write_material_artifact(
            payload["job_id"], filename, tex, root=self.config.get("materials_path", "data/materials")
        )
        return self.repo.save_material(
            payload["job_id"],
            "cover_letter",
            tex,
            payload.get("rationale", "Cover-letter TeX artifact for this application."),
            format="tex",
            file_path=file_path,
            source="agent",
            metadata={
                "artifact_role": "cover_letter",
                "provenance": {
                    "job_title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "fact_policy": "user_confirmed_only",
                },
            },
        )

    def _patch_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self.repo.get_material(payload["material_id"])
        proof_id = payload.get("proof_id")
        if proof_id:
            self.repo.validate_proof_for_use(proof_id, provenance_use_for_material(material))
        before = str(material.get("content") or "")
        after = patch_text(
            before,
            payload["old_string"],
            payload["new_string"],
            replace_all=parse_bool(payload.get("replace_all", False), "replace_all", default=False),
        )
        diff = text_diff(before, after, fromfile=f"{material['kind']}@before", tofile=f"{material['kind']}@after")
        file_path = material.get("file_path") or ""
        if material.get("format") in {"tex", "typ"}:
            if not file_path:
                job = self.repo.get_job(material["job_id"])["job"]
                extension = "typ" if material.get("format") == "typ" else "tex"
                file_path = write_material_artifact(
                    material["job_id"],
                    job_material_filename(job, material["kind"], extension),
                    after,
                    root=self.config.get("materials_path", "data/materials"),
                )
            else:
                safe_path = _validate_material_path(self.config, file_path)
                safe_path.parent.mkdir(parents=True, exist_ok=True)
                safe_path.write_text(after, encoding="utf-8")
                file_path = str(safe_path)
        updated = self.repo.update_material(
            material["id"],
            content=after,
            file_path=file_path or None,
            metadata={"last_edit_reason": payload.get("reason", ""), "review_status": "draft"},
        )
        revision = self.repo.record_material_revision(
            material["id"],
            before_text=before,
            after_text=after,
            diff=diff,
            reason=payload.get("reason", ""),
            requirement=payload.get("requirement", ""),
            proof_id=payload.get("proof_id"),
        )
        self.repo.record_application_change(
            material["job_id"],
            "material_patch",
            f"{material['kind']}.{material.get('format') or 'text'}",
            after,
            payload.get("reason", ""),
            material_id=material["id"],
            before_text=before,
            requirement=payload.get("requirement", ""),
            proof_id=payload.get("proof_id"),
        )
        return {"material": updated, "revision": revision, "diff": diff}

    def _diff_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self.repo.get_material(payload["material_id"])
        before = str(material.get("content") or "")
        if "proposed_content" in payload:
            after = str(payload.get("proposed_content") or "")
        else:
            after = patch_text(
                before,
                payload.get("old_string", ""),
                payload.get("new_string", ""),
                replace_all=parse_bool(payload.get("replace_all", False), "replace_all", default=False),
            )
        return {
            "material_id": material["id"],
            "changed": before != after,
            "diff": text_diff(before, after, fromfile=f"{material['kind']}@current", tofile=f"{material['kind']}@proposed"),
        }

    def _compile_material_pdf(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self.repo.get_material(payload["material_id"])
        material_format = normalize_material_format(material.get("format"))
        if material_format not in {"tex", "typ"}:
            return {
                "ok": False,
                "status": "unsupported_format",
                "material_id": material["id"],
                "next_step": "Only Typst or TeX materials can be compiled to PDF.",
            }
        file_path = material.get("file_path") or ""
        if not file_path:
            job = self.repo.get_job(material["job_id"])["job"]
            file_path = write_material_artifact(
                material["job_id"],
                job_material_filename(job, material["kind"], material_format),
                str(material.get("content") or ""),
                root=self.config.get("materials_path", "data/materials"),
            )
            material = self.repo.update_material(material["id"], file_path=file_path)
        file_path = str(_validate_material_path(self.config, file_path))
        if material_format == "typ":
            result = compile_typst_to_pdf(file_path, config=self.config)
        else:
            result = compile_tex_to_pdf(file_path, config=self.config)
        updated = self.repo.update_material(
            material["id"],
            metadata={
                "compile": result,
                "pdf_path": result.get("pdf_path", ""),
                "verification": result.get("verification", {}),
                "review_status": "compiled" if result.get("ok") else "compile_blocked",
            },
        )
        result["material"] = updated
        result["material_id"] = material["id"]
        return result

    def _mark_material_ready_for_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = self.repo.get_job(payload["job_id"])
        material_ids = payload.get("material_ids") or [item["id"] for item in job.get("materials", [])]
        job_material_ids = {item["id"] for item in job.get("materials", [])}
        outside_job = [material_id for material_id in material_ids if material_id not in job_material_ids]
        if outside_job:
            raise ValueError("All material_ids must belong to the requested job.")
        updated_materials = [
            self.repo.update_material(material_id, metadata={"review_status": "ready_for_review"})
            for material_id in material_ids
        ]
        reason = payload.get("reason", "Materials ready for final human review.")
        return {"approval": None, "materials": updated_materials, "progress_item": None, "reason": reason}

    def _save_prompt(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.save_prompt_build(
            payload["prompt_type"],
            payload["prompt"],
            job_id=payload.get("job_id"),
            context_snapshot=payload.get("context_snapshot", {}),
            status=payload.get("status", "drafted"),
        )

    def _record_research_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.save_research_note(
            payload["subject"],
            payload["summary"],
            job_id=payload.get("job_id"),
            source_url=payload.get("source_url", ""),
            confidence=float(payload.get("confidence", 0.5)),
        )

    def _record_application_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.record_application_change(
            payload["job_id"],
            payload["change_type"],
            payload["target"],
            payload["after_text"],
            payload["reason"],
            material_id=payload.get("material_id"),
            before_text=payload.get("before_text", ""),
            requirement=payload.get("requirement", ""),
            proof_id=payload.get("proof_id"),
        )

    def _record_learning_pattern(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.record_learning_pattern(
            payload["pattern_type"],
            payload["trigger"],
            payload["preference"],
            source=payload.get("source", "agent"),
            confidence=float(payload.get("confidence", 0.8)),
            metadata=payload.get("metadata", {}),
        )

    def _create_progress_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.create_progress_item(
            payload["title"],
            job_id=payload.get("job_id"),
            kind=payload.get("kind", "task"),
            status=payload.get("status", "open"),
            due_date=payload.get("due_date", ""),
            notes=payload.get("notes", ""),
        )

    def _create_followup(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.create_followup(
            payload["due_date"],
            payload["reason"],
            job_id=payload.get("job_id"),
            contact_id=payload.get("contact_id"),
            status=payload.get("status", "open"),
        )

    def _update_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.record_event(
            payload["job_id"],
            "status_changed",
            {
                "status": payload["status"],
                "note": payload.get("note", ""),
                "hermes_run_id": payload.get("hermes_run_id", ""),
                "hermes_session_id": payload.get("hermes_session_id", ""),
            },
        )

    def _request_approval(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.create_approval(
            payload["action"],
            job_id=payload.get("job_id"),
            status=payload.get("status", "pending"),
            payload=payload.get("payload", {}),
        )

    def _update_approval(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repo.update_approval(
            payload["approval_id"],
            payload["status"],
            payload=payload.get("payload", {}),
        )


def normalize_material_format(value: Any) -> str:
    return normalize_material_format_for_db(value)


def parse_bool(value: Any, name: str, *, default: bool | None = None) -> bool:
    if value is None:
        if default is None:
            raise ValueError(f"{name} must be a boolean, not null.")
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be a boolean true/false value, not {type(value).__name__}.")


def parse_optional_bool(payload: dict[str, Any], name: str) -> bool | None:
    if name not in payload:
        return None
    return parse_bool(payload.get(name), name)


def parse_limit(value: Any, *, default: int = 8, maximum: int = 50) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def provenance_use_for_material(material: dict[str, Any]) -> str:
    kind = str(material.get("kind") or "").lower()
    if "cover" in kind or "letter" in kind:
        return "cover_letter"
    if "outreach" in kind or "network" in kind:
        return "outreach"
    if "interview" in kind:
        return "interview"
    return "resume"


def _material_prep_job_ids(payload: dict[str, Any], dashboard: dict[str, Any]) -> list[str]:
    job_ids: list[str] = []
    if payload.get("job_id"):
        job_ids.append(str(payload["job_id"]))
    raw_job_ids = payload.get("job_ids")
    if isinstance(raw_job_ids, list):
        job_ids.extend(str(item) for item in raw_job_ids)
    scope = str(payload.get("scope") or "").strip().lower()
    if scope in {"pending", "all_pending", "apply_intent"}:
        job_ids.extend(_pending_material_prep_job_ids(dashboard.get("jobs", [])))
    output: list[str] = []
    seen: set[str] = set()
    for job_id in job_ids:
        normalized = str(job_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _pending_material_prep_job_ids(jobs: list[dict[str, Any]]) -> list[str]:
    blocked_statuses = {"applied", "waiting", "closed", "rejected", "declined", "archived", "hermes_completed", "skip", "skipped", "not_interested", "not_needed"}
    output: list[str] = []
    for job in jobs:
        decision = str(job.get("decision") or job.get("evaluation", {}).get("decision") or "pending").lower()
        status = str(job.get("status") or "").lower()
        active_run = job.get("active_run") or {}
        if decision == "skip" or status in blocked_statuses:
            continue
        if active_run.get("status") in ACTIVE_HERMES_RUN_STATUSES:
            continue
        job_id = str(job.get("id") or "").strip()
        if job_id:
            output.append(job_id)
    return output


def _profile_value(context: dict[str, Any], key: str, fallback: str) -> str:
    for fact in context.get("profile_facts", []):
        if fact.get("fact_key") == key and fact.get("value"):
            return str(fact["value"])
    return fallback


def _validate_material_path(config: dict[str, Any], file_path: str | Path) -> Path:
    root = resolve_project_path(config.get("materials_path", "data/materials")).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = resolve_project_path(candidate)
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if candidate.exists() and candidate.is_symlink():
        raise ValueError("Material file paths may not be symlinks.")
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Material file path must stay inside the configured materials_path.") from exc
    return resolved_candidate
