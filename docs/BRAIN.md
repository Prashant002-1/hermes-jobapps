# JobApps Career Brain

JobApps has a small career-brain layer inside the same SQLite database as the rest of the app. It is not a GBrain clone, not an MCP server, and not a second agent framework.

The purpose is to keep the human context alive: identity, constraints, job-search preferences, people, companies, proof points, decisions, daily notes, projects, conversations, revisions, networking history, and the reasons behind material changes.

## Shape

The brain has two primitives:

- `brain_entities` — canonical things worth recognizing again, such as a person, company, constraint, project, proof point, or decision theme.
- `brain_events` — immutable dated events: a conversation signal, correction, material revision, portrayal decision, research note, approval, follow-up, or application move.

SQLite FTS indexes events for local search. This keeps retrieval simple and inspectable before adding embeddings or external services.

## Hermes Boundary

Hermes stays the reasoning engine. JobApps stays the state owner.

Hermes can use:

- `jobapps_brain_context`
- `jobapps_search_brain`
- `jobapps_upsert_brain_entity`
- `jobapps_record_brain_event`

Specific tools still matter. If a memory is actually a proof point, profile fact, learning pattern, tailoring requirement, portrayal decision, material revision, or follow-up, Hermes should use that specific tool too. The brain event is the human trail; the specific table is the operational source of truth.

## Capture Policy

The app now records:

- chat turns as low-importance conversation events
- user messages with preference/correction/constraint signals as higher-importance events
- profile fact and proof point updates
- opportunity creation
- research notes
- tailoring requirements
- portrayal decisions
- material saves and revisions
- application changes
- progress, follow-ups, and approvals

This gives JobApps a memory trail without turning every detail into a generation rule. Reusable conclusions should be promoted into profile facts, proof points, or learning patterns.

## Future Gate

If the brain grows large, add a summarization/consolidation pass that reads retrieved events and writes a compact entity summary back to `brain_entities.summary`. That can use Hermes or another configured model, but it should remain an optional local workflow, not a required service.
