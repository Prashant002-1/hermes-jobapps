---
name: jobapps-material-quality-judge
description: "Fast content-quality gate for the user's resumes, cover letters, application answers, and important outreach."
---

# JobApps Material Quality Judge

Use this skill for substantive candidate-facing materials. It judges content, not compilation or layout.

A clean one-page PDF can still fail. The standard is simple:

> Would a recruiter or hiring manager understand something real about what the applicant built, how they think, and why that matters for this role?

If not, repair it.

## Fast single-pass review

Before compiling, run one content pass over the complete resume and cover letter together. Do not repeatedly judge each bullet in isolation.

### Resume

1. **Identity:** Is the intended role lane clear in 20 seconds? If a summary is used, does it add a specific ownership claim rather than adjectives or a second Skills list?
2. **Evidence order:** Does the strongest role-relevant Experience appear first?
3. **Mechanism:** Do major bullets show what changed and how it worked?
4. **Consequence:** Does every bullet state a verified user, business, research, delivery, or operational consequence explicitly?
5. **Differentiation:** Is the user's credible edge visible against candidates with direct internships or stronger brands?
6. **Truth:** Are all claims confirmed and free of planted JD keywords?
7. **Density:** Does Experience carry the resume while Projects and Skills support it?

### Cover letter

1. What is the letter's one-sentence thesis?
2. What company-specific operating problem does it address?
3. Which 2–3 proof anchors support the thesis?
4. What does it reveal about the user's judgment that the resume alone does not?
5. Could the company name be swapped without changing the letter? If yes, it fails.

Make one consolidated repair pass, then send the sources to compile/visual QA.

## Resume standard

Do not target a fixed word count. Word count is diagnostic only. Semantic quality and the rendered one-page geometry gate determine whether the page is appropriately developed.

Experience should carry the resume. Projects differentiate. Skills remain compact.

A strong bullet usually contains at least three of:

- problem/context
- technical mechanism
- scope/scale
- constraint or failure mode
- user/business/research consequence
- decision/result

Useful test:

> What was ambiguous, broken, risky, slow, or hard to trust; what did the user build/debug/validate; what mechanism made it work; and what changed?

### Accomplishment and consequence gate

Every bullet must state its consequence explicitly. Do not make the reviewer infer it from a feature or stack list. The consequence can be a verified metric, shipped milestone, research finding, enabled capability, prevented failure, reduced manual work, operational improvement, supported decision, scale, or external achievement. Quantification is optional. Consequence is not.

Routine approval gates, human-review steps, proposal/review/apply flows, policy gating, safe previews, and ordinary inspectability do not satisfy this gate. They may be necessary system details, but they are not flagship credibility claims unless tied to a verified non-routine consequence.

Do not invent business impact to satisfy this gate. Phrases such as `maintains high availability`, `improves oversight`, or `reduces unintended modifications` are claims that require evidence. When no metric exists, name the truthful operational result instead: what became possible, what risky path was blocked, what decision became reviewable, what system went live, or what failure could be caught before propagation.

Reject a bullet that ends after describing architecture, infrastructure, or features without answering `so what changed for the user, operator, or research process?`

### Reject these bullet patterns

- **Spec sheet:** tools and features with no operating problem
- **Tool dump:** long stack list standing in for work
- **Business fog:** impact language with no mechanism
- **Metric soup:** numbers with no interpretation
- **Sparse Experience:** projects carrying all credibility
- **JD mirror:** requirements copied into Skills or bullets
- **Generic verbs:** developed/implemented/leveraged with no substance

Prefer precise truthful verbs such as validated, reconciled, modeled, traced, blocked, debugged, instrumented, normalized, routed, tested, and diagnosed.

## Cover-letter standard

A cover letter is not a prose resume or compliance table. It needs a central idea connecting:

- the company's real operating problem
- the user's way of thinking
- 2–3 proof anchors
- the work this role will actually do
- why this is a meaningful next step

Good shapes include problem-first, personal discovery, company-specific technical problem, or research/method alignment. The structure should be invisible.

### Reject these letter patterns

- `Your role requires X; I have X`
- role-by-role resume narration
- fake enthusiasm: `thrilled`, `passionate`, `strong fit`
- generic praise: `innovative mission`, `cutting-edge`
- technical inventory dumping
- gap/apology framing
- polished but interchangeable prose

Do not invent a personal discovery. If the company problem or thesis cannot be found from the JD, evidence, and focused research, ask one targeted question rather than generating filler.

## Repair order

### Resume

1. Restore relevant confirmed Experience substance.
2. Strengthen weak bullets with mechanism and consequence.
3. Keep only role-relevant projects.
4. Compress Skills before cutting confirmed Experience.
5. Send the finished content to the material/layout workflow.

### Cover letter

1. Delete the generic opening.
2. State the company operating problem.
3. Choose one truthful point of view.
4. Use 2–3 proof anchors as evidence, not structure.
5. Map back to the role only after the argument exists.
6. Remove repeated resume details and tool lists.

## Final gate

The resume is content-ready only if:

- strongest evidence is visible quickly
- Experience is substantial
- every bullet shows difficult mechanism or ownership and an explicit verified consequence
- projects are role-relevant
- Skills are compact and truthful
- no keyword stuffing, internal scaffolding, banned credentials, or generic AI prose remains

The cover letter is content-ready only if:

- it has one memorable thesis
- it contains company-specific operating insight
- it uses 2–3 proof anchors without narrating the resume
- it shows judgment
- it sounds direct, specific, and human
- it preserves truthful domain gaps

Do not confuse clean output with good output. But also do not turn quality review into an open-ended writing workshop. One full-document pass, one repair pass, then compile and let the user review.
