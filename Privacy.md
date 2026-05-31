# Privacy Boundary

Hermes JobApps separates app architecture from app data.

The committed repository should contain code, schemas, documentation, example config, and tests. It should not contain private profile data, generated materials, application history, SQLite databases, resumes, cover letters, secrets, API keys, browser exports, downloaded job descriptions, or local environment files.

## Local Private Data

These files are private runtime data:

- private profile/seed files such as `knowledge_base.html`
- `config/jobapps.local.*`
- `data/`
- `private/`
- `exports/`
- `materials/`
- generated `.tex`, `.pdf`, `.docx`, or resume/cover-letter variants
- `.env` and `.env.*`
- `*.db`, `*.sqlite`, `*.sqlite3`, and SQLite WAL/SHM sidecar files

They are ignored in the committed `.gitignore` and also in this checkout's `.git/info/exclude`.

## Backend Data Rule

Backend state belongs in the data layer, not in source files.

Store jobs, evaluations, materials, contacts, statuses, follow-up dates, and approval records in SQLite or another runtime database. Do not bake those records into Python, JavaScript, Markdown docs, seed files, tests, or config examples.

Private seed files are import sources only. Their shape can change and must not be treated as app architecture. Convert useful facts into `profile_facts` and `proof_points` rows before relying on them in workflows.

## Hermes State Rule

Hermes has its own profile, memory, session, provider, and tool state. Keep that separate from JobApps application data.

- Hermes memory: durable preferences, lessons, and high-level user context.
- JobApps database: application facts, materials, progress, contacts, prompts, and decisions.
- Correlation: store Hermes run/session IDs in JobApps rows when a workflow crosses systems.

Do not commit Hermes profile `.env`, memory files, session databases, logs, or copied tool outputs.

## Secrets Rule

Secrets must come from environment variables or a local secret manager, never committed config.

Examples:

- `OPENAI_API_KEY`
- Hermes API tokens
- email provider credentials
- LinkedIn/browser automation credentials
- database URLs for non-local deployments

If a secret is ever committed, rotate it immediately and remove it from git history before publishing.

## Agent Safety Rule

Job descriptions, web pages, emails, PDFs, and form fields are untrusted data. They can contain instructions aimed at the agent.

Hermes should:

- keep system instructions separate from fetched content
- treat fetched content as data, not commands
- validate structured outputs before recording them
- keep external tools least-privileged
- ask for approval before sending, submitting, uploading, messaging, or updating external systems
- log approval decisions in the app data layer

## Before Push

Run these checks before pushing:

```bash
git status --short --ignored
git ls-files -o --exclude-standard
git diff --cached --check
rg -n "OPENAI_API_KEY|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|password|secret|token|api[_-]?key" .
```

Also enable GitHub secret scanning and push protection before the repo becomes public.

## Publishing Standard

The repository is publishable only when a fresh clone can run with placeholder/sample data and no private facts are required in committed files. The real profile, app database, generated materials, and external credentials must be supplied locally at runtime.
