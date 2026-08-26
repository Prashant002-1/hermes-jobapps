---
name: jobapps-material-build-qa
description: "Use when creating, tailoring, compiling, repairing, or verifying the user's Typst resumes and Typst/TeX cover letters."
version: 2.2.0
author: Hermes JobApps
license: MIT
metadata:
  hermes:
    tags: [job-search, resume, cover-letter, typst, tex, pdf, qa]
    related_skills: [jobapps-cockpit, jobapps-material-quality-judge]
---

# JobApps Material Build and QA

Use this skill for resume, cover-letter, CV, compile, layout, and PDF verification work. Resumes are Typst-first. Cover letters preserve their existing `.typ` or `.tex` format.

`jobapps-material-quality-judge` owns content judgment. This skill owns source files, layout, compilation, verification, filenames, and clean artifacts.

## Source rules

1. Start from one recent working role-specific or bucket resume, not several old variants.
2. If the user identifies a material as current/used/confirmed, preserve its structure, density, and claims unless the JD needs a targeted swap.
3. Old drafts and `knowledge_base.html` are extraction sources, not truth.
4. Keep searches inside the active JobApps repo and known material paths. Do not broadly search the home/Desktop tree.
5. Role-specific tailoring is a copy. Never overwrite the generic base.
6. Align public-facing names and titles with any portfolio, website, or artifact the employer has already received. If the user explicitly asks for consistency with a public project name such as `Hermes JobApps`, preserve that exact public name and add a role-relevant qualifier after `|` when useful (for example, `Hermes JobApps | Agent Workflow Platform`) rather than silently renaming it.
7. Otherwise, prefer architecture/tooling language such as `Local Agent Workflow Architecture` over a narrow product-domain title.
8. Upload-facing files use professional names with spaces:
   - `Candidate Name - Resume - Company - Role.typ/.pdf`
   - `Candidate Name - Cover Letter - Company - Role.tex/.pdf`

## Default document contract

### Resume

- Typst with `simple-technical-resume`
- US Letter, one page
- Avenir Next, **10.5pt body**
- A concise unlabeled summary only when it adds a specific ownership claim; omit it when it merely repeats Skills or adjectives
- Experience before Education for the graduated candidate unless the application makes education the stronger lead
- Experience carries the page
- Treat word count as diagnostic only; rendered one-page geometry and semantic quality govern readiness
- Target 0.65 inches from the lowest rendered content to the page edge; accept only 0.55–0.75 inches

Never reduce resume body below 10.5pt to fit. Trim redundant text, especially Skills, before cutting confirmed Experience.

### Temporary typography previews

When the user asks to try a font size visually before deciding, treat it as a reversible preview:

1. Copy the current source to an OS-safe temporary directory. Never touch the canonical source/PDF or JobApps records.
2. Change **only** the requested type size first, compile, and report the page count immediately.
3. Do not silently offset a larger font with margin, spacing, or content changes. That is a different experiment.
4. If the isolated preview becomes two pages, still deliver the temporary PDF and state exactly what overflowed. Do not claim the preview is ready to adopt.
5. Keep the preview source/PDF until the user says adopt or delete. On adoption, make the canonical change and run final QA; on rejection, remove the temp directory.

A 10pt body may be evaluated only as an isolated comparison. It is not the final default and must never be used merely to hide weak content allocation or avoid concise editing.

### Cover letter

- Preserve `.typ` or `.tex`; use article-style shared header for TeX
- Avenir Next, **10.8pt body**
- One page unless the application explicitly requires otherwise
- Same contact header as the resume
- No awkward hyphenation, duplicate greeting, workflow residue, or sparse bottom block
- Fuller professional business-document layout, not a wall of text and not a short template note

## Fast build path

For a standard resume/cover-letter pair:

1. Read one proven source pair and the small evidence packet.
2. Write both final sources into `data/materials/<job_id>/`.
3. Compile both in one deterministic script or command group:
   - For Typst resumes, call `hermes_jobapps.typst.compile_typst_to_pdf` from the project environment. It compiles the sibling PDF, runs integrity checks, and attaches `resume_qa.verify_resume_pdf` geometry output.
   - When only low-level control is needed, compile with `typst`, then call `hermes_jobapps.resume_qa.verify_resume_pdf` against the exact sibling PDF and absolute source path.
   - for a Typst letter: `typst compile <letter.typ> <letter.pdf>`
   - for a TeX letter: `tectonic --outdir <temp> <letter.tex>`, then copy only the final PDF beside the source
4. Run one QA script over both outputs.
5. Make one consolidated repair per reported defect family if needed.
6. Recompile and rerun the same QA. Stop after three total repair iterations or earlier when the numeric report shows no measurable progress.
7. Save/register final source rows once and mark ready once.

Do not read five prior resumes, compile each file independently across many calls, or interleave contact research between layout passes.

## Deterministic QA

One verifier should report:

- source and sibling PDF exist
- compiler exit code
- expected page count
- extracted text and word count
- required evidence/company phrases
- contamination/banned-credential scan
- professional filename
- clean folder containing only the final source/PDF pair and an explicitly requested JSON QA report
- final-PDF word and line bounding boxes
- measured bottom text whitespace/content occupancy
- exact line-level defects: overlap, near-collision, abnormal leading, weak hierarchy, and short final lines
- page, numeric measurements, source/semantic element ID when instrumented, severity, and repair scope
- a grouped `repair_plan` that collapses repeated defects into one shared-style edit

If a coding harness requires fresh evidence, use a temporary `hermes-verify-*` directory and the live project helpers. Call `hermes_jobapps.typst.compile_typst_to_pdf` for the resume and compile any letter with its real compiler, then collect page count, extracted text, contamination checks, and the nested layout report in one JSON file. Do not reference verifier scripts unless they exist in the current checkout.

### Bounded repair loop

1. Compile once and read `verification.layout.violations` plus `verification.layout.repair_plan`.
2. If the same violation and measurement repeat across several entries, edit the shared Typst macro/token once. Do not patch each rendered occurrence.
3. For a `short_final_line`, edit only the attributed bullet. Preserve factual meaning and provenance; content judgment remains owned by `jobapps-material-quality-judge`.
4. Recompile and compare violation types, counts, and measurements against the prior report.
5. Accept the repair only when the original defect disappeared and no new overlap, page-count, page-bound, hierarchy, or short-line regression appeared.
6. Stop after `resume_qa.max_repair_iterations` (default 3), or immediately when the report makes no measurable progress. Return the remaining diagnostics instead of guessing.

`jobapps_mark_material_ready_for_review` rejects Typst resumes unless the stored deterministic layout report has `ready: true` and its source/PDF SHA-256 values still match the current artifacts. Every material patch clears compile/layout QA metadata. Never write or claim `visual_qa: passed` from screenshot reassurance.

## Final visual QA

Compile success is not visual QA. Run one subjective image review only after deterministic geometry passes. Inspect:

- clipping, overlap, broken glyphs, missing links
- uneven section rhythm
- Experience vs Projects balance
- body readability at actual scale
- bottom whitespace
- orphan words or short wrapped lines
- header/contact wrapping
- ugly hyphenation

Treat 9–10% bottom whitespace as a repair trigger when the page visibly looks short. Treat 15–20% as a failure. Measure rather than reassure. Do not use repeated screenshots as the primary repair loop.

### Layout repair order

1. Fix the exact orphan/overflow phrase with a shorter equivalent.
2. Reclaim a line by removing redundant wording in that same bullet or Skills row.
3. Restore/expand grounded substance if the page is sparse.
4. Relax overly tight section/list spacing or margins consistently to use the page.
5. Trim only genuinely redundant content if the page overflows.
6. Never shrink the 10.5pt resume or 10.8pt cover-letter body as a workaround.

When the user identifies a specific defect, patch that line first. Do not rewrite unrelated experience.

## Content preservation and density

- Do not silently strip confirmed bullets or metrics.
- Keep the confirmed experience list stable when it fits; tailor bullets and emphasis before dropping roles.
- Research belongs in Experience when it is presented as Research Assistant work.
- Projects should prove architecture/method depth but not make Experience look thin.
- Skills should be compact, proper case, and truthful. Remove planted JD keywords and filler.
- Degree and GPA wording must come from user-confirmed profile facts, never this public skill.
- No `Anthropic AI Fluency` or `Claude 101` in any candidate-facing material.

## Cover-letter source checks

Before compiling, read the final source and reject:

- duplicated greeting or closing
- internal review/status text
- `Learned preference`, `tailoring_summary`, `JD-specific target`, `review_status`, `ready_for_review`, or similar scaffolding
- fake enthusiasm or generic company praise
- resume narration
- invented domain experience

TeX cover letters should use `fontspec`, compile with Tectonic/XeTeX, disable awkward hyphenation, and include a small `\emergencystretch` from the start rather than waiting for overfull-line failures.

## Typst pitfalls

- Escape literal C# as `C\#`.
- `@` followed by a number is parsed as a label; use `SR-at-10`, not `SR@10`.
- Visible markup inside a function body needs content brackets.
- Do not use LaTeX `\\` as a Typst line break.
- Avoid aggressive negative `v()`/row-gutter values that can overlap text.
- Keep visible project links human-readable (`Project`, `Publication`) so they do not create orphan fragments.

## Artifact and JobApps rules

A material folder should contain only the final resume source/PDF and cover-letter source/PDF. Build logs, aux files, thumbnails, temp scripts, and `build/` directories stay outside and are removed.

When saving material metadata, `compile` must be an object, not a bare string. Include compiler/status/PDF path, page count, word count, and review status. Save actual source content, not a JSON note saying the file exists.

Do not call queued material prep or scaffold notes a deliverable. A package is ready only when real PDFs exist, have been verified, are registered once, and are marked ready for human review.

## Specialized references

Load only the reference matching the active defect or material type. Useful routes:

- surgical edit → `references/surgical-material-fixes.md`
- density/occupancy → `references/resume-density-qa.md`
- compile contract → `references/compile-tool-contract.md`
- harness verification → `references/harness-adhoc-material-verification.md`
- Typst spacing → `references/typst-resume-spacing-debugging.md`
- cover-letter density → `references/cover-letter-density-and-spacing.md`
- quick apply → `references/quick-apply-material-quality.md`
- academic CV → `references/academic-phd-cv-workflow.md`

The long reference library preserves historical edge cases. Do not load the catalog during a normal one-job build.
