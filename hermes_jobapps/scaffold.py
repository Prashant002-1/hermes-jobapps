"""Starter files for a new JobApps workspace."""

from __future__ import annotations

import json
from pathlib import Path


TEMPLATES_DIR = Path(__file__).resolve().parent / "resources" / "templates"

WORKSPACE_README = """# JobApps workspace

This folder is the whole job search. Every record is a plain file you can open,
edit, search and back up. Agents read and write the same files.

| Folder | What lives there |
|---|---|
| `profile/profile.md` | Who you are: contact details, target direction, constraints, preferences. |
| `profile/voice.md` | How you write, with phrases to use and to avoid. |
| `profile/playbook.md` | Rules learned from your corrections, one section per kind of document. |
| `evidence/` | One file per experience, project, degree or award: verified facts and approved wording. |
| `jobs/<id>/` | One folder per application: `job.md` (posting, notes, log) plus the resume, letter and answers. |
| `people/` | One file per person you chose to track. |
| `leads/` | Postings found by search that you have not decided on. |
| `templates/` | Your base resume and letter sources. The starter files hold example content: replace all of it with your own. |
| `settings.json` | Blockers, follow-up timing and tool options. |

## Conventions

- The block between the `---` lines at the top of a file holds simple `key: value` fields. Keep it flat.
- A job's `status` is one of: new, ready, applied, interviewing, offer, rejected, closed, skipped.
- Dates are `YYYY-MM-DD`.
- Edit a rule in `playbook.md` in place. Do not append a second version of the same rule.
- Evidence files hold only what you can defend. Set `status: retired` to keep a file without using it.
- Files and folders whose names start with `_` are ignored.
"""


PROFILE = """---
name: {name}
email:
phone:
location:
linkedin:
github:
website:
headline:
---

# Profile

## Target direction

_What roles you want and why. One short paragraph._

## Constraints

_Work authorization, location, start date, seniority range, anything that rules a role out._

## Preferences

_Company stage, team type, industries, compensation floor, deal-breakers._

## Education

_Degree, school, dates, and how to display GPA or honors._

## Skills

_The inventory you can defend, grouped the way your resume groups it._
"""


VOICE = """# Voice

_How you write. The agent matches this in letters, answers and messages._

## Sounds like me

- _Direct, specific sentences. Plain words._

## Never

- _Phrases, tones and habits to avoid._

## Samples

_Paste two or three paragraphs you wrote and liked._
"""


PLAYBOOK = """# Playbook

Rules learned from your corrections. One section per topic. Edit a rule in
place when it changes.

## All documents

## Resume

## Cover letter

## Application answers

## Outreach

## Interview

## Workflow
"""


EVIDENCE_TEMPLATE = """---
title: Role or project name
type: experience
organization:
role:
start:
end:
status: active
tags: []
---

# Role or project name

## What it was

_One or two sentences a stranger would understand: the product, the users, your position._

## Facts

- _What you built, decided or owned. Mechanism first._
- _What changed because of it. Only numbers you can defend._

## Approved wording

- _Bullets you have already approved, ready to reuse or adapt._

## Do not claim

- _Limits: what you did not do, numbers that are not confirmed, names not to use._
"""


PERSON_TEMPLATE = """---
name: Full Name
company:
role:
email:
linkedin:
status: to_contact
next_touch:
jobs: []
---

# Full Name

## Why

_Why this person matters to the search._

## Notes

## Log
"""


def starter_files(*, name: str = "") -> dict[str, str]:
    settings = {
        "rules": {"needs_sponsorship": None},
        "criteria": {"blockers": []},
        "followups": {"application_check_after_days": 10, "networking_after_days": 5},
    }
    templates = {
        f"templates/{path.name}": path.read_text(encoding="utf-8")
        for path in sorted(TEMPLATES_DIR.glob("*.typ"))
    }
    return {
        **templates,
        "README.md": WORKSPACE_README,
        "settings.json": json.dumps(settings, indent=2) + "\n",
        "profile/profile.md": PROFILE.format(name=name),
        "profile/voice.md": VOICE,
        "profile/playbook.md": PLAYBOOK,
        "evidence/_TEMPLATE.md": EVIDENCE_TEMPLATE,
        "people/_TEMPLATE.md": PERSON_TEMPLATE,
    }
