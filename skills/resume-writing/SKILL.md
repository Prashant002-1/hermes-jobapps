---
name: resume-writing
description: "Use when writing or revising a resume. Covers evidence selection, role lane, bullet craft, summary and identity, truthful re-angling, ATS vocabulary, one-page density and revision scope."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, resume, bullets, ats, evidence]
    related_skills: [jobapps:jobapps, jobapps:material-build, jobapps:cover-letter-writing]
---

# Resume writing

This skill owns substance: which evidence, in what order, in what words. Source format, build errors and layout repair belong to `jobapps:material-build`.

## Evidence first

Work from one `jobapps_brief(job, purpose="resume")`: the evidence files, profile, job Notes, and the playbook sections `All documents` and `Resume`, which override this skill wherever they speak. Every claim traces to an evidence file, the profile, or the user's confirmation in this conversation. Never invent a metric, date, title, employer, award or finished outcome. If the brief ranked evidence, read the omitted files it lists before deciding something is missing. Honor `Approved wording` and `Do not claim` exactly. Truthful is not timid: use the strongest framing the facts support. When a load-bearing fact is missing (a number, a status, who used it), ask one targeted question and write the answer into the evidence file.

## One lane, one evidence order

State in one sentence what this reader is hiring for, then choose the single lane the candidate can truthfully occupy (`references/role-families.md`). Experience carries the page, Projects differentiate, Skills confirms coverage. Lead with the strongest relevant verified work, not the most sophisticated unrelated project and not a weaker story stretched to mirror the posting. Keep distinct roles distinct. Give each entry one job to do:

- Current or latest role: the scope and judgment the candidate holds now. It gets the most lines.
- Internships: work shipped inside a real team's codebase, review process and integration boundaries. Name what shipped and who used it.
- Research: a finding, and the rigor that makes it credible.
- Founder or solo work: the whole lifecycle and product judgment.
- Stakeholder, analyst, support and operations work: translating a need into something delivered, diagnosis, the consequence for the people served.
- Projects: depth the jobs do not show. Start each with a concrete descriptor (what it is, for whom) before any engineering.

## The bullet gate

Every bullet earns its line with **a difficult mechanism or clear ownership, plus an explicit verified consequence**.

- Consequence is mandatory; a number is not. Valid consequences: a capability shipped, a failure prevented, manual work removed, a decision supported, a finding established, real scale, external recognition. A consequence that exists only in the writer's head fails.
- Lead with the problem, the decision or the result, never the stack. Deletion test: strike every technology name; what remains must still be an accomplishment. Keep a technology in prose only when the mechanism or constraint is unintelligible without it.
- Swap test: if any candidate in the role family could paste the bullet unchanged, rewrite or cut it.
- No manufactured endings: "improving efficiency", "enhancing reliability", "ensuring scalability", "driving impact". End on the real consequence or end the sentence.
- Routine practice is not an accomplishment: code review, approvals, standups, "collaborated cross-functionally", tests merely existing.
- A count is not impact. "Ran 5,000 experiments" says nothing until the bullet says what they established.
- One mechanism and one consequence per bullet. Two concise bullets beat one semicolon chain. No first person, no "Responsible for", no "Worked on", "Helped", "Utilized".

Fails: `Developed REST APIs using Java, Spring Boot and PostgreSQL to improve performance.`
Passes: `Traced intermittent duplicate invoices to a retry path that re-ran a non-idempotent write; added idempotency keys and a nightly reconciliation job, ending the finance team's weekly manual cleanup.`

Load `references/bullet-patterns.md` when drafting bullets from raw facts or when the check flags bullets. It holds anatomy, failure patterns and before/after pairs by role family.

## Founder and owner scope

Show the whole responsibility: the product thesis, who uses it, design, engineering, operation, feedback, and how it reached people. Do not shrink an owner into the implementer of one internal migration; infrastructure is evidence of ownership, valuable for what it enables. Never inflate maturity: testers are not customers, credits are not funding, interest is not revenue, a pilot is not a launch. Pick the title among truthful alternatives that helps this reader place the work (`references/summary-and-identity.md`).

## Research bullets

Finding first, mechanism second: what is now known and why it matters, then the design that makes it believable (data construction, baselines, controls, ablations). Give the contribution and its venue or status separate bullets. Keep submitted, accepted, presented and published distinct, exactly as the evidence states.

## Summary and identity

A summary is not required. Include one only when it interprets the evidence: who this is, at what scope, with what differentiator. It is never a skills recap, a string of adjectives, or a restatement of employers visible below. If the lines would do more as a relevant project, use them for the project. Load `references/summary-and-identity.md` when writing or correcting a summary, title or project descriptor.

## Re-angling for a lane

The same true work can serve different lanes. You may change the slice shown, the order, which consequence leads, and the vocabulary. You may not change facts, numbers, scope, who did the work, or its status. Load `references/framing.md` for the method and a worked example when the candidate's history reads as a different lane from the target.

## ATS and Skills

Extract the posting's vocabulary before writing. Surface an exact term only where the evidence supports it: in the bullet where it truly happened, otherwise in Skills. Use ordinary Skills categories and practitioner names. Never plant a posting noun in empty prose or invent a category to mirror the posting. Verify coverage against the final PDF text, not the source. Details: `references/ats-and-skills.md`.

## Density and the page

One page unless the playbook or the lane says otherwise (academic CVs run longer). Finish Experience and Projects semantically before touching spacing. Never shrink type or squeeze leading to hide verbose writing: cut the weakest bullet or tighten sentences. Fill a short page with substance (a missing mechanism, a product descriptor, a restored relevant bullet), never with spacing or filler. Do not collapse a substantive multi-year role into one compound bullet to make room. A quick or low-priority application means faster reuse of an approved source, not a lower bar.

## Revision scope

Start a revision from the current file. Repair the named unit (a title, a bullet, the summary) and leave every other approved line byte-identical. "Look over the rest" means report, not rewrite. If an earlier broad edit weakened good wording, restore it. A rejected style is a semantic problem: name it, repair the affected bullets around problem, mechanism and consequence, then check again. Separate requisitions at one employer get separate resumes when the user asks, each with its own evidence order.

## Workflow

1. `jobapps_brief(job, purpose="resume")`. Confirm the decision is not `skip` or an unanswered `pending`.
2. Copy the closest approved source: this candidate's resume from a similar job folder, else `templates/`. Keep its structure and typography.
3. Write `<Name> - Resume - <Company> - <Role>.typ` in the job folder: lane, evidence order, bullets, Skills, then summary if it earns its lines.
4. Run the self-review below once over the whole document.
5. `jobapps_check(path)`. Repair findings (content here, layout via `jobapps:material-build`), at most three rounds, stop on no progress and report what remains.
6. Give the user the PDF path. Mark the job `ready` with `jobapps_track` only after a passing check and the user's review.

## Self-review before the check

- Can a reader place the candidate within ten seconds: lane, level, strongest proof in the first third of the page?
- Does every bullet pass the gate, the deletion test and the swap test?
- Is every number, date, title and status present in the evidence, at its real level?
- Does each role prove something different, with no repeated mechanism across bullets?
- Are the posting's key terms present where supported, and absent where not?
- Would the candidate be comfortable talking for two minutes about any line?
- No first person, placeholders, notes to self, review state or workflow text anywhere in the file.
