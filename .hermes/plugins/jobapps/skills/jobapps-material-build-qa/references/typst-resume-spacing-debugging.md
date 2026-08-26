# Typst resume spacing debugging

Use this when the user flags visual spacing in a Typst resume, especially `simple-technical-resume`-style materials.

## Common education-spacing failure

A narrow education-spacing fix can become unstable when the apparent gap is not controlled by a single `v()` line. A typical source may use:

- `custom-title`, which adds its own trailing `v(spacing-between)` after the whole section.
- A custom education grid using `linebreak()` inside grid cells.
- A separate `Recognitions:` paragraph after the grid.

Changing only the local `v()` may barely move the visible layout. Rebuilding Education as a multi-row grid with aggressive negative `row-gutter` can remove too much space and cause overlap. Revert to the last working layout, then apply small adjustments to the section-level trailing spacing and the local spacer without changing structure.

## Rule

For spacing-only feedback, do not restructure macros unless the structure is definitely broken and the user approves a broader layout fix. First identify all spacing sources:

1. Section helper trailing spacing, e.g. `custom-title(..., spacing-between: ...)`.
2. Entry/helper internal spacing after grids/headings.
3. List paragraph leading and item indentation.
4. Explicit local `v(...)` calls.
5. Template defaults in imported package helpers.

## Safe workflow

1. Read the surrounding source, not just the one visible line.
2. If there is a last known-good version, preserve its structure.
3. Compile once and save the `verification.layout` report. Treat final-PDF geometry as rendered truth.
4. Read the measured violation, source range or semantic ID, and grouped repair plan before editing.
5. Change one shared spacing control for repeated defects, or one attributed bullet for a short final line. Do not stack local negative `v()` patches.
6. Recompile and use `compare_layout_reports(before, after)` to prove the original defect disappeared without a new page-count, overlap, hierarchy, or wrapping regression.
7. Stop after three repair iterations or when `evaluate_repair_progress(...)` reports no measurable progress. Return the remaining numeric diagnostics instead of guessing.
8. Run one final subjective image review only after deterministic QA passes. Screenshots cannot override a geometry failure.

## Practical guidance

- Avoid aggressive negative `row-gutter` in Typst grids for multi-line education blocks. It can overlap text even when the source looks reasonable.
- If `Recognitions` is a separate paragraph below a grid, its visible gap may be affected by both the local `v(...)` and the section helper's trailing spacing before the next section.
- If the gap above and below the line both look similar, the issue may be section rhythm, not just the line immediately before it.
- Preserve content during spacing passes. Do not add/cut words to solve whitespace unless the user explicitly moves from spacing-only to content editing.

## Semantic telemetry

Generated Typst resumes wrap arbitrary sections and bullets with `qa-region(kind, id)[...]`. The wrapper emits measured width, height, page, and position through Typst metadata. Keep IDs stable when editing so final-PDF violations remain attributable across repair iterations.

Manually authored sources without telemetry still receive best-effort source-line attribution by matching rendered text against the `.typ` source. Prefer telemetry for new source generators; do not rewrite a stable legacy resume only to add instrumentation.

Use both layers:

- Typst telemetry identifies the intended semantic element.
- Poppler `pdftotext -bbox-layout` identifies actual exported words, lines, wrapping, overlap, and page geometry.

Neither replaces the other, and neither is a content-quality judge.
