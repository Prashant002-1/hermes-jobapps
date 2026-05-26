# Architecture

Hermes JobApps is a local-first cockpit for agent-assisted job applications. The core architectural decision is simple: the app owns structured state, and the agent performs transitions through explicit tools.

## System Shape

```text
Browser UI
  renders state, materials, sessions, commands, and approvals

Python HTTP server
  serves the UI, JSON APIs, generated material files, and Hermes bridge routes

Application services
  evaluator, workflow, writers, discovery, networking, materials, runs

SQLite repository
  jobs, evaluations, signals, requirements, proof points, materials, contacts, approvals

Hermes runtime, optional
  streaming chat, memory, sessions, slash commands, provider routing, plugin tools
```

The app intentionally uses the Python standard library for the local server. That keeps the default install small and makes the project easy to inspect.

The dashboard is a cockpit over the application database, not the only execution surface. Native Hermes TUI sessions and the Hermes web TUI/dashboard can use the project plugin to make the same `jobapps_*` state transitions. The JobApps dashboard then reflects that shared SQLite state when it loads or refreshes.

## Data Boundary

Application data belongs in SQLite. That includes jobs, profile facts, proof points, extracted signals, tailoring requirements, portrayal decisions, materials, contacts, progress, approvals, and follow-ups.

Hermes memory is useful for durable preferences and high-level lessons. It is not the source of truth for exact application facts or generated materials.

## Agent Boundary

Hermes is integrated through supported surfaces:

- streaming Responses API for chat
- run/event APIs for longer workflows
- slash command forwarding for native Hermes commands
- project plugin tools under `.hermes/plugins/jobapps`
- `pre_llm_call` context injection from current app state

The web app does not fork Hermes prompt assembly. It gives Hermes structured tools and retrieves app state through explicit database reads.

## Workflow Boundary

The workflow is approval-driven by design. JobApps may draft, compile, record, and prepare. It must not submit applications, send emails, message contacts, upload documents, or update external systems without explicit human approval in that moment.

## Why SQLite

SQLite is the right fit for this project because the product is local-first, personal, auditable, and workflow-heavy. The database gives the agent a durable contract without adding infrastructure before it is needed.

The schema supports:

- opportunities and evaluations
- application signals and tailoring requirements
- proof points and retrieval chunks
- generated materials and revisions
- contacts and networking history
- progress items and follow-ups
- approvals and external-action gates
- career-brain entities and events

## Extension Points

The project is intentionally modular where external systems touch it:

- discovery providers in `hermes_jobapps/discovery.py`
- networking providers in `hermes_jobapps/networking.py`
- material generation in `hermes_jobapps/materials.py` and `hermes_jobapps/latex.py`
- Hermes API/slash integration in `hermes_jobapps/hermes_client.py` and `hermes_jobapps/hermes_commands.py`
- native tool exposure in `.hermes/plugins/jobapps`
