---
name: material-build
description: "Use when building or fixing resume and letter PDFs. Covers source formats, file naming, reading a jobapps_check result, the bounded repair loop, Typst and TeX pitfalls, layout repair and final PDF verification."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, typst, latex, pdf, layout, qa]
    related_skills: [jobapps:jobapps, jobapps:resume-writing, jobapps:cover-letter-writing]
---

# Material build

This skill owns files, formats and the check loop. What the document says belongs to its writing skill. A layout repair never changes meaning, and a wording repair that the layout forces must keep every claim.

## Sources and formats

- Resumes are Typst (`.typ`) unless the candidate's approved source is something else. Letters follow their approved source: `.typ` or `.tex`. Answers, outreach and interview notes are Markdown.
- Start from the closest approved source: the same kind of document in a similar job folder, else `templates/`. Copy it into the job folder and edit the copy. Never edit `templates/` or another job's files while tailoring.
- Preserve the source's structure, macros, fonts, sizes, margins and section order. Typography comes from the candidate's source, never from a default in this skill. Do not redesign because another template looks better.
- Names: `<Name> - Resume - <Company> - <Role>.typ` and `<Name> - Cover Letter - <Company> - <Role>.typ` or `.tex`. The PDF is the sibling with the same name. The check infers the kind from the file name; pass `kind` if the name does not say.
- The job folder holds sources, PDFs, `answers.md`, `outreach.md`, `interview-prep.md` and `qa/`. Put previews, logs and scratch files in the system temporary directory. Do not delete files the user put there.

## Run the check

`jobapps_check(path)` on the source file, never on the PDF. It builds the PDF, measures the layout of resumes, lints the content, and saves `qa/<file>.json`. Any later edit makes that report stale: check again after every change, however small.

| Part of the result | What it tells you |
|---|---|
| `status` | `fail`: the build broke, or a resume's layout is not ready. `review`: content findings at error or warning level remain. `pass`: clean. |
| `build` | Compiler, page and word counts, the error text, PDF integrity problems, contamination (internal or scaffolding text that reached the PDF). |
| `layout` | Resumes only. `violations` with type, the text involved, source line and a suggested fix; `repair_plan` grouping them into a few actions; `bottom_whitespace_in`. |
| `content` | `findings`, each with rule, severity, where, excerpt and fix. Notes are advisory and do not change the status. |
| `content.coverage` | Requirements covered and uncovered, posting terms missing from the document. |
| `next` | The tool's own instruction for the next step. Follow it. |

## Repair order

1. **Build errors.** Nothing else is real until the PDF builds. Read the compiler message and line. `references/typst-pitfalls.md` covers the usual causes. A missing compiler is the user's to install: report it and stop.
2. **Content errors and warnings.** Fix these before layout, because every wording change moves the layout. A leak of scaffolding text is always an error. A number not found in the evidence is a question: find it in the evidence, confirm it with the user and record it there, or remove the precision.
3. **Layout.** Apply `repair_plan`, not the violations one by one. A shared-style action is one edit to a shared setting; a rewrite action lists the exact lines. `references/layout-repair.md` maps every violation type to its repair.
4. **Coverage.** Add a missing term only where verified experience supports it. Uncovered requirements with no evidence stay uncovered; say so in one line.

A lint finding is a prompt for judgment, not an order. If a warning is wrong for this sentence, leave the sentence, tell the user in one line, and do not contort good prose to silence it. Build and layout failures are facts and are never waved through.

## The bounded loop

- One consolidated edit per round, covering everything the report listed. Then one check.
- At most three check and repair rounds per document.
- After each round compare with the previous report: the original defects must be gone and no new ones introduced. If a round makes no measurable progress, or trades one violation for another, stop.
- On stopping, report plainly: what passes, what still fails with the measurement, what was tried, and the path of the latest PDF. Do not describe a failing document as ready, and do not mark the job `ready`. Overriding a failed check is the user's explicit decision.

## Never

- Shrink body type, squeeze leading until lines collide, or narrow margins below the approved source to make content fit.
- Add negative vertical space to pull blocks together, or stack local spacers on a problem that lives in a shared style.
- Pad with filler words or stretch spacing to use up white space.
- Change approved wording during a layout repair beyond the exact lines the report names.
- Raise a threshold in `settings.json` so the current file passes.

## Verify the final PDF

After the last passing check:

1. Read the extracted text of the PDF (`pdftotext` where available). Confirm the name and contact details, that special characters survived (`C#`, `C++`, `$`, `@`, `%`), that nothing was silently dropped, and that no placeholder, comment or note reached the page.
2. Confirm the page count, and that links show short readable text.
3. Look at the rendered page once, whole: hierarchy, even spacing, no clipped or touching text, a balanced bottom margin. If you cannot view images, say so and ask the user to look. One visual review, at the end. Screenshots do not override a measured failure.
4. Give the user the PDF path.

## Narrow fixes and experiments

- A request to fix one thing is a scoped fix: patch that unit, check, confirm the defect is gone and nothing else moved, report in a line or two.
- "Too dense" or "space it out" is a layout request. Keep the text and adjust spacing within the approved template.
- A typography experiment (a font, a size) goes in a separate preview copy with one variable changed. Leave the original untouched, report what happened, and keep the preview until the user chooses.

## References

- `references/typst-pitfalls.md`: load on a Typst build error, or when text is missing or altered in the PDF.
- `references/layout-repair.md`: load when `layout` reports violations, or the page is over or under filled.
- `references/tex-letters.md`: load when the letter source is `.tex`.
