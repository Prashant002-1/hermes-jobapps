# Backend Gaps — Agent-Centric Chat Flow

The harness UI (rewritten May 9) is **chat-first, agent-centric**. No forms, no text boxes beyond the chat composer. The user tells Hermes what to do in natural language; the UI displays structured results.

This document lists what the backend (`server.py`, `hermes_client.py`, `runs.py`, `workflow.py`) must support for the UI to work end-to-end.

---

## 1. Chat endpoint must support tool calling / local transitions

**Status:** Partially implemented.

`POST /api/hermes/chat` now routes through `ChatOrchestrator`:
- pasted job descriptions are parsed locally and sent through the full `prepare_opportunity` workflow
- responses include `output_text`, `job_id`, `app_run_id`, `tool_calls`, and fresh `state`
- non-opportunity chat still falls back to Hermes `/v1/responses`

**Still later:** true Hermes-hosted `jobapps_*` tool-call loops from `/api/hermes/chat`. For the first useful workflow, local transition routing is enough and avoids building a second agent framework inside the app.

---

## 2. State endpoint shape for structured rendering

**Status:** Implemented.

`GET /api/state` returns flattened harness-ready jobs plus aggregate counts:

```json
{
  "jobs": [
    {
      "id": "abc123def456",
      "title": "AI Engineer",
      "company": "Acme Corp",
      "location": "Remote",
      "url": "https://...",
      "role_family": "ai_agent_systems",
      "decision": "apply",
      "evaluation_mode": "blocker_preflight",
      "score": null,
      "tailoring_requirements": [
        { "requirement": "Build LLM agents with memory", "category": "agent_systems", "status": "targeted" }
      ],
      "portrayal_decisions": [
        { "target": "resume.projects", "rationale": "JD asks for agent memory and evaluation traces" }
      ],
      "matches": [
        { "requirement": "3+ yrs Python", "proof_id": "proof_x", "strength": "usable" }
      ],
      "resume_tex": "...",
      "cover_letter_tex": "...",
      "prompt": "...",
      "hermes_output": "...",
      "research_notes": [{ "content": "..." }],
      "progress": [{ "summary": "...", "status": "..." }],
      "risks": [{ "area": "sponsorship", "assessment": "Unknown", "level": "unknown" }],
      "events": [{ "description": "...", "event_type": "..." }],
      "hermes_run_status": "completed",
      "hermes_run_id": "run_xxx"
    }
  ],
  "job_count": 3,
  "followup_count": 2,
  "progress_count": 5,
  "approval_count": 1
}
```

**Files to touch:** `repository.py` (`dashboard()` method)

---

## 3. Chat → Prepare flow (natural language ingestion)

**Status:** Implemented for pasted descriptions.

When the user pastes a job description in chat, `ChatOrchestrator` parses a conservative job payload and runs `JobAppsWorkflow.prepare_opportunity()`. The `jobapps_prepare_opportunity` tool also accepts `{text}` / `{message}` / structured job fields and creates the full DB record.

**Still later:** URL crawling/extraction. Manual pasted descriptions remain the first useful workflow.

---

## 4. Chat endpoint → run ID for polling

**Status:** Implemented for chat-started local prep and Hermes runs.

Chat responses now include stable app fields where available:
```json
{
  "output_text": "...",
  "run_id": "run_xxx",
  "session_id": "sess_xxx"
}
```

The frontend can poll `GET /api/jobs/:id/hermes-run` for status after `started_hermes_run` or use the returned app state after `prepared_opportunity`.

---

## 5. System context injection for chat

**Status:** Implemented.

Every Hermes chat fallback and long-running Hermes run now injects:
- Current active job (if any) — title, company, description, current blocker decision
- Profile summary — target role, constraints (F-1/OPT), proof points count
- Tailoring lifecycle counts — application signals, tailoring requirements, portrayal decisions, learning patterns
- Available tools — list of `jobapps_*` tools with descriptions

This ensures Hermes has full context without the user having to repeat themselves.

**Files to touch:** `prompts.py` (`build_chat_instructions`), `server.py` (chat handler — pass repo data)

---

## 6. Approval actions endpoint

**Status:** Implemented.

The UI keeps explicit approval/rejection buttons for pending generated-material gates. Direct job-status mutation buttons were removed because status changes should happen through chat-driven agent state transitions, not dashboard shortcuts.

Backend endpoint:
- `POST /api/jobs/:id/approvals/:approval_id` with `{ "action": "approve" | "reject" }`

---

## 7. Live application-materials workbench

**Status:** Implemented for app-owned TeX artifacts, revisions, diffs, compile contract, and approval gates.

The cockpit now treats materials as first-class state:
- `material_revisions` table records every agent/user patch with before/after text, unified diff, reason, requirement, and proof reference.
- `GET /api/state` includes `materials_workbench` with primary resume/cover-letter artifacts, revision count, latest diff, compile status, PDF/log paths, and explicit external-use warning.
- New tools expose the workbench through the existing `/api/tools/:tool` route:
  - `jobapps_create_resume_tex` — creates full `resume.tex` artifact.
  - `jobapps_create_cover_letter_tex` — creates full `cover_letter.tex` artifact.
  - `jobapps_patch_material` — exact replacement patch, file update, revision diff, provenance record.
  - `jobapps_diff_material` — preview diff without mutation.
  - `jobapps_compile_material_pdf` — compiles TeX to PDF using configured compiler search paths and common macOS locations (`/opt/homebrew/bin`, `/usr/local/bin`, `/Library/TeX/texbin`); reports `missing_compiler` without installing anything when unavailable.
  - `jobapps_mark_material_ready_for_review` — creates explicit human approval gate.
- Frontend renders a **Materials** card with artifact metadata, revisions, latest diff, compile status, and a `Compile PDF` action.

**Compiler status:** `tectonic` 0.16.9 is installed at `/opt/homebrew/bin/tectonic`; smoke tests now compile generated resume and cover-letter TeX artifacts to PDF through the app API. The code still returns `missing_compiler` cleanly on machines without a compiler.

---

## 8. Evidence + signals retrieval layer

**Status:** Implemented first pass.

The app should not rely on Hermes memory or raw vector similarity to choose resume bullets. JobApps owns exact application truth. Hermes should ask the app for eligible evidence.

New backend contract:
- `proof_points` carries lifecycle metadata: `status`, `user_confirmed`, `narrative_version`, `allowed_uses`, `risk_level`, `superseded_by`, usage counters, and validity fields.
- `application_signals` stores extracted job facts and reusable application signals: sponsorship, role family, location, seniority, effort, requirements, and matching needs.
- `tailoring_requirements` stores the JD needs that generated materials must address.
- `portrayal_decisions` stores how a requirement changed resume/cover-letter framing and which proof/material it touched.
- `learning_patterns` stores reusable corrections/preferences so the same material mistake does not repeat.
- `retrieval_chunks` plus SQLite FTS provides local search over app-owned evidence.
- Retrieval filters eligibility before ranking. Default: active + user-confirmed + not superseded/retired/forbidden + allowed for the requested use.
- Embeddings are optional future infrastructure. If added, they must be hybrid and metadata-filtered; they should not override lifecycle eligibility.

Tool contract:
- `jobapps_search_evidence` — search current proof/evidence with lifecycle filters.
- `jobapps_retrieve_for_job` — retrieve eligible evidence for a stored job and report excluded stale/risky evidence.
- `jobapps_record_application_signal` — persist one extracted signal for later pattern analysis.
- `jobapps_record_tailoring_requirement` — persist one JD-grounded material target.
- `jobapps_record_portrayal_decision` — persist why a material framing changed.
- `jobapps_record_learning_pattern` — persist a reusable correction/preference.
- `jobapps_update_proof_lifecycle` — mark proof points active, retired, superseded, forbidden, candidate, or needs-review.

This is the local Honcho-like layer: app-owned conclusions with metadata, filters, consolidation hooks later, and no external memory bill.

---

## Summary

| # | Gap | Status |
|---|-----|--------|
| 1 | Chat tool calling/local transitions | 🟡 Local transition routing implemented; true Hermes-hosted tool loops later |
| 2 | State endpoint shape | ✅ Implemented |
| 3 | NL job ingestion via chat | ✅ Implemented for pasted descriptions |
| 4 | Run ID in chat response | ✅ Implemented where available |
| 5 | System context injection | ✅ Implemented |
| 6 | Approval endpoint | ✅ Implemented |
| 7 | Live materials workbench | ✅ Implemented for TeX artifacts/revisions/diffs/PDF compile via Tectonic |
| 8 | Evidence + signals + tailoring lifecycle | ✅ Implemented with proof lifecycle, application signals, tailoring requirements, portrayal decisions, learning patterns, retrieval chunks, and FTS search |
| 9 | Personal career brain | ✅ Implemented in SQLite with `brain_entities`, `brain_events`, FTS search, tool exposure, chat capture, and automatic event trails |

The first useful chat-driven workflow is now real: paste a job description → blocker preflight/assume-apply → signal and tailoring extraction → structured state cards → career-brain trail → TeX materials → revision diffs/provenance → PDF compile → explicit review approval gate. The next shift is stronger frontend ergonomics and deeper review UX, not rebuilding the backend lifecycle.
