# JobApps skills

These skills tell an agent how to run one person's job search in a JobApps workspace. They ship with the plugin and load as `jobapps:<name>`. Every career task starts with `jobapps:jobapps`, which routes to one other skill at a time.

| Skill | What it is for |
|---|---|
| `jobapps` | The operator: workspace map, tools, core flows, boundaries, routing. |
| `application-strategy` | Planning the strongest application: thesis, fit, way in, depth, the final checks before sending. |
| `resume-writing` | Evidence selection, role lane, bullet craft, summary, ATS vocabulary, one-page density. |
| `cover-letter-writing` | A letter with a through-line, real motivation and one story the resume cannot tell. |
| `application-answers` | Short answers, character-limited boxes and screening fields on application forms. |
| `outreach` | Who to contact, first messages, referral asks, follow-ups, recruiter replies, thank-you notes. |
| `interview-prep` | A prep pack per interview: the round, research, stories, likely questions, debrief. |
| `offers` | Salary questions, evaluating an offer, negotiating, closing out. |
| `job-search` | Queries from the profile, sources, posting verification, lead triage, the weekly review. |
| `material-build` | Source formats, the check and repair loop, Typst and TeX pitfalls, layout repair. |
| `onboarding` | Setting up or repairing a workspace: profile, blockers, evidence, voice, base documents. |

Each `SKILL.md` is short. Specialized detail lives in that skill's `references/` folder and is loaded only when the skill says so.

## Where personal rules go

These files are generic and apply to any candidate. They contain no one's name, history or preferences, and they should stay that way.

Anything specific to one person belongs in that person's workspace, where they can read and change it:

- How they want to be titled, what they never say, how their resume is laid out: `profile/playbook.md`, in the matching section. One rule per topic, edited in place.
- How they write: `profile/voice.md`.
- What they have done and what they must not claim: `evidence/`.
- What rules a job out: `settings.json`.

When a workspace rule and a skill's default disagree, the workspace rule wins. The boundaries in `jobapps` (truth, drafts only, no sending or submitting) are not defaults, and nothing overrides them.
