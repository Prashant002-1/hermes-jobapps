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

**Status:** Implemented for pasted descriptions as intake/evaluation state.

When the user pastes a job description in chat, `ChatOrchestrator` parses a conservative job payload and runs `JobAppsWorkflow.prepare_opportunity()`. The `jobapps_prepare_opportunity` tool also accepts `{text}` / `{message}` / structured job fields and creates the DB record, blocker preflight, application signals, tailoring requirements, portrayal plan, and Hermes prompt handoff.

It intentionally does not author candidate-facing resume, cover-letter, short-answer, or outreach materials. Native Hermes file/patch/terminal tools own writing, compilation, and QA; JobApps links finished artifacts and provenance after the material is good.

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
- Right-tool boundary — native Hermes tools for writing/editing/compilation/QA, JobApps tools for retrieval and ledger state
- Compact profile and lifecycle counts — profile facts, proof points, application signals, tailoring requirements, portrayal decisions, learning patterns
- Recent opportunities only when the turn is JobApps/job/material/networking related
- Default JobApps tool specs only; broad context, debug/audit, prompt dump, and app-owned authoring helpers stay out of normal material-generation context

This gives Hermes enough context to act without making JobApps feel like the default authoring environment.

**Files to touch:** `prompts.py` (`build_chat_instructions`), `server.py` (chat handler — pass repo data)

---

## 6. Approval actions endpoint

**Status:** Implemented.

The UI keeps explicit approval/rejection buttons for pending generated-material gates. Direct job-status mutation buttons were removed because status changes should happen through chat-driven agent state transitions, not dashboard shortcuts.

Backend endpoint:
- `POST /api/jobs/:id/approvals/:approval_id` with `{ "action": "approve" | "reject" }`

---

## 7. Live application-materials workbench

**Status:** Implemented for app-owned Typst resume artifacts, TeX cover-letter artifacts, revisions, diffs, compile contract, and material-ready metadata. These helpers remain available, but normal Hermes sessions should use native file/patch/terminal tools for authoring and compilation, then link finished artifacts back to JobApps.

The cockpit now treats materials as first-class state:
- `material_revisions` table records every agent/user patch with before/after text, unified diff, reason, requirement, and proof reference.
- `GET /api/state` includes `materials_workbench` with primary resume/cover-letter artifacts, revision count, latest diff, compile status, PDF/log paths, and explicit external-use warning.
- Specialist/internal tools remain callable through the existing `/api/tools/:tool` route:
  - `jobapps_create_resume_typst` — creates full `resume.typ` artifact when an app-owned helper is explicitly needed.
  - `jobapps_create_resume_tex` — legacy alias that now creates the Typst resume artifact.
  - `jobapps_create_cover_letter_tex` — creates full `cover_letter.tex` artifact when an app-owned helper is explicitly needed.
  - `jobapps_patch_material` — exact replacement patch, file update, revision diff, provenance record when JobApps material-revision semantics are required.
  - `jobapps_diff_material` — preview diff without mutation when operating on a stored material record.
  - `jobapps_compile_material_pdf` — compiles Typst or TeX to PDF using configured compiler search paths and common macOS locations (`/opt/homebrew/bin`, `/usr/local/bin`, `/Library/TeX/texbin`); reports `missing_compiler` without installing anything when unavailable.
  - `jobapps_mark_material_ready_for_review` — marks materials ready for human review without creating a dashboard Action.
- Frontend renders a **Materials** card with artifact metadata, revisions, latest diff, compile status, and a `Compile PDF` action.

**Compiler status:** `typst` 0.14.2 is installed at `/opt/homebrew/bin/typst`; smoke tests compile generated resume Typst artifacts to PDF through the app API. `tectonic` remains supported for TeX cover-letter and legacy artifacts. The code still returns `missing_compiler` cleanly on machines without the requested compiler.

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
| 7 | Live materials workbench | ✅ Implemented for Typst resume artifacts, TeX cover-letter/legacy artifacts, revisions, diffs, PDF compile, and specialist/internal helpers |
| 8 | Evidence + signals + tailoring lifecycle | ✅ Implemented with proof lifecycle, application signals, tailoring requirements, portrayal decisions, learning patterns, retrieval chunks, and FTS search |
| 9 | Personal career brain | ✅ Implemented in SQLite with `brain_entities`, `brain_events`, FTS search, tool exposure, chat capture, and automatic event trails |

The first useful chat-driven workflow is now real: paste a job description → blocker preflight/assume-apply → signal and tailoring extraction → compact evidence/state cards → candidate-facing materials created in the native Hermes workbench → provenance/status recorded in JobApps → PDF/Gmail/manual submission artifacts verified. The next shift is stronger material quality and review ergonomics, not more backend lifecycle expansion.
