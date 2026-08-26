# JobApps Compile Tool Contract

Session lesson: when material compilation repeatedly needs manual cleanup, do not keep adding workaround notes or one-off scripts. The durable fix belongs in the app-owned compile primitive plus regression tests.

## Contract

For `jobapps_compile_material_pdf` and the underlying local compile helper:

1. Compile TeX in an isolated build/output directory.
2. Copy the final PDF beside the source `.tex` using the professional upload-facing filename.
3. Verify the final sibling PDF, not only an intermediate build artifact:
   - file exists
   - page count via `pdfinfo` or equivalent
   - extracted text via `pdftotext` or equivalent
   - word count when relevant
   - contamination scan for internal workflow/scaffold terms
4. Remove transient build directories and auxiliary files from the material folder.
5. Persist `pdf_path` and verification metadata back to the material record when app tooling is available.
6. Add/keep a regression test for this contract so the workflow does not drift back to manual folder cleanup.

## Operator rule

If a future session sees the compiler returning PDFs only under `build/` or leaving build clutter behind, treat that as a tool-contract bug. Patch the reusable compile function and tests. Do not solve it by adding another narrow helper script or by expanding SKILL.md with more manual cleanup prose.
