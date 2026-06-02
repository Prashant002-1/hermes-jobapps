# Hermes JobApps

Hermes JobApps is a local job-application cockpit. Paste a job, run blocker preflight, prepare database state, build Typst resume materials and TeX cover-letter materials, chat with Hermes, and record the next action.

The app owns structured state. Hermes performs transitions. A pasted JD means apply intent unless the role has a hard blocker: sponsorship/work authorization, impossible seniority, impossible location, or unreasonable application effort.

## Run Locally

This version uses only the Python standard library for the cockpit.

```bash
python3 -m hermes_jobapps.server --port 8765
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

For a detachable local process, use a terminal multiplexer such as `screen`:

```bash
screen -dmS hermes-jobapps sh -lc 'python3 -m hermes_jobapps.server --port 8765'
screen -r hermes-jobapps
```

A separate `screen` is just a named terminal session that can keep the app
running after you detach from it.

## Connect Hermes

Run Hermes with the API server enabled, preferably in a dedicated profile. In
Hermes, a profile has its own config, `.env`, sessions, memory, skills, and
gateway process. JobApps only needs the API server, but Hermes hosts that API
from the profile gateway process.

```bash
hermes profile create jobapps
cat >> ~/.hermes/profiles/jobapps/.env <<'EOF'
API_SERVER_ENABLED=true
API_SERVER_PORT=8642
API_SERVER_KEY=<local-api-key>
API_SERVER_MODEL_NAME=jobapps
HERMES_ENABLE_PROJECT_PLUGINS=true
EOF

# Keep this profile API-only if your default Hermes profile already owns
# Discord/Slack/etc. messaging tokens.
hermes --profile jobapps gateway start
```

Point the cockpit at that API:

```bash
export HERMES_API_BASE=http://127.0.0.1:8642/v1
export HERMES_API_KEY=<local-api-key>
export HERMES_API_MODEL=jobapps
python3 -m hermes_jobapps.server
```

For local use, you can also put the API settings in ignored
`config/jobapps.local.json` instead of exporting them each time.

The committed `.hermes/plugins/jobapps` plugin exposes JobApps database tools,
the `/jobapps` command, context injection, and a workflow skill to native Hermes
sessions. Enable project plugins in the Hermes environment you use for this repo:

```bash
export HERMES_ENABLE_PROJECT_PLUGINS=true
hermes plugins enable jobapps
```

The cockpit chat sends normal conversation to the `jobapps` profile API using
streaming Responses events. Native Hermes slash commands such as `/help`,
`/profile`, `/model`, and `/jobapps` route through Hermes' own command surfaces
for the same profile. The UI also reads Hermes' command catalog so slash
commands and installed skill commands can appear in the chat composer.

## Session State Behavior

Hermes owns chat session history. JobApps owns application data. The browser
owns only a lightweight cockpit checkpoint.

- Completed Hermes chat turns are stored by the `jobapps` Hermes profile.
- JobApps writes structured state to SQLite as each tool/workflow step happens.
- The browser saves the active chat selection, visible recent transcript,
  current view, draft composer text, last usage panel, and in-flight turn marker
  to local storage as those values change.
- Closing or refreshing the tab does not send a special shutdown signal. On the
  next load, the cockpit restores its local checkpoint. If a turn was in flight,
  it is shown as interrupted instead of treated as complete.
- If the local browser checkpoint is missing, use the Sessions panel to resume a
  Hermes session from the profile store.

## Generated Materials

Generated application materials are app-owned rows in SQLite with optional local
files under the configured `materials_path` (`data/materials` by default). The
default file convention is:

```text
data/materials/<job_id>/resume_tailoring.typ
data/materials/<job_id>/cover_letter.tex
data/materials/<job_id>/resume.typ
data/materials/<job_id>/<material_kind>.typ or .tex
data/materials/<job_id>/<material_name>.pdf
```

`<job_id>` is the 12-character JobApps job id, so multiple job descriptions in
the same Hermes conversation get separate material folders and do not overwrite
each other. The Materials tab shows generated artifacts, compile status, PDF
links when available. Old resumes, cover letters, CVs, and private seed files
should be imported into structured database records when their facts still
matter; they are not browsed as a live app surface.

## Discovery

The Discovery view is a removable feed layer. It stores candidate jobs separately
from application jobs, hydrates Greenhouse, Lever, and Ashby URLs through their
official public job surfaces, and promotes a candidate into the normal JobApps
workflow only when you choose Prepare. The implementation notes and removal
boundary live in [docs/DISCOVERY.md](docs/DISCOVERY.md).

Exa search is configured through an environment variable. Keep the key outside
git, for example in the dedicated Hermes profile env or your shell:

```bash
export EXA_API_KEY=<exa-api-key>
```

Without `EXA_API_KEY`, ATS URL hydration still works and Exa search reports a
missing-key status. Set `discovery.enabled` to `false` to disable search,
hydrate, and promote actions while leaving already-promoted JobApps records
alone.

The same key also powers networking people search. Hermes can cache public
contacts with `jobapps_find_people` and create Gmail drafts with
`jobapps_create_gmail_draft`, which calls `gog --gmail-no-send gmail drafts
create`. JobApps exposes no email-send tool.

The default Hermes dashboard can keep running separately:

```bash
hermes dashboard --tui
```

That dashboard is for the active/default Hermes profile unless launched with a
different profile. JobApps talks to the dedicated `jobapps` API profile.

## Data Model

The SQLite database is the source of truth for app data:

- profile facts and proof points with lifecycle state
- discovery candidates and source sightings
- application signals extracted from pasted jobs
- tailoring requirements extracted from JD needs
- portrayal decisions linking requirements to material framing
- learning patterns from reusable corrections/preferences
- retrieval chunks and local FTS search over eligible evidence
- jobs and evaluations
- prompt builds
- `.tex` resume and cover-letter materials
- research notes
- application changes
- contacts, progress, follow-ups, approvals
- Hermes run/session IDs

The cockpit surfaces pending approval gates and read-only database health. Health
checks show stale or unattached records so you can review them before using the
database for a real application; they do not delete private app state.

Private seed files can populate the database, but they are not runtime source of truth or schema.

Import private structured seed records when useful:

```bash
python3 -m hermes_jobapps.importer private/profile-seed.json --dry-run
python3 -m hermes_jobapps.importer private/profile-seed.json
```

Non-JSON private files must include a `JOBAPPS_IMPORT_RECORDS` JSON block with
`profile_facts` and/or `proof_points`; the app never parses `knowledge_base.html`
as a live schema.

## What Exists

- `hermes_jobapps/`: SQLite repository, tools, Hermes client, prompt builder, Typst resume helpers, TeX cover-letter/legacy helpers, workflow, and HTTP server.
- `.hermes/plugins/jobapps/`: Hermes-native tool and context bridge.
- `web/`: the cockpit UI.
- `config/jobapps.default.json`: committed, non-secret runtime defaults.
- `config/jobapps.example.yaml`: human-readable example settings.
- `docs/ARCHITECTURE_RESEARCH.md`: research-backed architecture notes.
- `docs/BRANDING.md`: Hermes-native JobApps visual and naming guidance.
- `design-system/`: extracted Hermes visual tokens and component references.
- `Privacy.md`: privacy and repo-boundary rules.
- `tests/`: standard-library tests for the workflow engine and database.

## Privacy Boundary

Do not commit local profile data, generated materials, SQLite databases, exports, resumes, cover letters, secrets, or `.env` files. The committed app code should be publishable without exposing backend private data.

Keep `docs/` public-safe. Local-only secrets, private profile notes, generated
materials, and machine-specific runtime data belong in ignored config/profile
files, not in repo documentation.

See [Privacy.md](/Users/prashantshah/Desktop/Prashant/Prashant%20Gallery/Code/hermes-jobapps/Privacy.md).
