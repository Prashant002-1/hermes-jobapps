# Personalization

The public repository includes generic skills and plugin prompts so JobApps can
be inspected, run, and extended without publishing anyone's private career
patterns.

For real use, treat these files as templates:

- `skills/jobapps-role-evaluator/SKILL.md`
- `skills/jobapps-application-writer/SKILL.md`
- `skills/jobapps-outreach-operator/SKILL.md`
- `.hermes/plugins/jobapps/skills/jobapps-cockpit/SKILL.md`

Replace or override them with private/local versions that reflect your own:

- target roles and fallback role families
- work-authorization, location, seniority, and effort rules
- proof points and proof-point lifecycle policy
- resume and cover-letter strategy
- writing voice and banned phrases
- outreach channels, sender identities, relationship paths, and follow-up cadence
- corrections that should become reusable learning patterns

Keep private personalization out of public commits. Good homes for real personal
context are ignored local config files, a private Hermes profile, Hermes memory,
private skills, and the JobApps SQLite database.

Before publishing a fork or snapshot, scan the repo for names, school/employer
details, GPA, legal/work-status details, email addresses, personal voice rules,
and private outreach habits.
