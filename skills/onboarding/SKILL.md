---
name: onboarding
description: "Use when setting up or repairing a JobApps workspace. Fills the profile, constraints and blockers, builds evidence files by interview, captures voice, stores the base resume, and ends with a first overview."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, onboarding, setup, profile, evidence]
    related_skills: [jobapps:jobapps, jobapps:resume-writing, jobapps:job-search]
---

# Onboarding

Run when `jobapps_overview` returns a `setup` list, when the user says they are new, or when a profile or evidence gap blocks other work. The goal is the smallest true workspace that lets the first resume be written well. Everything is filled from the user's documents and answers. Nothing is invented to complete a template: an empty section is correct until the user fills it.

## How to run it

- Start with `jobapps_overview`. It reports the workspace path and what is missing. Read the files that exist before asking anything; never overwrite content that is already there.
- Short and resumable. One topic per turn, a few questions at a time. A first sitting needs only contact details, target direction, constraints and the two most relevant experiences. The rest can wait for the next job.
- The files are the progress record. Placeholder lines (italic text between underscores) mark sections still to fill; replace them when filling. Evidence marked `needs_review` marks facts still to confirm. To resume, read the files and continue from the gaps.
- Repeat back what you recorded in a line or two, not the whole file.
- If the user wants to start on a posting right away, do the minimum (steps 1 to 3 and one evidence file) and continue later.

## Steps

### 1. Collect what exists
Ask for a current resume (any format), a LinkedIn export or profile text, a portfolio link, and any cover letters or messages they wrote themselves. Read them fully. Treat them as the candidate's own claims: a good starting point, not yet confirmed evidence.

### 2. Profile
Fill `profile/profile.md`.
- Frontmatter (`name`, `email`, `phone`, `location`, `linkedin`, `github`, `website`, `headline`): copy exactly from their documents, then confirm. These go on every document.
- **Target direction**: ask what roles they want, at what level, and why. Write their answer in their words, one short paragraph. Do not broaden it to seem more marketable.
- **Constraints**: work authorization (step 3), locations and work mode, earliest start date, level range, anything that rules a role out.
- **Preferences**: company stage, team type, industries, salary floor, deal-breakers. These guide search and form answers.
- **Education**: degree, institution, dates, and how to show GPA or honors. Mark an unfinished degree as expected.
- **Skills**: the inventory they can defend in an interview, grouped as their resume groups it. Ask about anything listed that no experience supports.

### 3. Work authorization and blockers
Ask plainly, once: are they authorized to work where they are applying, and will they need employer sponsorship now or later? Record the answer in Constraints at the level of detail they choose, plus the wording they want used on forms. Then set `rules.needs_sponsorship` in `settings.json`:

| Value | Meaning | Effect on a new posting |
|---|---|---|
| `true` | They need sponsorship | A posting that says it will not sponsor is decided `skip`; one that offers it is noted as clear |
| `false` | They do not | No sponsorship check |
| `null` | Not yet known | Sponsorship wording is noted, nothing is blocked |

Leave `null` rather than guess. Do not give legal or immigration advice.

Then ask what should stop a posting automatically, and add only real deal-breakers to the `criteria.blockers` list. A preference is not a blocker. Example entries:

```json
{"area": "seniority", "type": "title", "patterns": ["staff", "principal", "director"], "severity": "blocker", "action": "Skip unless the user wants a reach application."}
{"area": "experience", "type": "years", "threshold": 8, "severity": "flag", "action": "Ask before tailoring."}
{"area": "location", "type": "pattern", "patterns": ["relocation required"], "severity": "flag", "action": "Confirm the location works."}
```

- `type`: `pattern` searches the title, location and description for the listed phrases; `title` searches the title only; `years` matches when the posting asks for at least `threshold` years.
- `severity`: `blocker` makes the decision `skip`; `flag` makes it `pending`, so the user is asked; `clear` records a reassuring phrase.
- Patterns are literal phrases, not case-sensitive. Use the wording postings actually use. Keep the list short.
- After editing, confirm the file is still valid JSON. A malformed entry stops posting intake.

### 4. Evidence
Create one file per experience, project, degree or award by copying `evidence/_TEMPLATE.md` to `evidence/<short-slug>.md`. Start with what matters most for the target direction.
- Draft Facts from the user's documents, then interview for what documents leave out: the mechanism and the consequence. Load `references/evidence-interview.md` for the questions and a worked file.
- Set `status: needs_review` on any file whose facts the user has not yet confirmed. Change it to `active` when they have. Use `retired` for work they do not want used.
- Put only wording the user stands behind under Approved wording. Put limits under Do not claim: numbers they cannot defend, parts others built, names not to use.
- Never sharpen a vague claim into a precise one. If the resume says "improved performance" and the user has no figure, the fact stays without a figure.

### 5. Voice
Ask for two or three things they wrote themselves and liked: an email, a letter, a post. Paste them under Samples in `profile/voice.md`. From the samples, write four to six observations under Sounds like me (sentence length, formality, how they open and close, what they never do) and ask what they dislike in writing for Never. Show the result and adjust. Do not infer voice from a resume. With no samples, leave the starter text; the file fills in as they correct drafts.

### 6. Base documents
Put the source of their base resume, and a letter if they have one, in `templates/`. If they have only a PDF or a word-processor file, ask whether to rebuild it as a Typst source: reproduce their structure and text faithfully, run `jobapps_check`, and get their approval before treating it as the base. Do not restyle it, and confirm the font it names is installed.

### 7. Playbook
Leave `profile/playbook.md` empty unless the user states rules. Record any they give during onboarding in the matching section, one rule per topic.

### 8. Finish
Call `jobapps_overview` again and confirm the `setup` list is clear or name what remains. Tell the user in a few lines: what is filled, which evidence is still `needs_review`, and that the next step is to paste a posting or run a search (`jobapps:job-search`).

## Repairing a workspace

- A missing starter file: recreate it with the headings listed in the workspace `README.md`. Never replace a file that has content.
- Evidence that contradicts itself across files: ask the user which is right, fix the file, and move the wrong claim to Do not claim if it could resurface.
- Contact details that differ between the profile and a document: the user decides; the profile is then corrected and documents follow it.
- Settings that fail to load: fix the JSON syntax, keep every value the user set.

## Boundaries

- Facts come from the user. Ask rather than assume, and record uncertainty as `needs_review`, never as fact.
- The workspace is private. Do not copy its contents anywhere else or send them to anyone. Record sensitive details only at the level the user chooses and the forms require.
- Onboarding writes workspace files only. It does not search, apply, contact anyone or create people records.
