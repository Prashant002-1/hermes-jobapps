"""Tool handlers for JobApps database transitions.

These handlers are used by the local app and by the Hermes plugin wrapper.
Hermes-facing tool names use underscores because model tool schemas generally
expect simple function identifiers.
"""

from __future__ import annotations

import hashlib
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
    LEARNING_POLICY_SPECS,
    TOOL_CALL_INLINE_LIMIT_BYTES,
    normalize_material_format_for_db,
    normalize_material_kind_for_db,
)
from .writers import draft_materials


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "jobapps_read_context",
        "description": "Read a compact admin/debug context packet. Normal material work should prefer targeted retrieval tools instead of this broad context tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "use": {"type": "string", "description": "Evidence use filter, e.g. resume, cover_letter, outreach, interview."},
                "limit": {"type": "integer", "description": "Maximum recent rows for compact lists."},
                "include_dashboard": {"type": "boolean", "description": "Admin/debug only: attach compact dashboard state."},
            },
            "additionalProperties": False,
        },
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
        "description": "Read compact JobApps career-brain counts and optional targeted search results. Recent history is opt-in.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "include_recent": {"type": "boolean"},
                "event_type": {"type": "string"},
                "job_id": {"type": "string"},
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
        "name": "jobapps_list_people",
        "description": "List or search the user-curated People tracker. This does not return contacts merely discovered by Hermes or Exa.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "status": {"type": "string", "enum": ["all", "to_contact", "contacted", "follow_up", "paused"]},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        "writes": False,
    },
    {
        "name": "jobapps_upsert_person",
        "description": "Add or update one person the user explicitly wants in the personal networking tracker. Require a reason, preserve missing email as missing, and never infer or guess contact details.",
        "input_schema": {
            "type": "object",
            "required": ["name", "why_added"],
            "properties": {
                "person_id": {"type": "string", "description": "Existing People tracker ID when updating."},
                "name": {"type": "string"},
                "company": {"type": "string"},
                "role": {"type": "string"},
                "email": {"type": "string"},
                "linkedin_url": {"type": "string"},
                "why_added": {"type": "string"},
                "notes": {"type": "string"},
                "status": {"type": "string", "enum": ["to_contact", "contacted", "follow_up", "paused"]},
                "source": {"type": "string", "description": "Calling adapter, for example user, codex, hermes, or import."},
            },
            "additionalProperties": False,
        },
        "writes": True,
    },
    {
        "name": "jobapps_add_person_note",
        "description": "Append a note to one user-tracked person without replacing prior notes. Optionally update the personal networking status.",
        "input_schema": {
            "type": "object",
            "required": ["person_id", "note"],
            "properties": {
                "person_id": {"type": "string"},
                "note": {"type": "string"},
                "status": {"type": "string", "enum": ["to_contact", "contacted", "follow_up", "paused"]},
                "source": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "writes": True,
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
        "description": "Mark exact current materials ready for human review after source-bound semantic review and required resume layout QA. Does not create a dashboard Action.",
        "input_schema": {
            "type": "object",
            "required": ["job_id"],
            "properties": {
                "job_id": {"type": "string"},
                "material_ids": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
                "semantic_review": {
                    "type": "object",
                    "required": ["reviewer", "checks", "material_sha256"],
                    "properties": {
                        "reviewer": {"type": "string"},
                        "checks": {
                            "type": "object",
                            "required": ["truth", "role_relevance", "evidence_quality", "voice_and_no_scaffolding"],
                            "properties": {
                                "truth": {"type": "boolean"},
                                "role_relevance": {"type": "boolean"},
                                "evidence_quality": {"type": "boolean"},
                                "voice_and_no_scaffolding": {"type": "boolean"},
                            },
                        },
                        "material_sha256": {
                            "type": "object",
                            "description": "Map each selected material_id to the SHA-256 reviewed from its current source file or stored content.",
                        },
                    },
                },
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
        "description": (
            "Persist one canonical reusable policy. Facts belong in profile facts/proof points and one-job "
            "choices belong in portrayal decisions. Choose one fixed rule_key; code owns its type and scope. "
            "A newer write with the same rule_key automatically supersedes the older active version."
        ),
        "input_schema": {
            "type": "object",
            "required": ["rule_key", "trigger", "preference"],
            "properties": {
                "trigger": {"type": "string"},
                "preference": {"type": "string"},
                "rule_key": {
                    "type": "string",
                    "enum": [
                        "candidate.truth",
                        "candidate.voice",
                        "resume.layout",
                        "resume.summary",
                        "resume.evidence_selection",
                        "resume.bullets",
                        "cover_letter.substance",
                        "outreach.first_contact",
                        "workflow.operations",
                    ],
                },
                "source": {"type": "string"},
                "confidence": {"type": "number"},
                "metadata": {"type": "object"},
            },
        },
        "writes": True,
    },
    {
        "name": "jobapps_update_learning_pattern",
        "description": "Retire, supersede, reactivate, or canonicalize one policy while preserving its audit history.",
        "input_schema": {
            "type": "object",
            "required": ["pattern_id", "status"],
            "properties": {
                "pattern_id": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "retired", "superseded"]},
                "superseded_by": {"type": "string"},
                "pattern_type": {"type": "string"},
                "trigger": {"type": "string"},
                "preference": {"type": "string"},
                "rule_key": {
                    "type": "string",
                    "enum": [
                        "candidate.truth",
                        "candidate.voice",
                        "resume.layout",
                        "resume.summary",
                        "resume.evidence_selection",
                        "resume.bullets",
                        "cover_letter.substance",
                        "outreach.first_contact",
                        "workflow.operations",
                    ],
                },
                "metadata": {"type": "object"},
                "reason": {"type": "string"},
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
                "next_action": {"type": "string"},
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
        "jobapps_update_learning_pattern",
        "jobapps_record_brain_event",
        "jobapps_update_status",
        # Networking state and draft-only communication support.
        "jobapps_list_people",
        "jobapps_upsert_person",
        "jobapps_add_person_note",
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


_REQUIRED_FIELDS_BY_TOOL: dict[str, tuple[str, ...]] = {
    spec["name"]: tuple(spec.get("input_schema", {}).get("required", ()))
    for spec in ALL_TOOL_SPECS
}


def _missing_required_fields(name: str, payload: dict[str, Any]) -> list[str]:
    required = _REQUIRED_FIELDS_BY_TOOL.get(name, ())
    return [
        field
        for field in required
        if payload.get(field) is None or (isinstance(payload.get(field), str) and not payload[field].strip())
    ]


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
            "jobapps_list_people": self._list_people,
            "jobapps_upsert_person": self._upsert_person,
            "jobapps_add_person_note": self._add_person_note,
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
            "jobapps_update_learning_pattern": self._update_learning_pattern,
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
        payload = payload if isinstance(payload, dict) else {}
        missing = _missing_required_fields(name, payload)
        if missing:
            output = {
                "error": (
                    f"{name} is missing required field(s): {', '.join(missing)}. "
                    f"Provided fields: {sorted(payload.keys()) or 'none'}."
                )
            }
            self.repo.record_tool_call(name, payload, output, status="failed", run_id=run_id)
            raise ValueError(output["error"])
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
        """Return compact context for admin/debug use without hydrating dashboard by default."""
        result_limit = parse_limit(payload.get("limit", 20), default=20, maximum=80)
        use = payload.get("use") or "resume"
        career = self.repo.career_context(use=use)
        brain_context = career.get("brain_context") or {}
        output: dict[str, Any] = {
            "scope": "compact_admin_context",
            "usage_note": (
                "For normal material work, prefer jobapps_retrieve_for_job, "
                "jobapps_search_evidence, jobapps_search_brain, or jobapps_brain_context. "
                "This tool intentionally omits full dashboard/job payloads unless include_dashboard is true."
            ),
            "summary": self.repo.instruction_summary(),
            "career_context": {
                "profile_facts": career.get("profile_facts", []),
                "proof_points": career.get("proof_points", []),
                "learning_patterns": career.get("learning_patterns", []),
                "brain_context": {
                    "entity_counts": brain_context.get("entity_counts", {}),
                    "event_counts": brain_context.get("event_counts", {}),
                },
                "context_policy": career.get("context_policy", {}),
            },
        }
        if parse_bool(payload.get("include_dashboard", False), "include_dashboard", default=False):
            output["dashboard"] = self.repo.dashboard()
        return output

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
            limit=parse_limit(payload.get("limit", 6), default=6, maximum=8),
            include_recent=bool(payload.get("include_recent", False)),
            event_type=payload.get("event_type"),
            job_id=payload.get("job_id"),
        )

    def _search_brain(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _compact_brain_search_tool_result(
            self.repo.search_brain(
                payload["query"],
                entity_type=payload.get("entity_type"),
                event_type=payload.get("event_type"),
                job_id=payload.get("job_id"),
                limit=parse_limit(payload.get("limit", 8), default=8, maximum=10),
            )
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
        result = self.repo.retrieve_for_job(
            payload["job_id"],
            use=payload.get("use", "resume"),
            limit=parse_limit(payload.get("limit", 6), default=6),
        )
        return _compact_retrieval_tool_result(result)

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

    def _list_people(self, payload: dict[str, Any]) -> dict[str, Any]:
        people = self.repo.list_people(
            payload.get("query", ""),
            status=payload.get("status", "all"),
            limit=parse_limit(payload.get("limit", 50), default=50, maximum=200),
        )
        return {"count": len(people), "people": [_compact_person_tool_result(person) for person in people]}

    def _upsert_person(self, payload: dict[str, Any]) -> dict[str, Any]:
        person = self.repo.upsert_person(
            payload["name"],
            payload["why_added"],
            contact_id=payload.get("person_id", ""),
            company=payload.get("company", ""),
            role=payload.get("role", ""),
            email=payload.get("email", ""),
            linkedin_url=payload.get("linkedin_url", ""),
            notes=payload.get("notes", ""),
            network_status=payload.get("status", "to_contact"),
            source=payload.get("source", "agent"),
        )
        return {"person": _compact_person_tool_result(person)}

    def _add_person_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        person = self.repo.append_person_note(
            payload["person_id"],
            payload["note"],
            network_status=payload.get("status"),
            source=payload.get("source", "agent"),
        )
        return {"person": _compact_person_tool_result(person)}

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
        job = payload["job"]
        query = "\n".join(str(job.get(field) or "") for field in ("title", "company", "description"))
        context = payload.get("context") or self.repo.career_context(use="resume", query=query, learning_limit=8)
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
        return _compact_job_tool_record(workflow.prepare_opportunity(job))

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
        job = payload["job"]
        query = "\n".join(str(job.get(field) or "") for field in ("title", "company", "description"))
        context = payload.get("context") or self.repo.career_context(use="resume", query=query, learning_limit=8)
        return draft_materials(payload["job"], payload["evaluation"], context, self.config)

    def _record_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = dict(payload["job"])
        if payload.get("job_id") and not job.get("id"):
            job["id"] = payload["job_id"]
        return _compact_job_tool_record(self.repo.create_job(job, payload["evaluation"]))

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
        name = payload.get("name") or _profile_value(context, "name", "Candidate Name")
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
            name=payload.get("name") or _profile_value(context, "name", "Candidate Name"),
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
            metadata={
                "last_edit_reason": payload.get("reason", ""),
                "review_status": "draft",
                "compile": {},
                "verification": {},
                "layout_qa": {},
                "semantic_review": {},
            },
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
        selected_materials = [item for item in job.get("materials", []) if item["id"] in material_ids]
        blocked_materials: list[dict[str, Any]] = []
        for material in selected_materials:
            if not str(material.get("kind") or "").startswith("resume"):
                continue
            if normalize_material_format(material.get("format")) != "typ":
                continue
            metadata = material.get("metadata") or {}
            verification = metadata.get("verification") or (metadata.get("compile") or {}).get("verification") or {}
            layout = verification.get("layout") if isinstance(verification, dict) else None
            artifact_errors = _layout_artifact_errors(self.config, material, layout)
            if not isinstance(layout, dict) or not layout.get("ready") or artifact_errors:
                blocked_materials.append(
                    {
                        "material_id": material["id"],
                        "layout_status": layout.get("status", "not_run") if isinstance(layout, dict) else "not_run",
                        "violations": layout.get("violations", []) if isinstance(layout, dict) else [],
                        "artifact_errors": artifact_errors,
                    }
                )
        if blocked_materials:
            return {
                "ok": False,
                "status": "layout_qa_blocked",
                "job_id": payload["job_id"],
                "blocked_materials": blocked_materials,
                "next_step": "Compile the Typst resume, apply verification.layout.repair_plan, and mark ready only after layout.ready is true.",
            }

        semantic_review = payload.get("semantic_review")
        semantic_blocked: list[dict[str, Any]] = []
        required_checks = (
            "truth",
            "role_relevance",
            "evidence_quality",
            "voice_and_no_scaffolding",
        )
        reviewer = ""
        checks: dict[str, Any] = {}
        reviewed_hashes: dict[str, Any] = {}
        if isinstance(semantic_review, dict):
            reviewer = str(semantic_review.get("reviewer") or "").strip()
            raw_checks = semantic_review.get("checks")
            checks = raw_checks if isinstance(raw_checks, dict) else {}
            raw_hashes = semantic_review.get("material_sha256")
            reviewed_hashes = raw_hashes if isinstance(raw_hashes, dict) else {}
        for material in selected_materials:
            errors: list[str] = []
            if not isinstance(semantic_review, dict):
                errors.append("semantic_review_missing")
            if not reviewer:
                errors.append("semantic_reviewer_missing")
            failed_checks = [name for name in required_checks if checks.get(name) is not True]
            if failed_checks:
                errors.extend(f"semantic_check_failed:{name}" for name in failed_checks)
            current_hash = _material_source_sha256(self.config, material)
            if not current_hash:
                errors.append("material_source_unavailable")
            elif str(reviewed_hashes.get(material["id"]) or "") != current_hash:
                errors.append("semantic_review_hash_mismatch")
            if errors:
                semantic_blocked.append({"material_id": material["id"], "errors": errors})
        if semantic_blocked:
            return {
                "ok": False,
                "status": "semantic_review_blocked",
                "job_id": payload["job_id"],
                "blocked_materials": semantic_blocked,
                "next_step": "Review the exact current sources against the four semantic checks and provide their current SHA-256 values.",
            }

        updated_materials = [
            self.repo.mark_material_ready_for_review(
                material["id"],
                reviewer=reviewer,
                checks=checks,
                source_sha256=str(reviewed_hashes[material["id"]]),
            )
            for material in selected_materials
        ]
        reason = payload.get("reason", "Materials ready for final human review.")
        return {
            "ok": True,
            "status": "ready_for_review",
            "job_id": payload["job_id"],
            "approval": None,
            "materials": [_compact_material_tool_result(item) for item in updated_materials],
            "progress_item": None,
            "reason": reason,
        }

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
        metadata = dict(payload.get("metadata", {}))
        rule_key = str(payload.get("rule_key") or metadata.get("rule_key") or "").strip()
        if not rule_key:
            raise ValueError("Reusable learning policies require a fixed rule_key.")
        metadata = {"rule_key": rule_key}
        spec = LEARNING_POLICY_SPECS.get(rule_key)
        if spec is None:
            raise ValueError(f"Unsupported learning policy key: {rule_key}")
        return self.repo.record_learning_pattern(
            spec["pattern_type"],
            payload["trigger"],
            payload["preference"],
            source=payload.get("source", "agent"),
            confidence=float(payload.get("confidence", 0.8)),
            metadata=metadata,
        )

    def _update_learning_pattern(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(payload.get("metadata", {}))
        if "rule_key" in payload:
            metadata["rule_key"] = payload["rule_key"]
        return self.repo.update_learning_pattern(
            payload["pattern_id"],
            status=payload["status"],
            superseded_by=payload.get("superseded_by"),
            pattern_type=payload.get("pattern_type"),
            trigger=payload.get("trigger"),
            preference=payload.get("preference"),
            metadata=metadata or None,
            reason=payload.get("reason", ""),
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
        return _compact_job_tool_record(
            self.repo.record_event(
                payload["job_id"],
                "status_changed",
                {
                    "status": payload["status"],
                    "note": payload.get("note", ""),
                    "next_action": payload.get("next_action"),
                    "hermes_run_id": payload.get("hermes_run_id", ""),
                    "hermes_session_id": payload.get("hermes_session_id", ""),
                },
            )
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


def _tool_clip(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _compact_person_tool_result(person: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": person.get("id", ""),
        "name": person.get("name", ""),
        "company": person.get("company", ""),
        "role": person.get("role", ""),
        "email": person.get("email", ""),
        "email_status": person.get("email_status", ""),
        "linkedin_url": person.get("linkedin_url", ""),
        "why_added": person.get("why_added", ""),
        "notes": _tool_clip(person.get("notes", ""), 1200),
        "status": person.get("network_status", "to_contact"),
        "updated_at": person.get("updated_at", ""),
    }


def _compact_brain_search_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    compact_events: list[dict[str, Any]] = []
    for event in result.get("events", []):
        raw_entity = event.get("entity")
        entity = raw_entity if isinstance(raw_entity, dict) else {}
        compact_events.append(
            {
                "id": event.get("id"),
                "job_id": event.get("job_id"),
                "event_type": event.get("event_type"),
                "title": _tool_clip(event.get("title"), 180),
                "content": _tool_clip(event.get("content"), 500),
                "source": event.get("source"),
                "occurred_at": event.get("occurred_at"),
                "rank": event.get("rank"),
                "entity": {
                    "id": entity.get("id"),
                    "type": entity.get("type"),
                    "title": _tool_clip(entity.get("title"), 160),
                },
            }
        )
    return {
        "query": result.get("query"),
        "retrieval_mode": result.get("retrieval_mode"),
        "filters": result.get("filters"),
        "events": compact_events,
    }


def _compact_job_header(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: job.get(key)
        for key in (
            "id",
            "title",
            "company",
            "location",
            "url",
            "status",
            "role_family",
            "decision",
            "next_action",
            "hermes_session_id",
            "hermes_run_id",
            "created_at",
            "updated_at",
        )
        if job.get(key) not in (None, "")
    }


def _compact_evaluation_tool_result(evaluation: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: evaluation.get(key)
        for key in (
            "job_id",
            "decision",
            "role_family",
            "sponsorship_risk",
            "location_risk",
            "seniority_risk",
            "effort_risk",
            "strongest_angle",
            "next_action",
        )
        if evaluation.get(key) not in (None, "")
    }
    compact["blocker_flags"] = [
        {
            "area": item.get("area"),
            "assessment": _tool_clip(
                item.get("assessment") or item.get("evidence") or item.get("label"),
                240,
            ),
        }
        for item in (evaluation.get("blocker_flags") or [])[:6]
        if isinstance(item, dict)
    ]
    return compact


def _compact_material_tool_result(material: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = material.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_compile_metadata = metadata.get("compile")
    compile_metadata: dict[str, Any] = (
        raw_compile_metadata if isinstance(raw_compile_metadata, dict) else {}
    )
    compact_metadata = {
        key: metadata.get(key)
        for key in ("review_status", "pdf_path", "page_count", "word_count")
        if metadata.get(key) not in (None, "")
    }
    if compile_metadata:
        compact_metadata["compile"] = {
            key: compile_metadata.get(key)
            for key in ("status", "compiler", "pdf_path", "ok")
            if compile_metadata.get(key) not in (None, "")
        }
    raw_semantic_review = metadata.get("semantic_review")
    if isinstance(raw_semantic_review, dict):
        compact_metadata["semantic_review"] = {
            key: raw_semantic_review.get(key)
            for key in ("status", "reviewer", "source_sha256")
            if raw_semantic_review.get(key) not in (None, "")
        }
    return {
        key: value
        for key, value in {
            "id": material.get("id"),
            "job_id": material.get("job_id"),
            "kind": material.get("kind"),
            "format": material.get("format"),
            "file_path": material.get("file_path"),
            "source": material.get("source"),
            "status": material.get("status"),
            "metadata": compact_metadata,
            "created_at": material.get("created_at"),
            "updated_at": material.get("updated_at"),
        }.items()
        if value not in (None, "", {})
    }


def _compact_job_tool_record(record: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "job": _compact_job_header(record.get("job") or {}),
        "evaluation": _compact_evaluation_tool_result(record.get("evaluation") or {}),
        "materials": [
            _compact_material_tool_result(item)
            for item in (record.get("materials") or [])
            if isinstance(item, dict)
        ],
        "prompts": [
            {
                key: item.get(key)
                for key in ("id", "job_id", "prompt_type", "status", "created_at")
                if item.get(key) not in (None, "")
            }
            for item in (record.get("prompts") or [])
            if isinstance(item, dict)
        ],
        "tailoring_requirements": [
            {
                "id": item.get("id"),
                "requirement": _tool_clip(item.get("requirement"), 420),
                "category": item.get("category"),
                "priority": item.get("priority"),
                "status": item.get("status"),
            }
            for item in (record.get("tailoring_requirements") or [])
            if isinstance(item, dict)
        ],
        "application_signals": [
            {
                "id": item.get("id"),
                "signal_type": item.get("signal_type"),
                "label": item.get("label"),
                "value": _tool_clip(item.get("value"), 320),
            }
            for item in (record.get("application_signals") or [])
            if isinstance(item, dict)
        ],
        "approvals": [
            {key: item.get(key) for key in ("id", "action", "status") if item.get(key) not in (None, "")}
            for item in (record.get("approvals") or [])
            if isinstance(item, dict)
        ],
        "progress_items": [
            {key: item.get(key) for key in ("id", "title", "kind", "status", "due_date") if item.get(key) not in (None, "")}
            for item in (record.get("progress_items") or [])
            if isinstance(item, dict)
        ],
        "tool_calls": [
            {key: item.get(key) for key in ("id", "tool_name", "status", "created_at") if item.get(key) not in (None, "")}
            for item in (record.get("tool_calls") or [])
            if isinstance(item, dict)
        ],
    }
    run = record.get("run")
    if isinstance(run, dict):
        compact["run"] = {
            key: run.get(key)
            for key in ("id", "job_id", "status", "started_at", "finished_at")
            if run.get(key) not in (None, "")
        }
    prompt = record.get("prompt_to_hermes")
    if isinstance(prompt, dict):
        compact["prompt_to_hermes"] = {
            key: prompt.get(key)
            for key in ("id", "job_id", "prompt_type", "status")
            if prompt.get(key) not in (None, "")
        }
    return compact


def _compact_retrieval_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    for item in result.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        raw_source = item.get("source")
        source: dict[str, Any] = raw_source if isinstance(raw_source, dict) else {}
        evidence.append(
            {
                "rank": item.get("rank"),
                "why": _tool_clip(item.get("why"), 320),
                "source": {
                    "id": source.get("id"),
                    "label": source.get("label"),
                    "summary": _tool_clip(source.get("summary"), 700),
                    "evidence": _tool_clip(source.get("evidence"), 900),
                    "role_family": source.get("role_family"),
                    "tags": (source.get("tags") or [])[:16],
                    "status": source.get("status"),
                    "user_confirmed": source.get("user_confirmed"),
                    "narrative_version": source.get("narrative_version"),
                    "allowed_uses": (source.get("allowed_uses") or [])[:12],
                    "risk_level": source.get("risk_level"),
                },
            }
        )
    return {
        "job_id": result.get("job_id"),
        "job": _compact_job_header(result.get("job") or {}),
        "profile_facts": [
            {
                "fact_key": item.get("fact_key"),
                "value": _tool_clip(item.get("value"), 500),
                "category": item.get("category"),
            }
            for item in (result.get("profile_facts") or [])
            if isinstance(item, dict)
        ],
        "policy": result.get("policy"),
        "query": _tool_clip(result.get("query"), 900),
        "requirements": [_tool_clip(item, 420) for item in (result.get("requirements") or [])[:8]],
        "signals": [
            {
                "signal_type": item.get("signal_type"),
                "label": item.get("label"),
                "value": _tool_clip(item.get("value"), 320),
            }
            for item in (result.get("signals") or [])[:12]
            if isinstance(item, dict)
        ],
        "learning_patterns": [
            {
                "id": item.get("id"),
                "rule_key": (item.get("metadata") or {}).get("rule_key"),
                "pattern_type": item.get("pattern_type"),
                "trigger": _tool_clip(item.get("trigger"), 280),
                "preference": _tool_clip(item.get("preference"), 700),
            }
            for item in (result.get("learning_patterns") or [])[:8]
            if isinstance(item, dict)
        ],
        "evidence": evidence,
        "excluded": [
            {
                key: item.get(key)
                for key in ("id", "label", "status", "user_confirmed", "reason", "superseded_by")
                if item.get(key) not in (None, "")
            }
            for item in (result.get("excluded") or [])[:8]
            if isinstance(item, dict)
        ],
        "eligibility_filter": result.get("eligibility_filter"),
        "retrieval_mode": result.get("retrieval_mode"),
    }


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


def _layout_artifact_errors(
    config: dict[str, Any],
    material: dict[str, Any],
    layout: Any,
) -> list[str]:
    if not isinstance(layout, dict):
        return ["layout_report_missing"]
    artifact = layout.get("artifact")
    if not isinstance(artifact, dict):
        return ["artifact_hashes_missing"]
    expected_source = str(artifact.get("source_sha256") or "")
    expected_pdf = str(artifact.get("pdf_sha256") or "")
    if not expected_source or not expected_pdf:
        return ["artifact_hashes_missing"]

    errors: list[str] = []
    try:
        source_path = _validate_material_path(config, str(material.get("file_path") or ""))
    except ValueError:
        return ["source_path_invalid"]
    if not source_path.is_file() or _sha256_path(source_path) != expected_source:
        errors.append("source_hash_mismatch")
    content = material.get("content")
    if isinstance(content, str) and hashlib.sha256(content.encode("utf-8")).hexdigest() != expected_source:
        errors.append("stored_content_hash_mismatch")

    metadata = material.get("metadata") or {}
    raw_compile = metadata.get("compile")
    compile_metadata: dict[str, Any] = raw_compile if isinstance(raw_compile, dict) else {}
    pdf_value = metadata.get("pdf_path") or compile_metadata.get("pdf_path") or source_path.with_suffix(".pdf")
    try:
        pdf_path = _validate_material_path(config, str(pdf_value))
    except ValueError:
        errors.append("pdf_path_invalid")
    else:
        if not pdf_path.is_file() or _sha256_path(pdf_path) != expected_pdf:
            errors.append("pdf_hash_mismatch")
    return errors


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _material_source_sha256(config: dict[str, Any], material: dict[str, Any]) -> str:
    file_path = str(material.get("file_path") or "").strip()
    if file_path:
        try:
            source_path = _validate_material_path(config, file_path)
        except ValueError:
            return ""
        return _sha256_path(source_path) if source_path.is_file() else ""
    content = material.get("content")
    if not isinstance(content, str):
        return ""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
