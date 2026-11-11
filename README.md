# JobApps

A job-search workspace for the [Hermes](https://github.com/NousResearch/hermes-agent) agent.

Your whole search lives in one folder of plain files: who you are, what you have done, every job you are pursuing with its resume and letter, the people you are talking to. Hermes reads and writes those files, tailors documents from your real evidence, checks them, and keeps track of what is due.

There is no database and no hidden memory. You can open, edit and back up everything yourself.

## What it does

- **Tracks the pipeline.** `/jobapps` shows what is due, which applications have gone quiet, what is ready to send, and who to reach.
- **Takes in postings.** Paste a link or a description. JobApps saves it, checks it against your hard blockers and lists the requirements.
- **Writes from your evidence.** One call hands the agent the posting, your profile, your voice, your rules and your evidence files. Bundled skills cover strategy, resumes, cover letters, application answers, outreach, interview prep and offers.
- **Plans before it writes.** A short strategy per job (the thesis, the proof, the gap, the way in) keeps the resume, letter, answers and outreach arguing the same case.
- **Checks the result.** Each document is built to PDF, measured for layout and linted for weak bullets, leaked notes, unsupported numbers and posting coverage.
- **Catches the fatal slips.** Another employer's name left in a letter, contact details that differ from your profile, a PDF a parser cannot read, the relevant experience buried at the bottom.
- **Nudges at the right moment.** Marking a job ready or applied tells you who to reach, which form questions are unanswered and whether the posting has gone stale. Optional scheduled runs give a daily brief, a scan for fresh postings and a weekly review.
- **Finds roles and people.** Optional search saves postings as leads and lists people at a company. Nothing is sent on your behalf; Gmail support is draft-only.
- **Shows it all.** A local cockpit, also available as a tab in the Hermes dashboard.

## Install

Requires Python 3.11+ and Hermes 0.21 or newer.

```sh
hermes plugins install Prashant002-1/hermes-jobapps
hermes plugins enable jobapps
```

Start a new Hermes session and say:

> Set up my JobApps workspace.

The onboarding skill creates `~/JobApps`, fills your profile and builds one evidence file per experience from your existing resume.

To set the folder up by hand instead:

```sh
python3 -m hermes_jobapps init --name "Your Name"
python3 -m hermes_jobapps doctor
```

Run those from the plugin folder (`~/.hermes/plugins/jobapps`).

## Use

Talk to Hermes as you normally would:

- "Here's a posting: <link>. Tailor my resume."
- "Write the cover letter for the Northstar role."
- "I applied to Fieldwork today."
- "What should I follow up on this week?"
- "Find engineering managers at Northstar and draft a note."
- "I have a technical screen with Meridian on Thursday. Help me prepare."

Or open the cockpit:

```sh
python3 -m hermes_jobapps ui
```

## The workspace

```
~/JobApps/
  profile/profile.md     who you are, what you want, constraints
  profile/voice.md       how you write
  profile/playbook.md    rules learned from your corrections
  evidence/*.md          one file per experience, project, degree or award
  jobs/<id>/             job.md plus the resume, letter, answers and PDFs
  people/*.md            people you chose to track
  leads/*.md             postings found by search, not yet decided
  templates/             your base resume and letter
  settings.json          blockers and follow-up timing
```

Set `JOBAPPS_HOME` to use a different folder. Correct the agent once and it updates `playbook.md`; you can edit that file yourself at any time.

## Optional tools

| Tool | Used for |
|---|---|
| [Typst](https://typst.app) | Building resumes and letters. |
| Tectonic | Building TeX letters. |
| Poppler (`pdftotext`, `pdfinfo`) | Resume layout checks. |
| `EXA_API_KEY` | Job and people search. |
| `gog` | Gmail drafts. |

`python3 -m hermes_jobapps doctor` reports which are present. Everything else works without them.

## Coming from the SQLite version

```sh
python3 -m hermes_jobapps migrate path/to/hermes-jobapps.sqlite3 --dry-run
python3 -m hermes_jobapps migrate path/to/hermes-jobapps.sqlite3
```

The old database is opened read-only and left untouched. Profile facts, proof points, active rules, jobs with their documents, tracked people and recent leads are written as files; `MIGRATION.md` in the workspace lists what was carried over.

## Privacy

The plugin stores nothing outside your workspace folder and sends nothing anywhere except the searches you ask for. Keep the workspace out of public repositories. See [Privacy.md](Privacy.md).

## Development

```sh
python3 -m unittest discover -s tests
node --test tests/test_cockpit.cjs
```

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains the design. Licensed under MIT.
