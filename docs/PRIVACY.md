# Privacy And Public Release Checklist

Hermes JobApps is designed to be public code with private runtime data.

## Never Commit

- SQLite databases, WAL files, or backups
- generated resumes, cover letters, PDFs, TeX builds, or exports
- real applicant profile imports
- application history or contact lists
- personal target-role rules, writing voice rules, proof-point preferences, outreach habits, or private plugin skills
- `.env` files, API keys, provider tokens, or local config
- Hermes profile memory, sessions, logs, or gateway state
- browser exports, downloaded job descriptions, or local caches

## Safe To Commit

- application code
- tests with synthetic examples
- sanitized Hermes plugins and skills
- example config with placeholder env var names
- public docs that describe architecture and setup
- public-safe UI assets

## Skills And Plugin Prompts

The public `skills/` directory and `.hermes/plugins/jobapps/skills/` directory
must stay generic. They should describe workflow mechanics, not a real person's
career strategy, voice, legal/work-status details, school/employer history,
email identity, or outreach preferences.

For real use, replace those public templates with private/local skills. See
[PERSONALIZATION.md](PERSONALIZATION.md).

## Pre-Push Checks

```bash
git status --short --ignored
git ls-files -o --exclude-standard
git diff --cached --check
rg -n "OPENAI_API_KEY|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|password|secret|token|api[_-]?key" .
rg -n "/Users/|\.sqlite|\.db|\.env|data/|private/" .
```

## GitHub Settings

Before broad sharing, enable GitHub secret scanning and push protection. If a secret is ever committed, rotate it first, then remove it from history.

## Public Snapshot Rule

Public releases should be published as sanitized snapshots. The private development repo can keep full working history; the public repo should receive only reviewed public trees.
