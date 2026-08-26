# Resume density QA

Use this when a one-page resume compiles but may be sparse, crowded, clipped, or missing role-relevant substance.

## Checks

1. Compile in a temporary output directory and keep only the final source/PDF pair.
2. Confirm page count with `pdfinfo` or an equivalent tool.
3. Extract text with `pdftotext`; treat word count as a diagnostic, not a universal target.
4. Render the final PDF and inspect bottom whitespace, overlap, cutoff text, missing sections, orphan words, and legibility.
5. If the page is sparse, restore confirmed experience substance before padding projects or stretching typography.
6. If the page overflows, remove redundancy before shrinking body text.
7. Record layout evidence in JobApps metadata when tools are available.

Compile success alone is not readiness. A resume passes when the final PDF is one page, readable, grounded, uncontaminated by workflow text, and visually balanced for its chosen template.
