# Architecture Research Notes

These notes convert the local product direction into implementation choices. They are research inputs, not permanent constraints.

## Correct Working Shape

Hermes JobApps should be a cockpit plus domain database around Hermes:

- The app database owns jobs, profile facts, proof points, evaluations, prompt builds, material links/provenance, application changes, research notes, contacts, progress, follow-ups, approvals, and Hermes correlation IDs.
- Hermes performs transitions: research, evaluate, author candidate-facing material with native file/patch/terminal tools, ask, call targeted JobApps retrieval/ledger tools, and update structured state after the artifact exists.
- Private seed files can import into the database, but they are not source of truth and not stable schema.
- SQLite is enough until the workflow needs multi-user sharing or remote deployment.
- External actions stay behind explicit approval.

## Hermes Findings

The Hermes API server is the app bridge. It exposes OpenAI-compatible `/v1/chat/completions` and `/v1/responses`, plus `/v1/runs` for long-form agent runs with polling and SSE events. `/v1/responses` supports named conversations and stored response chains, which maps well to in-app Hermes chat. `/v1/runs` maps better to company research and full tailoring workflows. Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server

Hermes streaming is a first-class UI contract, not a cosmetic layer. Responses
streaming emits token deltas and function-call/function-output items, while the
capabilities endpoint lets external UIs detect streaming, runs, cancellation,
session headers, and tool progress. JobApps should render those events directly
instead of waiting for a final blob.

Hermes profiles are the right isolation boundary for JobApps. A profile gets separate config, env, memory, sessions, skills, cron, and state. Profiles are not security sandboxes, so secrets and private data still need normal repo hygiene. Source: https://hermes-agent.nousresearch.com/docs/user-guide/profiles

Hermes prompt assembly intentionally separates cached system prompt state from ephemeral API-call additions. JobApps should use supported prompt inputs, instructions, skills, context files, and plugin context injection instead of editing Hermes prompt internals. Source: https://hermes-agent.nousresearch.com/docs/developer-guide/prompt-assembly

The agent loop owns provider resolution, prompt assembly, tool dispatch, memory/session behavior, and gateway/API modes. JobApps should not reimplement those responsibilities. Source: https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop

Gateway and session storage matter because native Hermes, API chat, and app-triggered runs need continuity. JobApps should store Hermes run/session IDs for correlation while leaving Hermes session records in Hermes state. Sources: https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals and https://hermes-agent.nousresearch.com/docs/developer-guide/session-storage

The Hermes web dashboard gets exact TUI behavior by embedding the real TUI in a
PTY/WebSocket/xterm.js surface. JobApps should not duplicate the full terminal
renderer. It should carry over the useful dashboard/TUI concepts: profile/model
status, command catalog, slash command execution, streaming transcript, tool
cards, reasoning/status visibility, and run/event correlation.

Provider runtime resolution belongs to Hermes. JobApps should configure the Hermes API/profile and let Hermes choose the actual provider/model path. Source: https://hermes-agent.nousresearch.com/docs/developer-guide/provider-runtime

Hermes plugins are the immediate way to expose app database tools and a JobApps skill to native Hermes sessions. A future MCP bridge can replace or complement the project plugin if JobApps becomes a separate service. Sources: https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin and https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp

The Hermes repo confirms the docs: tools register through plugin contexts, prompt/context files are loaded as part of agent setup, sessions persist through Hermes state, and gateway/API are long-running entry points. Source: https://github.com/NousResearch/hermes-agent

## Current Implementation Choice

The first implementation is a dependency-free Python local server:

- `hermes_jobapps/repository.py` persists app state in SQLite.
- `hermes_jobapps/tools.py` exposes app database transitions as agent-callable tools.
- `hermes_jobapps/hermes_client.py` talks to the Hermes API server and proxies Responses SSE so the web UI can show streaming text, tool/function calls, and response lifecycle.
- `hermes_jobapps/hermes_commands.py` routes native Hermes slash commands and command metadata through the `jobapps` profile's TUI/gateway command surfaces.
- `hermes_jobapps/prompts.py` builds reproducible prompts for Hermes.
- `hermes_jobapps/typst.py` writes reviewable `.typ` resume artifacts and compiles them to PDF; `hermes_jobapps/latex.py` remains for TeX cover letters and legacy TeX compile/verification helpers.
- `hermes_jobapps/workflow.py` prepares local state, prompt builds, progress, follow-ups, and artifacts before a Hermes run.
- `.hermes/plugins/jobapps/` exposes the same app tools and context to native Hermes.
- `web/` exposes the cockpit and Hermes chat.

This is not an LLM replacement. It gives Hermes a durable state/tool contract and gives the applicant a useful cockpit.

The personal memory layer also stays inside this implementation. JobApps now uses `brain_entities` and `brain_events` in SQLite for the human trail: conversations, corrections, constraints, preferences, people, companies, decisions, networking history, and why materials changed. This borrows the useful personal-brain pattern of canonical entities plus an event timeline, without adding an MCP server, GBrain dependency, or separate markdown wiki runtime.

## Tool Boundary

Hermes should be able to call tools for:

- reading app context
- upserting profile facts and proof points
- evaluating jobs against current database context
- drafting materials
- saving `.tex` materials
- saving prompt builds
- recording research notes
- recording material changes
- creating progress items and follow-ups
- changing application status
- reading/searching career-brain context
- recording career-brain entities/events when personal context, corrections, decisions, networking history, or revision rationale appears

Tooling must be visible, inspectable, and safe. State-changing JobApps tools write to the app database. Native Hermes tools handle general writing/editing/compilation. External actions remain out of scope until explicit approval and preview workflows exist.

## Future Adapter Boundary

If JobApps becomes a separate service, expose the same tool contract over MCP:

```json
{
  "tools": [
    "jobapps_brain_context",
    "jobapps_retrieve_for_job",
    "jobapps_upsert_profile_fact",
    "jobapps_upsert_proof_point",
    "jobapps_save_material",
    "jobapps_record_application_change",
    "jobapps_create_followup"
  ]
}
```

Hermes would then use MCP instead of importing the Python package from a project plugin. The database boundary and workflow contract stay the same.

## Expansion Gates

The next product direction is discovery: a simple curated list of roles pulled from real sources, not a scoring layer or cosmetic matching dashboard.

Planned order:

1. Manual job description/link.
2. Hermes research and tailoring run.
3. Curated discovery inbox.
4. Progress/follow-up/contact management.
5. Networking search layer.
6. Browser autofill with stop-before-submit approval.

Discovery sources should start practical:

- ATS public feeds: Greenhouse, Lever, Ashby, then Workday where stable.
- TinyFish search/fetch for candidate URLs and clean job descriptions.
- Job board mailing lists: extract job URLs from email, fetch the JD, then run the same blocker preflight.
- Paid job APIs only after the free/source-list workflow proves useful.

Discovery output is just candidates with `apply`, `skip`, or `pending`. No heuristic fit scores, match-strength labels, rankings, or made-up UI polish.
