# Hermes JobApps Agent Instructions

This project is Prashant's Hermes-centered job-application cockpit. Keep it simple, useful, and alive.

## Source of Truth

Read these before meaningful product, agent, or writing work:

1. `GOAL.md` — product direction and first useful workflow.
2. The JobApps database schema and current app data — jobs, profile facts, proof points, application signals, tailoring requirements, portrayal decisions, learning patterns, materials, contacts, progress, follow-ups, approvals, and prompt builds.
3. `DESIGN.md` and `docs/ARCHITECTURE_RESEARCH.md` — architecture stance and Hermes integration notes.
4. `docs/BRANDING.md` and `design-system/` — Hermes-native visual language and JobApps branding layer.
5. Relevant project skills under `skills/` and the Hermes project plugin under `.hermes/plugins/jobapps/`.

`knowledge_base.html` is not canonical runtime structure. It is a private seed/example file only. Do not couple app behavior to its shape, parse it as the live source of truth, or treat its sections as a database schema. If private seed material exists, import useful facts into structured database rows first.

Do not treat old generated drafts as truth. Generate from the database, current job context, Hermes memory where appropriate, and explicit user corrections.

## What We Are Building

Hermes JobApps helps Prashant move from an opportunity to a clear next action:

- run blocker preflight quickly: sponsorship/work authorization, impossible seniority, location, and application effort
- assume apply intent when Prashant provides a JD and no hard blocker appears
- research the company and role just enough to avoid blind tailoring
- find the strongest truthful angle
- turn JD needs into tailoring requirements
- tailor resume material as Typst (`.typ`)
- draft cover letters as `.tex`
- draft short application answers
- draft networking search notes, outreach, and follow-ups
- record portrayal decisions, learning patterns, what happened, why materials changed, and what should happen next

The app owns structured state. Hermes performs transitions.

## Operating Principles

- **Hermes at the center.** The product should expose what Hermes is thinking, doing, asking, and changing. Do not hide the agent behind generic dashboard chrome.
- **Database over document coupling.** Profile facts, proof points, application signals, tailoring requirements, portrayal decisions, learning patterns, jobs, materials, contacts, approvals, progress, and follow-ups belong in structured app data.
- **Config over hardcoding.** Sponsorship rules, blocker thresholds, source lists, banned phrases, templates, and profile facts should be configurable and inspectable.
- **Transparent by default.** Every recommendation should show evidence: job requirement, matched proof point, blocker/risk, and material provenance.
- **Human approval for external actions.** Draft freely. Fill forms cautiously later. Never submit applications, send emails, or message people without explicit approval in that moment.
- **State is structured. Memory is selective.** Jobs, dates, contacts, statuses, generated materials, decisions, and material provenance belong in the app data layer. Durable career preferences and lessons can live in Hermes memory or profile config.
- **Sponsorship filter early.** No sponsorship or obvious work-authorization blocker means skip unless Prashant explicitly says otherwise.
- **Build the workflow before the crawler.** Manual job link/description first. Discovery and browser automation come later.

## Hermes Integration

Follow Hermes architecture rather than duplicating it:

- Use a dedicated Hermes profile for JobApps when practical.
- Use the Hermes API server for app chat and long-running runs.
- Use `/v1/responses` or named conversations for conversational continuity.
- Use `/v1/runs` plus run status/events for longer research/tailoring workflows.
- Preserve Hermes session/run IDs in the app database.
- Expose JobApps database transitions as tools through the `.hermes/plugins/jobapps` project plugin, or via MCP if this later moves out of process.
- Let Hermes provider routing, prompt assembly, session storage, memory, skills, and tool dispatch remain Hermes responsibilities.
- Inject JobApps context through supported Hermes surfaces: project context files, plugin skills, plugin tools, and `pre_llm_call` ephemeral context. Do not fork Hermes prompt assembly for app-specific behavior.

## Code Taste

- No fluff. Every abstraction must earn its place.
- Prefer focused, practical code over generic frameworks that look impressive.
- Ad-hoc is acceptable when it is clear and reliable.
- Fail visibly. Do not bury failures behind silent fallbacks.
- Comments explain intent, tradeoffs, or non-obvious behavior. Do not narrate obvious code.
- No emojis in code, logs, seed data, or product copy unless explicitly requested.
- No overbuilt `tasks/` directory or planning sprawl unless Prashant asks for it.

## Workflow Loop

For each opportunity:

1. **Ingest** the job link or pasted description.
2. **Blocker preflight** for sponsorship/work authorization, location, seniority, and application effort. Do not fit-score Prashant.
3. **Assume apply intent** when Prashant supplied the JD and no hard blocker appears.
4. **Classify** the role family: AI/agent, backend, full-stack, data engineering, data analytics, ML/DS, mobile/iOS, DevOps/IT, research, other.
5. **Research lightly** with Hermes for sponsorship signal, company context, team/product context, and networking targets.
6. **Extract signals and tailoring requirements** from the JD.
7. **Match** requirements to active, user-confirmed database proof points.
8. **Update context** when the user gives a new durable experience story or preference.
9. **Choose angle**: the one truthful story that gives Prashant the strongest position.
10. **Draft materials** using project skills and native Hermes workbench tools; save resume builds as `.typ` and cover-letter builds as `.tex`.
11. **Record provenance**: tailoring requirement, portrayal decision, material change, and supporting proof point.
12. **Record learning patterns** when corrections should carry into future applications.
13. **Ask for approval** before any external side effect.
14. **Record state**: role, blocker decision, angle, signals, tailoring, materials, next action, progress, follow-up date, contacts, and Hermes run/session IDs.

## Agent/Tool Guidance

Use Hermes as the intelligence engine through its API server. Keep the web app as the cockpit and database owner.

Borrow patterns from agent systems without copying their complexity:

- structured outputs for job evaluations and material drafts
- explicit tools for database reads/writes
- human-in-the-loop checkpoints for submit/send actions
- durable execution concepts for paused workflows
- live progress events for transparency

Do not add LangGraph, Browser Use, Stagehand, queues, or multi-agent orchestration until the first workflow proves it needs them.

## Done Means

A change is done when it improves the real workflow and has been checked:

- the user-facing state is clear
- generated writing follows Prashant's voice
- job facts are traceable to the job description or research source
- profile claims are traceable to database proof points/profile facts
- material changes are recorded with tailoring requirements, portrayal decisions, and proof-point support
- useful corrections are recorded as learning patterns when they should repeat
- follow-ups and progress are visible
- no external action happened without approval
