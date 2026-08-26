---
name: jobapps-latex-materials
description: "Create, tailor, compile, repair, and verify the user's Typst resumes and Typst/TeX cover letters with a fast deterministic workflow."
version: 2.0.0
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
6. Candidate-facing project title: use `Local Agent Workflow Architecture` or role-appropriate architecture/tooling language, never `Hermes JobApps`.
7. Upload-facing files use professional names with spaces:
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
   - `typst compile <resume.typ> <resume.pdf>`
   - `tectonic --outdir <temp> <letter.tex>`, then copy only the final PDF beside the source
4. Run one QA script over both outputs.
5. Make one consolidated content/layout repair if needed.
6. Recompile and rerun the same QA once.
7. Save/register final source rows once, then mark ready once with the four passed semantic checks and the current SHA-256 for every selected source.

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
- clean folder containing only final source/PDF pairs
- rendered thumbnail/image
- measured rendered bottom whitespace in points, inches, and page ratio
- a strict resume target of **0.65in ± 0.10in** from the lowest rendered content to the page edge
- exact line-level defects such as orphan words

If the coding harness requires fresh evidence, use the temporary `hermes-verify-*` pattern in `references/harness-adhoc-material-verification.md`. Report it as ad-hoc verification, not canonical suite green.

## Visual QA

Compile success is not visual QA. Render the page and inspect:

- clipping, overlap, broken glyphs, missing links
- uneven section rhythm
- Experience vs Projects balance
- body readability at actual scale
- bottom whitespace
- orphan words or short wrapped lines
- header/contact wrapping
- ugly hyphenation

Every resume render must measure the distance from the lowest rendered content to the page edge. The accepted band is **0.55–0.75in**, centered on a **0.65in** target. A resume outside that band fails deterministic QA even when it is one page, otherwise collision-free, and visually plausible. Measure both directions: excess whitespace wastes usable space; too little whitespace crowds the page. Do not substitute the configured Typst page margin for this rendered-content measurement.

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

`jobapps_mark_material_ready_for_review` is the final state boundary. It requires a reviewer label; `truth`, `role_relevance`, `evidence_quality`, and `voice_and_no_scaffolding` all set to true; and a `material_sha256` map containing the exact current source hash for every selected material. Any edit invalidates that attestation. Typst resumes separately require current layout source/PDF hashes and `layout.ready: true`.

For native-authored Typst registration, place the deterministic report at `metadata.verification.layout`, not `metadata.layout`. That object must include `status`, `ready`, `violations`, and `artifact.source_sha256` / `artifact.pdf_sha256`; `metadata.pdf_path` or `metadata.compile.pdf_path` must point to the exact sibling PDF. The stored Typst `content` must byte-match the source file or readiness blocks with `stored_content_hash_mismatch`. If the available save tool cannot preserve an exact source byte stream, register the already-verified upload-facing PDF as standard `kind="resume"`, `format="pdf"`, bind semantic review to the PDF SHA-256, and retain the canonical `.typ` beside it.

When saving material metadata, `compile` must be an object, not a bare string. Include compiler/status/PDF path, page count, word count, and review status. Save actual source content, not a JSON note saying the file exists.

Do not call queued material prep or scaffold notes a deliverable. A package is ready only when real PDFs exist, have been verified, are registered once, and are marked ready for human review.

## Specialized references

Load only the reference matching the active defect or material type. Useful routes:

- surgical edit → `references/surgical-material-fixes.md`
- harness verification → `references/harness-adhoc-material-verification.md`

The long reference library preserves historical edge cases. Do not load the catalog during a normal one-job build.
