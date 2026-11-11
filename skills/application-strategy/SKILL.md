---
name: application-strategy
description: "Use before writing for a role, to plan the strongest application."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, strategy, positioning, applications]
    related_skills: [jobapps:jobapps, jobapps:resume-writing, jobapps:cover-letter-writing, jobapps:outreach, jobapps:job-search]
---

# Application strategy

A top application is one argument made four times: resume, letter, answers and outreach all prove the same claim about why this candidate fits this role. Decide the argument once, write it into `job.md`, and every document gets faster and stronger. Skip this and each document drifts toward generic.

Most applications fail for reasons no wording fixes: sent late, sent cold, aimed at a role the evidence does not cover, or carrying a fatal slip. Check those first.

## Before any writing

1. Call `jobapps_brief(job, purpose="general")`. Read the posting twice: once for what they say, once for the problem behind it (why this role is open now, what would make the hire a success in six months).
2. **Timing.** If the posting is older than about three weeks, confirm it is still open before investing. If it is fresh, speed matters: a good application in the first days beats a perfect one in week three.
3. **Fit, honestly.** List the five or six requirements that decide the hire. For each, name the evidence file that proves it: strong, partial, or none. Two or more deciding requirements with no evidence means say so plainly and let the user choose to skip or proceed as a reach. No scores.
4. **Way in.** Look at `people` in the brief. If nobody is tracked at the company, say that a referral or a direct note to the hiring manager is the single biggest lever and offer to look (`jobapps:outreach`). A referral changes the plan: outreach goes first.
5. **Depth.** Match effort to the user's priority for the role (`jobapps_track(priority=...)` when they tell you):
   - high: research, tailored resume, letter, answers, outreach to two or three people, and consider one proof artifact (below).
   - normal: tailored resume from the closest precedent, answers if the form asks, one outreach note.
   - low: closest precedent with light edits, only if the user still wants to send it.

## Write the strategy into job.md

Add a `## Strategy` section (after Assessment) with exactly this, in the user's plain words:

```
Thesis: one sentence. Why this candidate, for this role, at this company.
Proof:
- <deciding requirement> : <evidence file> : <the fact that proves it>
- ... (three to five lines, strongest first)
Gap: the weakest deciding requirement and how it is handled (adjacent evidence, fast-learning proof, or left unsaid). Never hide a hard blocker.
Lead with: which experience opens the resume and which story carries the letter.
Way in: who to reach, in what order, and what to ask.
Company hook: one specific, sourced thing about the company that connects to the thesis (product, recent launch, stated problem). No flattery.
```

Keep it under 200 words. Show it to the user when the role is high priority or the thesis involved a judgment call; one line of confirmation is enough. Later documents read it from the brief and must agree with it.

## A thesis that works

- It is specific to the pairing. "Strong engineer who loves learning" fits anyone. "Built and ran the same kind of ingestion pipeline this team is hiring to stabilize" fits one candidate and one role.
- It is proven by the top third of the resume. If the proof sits at the bottom of the page, reorder; `jobapps_check` reports `buried_relevance` when it does.
- It uses the posting's own words for the problem, and the candidate's real facts for the proof.
- It survives the question "so what?" from a skeptical hiring manager.

## Proof artifact (high priority only)

One small, real thing that shows the work rather than describes it: a short teardown of their public product with one concrete improvement, a tiny working demo on their API, a one-page plan for the first 60 days built from the posting. Only when the user has time and the role warrants it, never fabricated, never confidential material. Link it from the letter or the outreach note.

## Before the user submits

Run `jobapps_check` on every document, then walk this list out loud. Each line has ended real applications.

- The right company and role name everywhere. A reused letter still naming the last employer is fatal (`wrong_company`).
- Contact details match `profile/profile.md` and the links open.
- The PDF text reads cleanly for parsers (`ats` in the check result), one page for the resume, professional file names.
- Resume, letter and answers agree on titles, dates and numbers.
- Every form question has an answer in the user's voice, within its limit.
- Work authorization and logistics answers are exactly true.
- The follow-up is scheduled: `jobapps_track(status="applied")` sets it, and its reminders say who to tell.

Then stop. The user submits. Never submit, send or upload for them.

## After sending

- Same day: the note to the referrer or hiring manager, if there is one.
- At the check-in date: one follow-up through a person, not the portal. After a second silence, close the job so the pipeline stays honest.
- When any reply arrives, record it with `jobapps_track` and load `jobapps:interview-prep` or `jobapps:offers`.
- When the user learns why something worked or failed, write the lesson into `profile/playbook.md` so the next application starts ahead.
