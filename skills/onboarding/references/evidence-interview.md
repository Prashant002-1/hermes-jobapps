# Evidence interview

Load when creating or deepening an evidence file with the user. The purpose is to get from "what the resume says" to facts that can carry a strong bullet: what was hard, what the candidate decided and did, and what changed. The example is invented.

## Rules for the interview

- One experience at a time. Five to eight questions is usually enough. Stop when the file can support three strong bullets.
- Ask open questions, then narrow. Do not offer the answer you hope for ("so it improved speed by about 30%?").
- Record the user's words. Tidy grammar; do not upgrade verbs or scope.
- When they are unsure, write the uncertainty down. "About 40 minutes, from memory" is a usable fact with a limit attached.
- When they say "we", ask what their own part was.
- If the user is short of time, take what they give, mark the file `needs_review`, and stop.

## Questions

**What it was**

- In a sentence or two, what was this, and who was it for?
- What was your position: title, team size, who you reported to, how long?
- Was it paid work, an internship, research, coursework, your own project?

**What was hard**

- What was the problem before you started? Who felt it?
- What made it difficult: scale, ambiguity, a constraint, people, time?
- What had been tried before?

**What you did**

- What did you decide that someone else might have decided differently? Why?
- What did you personally build, write, analyze or run? What did others do?
- What was the hardest technical or practical part, and how did it work?
- How did you know it was correct? Tests, checks, review, measurement?

**What changed**

- What happened next because of this work? Who noticed?
- Is it still in use? By how many people, how often?
- Did anything stop happening: a manual task, an error, a delay?
- Is there a number? Where does it come from: a log, a dashboard, someone's estimate?
- Any recognition: an award, a publication, a talk, a selection? What is its exact status today?

**Limits**

- What should a resume not say about this? Parts you did not do, figures you cannot back up, names or details that are confidential.
- If an interviewer pushed on this, where would you be on thin ice?

**For a degree**

- Degree, institution, dates, GPA and whether to show it, honors, relevant coursework only if it matters for the target roles, thesis or capstone.

**For research**

- The question, the finding in one sentence, the design that makes it credible (data, baselines, controls), the status (in progress, submitted, accepted, presented, published) and the venue.

**For solo or founder work**

- What the product is and who uses it, at its real level today: testers, pilot users, paying customers, none yet.
- Everything they do for it beyond engineering.
- Any outside validation, named exactly: a grant, credits, a program, press. Not rounded up.

## Writing the file

Frontmatter:

- `title`: the role or project name as it should appear.
- `type`: experience, project, education or award.
- `organization`, `role`, `start`, `end`: as the user states them. Month precision is fine. Leave `end` empty for ongoing work.
- `status`: `needs_review` until the user confirms the facts, then `active`. `retired` keeps the file out of use.
- `tags`: a few plain terms that help find it later: lane, domain, main technologies.

Sections:

- **What it was**: two sentences a stranger would understand.
- **Facts**: short plain statements, mechanism first, then consequence. One fact per line. Attach the source or the uncertainty to any number. Facts are raw material, not resume bullets; they can be longer and plainer.
- **Approved wording**: only bullets or sentences the user has approved, or lines from their current resume that they confirm they stand behind. Leave empty at first if unsure.
- **Do not claim**: the limits, stated as clearly as the facts.

## Checking a resume's existing claims

For each bullet in the document the user supplied:

1. Is there a number? Ask where it comes from. If they cannot say, record the fact without the number and put the number under Do not claim.
2. Is there an outcome word with nothing behind it ("improved", "streamlined")? Ask what actually changed. Record that, or record nothing.
3. Is the scope clear? "Led" and "owned" get one question: who else was involved?
4. Is a status stated (published, launched, in production)? Confirm it is true today.

This is fact-finding, not criticism. Say what you are doing and why: stronger, safer documents later.

## Example

```markdown
---
title: Call-out reassignment tool
type: experience
organization: Northstar Logistics
role: Software Engineering Intern
start: 2025-06
end: 2025-08
status: active
tags: [backend, internal-tools, logistics, python]
---

# Call-out reassignment tool

## What it was

An internal web tool that lets depot supervisors reassign delivery stops when a driver calls out. Summer internship on a five-person operations engineering team; I built the tool, my mentor reviewed it.

## Facts

- Before the tool, dispatch handled call-outs by phone and a shared spreadsheet.
- I built a board where supervisors drag stops between drivers, and a rule check on vehicle capacity and driver hours that rejects invalid swaps before saving.
- I built a nightly import from the order system that sets aside malformed stops for review instead of failing.
- Three rounds of feedback with six supervisors at two depots shaped the board.
- I tested the rules by replaying 60 past call-out days.
- Reassignment went from about 40 minutes to under 10. Source: the supervisors' own shift logs, compared by my mentor.
- Both depots were still using it when I left.

## Approved wording

- Built the call-out reassignment tool used by supervisors at two depots: a rule check on vehicle capacity and driver hours rejects invalid swaps before they reach dispatch.

## Do not claim

- Not a company-wide rollout: two depots only.
- I did not build the order system or the authentication; both existed.
- No cost-saving figure. Nobody measured one.
- Usage after August 2025 is unknown to me.
```

## Splitting and merging

- One file per role. Two distinct roles at one employer get two files.
- A large project inside a job may get its own file when it will be used separately; link them by mentioning each in the other's What it was.
- Do not create a file for something the user will never put on a document. Ask.
- When two files describe the same work, merge them and keep the stricter Do not claim list.
