# Integrations

Hermes JobApps runs locally without external services. Integrations add agent reasoning, search, contact enrichment, draft creation, and PDF compilation.

## Hermes API

Hermes gives the cockpit streaming chat, named sessions, slash commands, command catalogs, provider routing, memory, and tool dispatch.

Example local profile setup:

```bash
hermes profile create jobapps
cat >> ~/.hermes/profiles/jobapps/.env <<'EOF'
API_SERVER_ENABLED=true
API_SERVER_PORT=8642
API_SERVER_KEY=<local-api-key>
API_SERVER_MODEL_NAME=jobapps
HERMES_ENABLE_PROJECT_PLUGINS=true
EOF

export HERMES_API_BASE=http://127.0.0.1:8642/v1
export HERMES_API_KEY=<local-api-key>
export HERMES_API_MODEL=jobapps

hermes --profile jobapps gateway start
python3 -m hermes_jobapps.server --port 8765
```

Keep the JobApps profile API-only if another Hermes profile owns messaging adapters.

## Hermes Project Plugin

The public repo includes `.hermes/plugins/jobapps`. Enable project plugins in the Hermes profile that runs this repo:

```bash
export HERMES_ENABLE_PROJECT_PLUGINS=true
hermes plugins enable jobapps
```

The plugin registers `jobapps_*` tools, the `/jobapps` command, a cockpit skill, and pre-call context injection from the SQLite database.

The committed plugin skill is generic. Before real use, replace
`.hermes/plugins/jobapps/skills/jobapps-cockpit/SKILL.md` with a private local
version that matches your target roles, proof-point policy, writing voice, and
outreach preferences. Do not publish that private replacement in a public fork.

## Native Hermes TUI And Web TUI

The JobApps web dashboard is not the only way to operate the system. With the project plugin enabled, you can work directly in the native Hermes TUI or Hermes web TUI/dashboard and still update the same JobApps SQLite state through `jobapps_*` tools.

```bash
hermes --profile jobapps --tui
```

In that mode, Hermes can evaluate roles, record proof points, create materials, cache contacts, request approvals, and update follow-ups through the plugin. The JobApps dashboard can then be opened or refreshed as a reference cockpit for the same database state.

Use the dashboard when you want dense visual review. Use the native Hermes surfaces when you want a full agent conversation or a terminal-native workflow.

## Exa Search

Exa powers optional job discovery and public people search.

```bash
export EXA_API_KEY=<exa-api-key>
```

Without `EXA_API_KEY`, the app still runs. Official ATS URL hydration continues to work for supported URLs, while Exa-backed search reports a visible missing-key status.

## Exa Websets

Websets are available as a slower contact-enrichment fallback, especially when a normal people search finds useful contacts but no verified email. They are disabled only by configuration, not by code removal.

Use Websets deliberately because enrichment can be slower and more expensive than normal search.

## Gmail Drafts

JobApps can create Gmail drafts through `gog`, but it never sends email.

The networking tool invokes:

```bash
gog --gmail-no-send gmail drafts create
```

That command must be authenticated locally. If `gog` is unavailable or not authenticated, the tool fails visibly instead of pretending the draft was created.

## LaTeX And PDFs

Generated materials are saved as TeX. PDF compilation is optional. The app checks configured compiler paths and tries supported compilers in order:

- `tectonic`
- `latexmk`
- `xelatex`
- `pdflatex`

If no compiler is installed, TeX materials still save and the compile status reports the missing compiler clearly.

## Environment Summary

```bash
export HERMES_API_BASE=http://127.0.0.1:8642/v1
export HERMES_API_KEY=<local-api-key>
export HERMES_API_MODEL=jobapps
export HERMES_JOBAPPS_DB=/path/to/local.sqlite3
export HERMES_JOBAPPS_CONFIG=/path/to/local-config.json
export EXA_API_KEY=<exa-api-key>
```

Never commit real values for these variables.
