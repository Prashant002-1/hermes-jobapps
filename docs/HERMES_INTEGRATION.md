# Hermes Integration

JobApps is designed as a domain cockpit around Hermes, not a replacement for Hermes.

## Runtime Pieces

```text
Hermes profile: jobapps
  API server: http://127.0.0.1:8642/v1
  native memory/session/provider/tool runtime
  project plugin: .hermes/plugins/jobapps

JobApps cockpit
  local web server: http://127.0.0.1:8765
  SQLite app DB: data/hermes-jobapps.sqlite3
  generated materials: data/materials/
```

Hermes uses the word "gateway" for the long-running Hermes process. A gateway
can host messaging adapters, but it is also how the API server stays alive. For
JobApps, the `jobapps` profile gateway is intentionally API-only: no Discord,
Slack, Telegram, or submit/send side effects are required.

Two Hermes profiles mean two Hermes homes and two independent long-running
processes when both are active:

- default profile: `~/.hermes`, normal dashboard/TUI/messaging setup
- JobApps profile: `~/.hermes/profiles/jobapps`, API server for this app

The profile boundary separates config, `.env`, skills, memory, sessions, state,
cron jobs, logs, and service names. It is not a filesystem sandbox; local tools
still run as the same OS user.

## Recommended Setup

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

hermes plugins enable jobapps
hermes --profile jobapps gateway start
```

Then run the app:

```bash
python3 -m hermes_jobapps.server
```

Detached app process:

```bash
screen -dmS hermes-jobapps sh -lc 'python3 -m hermes_jobapps.server --port 8765'
screen -ls
screen -r hermes-jobapps
```

A separate `screen` is a detachable terminal. It is not another app screen or
web page; it is just a terminal session with a name. If a screen session is
closed unexpectedly, check the port directly:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
curl http://127.0.0.1:8765/api/state
```

If a process is listening but `curl` returns an empty reply, stop that orphaned
app process and start a fresh one. Hermes updates and terminal restarts can
close or detach long-running processes, so port checks are the fastest way to
separate "not running" from "running but stale."

If the default Hermes profile already owns messaging platforms such as Discord,
keep the `jobapps` profile API-only by removing or commenting those messaging
tokens from `~/.hermes/profiles/jobapps/.env`. The app should talk to the
`jobapps` profile on `127.0.0.1:8642`; the default profile dashboard/gateway can
continue running separately.

## API Use

- In-app Hermes chat uses streaming `/v1/responses` with a named conversation.
- The app renders response lifecycle, token deltas, tool/function-call events,
  and final response IDs from Hermes' SSE stream.
- Longer opportunity workflows use `/v1/runs` and can attach to run events.
- In-app slash commands that start with `/` route to Hermes' native command
  surfaces under the same `jobapps` profile, so `/help`, `/profile`, `/model`,
  `/jobapps`, skill commands, quick commands, and plugin commands stay native.
- The app reads Hermes' command catalog for composer menus. `/model` also uses
  Hermes' native model option data so the chat can show dashboard-like model
  visibility without embedding the full Hermes dashboard.
- The app stores Hermes run/session IDs in its own database for correlation.
- Hermes stores its own session history in the Hermes profile state.

The Hermes web dashboard achieves full browser TUI parity by spawning the real
Hermes TUI behind a PTY and rendering it in xterm.js. JobApps is not trying to
clone that. It carries over the key surfaces that matter for this workflow:
streaming text, visible tool calls, status, command catalog, profile/model
state, and native slash commands.

## Native Hermes Use

With the project plugin enabled, native Hermes can:

- read compact JobApps context through `pre_llm_call` context injection
- call `jobapps_*` tools
- load `jobapps:jobapps-cockpit`
- use `/jobapps` to view a compact dashboard summary

The public `jobapps-cockpit` skill is a generic template. For real use, replace
it locally with private rules for your own target roles, work constraints,
writing voice, proof-point policy, and outreach strategy.

You can also ignore the web cockpit and run native Hermes against the JobApps
profile:

```bash
hermes --profile jobapps --tui
```

The Hermes profile skills, memory, sessions, self-improvement behavior, and
provider config still work normally. The JobApps database tools are available
when the project plugin is enabled from this repo; if you run outside the repo,
Hermes profile behavior remains, but repo-local app tools may not be loaded.

## Boundary

Use JobApps tools for structured app state changes. Use Hermes memory for durable preferences and lessons. Do not store application history only in Hermes memory, and do not store every session memory item in the JobApps database.

## Startup Map

Typical local setup:

```bash
# Optional default Hermes dashboard/TUI for normal Hermes use.
hermes dashboard --tui

# JobApps Hermes API profile.
hermes --profile jobapps gateway start

# JobApps web app.
python3 -m hermes_jobapps.server --port 8765
```

Health checks:

```bash
hermes profile list
curl -H "Authorization: Bearer <local-api-key>" http://127.0.0.1:8642/v1/capabilities
curl http://127.0.0.1:8765/api/hermes/status
curl http://127.0.0.1:8765/api/hermes/commands
```

If the API says "connection refused," the JobApps app is up but the Hermes
profile gateway/API server is not. If the browser cannot load JobApps, the app
server is not up or is stale. If slash commands work but normal chat does not,
check the Hermes API key/base URL and `/v1/capabilities`.
