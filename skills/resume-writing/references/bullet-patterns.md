# Bullet patterns

Load when drafting bullets from raw evidence or repairing bullets the check flagged. Every example here is invented. Copy the shape, never the nouns or numbers: a number appears in a bullet only when the candidate's evidence states it.

## Anatomy

A bullet has three parts. The order can vary; none may be missing.

1. What was hard, or what was owned.
2. The decision or mechanism: what the candidate actually did about it.
3. The consequence: what changed, and for whom.

Three orders that work:

- Result first: `Cut <thing> from A to B by <mechanism>.`
- Problem first: `<Problem as the user or business felt it>: <mechanism>, <consequence>.`
- Ownership first: `Owned <surface or system> for <who>: <hardest decision>, <consequence>.`

Use result first when the number is strong and verified. Use problem first when the judgment is the point. Use ownership first for founder, solo and lead work.

## Finding the consequence

Ask of each fact in the evidence: what happened next because of this? Accept only answers the evidence or the user supplies.

| Consequence type | What to name |
|---|---|
| Capability shipped | Who can now do what they could not before |
| Failure prevented | The class of error, and who no longer sees it |
| Manual work removed | The recurring task, who did it, how often |
| Decision supported | The decision, and who makes it from this work |
| Finding established | What is now known |
| Scale carried | The real figure: users, records, requests, accounts |
| Others unblocked | What teammates built on top of it |
| External recognition | The award, acceptance or selection, at its exact status |

If no consequence can be found, the fact may belong in Skills, in a project descriptor, or nowhere. Ask the user once before dropping work that looks important.

## Five tests

1. Deletion: strike the technology names. Is an accomplishment left?
2. Swap: could any peer in this role family paste it unchanged?
3. So what: can a reader say what changed in the world?
4. Interview: could the candidate talk for two minutes about the decision inside it?
5. Evidence: is each number, name and status in the evidence files?

## Failure patterns and repairs

| Pattern | Looks like | Repair |
|---|---|---|
| Stack inventory | "Built X using A, B, C and D" | Name the problem and the decision. Move the tools to Skills. |
| Manufactured ending | ", improving efficiency and scalability" | Replace with the observed consequence, or delete the clause. |
| Duty | "Responsible for maintaining the billing service" | Say what changed while it was theirs. |
| Activity without outcome | "Conducted 30 user interviews" | Say what the interviews changed. |
| Count as impact | "Wrote 200 tests", "ran 5,000 experiments" | Say what the volume caught or established. |
| Borrowed result | "Increased revenue 20%" for a team effort | State the candidate's part and the team result as separate facts. |
| Vague scale | "large-scale", "high-traffic", "numerous" | Give the figure, or drop the adjective. |
| Routine as feat | "Participated in code reviews and agile ceremonies" | Cut. |
| Hedged ownership | "Helped with", "Assisted in", "Contributed to" | State the exact part owned, even if small. |
| Echo of the posting | The posting's phrase, no specifics | Find the evidence the phrase points to, or remove it. |
| Semicolon chain | Three mechanisms in one bullet | Split. One mechanism and one consequence each. |
| Twin bullets | Two bullets, same mechanism | Merge, or give the second a different proof. |
| Tool as subject | "Leveraged Kubernetes to..." | Make the candidate's decision the subject. |

## Before and after by role family

**Backend**

- Before: `Developed REST APIs using Java, Spring Boot and PostgreSQL to improve performance.`
- After: `Traced intermittent duplicate invoices to a retry path that re-ran a non-idempotent write; added idempotency keys and a nightly reconciliation job, ending the finance team's weekly manual cleanup.`
- Why: a diagnosis, a design decision, and a named team whose recurring work ended. No number was needed.

**Frontend**

- Before: `Built responsive UI with React 18, TypeScript and Tailwind CSS.`
- After: `Rebuilt claims intake as a save-as-you-go, keyboard-navigable flow with inline validation and recovery from dropped connections, so adjusters stopped losing partly entered claims.`
- Why: a complete surface, real interaction and state decisions, a named user. It still reads as frontend work with every framework name removed.

**Data and analytics**

- Before: `Created Tableau dashboards to provide actionable insights to stakeholders.`
- After: `Merged five regional spreadsheets into one validated model and dashboard; operations leads now set weekly staffing from it instead of waiting two days for a manual report.`
- Why: it names the decision made from the work and the delay removed.

**ML and AI**

- Before: `Built a RAG chatbot using LangChain, OpenAI and a vector database.`
- After: `Built retrieval for support answers over 12,000 policy documents and a 300-ticket evaluation set; the evaluation showed section-based chunking removed most wrong-policy citations, which set the design before launch.`
- Why: evaluation and a design decision it drove, not a list of components.

**Research**

- Before: `Ran 5,000 experiments on LLM performance using Python and PyTorch.`
- After: `Found that passage order, not passage count, drove accuracy on multi-hop questions: reordering identical passages moved exact match by 9 points across three models under fixed prompts and seeds.`
- Second bullet: `Presented the result as a poster at <venue>; manuscript under review.`
- Why: finding first, then the control that makes it credible. Status sits in its own bullet at its exact level.

**Support and operations**

- Before: `Provided technical support to customers and resolved tickets in a timely manner.`
- After: `Handled escalated integration tickets for 40 enterprise accounts and wrote the webhook-failure runbook that let first-line agents close that category without engineering.`
- Why: scope, a diagnostic artifact, and work taken off another team.

**Early career and coursework**

- Before: `Worked on a team project to build a mobile app using Flutter and Firebase.`
- After: `Owned offline sync in a four-person capstone app for field inspectors: queued writes, conflict rules agreed with the client, and tests replaying real connectivity gaps.`
- Why: a precise owned part, a real user, a decision. Team size stated, nothing inflated.

**Founder and solo work**

- Before: `Founded a startup and built an MVP using Next.js and AWS.`
- After: `Designed, built and operate Fieldwork, a scheduling product for independent clinics: product decisions from 14 pilot interviews, the booking engine, billing, deployment and support. Six clinics use it in a free pilot.`
- Why: whole-lifecycle ownership, with maturity stated at its real level.

## When there is no number

A number belongs when it changes the reader's sense of scope or rigor. Never estimate one. Alternatives, each only if the evidence states it:

- A named user or team: "depot supervisors", "the on-call rotation".
- A frequency: "weekly", "every release".
- A before and after state: "from a two-day manual report to same-day".
- A boundary: "across two depots", "for all new accounts".

If the user probably knows a number the evidence lacks, ask for that one number.

## Verbs and form

- Use the verb that names the act: designed, built, traced, replaced, cut, wrote, measured, decided, negotiated, taught, ran.
- "Led" needs people or a decision that was led. "Migrated" needs what the migration enabled.
- Avoid: utilized, leveraged, spearheaded, orchestrated, drove, worked on, helped, assisted, participated in, was responsible for.
- Past tense for finished work, present for ongoing. No first person. Numerals for figures.
- One or two rendered lines. Three only for a flagship bullet.

## How many

Current role three to five bullets, earlier roles two or three, projects one to three. Fewer strong bullets beat a full set with fillers. Order bullets within a role by relevance to the lane, strongest first.
