# Surgical material fixes

Use this when the user asks for a narrow resume/cover-letter/PDF/source repair and explicitly says to be quick, fix only one thing, or not record/save/learn during the task.

## Operating rule

Treat the request as a scoped bug fix, not a material-prep workflow. Do not reopen strategy, evidence, status tracking, dashboard recording, broad QA commentary, or preference-learning discussion while executing the fix.

## Minimal workflow

1. Identify the exact source file for the visible PDF/material.
2. Patch only the broken line/section unless the requested fix cannot work without a local helper change.
3. Recompile the affected PDF.
4. Verify the specific defect is gone with extracted text or rendered inspection.
5. Verify page count still holds for resumes.
6. Report a concise done-state only.

## Typst line-break pitfall

In Typst strings/content, a literal LaTeX-style `\\` can render as visible backslashes instead of line breaks. For `simple-technical-resume` education/header repairs, avoid embedding `\\` as text. Use Typst-native structure instead: separate content blocks/rows, `linebreak()` where appropriate, or the template's normal two-row education rhythm. After patching, run `pdftotext` and confirm the visible text contains real line breaks and no literal `\\` in that section.

## Typst spacing micro-fixes

When the user asks for a narrow spacing repair in a resume:

- Keep the last working layout as the safety baseline. If a spacing experiment causes overlap, revert immediately before trying another approach.
- Prefer small adjustments to existing spacing knobs (`v(...)`, `custom-title(..., spacing-between: ...)`, paragraph leading) over rebuilding section macros.
- If changing one `v(...)` does not visibly affect the target gap, the gap may be controlled by the surrounding block/section helper. Inspect the local Typst structure before repeatedly changing the same line.
- Before changing section structure, compare against the known template/source pattern. For `simple-technical-resume`, section-title `spacing-between`, the content block's own paragraph spacing, and nearby helper macros can all affect perceived gaps.
- Avoid quick three-row `grid` rewrites with negative `row-gutter` for Education blocks; they can compile while visually overlapping text. Do not replace a stable Education block with a new macro/grid just to shave a few pixels.
- When there is bottom whitespace and the content is already approved, solve spacing by redistributing breathing room through section/body spacing, bullet leading, and title-to-body spacing. Do not add words or cut content unless the user asks.
- For objective sanity without full visual QA, `pdftotext -bbox` can show line positions/gaps around the affected lines, but the user's visual judgment wins for micro-layout taste.
- If the user says not to vision-analyze and will judge the layout personally, do not run visual QA. Recompile, verify `Pages: 1` and text sanity only, copy the PDF, and report briefly.

## What not to do during the fix

- Do not create JobApps records or progress/actions if the user says not to record.
- Do not update proof points, brain events, or materials metadata unless explicitly requested.
- Do not broaden into wording/strategy changes.
- Do not produce a long explanation. A one- or two-line completion report is enough after verification.
