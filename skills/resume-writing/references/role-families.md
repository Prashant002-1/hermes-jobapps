# Emphasis by role family

Load when choosing the lane and evidence order, or when a draft reads like the wrong kind of resume. Each entry: what the reader is hiring for, the evidence that counts, what to demote, and the usual failure. Choose one lane per resume.

## Backend and platform

- Hiring for: someone who can own a service: design it, keep it correct under load and failure, and debug it at 2 a.m.
- Counts: data-model and API decisions, correctness under concurrency or retries, migrations done without downtime, root-cause work across services, on-call and incident follow-through, performance work with a measured before and after.
- Demote: interface polish, framework lists, "built CRUD endpoints".
- Usual failure: a stack inventory per job. Repair by naming the failure mode each piece of work addressed.

## Frontend and product engineering

- Hiring for: someone who ships complete, usable surfaces and keeps them coherent as the product grows.
- Counts: named users and journeys, information hierarchy, interaction and state design, component contracts and design systems, accessibility, responsive behavior, loading, empty, error and recovery states, iteration with users or designers, tests, production fixes.
- Demote: dependency names and versions. They stay in Skills.
- Usual failure: "built responsive UI" repeated per role. Give each role a distinct interface story. If removing framework names makes the work stop sounding like frontend, the bullet still lacks substance.
- Gate: each relevant role shows at least three of: a named user, a complete surface, feedback iteration, concrete components, accessibility or responsiveness, state handling, testing, an explicit consequence.

## Data: analyst, analytics engineer, data engineer

- Hiring for: trustworthy numbers that someone acts on, or pipelines that keep them trustworthy.
- Counts: the decision each analysis fed, validation and reconciliation, definitions agreed with stakeholders, pipeline reliability and recovery, modeling choices, time removed from recurring reporting.
- Demote: tool names as the subject ("used SQL to"), dashboards with no named reader.
- Usual failure: "provided insights". Repair by naming the decision and who made it.
- Analyst lanes lead with the question and the decision. Engineering lanes lead with the pipeline and its guarantees.

## ML and AI engineering

- Hiring for: someone who can get a model-backed system to behave reliably, and prove it.
- Counts: evaluation design and what it changed, data construction, failure analysis, retrieval or context design tied to a measured effect, latency and cost trade-offs, serving and monitoring, guardrails with a named reviewer and what stays unchanged until approval.
- Demote: model and library name-dropping, "prompt engineering" as a standalone skill, demo-only work presented as production.
- Usual failure: a component list ("RAG pipeline with embeddings and a vector store"). Repair by stating what was measured and what decision followed.
- For customer-facing or solutions variants, pair the technical evidence with proof of turning a non-technical user's need into a shipped workflow.

## Research and research engineering

- Hiring for: someone who can ask a sharp question, run a clean experiment and report it honestly.
- Counts: the finding, controls and baselines, dataset construction, ablations, reproducibility, negative results that changed direction, venues and status at their exact level.
- Demote: query and run counts, tool inventories, product features unrelated to the question.
- Usual failure: methods before findings. Lead with what is now known.
- Coming from product engineering, lead with the research evidence and use engineering as support: reproducible pipelines, diagnosable failures, documented handoff.

## Support, solutions and operations

- Hiring for: someone who diagnoses under ambiguity, communicates clearly and reduces repeat problems.
- Counts: the queue or accounts owned, diagnosis across logs, data and configuration, runbooks and documentation that changed outcomes, escalation judgment, fixes fed back to engineering, the effect on the people served.
- Demote: deep architecture narratives, research detail.
- Usual failure: an engineering resume with the title changed. Re-angle each role around who was served, what broke, how it was diagnosed and what stopped recurring.
- Useful sequence for bullets: reproduce, classify, communicate, fix or route, verify, document.

## Early career, internships and new graduates

- Hiring for: evidence of finishing real work and learning fast inside constraints.
- Counts: anything shipped to real users, a precisely owned part of team work, internships with a named deliverable, research or teaching with outcomes, projects with users or with unusual depth.
- Demote: course lists, tutorials, group projects with no stated part, high-school material.
- Usual failure: underselling real ownership with "worked on" and "helped". State the exact part and its consequence. The reverse failure is inflating a class project into a product.
- Education placement follows the candidate's approved source. Recent graduates with strong experience still lead with Experience.
- Check eligibility facts early: graduation date, cohort and start window in the posting or the form, against `profile/profile.md`. Raise a mismatch before writing.

## Mixed or unclear postings

When a posting spans lanes, or is only a few lines long:

1. Use the title and the first three responsibilities to pick the lane. Requirements lists are often boilerplate.
2. Treat the current posting as core, earlier postings for the same team as adjacent signal, and company pages as context. Label which is which in the job's Research section.
3. Do not turn the employer's domain into a claim. Understanding their work guides which evidence to select; it does not make the candidate a practitioner of it.
4. Complementary strength is a valid angle. A resume does not need counterfeit symmetry with the team's own background.
