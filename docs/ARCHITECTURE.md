# Architecture

JobApps has one idea: the job search is a folder of plain files, and the agent is good enough to work in it directly.

## Why files

A personal job search is small. A few dozen evidence files, a few hundred jobs and a handful of people fit comfortably in what a current model can read. Putting that behind a database, a retrieval index and a memory ledger made the agent slower and less reliable: it spent tool calls writing records nobody read, and it could miss experience that a ranked search did not return.

Files remove those problems.

- **Nothing is hidden.** You can open, edit, search, diff and back up everything. So can any agent, with or without this plugin.
- **Context is whole.** The agent reads the evidence files themselves, not a ranked sample.
- **One copy.** A resume is the file in the job folder. There is no second copy to drift out of date.
- **Few tools.** Nine small tool schemas instead of dozens, so every turn is cheaper and faster.

## Layout

```
~/JobApps/
  profile/profile.md     who you are, what you want, constraints
  profile/voice.md       how you write
  profile/playbook.md    rules learned from your corrections
  evidence/*.md          one file per experience, project, degree or award
  jobs/<id>/job.md       posting, assessment, requirements, notes, log
  jobs/<id>/...          resume, letter, answers, PDFs, qa/ reports
  people/*.md            people you chose to track
  leads/*.md             postings found by search, not yet decided
  templates/             base resume and letter sources
  settings.json          blockers, follow-up timing, tool options
```

Each record starts with a flat `key: value` block between `---` lines. `hermes_jobapps/workspace.py` reads and writes that format and leaves lines it does not understand untouched.

## What code does

Code exists only for what files cannot do on their own.

| Module | Job |
|---|---|
| `workspace.py` | File format, folder layout, safe paths, atomic writes. |
| `tracking.py` | Computed views (what is due, quiet, ready), the writing brief, stage changes, people. |
| `intake.py` | Turn a posting into a job folder; check configured blockers; save search results as leads. |
| `sources.py` | Outside lookups: ATS posting APIs, job and people search, draft-only Gmail. |
| `check.py` | Build a document and check it: layout QA for resumes, content lint and submission checks for everything. |
| `build.py`, `resume_qa.py` | Typst and TeX builds, PDF geometry measurement. |
| `content_qa.py` | Deterministic writing checks: weak or generic bullets, missing consequence, numbers absent from evidence, posting coverage. |
| `submission_qa.py` | The mistakes that sink an application: another employer's name, contact details that differ from the profile, PDF text a parser cannot read, relevance buried low on the page. |
| `api.py` | The cockpit API as plain functions, shared by both hosts. |
| `server.py` | Local cockpit host. |
| `plugin.py` | Hermes registration: tools, skills, `/jobapps`, one system prompt pointer. |
| `migrate.py` | One-way import from the legacy SQLite database. |

## The agent's path through a job

1. `jobapps_add_job` creates `jobs/<id>/job.md` with the verbatim posting, the blocker check and any form questions the posting site exposes.
2. `jobapps_brief` returns the posting, the profile, the voice, the playbook rules for that document, the evidence files and the closest earlier documents, in one call.
3. The agent writes a short Strategy section into `job.md`: the thesis, the proof for each deciding requirement, the gap, the way in. Every later document argues that same case.
4. The agent loads one writing skill and writes the document into the job folder with its own file tools.
5. `jobapps_check` builds the PDF and reports layout, content and submission defects with exact repairs. The agent fixes and re-runs, at most three rounds.
6. `jobapps_track` records the stage, the next action and its due date, and returns reminders at the moments that matter: nobody tracked at the company, unanswered form questions, a posting that has gone stale.

`jobapps_overview` answers "where am I" at any time by scanning frontmatter.

## Skills

The craft lives in `skills/`: application strategy, resume writing, cover letters, application answers, outreach, interview prep, offers, job search, document builds and onboarding, with `jobapps:jobapps` as the entry point. They ship with the plugin, so Hermes's skill curator never archives them. Personal rules do not belong there. They live in the workspace playbook and voice files, where the user can read and change them.

## Cockpit

The cockpit is a view over the same folder. `api.handle()` serves it, hosted either by `python -m hermes_jobapps ui` or as a tab in the Hermes dashboard (`dashboard/`). It shows the pipeline, each job with its documents and check state, people and leads, and lets you change a stage, set a next action or add a posting. It holds no state of its own.

## Proactive runs

The plugin registers three Hermes automation blueprints the user can switch on: a weekday brief of what is due, a weekday scan for fresh postings, and a weekly review of the funnel. They recommend only; they never change or send anything.

## Readiness

A check writes `qa/<file>.json` beside the document with the file's hash. The saved result is `pass`, `review` or `fail`, and becomes `stale` as soon as the file changes. A job cannot be marked `ready` while a resume is unchecked, stale or failing, unless the user explicitly accepts that.

## What was removed

The SQLite store, the evidence retrieval index, the career-brain entity and event ledger, application signals, portrayal-decision records, prompt builds, approval rows, tool-call logs, background agent runs and the embedded chat. `python -m hermes_jobapps migrate` carries the data that matters into files and leaves the old database untouched.
