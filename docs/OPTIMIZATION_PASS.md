# State And Personalization Optimization Pass

This snapshot includes a focused optimization pass for the parts of JobApps that matter most during real application work: prompt assembly, retrieval, learning patterns, tool contracts, and dashboard state.

The issue was not one slow endpoint by itself. The system was letting operational exhaust travel too far. Audit payloads lived inline in normal rows. Opportunity prompts carried too much old application context. Learning patterns were written as free-form fragments, which made older but important rules easy to miss. Evidence retrieval used role family as a hard gate, so adjacent proof could disappear even when it was still relevant. The dashboard was also serializing long bodies where list views only needed summaries.

The fix was to make the boundary explicit: career context stays durable, but only the useful slice moves into each run or view.

## What Changed

### Tool-call storage

Large tool-call input/output payloads are now archived out of the inline database row when they cross the configured size limit. The row keeps the inspectable metadata and an archive pointer, while the bulky payload lives under the local runtime archive path.

Why it matters: auditability should not make every dashboard load and context read carry old JSON bodies. JobApps still keeps a trail, but the normal application loop no longer pays for full historical payloads.

### Learning-pattern taxonomy

`learning_patterns` now normalize into a fixed taxonomy:

- `truth_boundary`
- `voice`
- `positioning`
- `materials_content`
- `materials_format`
- `materials_quality`
- `outreach`
- `workflow`

New writes use canonical pattern types. Similar rules merge in place instead of becoming near-duplicate rows. Merge metadata preserves the update trail.

Why it matters: reusable corrections are supposed to keep shaping future applications. If every correction invents a new type, retrieval becomes recency-biased noise. Fixed categories make the personalization layer more predictable without turning it into a rigid prompt template.

### Evidence retrieval

Role family is now a ranking boost, not an eligibility gate. Retrieval still respects the real truth boundary: active proof points, user-confirmed facts, lifecycle state, allowed uses, and supersession rules. The change only stops `role_family` mismatch from returning no evidence when adjacent proof should still be considered.

Why it matters: job descriptions are messy and role labels are approximate. A backend-heavy full-stack role, an AI systems role, and a data-platform role can need overlapping proof. The app should rank the closer proof higher, not hide everything else.

### Opportunity prompts

Opportunity prompts now carry compact, deterministic context:

- profile facts as key/value/category
- proof points as label, summary, evidence, tags, risk, and allowed uses
- learning patterns as type, trigger, and preference
- clipped recent portrayal decisions and brain events
- recent jobs as headers, not full histories

The job description itself is not trimmed.

Why it matters: the JD is the source document for the current application. Old application context is supporting signal. The prompt should protect the current role from being diluted by unrelated history while still giving Hermes the career facts and reusable corrections it needs.

### Material quality contract

The opportunity prompt now includes a concrete material-quality contract. It tells Hermes to write decisively, obey truth boundaries first, use learning patterns without re-litigating them, avoid internal strategy text in candidate-facing materials, and verify one-page resume output before marking work ready.

Why it matters: fast output is not useful if it gets fast by becoming vague. The goal is shorter local orchestration and stronger material discipline at the same time.

### Tool validation

Agent tool execution now validates required fields from the tool schema before dispatch. Follow-up creation also checks foreign keys and returns actionable errors when a job or contact reference is wrong.

Why it matters: agent-facing tools should fail visibly and locally. A missing `job_id` should produce a clear validation error, not a traceback that hides the real problem.

### Dashboard payloads

List-state payloads now carry previews, references, counts, and compile state instead of full prompt bodies, generated source bodies, raw provider payloads, and repeated contact/follow-up detail.

Why it matters: the dashboard is a cockpit over state, not a backup export format. It should load enough to show what needs attention, then fetch or render the detail when the workflow actually needs it.

### Compact tool context

`jobapps_read_context` is compact/admin by default. Full dashboard state is opt-in through an explicit flag.

Why it matters: native Hermes, the project plugin, and the web cockpit all operate the same SQLite state. Tool reads should default to the smallest useful packet so agent sessions stay focused on the current move.

### Deterministic writers

The local deterministic draft notes now apply canonical learning patterns instead of ignoring them.

Why it matters: even fallback or preview generation should respect durable corrections. Personalization should not only exist when a full model-backed run happens.

## Privacy Boundary

This public write-up intentionally describes architecture, failure modes, and implementation changes without publishing private runtime data. It does not include local working notes, application history, private profile facts, contacts, generated materials, database rows, or job-specific payloads.

The public repo should remain useful as code and architecture. Real applicant data belongs in ignored local config, private Hermes profile state, and the JobApps SQLite database.

## Verification

The release path for this snapshot is:

- run the unit test suite
- run syntax checks for the JavaScript and Python entry points
- run whitespace checks
- build the public snapshot from `public/main`
- restore or keep public-only docs and screenshots
- scan for local data, databases, ignored private files, secret-like strings, and personal runtime details
- push the sanitized public snapshot only after those checks pass

The important test coverage added or preserved around this pass includes:

- role-family retrieval boosts without evidence starvation
- learning-pattern normalization and merge-on-write
- compact prompt assembly
- compact dashboard state
- tool required-field validation
- tool-call payload archiving
- draft-only Gmail behavior
- material provenance and compile-state visibility
