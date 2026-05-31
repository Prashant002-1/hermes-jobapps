# Hermes JobApps Design and Code System

This file sets direction without locking the product too early. The project should evolve through use.

## Product Shape

Hermes JobApps is a career operating system, not a spray-and-pray job bot.

The core experience is a cockpit:

- **Inbox**: job links/descriptions Prashant is considering.
- **Blocker Preflight**: sponsorship/work authorization, seniority, location, risks, effort. No fit scoring.
- **Research**: company context, sponsorship signal, product/team context, and networking targets.
- **Tailoring**: JD requirements, matched proof points, gaps requiring user story, and portrayal decisions.
- **Materials**: `.tex` resume builds, `.tex` cover-letter builds, short answers, and outreach.
- **Approvals**: submit/send/follow-up decisions.
- **Management**: progress items, contacts, follow-ups, changes, learning patterns, and application history.

The interface should make the next action obvious. The agent should be visible: reasoning, evidence, questions, drafts, tool calls, and transitions.

## Design Principles

1. **Hermes front and center**
   - Hermes is the primary reasoning/session/memory engine.
   - The app is a cockpit and database owner.
   - Native Hermes should be aware of JobApps through the project plugin or future MCP bridge.

2. **Transparent intelligence**
   - Show why Hermes made a recommendation.
   - Pair every requirement with the matched proof point.
   - Mark uncertainty instead of pretending confidence.

3. **Database-first state**
   - Store profile facts, proof points, opportunities, application signals, tailoring requirements, portrayal decisions, learning patterns, materials, prompts, contacts, progress, follow-ups, approvals, and application changes in the app database.
   - Private seed files can import into this database, but they are not source-of-truth runtime documents.

4. **Personalizable system**
   - Use editable config and tool-updatable records for scoring weights, sponsorship rules, sources, templates, banned phrases, company notes, and profile facts.
   - Let Prashant correct the system once and have that correction matter later.

5. **One good workflow first**
   - Start with pasted links/descriptions.
   - Produce blocker preflight + research prompt + tailoring requirements + portrayal decisions + LaTeX materials + outreach + recorded state.
   - Do not build a giant crawler before this works.

6. **Human-approved external action**
   - Drafting is safe.
   - Recording app state is safe.
   - Sending messages, submitting applications, uploading documents, or changing external systems requires approval.

7. **No hidden magic**
   - Use explicit statuses.
   - Store artifacts.
   - Keep logs readable.
   - Make every generated document reproducible from inputs.

## Hermes-Native Architecture

Use Hermes as designed:

```text
Hermes profile / gateway / API server
  - memory, sessions, provider runtime, skills, tools
  - /v1/responses for chat
  - /v1/runs for longer research and tailoring runs
  - project plugin exposes JobApps tools and ephemeral context

JobApps local cockpit
  - displays state, evidence, artifacts, and progress
  - sends chat/run requests to Hermes
  - owns SQLite app database

SQLite app database
  - jobs, blocker preflights, proof points, profile facts
  - application signals, tailoring requirements, portrayal decisions, learning patterns
  - materials, prompt builds, research notes
  - application changes, contacts, follow-ups, approvals
  - Hermes run/session IDs for correlation
```

Avoid duplicating Hermes provider routing, prompt assembly, session storage, or memory systems. JobApps should add domain state and domain tools.

## Research Notes Baked In

Hermes docs and repo show the integration path:

- API server exposes OpenAI-compatible `/v1/chat/completions`, `/v1/responses`, `/v1/runs`, run polling, SSE events, health, and capabilities.
- Profiles isolate Hermes config, env, memory, sessions, skills, and state per use case. A `jobapps` profile is the right long-term home.
- Prompt assembly separates cached system prompt layers from ephemeral API-call additions. JobApps should use supported surfaces rather than patching Hermes internals.
- Project context files and skills are first-class prompt inputs; plugin `pre_llm_call` context is ephemeral and appended to the current user turn.
- Session storage is Hermes-owned SQLite state. JobApps should store its own app state separately and correlate via Hermes session/run IDs.
- Provider runtime resolution belongs to Hermes. JobApps should not decide the underlying LLM provider.
- Plugin tools are the right first bridge for native Hermes. MCP is the likely bridge if JobApps becomes a separate service.

## Configuration Philosophy

Configuration should be readable by humans and agents.

Good config candidates:

- sponsorship and location rules
- blocker thresholds
- company allowlist/denylist
- job source list
- template preferences
- banned phrases
- resume section ordering rules
- follow-up cadence
- approval thresholds

Bad config candidates:

- every tiny UI behavior
- premature workflow DSLs before one workflow is real
- anything that exists only to make the architecture look flexible

## Data Boundaries

Use four layers:

1. **App database**: durable structured truth for jobs, contacts, applications, materials, dates, statuses, prompts, research notes, progress, approvals, profile facts, proof points, application signals, tailoring requirements, portrayal decisions, and learning patterns.
2. **Private imports**: optional local seed files used to populate the app database. Their format is not stable and must not define runtime behavior.
3. **Hermes memory/profile**: durable preferences, lessons, high-level career direction, and session continuity. Do not store every application event here.
4. **Generated artifacts**: `.tex` materials and exports under ignored runtime directories, with database records pointing to them.

Add one app-owned human layer inside the database:

- `brain_entities`: canonical people, companies, constraints, projects, decision themes, proof points, preferences, and other recurring context.
- `brain_events`: immutable dated events for conversations, corrections, revisions, networking moves, decisions, approvals, research notes, follow-ups, and application state changes.

This is inspired by personal-brain systems, but it stays native to JobApps. No MCP server, no GBrain clone, no separate knowledge runtime. Hermes gets tools to read and write this layer through the existing JobApps plugin/tool surface.

## First Workflow Contract

Input: job URL or pasted job description.

Output:

- decision: apply, maybe, skip based on blocker preflight, not generic fit scoring
- reason for decision
- sponsorship/location/seniority/application-effort risk
- role family
- extracted application signals
- tailoring requirements
- matched eligible proof points
- strongest angle
- portrayal decisions and material-change provenance
- learning patterns when user corrections should repeat
- company/job research notes
- resume tailoring `.tex`
- cover letter `.tex`
- short-answer draft when useful
- networking search notes and outreach draft when useful
- prompt build sent to Hermes
- next action
- progress items and follow-ups
- recorded state and material-change provenance

If this workflow is not excellent, nothing else matters.

## UI Taste Direction

The app should feel like a focused operator cockpit, not a corporate ATS clone.

- use `design-system/TOKENS.css` as the visual baseline
- inherit Hermes deep teal, cream, gold, bronze, sans/mono typography, and chat rhythm
- layer JobApps naming and career-operator vocabulary on top
- dense but readable
- strong evidence cards
- visible status trail
- Hermes chat visible in the main workflow
- drafts beside source evidence
- approval buttons that are explicit and calm
- no fake gamification
- no productivity-dashboard clutter

## Future Expansion Gates

Add new systems only when the previous layer earns it:

- **Discovery** after manual job evaluation is useful.
- **Browser autofill** after materials and tracking are reliable.
- **Multi-run batching** after one-at-a-time workflow is stable.
- **Vector search** after database proof points and profile facts are too large for direct context.
- **External sending/submission** only after approval logging and preview are trustworthy.
