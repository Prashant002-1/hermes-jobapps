# Hermes JobApps

## Goal

Hermes JobApps is a local career-context system for job applications.

Its job is not to automate every part of a job search from day one. Its job is to help a user carry verified context from one opportunity to the next: the right angle, the right material, the right outreach, and the next action.

The public repository is intentionally generic. Personal target roles, constraints, proof points, writing preferences, and outreach habits belong in local database records, local Hermes memory/profile state, or private replacement skills.

## Why This Exists

Most job tools treat the applicant like a form-filling machine. That is not the hard part.

The hard part is knowing what matters for each opportunity: which story fits the JD, which project should be emphasized, which resume sections should change, whether there is a hard blocker, who should be contacted, and what should be said without sounding fake.

Hermes is the reasoning engine. It should stay current with the user's verified context through explicit tools, memory, skills, and database-backed state.

The dashboard, database, browser automation, and job sources can evolve. They are surfaces and utilities. The core is the career memory and decision layer.

## Product Direction

Hermes JobApps should help a user move from a job opportunity to a clear next action.

For any role, it should be able to answer:

- Are there hard blockers: work authorization, seniority, location, or excessive application effort?
- What is the strongest truthful angle?
- Which JD requirements must the materials address?
- Which current, user-confirmed proof points fit this role?
- Which old or risky proof points must be excluded?
- Which resume version or bullets fit best?
- What should the cover note or application answer say?
- Which portrayal decisions were made, and why?
- Which corrections/preferences should carry into future applications?
- Who should the user contact?
- What should the networking message say?
- What should happen next, and when?

The goal is not volume for its own sake. The goal is high-quality movement: better applications, sharper positioning, and less wasted time.

## Current Product Boundary

The main workflow is not autonomous job search. The useful workflow is:

> A user sends a job description. JobApps assumes apply intent unless hard blockers appear, extracts signals, turns JD requirements into tailoring targets, retrieves only eligible evidence, drafts truthful materials, records portrayal decisions, compiles reviewable artifacts, and learns from corrections.

The job search and application remain in the user's hands. The system accelerates repeated application work; it does not optimize everything, impersonate the applicant, or decide their career for them.

This means the cockpit should optimize for speed after paste:

1. Parse job facts and application constraints.
2. Run blocker preflight: work authorization, seniority, location, effort.
3. Assume apply intent when there is no hard blocker.
4. Extract reusable signals.
5. Turn JD requirements into `tailoring_requirements`.
6. Retrieve active, user-confirmed proof points.
7. Exclude retired, superseded, unconfirmed, forbidden, or old-narrative evidence.
8. Pick one positioning angle.
9. Record `portrayal_decisions` that explain how the JD changed material framing.
10. Apply and record `learning_patterns` from user corrections.
11. Generate TeX resume and cover-letter artifacts.
12. Compile PDFs when possible.
13. Show diffs, provenance, and rationale.
14. Stop at explicit human approval.

## First Useful Version

The first version should stay minimal and fast.

It should focus on three things:

1. Resume customization
2. Cover letters and short application answers
3. Networking messages and follow-ups

Submission automation can come later. Discovery can get smarter over time. The first layer should make the thinking and writing better.

A useful first workflow is simple:

The user gives a job link or description. Hermes reads it, checks blockers, assumes application intent when safe, chooses the right angle, records tailoring requirements, suggests resume changes, drafts application material, drafts networking outreach, and records what happened.

## What Hermes Should Remember

Hermes should remember durable context, not every tiny detail.

It can remember high-level target direction, durable constraints, reusable lessons, preferred voice, and behavioral guidance when the user chooses to store those details locally. The public repo should not contain private examples of those rules.

Hermes memory should not store every job, every resume version, every PDF path, or every bullet variant. Those are application facts, not personal memory.

Structured facts should live outside Hermes memory. Job status, contacts, dates, resume versions, material diffs, application history, exact proof points, and retrieval eligibility should be stored as ground truth in the app's data layer.

JobApps also has a career-brain layer below Hermes memory. It is app-owned SQLite state that captures the human trail: identity, constraints, job-search preferences, people, companies, proof points, decisions, daily notes, projects, conversations, networking history, revisions, corrections, and why material choices changed.

Default memory policy:

- conversations become low-importance brain events
- corrections, constraints, preferences, people/company notes, and decision rationales become higher-importance brain events
- reusable conclusions should also be promoted into profile facts, proof points, learning patterns, tailoring requirements, portrayal decisions, or follow-ups
- Hermes memory remains useful for durable behavior and session continuity, but JobApps owns the career/application provenance

## Evidence, Signals, And Retrieval Lifecycle

JobApps needs a focused evidence layer, not generic memory sludge.

The app should distinguish these kinds of state:

1. **Hermes memory** - durable user context and operating preferences.
2. **JobApps structured state** - jobs, materials, approvals, contacts, follow-ups, outcomes.
3. **Evidence layer** - user-confirmed proof points and searchable chunks with lifecycle metadata.
4. **Application signals** - extracted job facts that make future applications faster.
5. **Tailoring requirements** - JD-grounded targets each material should address.
6. **Portrayal decisions** - how a requirement changed the resume/cover-letter framing.
7. **Learning patterns** - reusable corrections/preferences discovered during review.

Pure vector search is not enough. An old bullet and a current bullet can be semantically close while only one is safe to use. The first retrieval step must be eligibility, not cosine distance.

Default retrieval policy:

- use only `status = active`
- require `user_confirmed = true`
- exclude `superseded`, `retired`, `forbidden`, and `candidate` records
- honor `allowed_uses` such as resume, cover letter, outreach, or interview
- prefer current `narrative_version`
- return source IDs and rationale so every generated material can cite its evidence

Proof point lifecycle states:

- `candidate` - visible for review, never used automatically
- `active` - usable by default
- `needs_review` - show to user, do not generate from it silently
- `superseded` - retained for history but excluded when a better version exists
- `retired` - true but outside the current narrative
- `forbidden` - never use unless explicitly re-enabled
- `archived` - kept for audit/history, not retrieval

The app should "forget" a bullet for generation when it is rejected, superseded, unconfirmed, risky, old-narrative, outcome-negative, too vague, or contradicted by a canonical fact. It should hard-delete only for privacy/legal reasons or explicit user request.

## Public Personalization Boundary

This repository ships generic project skills and plugin prompts so the architecture can be inspected and reproduced. For real use:

- replace `skills/*.md` with private local skills
- replace `.hermes/plugins/jobapps/skills/*.md` with your own cockpit rules
- keep personal proof points, school/employer details, immigration/work-status constraints, writing preferences, and outreach patterns out of public commits
- store real profile facts and preferences in ignored local config, Hermes profile memory, or the JobApps SQLite database

## Role Of The App

The app is the cockpit.

It should show opportunities, materials, contacts, follow-ups, and progress. It should make the next action obvious. It should let the user approve, reject, edit, and move on.

The app should not force the architecture too early. It should stay flexible enough for the workflow to evolve as it is built.

The right principle is:

The app owns state. Hermes performs transitions.

The database is the app's source of truth. Private files can seed the database, but they are not the runtime schema and should not drive behavior directly.

## Role Of Hermes

Hermes is the engine.

It reasons through the opportunity, applies user context, uses tools when useful, drafts material, updates records, and asks for approval when the next step matters.

Hermes should not become a generic job bot. It should act like a career operator that protects the user's time.

Hermes should stay native to its own architecture: profiles, API server, session storage, memory, skills, provider runtime, and tool dispatch. JobApps adds a cockpit and database/tool layer around Hermes; it should not replace Hermes memory/session management.

## Correct Architecture Stance

JobApps should be agent-centric without turning the app into an agent framework.

- Hermes chat should be available inside the app.
- Native Hermes TUI/API sessions should be able to see JobApps context through the project plugin or a future MCP bridge.
- JobApps tools should let Hermes read and update database state.
- Resume and cover-letter builds should be LaTeX files.
- Prompt builds should be saved so decisions are reproducible.
- Research, networking notes, material changes, progress, and follow-ups should be structured records.
- Application data and app architecture should stay separate so the repository can become public without private backend data.

## Submission Automation

Submission automation is useful, but it is not the foundation.

The safe path is browser autofill first: open the form, fill repeated fields, upload documents, answer known questions, and stop before final submit.

Blind auto-submit should not be part of the early system. The system should earn trust before it gets that much control.

## Discovery And Job Data

Job discovery matters, but it does not need to be solved first.

The system can begin with pasted links and manually chosen roles. Later it can add reliable sources: company career pages, Greenhouse, Lever, Remotive, Arbeitnow, Hacker News, selected job boards, and paid search/scraping APIs if they prove worth it.

The data layer should stay practical. Pull in enough jobs to create good choices. Do not build a giant crawler before the application workflow is useful.

## Design Principle

Do not over-design the architecture upfront.

This app should evolve through use. The first design should create direction, not constraints. It should leave room for Hermes and future agents to discover better workflows as the system becomes real.

The goal is not to build the perfect job automation platform.

The goal is to build a system that helps a user apply with memory, judgment, and momentum while keeping private context private.
