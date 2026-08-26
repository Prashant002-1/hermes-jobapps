# Harness Ad-hoc Material Verification

Use this only when the coding harness explicitly marks edited `.typ`/`.tex` or related code paths `unverified` because it did not recognize a canonical test/build command. This is a harness requirement, not a normal extra JobApps review stage.

## Fast path: one terminal call

Two reusable verifiers live under this skill:

- `scripts/verify_material_pair.py` for a resume plus cover-letter package. It auto-detects `.typ` versus `.tex` cover letters and uses Typst or Tectonic accordingly.
- `scripts/verify_resume.py` for resume-only tasks. Do not invent a dummy cover letter or force the pair verifier when the user requested only a resume.

Select the matching verifier before creating the temporary harness copy. Do not allocate a path, write a second full verifier, hand-patch the temporary copy for a Typst cover letter, run it, and clean it up through four separate tool calls.

For a material-only warning, use one `terminal` call that:

1. creates the required OS-safe path with `mktemp`/`tempfile` and the `hermes-verify-` prefix under the exact harness temp root;
2. copies the matching reusable verifier directly to that path;
3. runs it once against the changed material with the required phrase/word/whitespace arguments;
4. captures its exit code;
5. removes the temporary verifier and confirms removal.

Do not stage a generated verifier inside the active workspace before copying it. Even if that staging file is deleted, the coding harness can record it as another changed path and demand a second verification cycle.

Pair command shape:

```bash
VERIFY=$(python3 -c 'import os,tempfile; fd,p=tempfile.mkstemp(prefix="hermes-verify-",suffix=".py",dir="<HARNESS_TEMP_ROOT>"); os.close(fd); print(p)')
cp '<SKILL_DIR>/scripts/verify_material_pair.py' "$VERIFY"
python3 "$VERIFY" --folder '<MATERIAL_DIR>' --resume '<RESUME.typ>' --cover '<LETTER.typ-or-tex>' <focused thresholds/phrases>
RC=$?
rm -f "$VERIFY"
REMOVED=false
[ ! -e "$VERIFY" ] && REMOVED=true
printf '\nAD_HOC_VERIFIER_EXIT=%s\nTEMP_SCRIPT_REMOVED=%s\n' "$RC" "$REMOVED"
[ "$RC" -eq 0 ] && [ "$REMOVED" = true ]
```

For a resume-only task, use the same wrapper but copy `scripts/verify_resume.py` and invoke it as:

```bash
python3 "$VERIFY" \
  --folder '<MATERIAL_DIR>' \
  --resume '<RESUME.typ>' \
  --phrase '<PUBLIC TITLE OR REQUIRED EVIDENCE>' \
  --min-words 450 --max-words 545 \
  --max-bottom-whitespace 8
```

Capture and print the verifier exit code explicitly, then make the final shell expression assert both verifier success and cleanup. Do not rely only on `set -e` plus an `EXIT` trap: some harness shells can report a nonzero wrapper status even after the verifier printed `ok: true`, leaving the run marked unverified. This shape gives the harness an unambiguous final exit code and cleanup signal in one tool round trip. `cp` is intentional here: it avoids the file-writer guard on system temp paths and avoids regenerating the same verifier logic.

## Required-phrase checks over extracted PDF text

`pdftotext` can insert newlines inside a visually continuous phrase when a PDF line wraps, for example `submitted\nmanuscript`. The reusable pair verifier normalizes all extracted whitespace before required-phrase and contamination matching. Keep multiword assertions semantically exact; do not weaken `submitted manuscript` to `manuscript` merely to work around PDF extraction layout.

If a phrase still fails after whitespace normalization, inspect the extracted text for glyph/encoding changes or confirm that the source actually contains the claim. Fix the extractor/check only when the rendered PDF is correct; never patch candidate-facing prose solely to satisfy a brittle raw-text substring test.

## Focused assertions for surgical edits

When the user requests a tiny source change under the coding harness, run the matching ad-hoc verifier immediately after the edit instead of doing a manual compile first. A successful manual Typst compile does not satisfy a harness request for a temporary `hermes-verify-*` script.

Verify the changed scope, not an overbroad proxy. If removing `Jest` only from the Skills row while the word legitimately remains in a project bullet, inspect that exact source row and assert its new ending; do not fail because the term still appears elsewhere in the PDF. Pair that source-level assertion with normal page, font, occupancy, phrase, contamination, and clean-folder checks.

## Mixed code + material changes

If Python code changed too, prepend only the focused regression tests for those changed contracts in the same terminal call. Do not rerun the whole suite inside the ad-hoc verifier when the full suite already passed after the last code edit. Before a commit, run the canonical/full project tests separately once.

The focused verifier should cover:

- compile the changed Typst/TeX sources;
- final sibling PDFs exist;
- expected page count;
- extracted text, word limits, and required phrases;
- contamination/banned credentials;
- rendered occupancy and bottom whitespace;
- exact reported orphan/line defect when relevant;
- clean material folder;
- `git diff --check` when code is involved.

## Do not duplicate or weaken verification

- Do not run manual compile, then the reusable verifier, then another handwritten ad-hoc verifier. The reusable verifier is the compile/QA run.
- Do not render with both `qlmanage` and `pdftoppm`; use the verifier's single render path.
- Do not measure live database payloads in every material verification; regression tests cover tool contracts.
- Do not run broad JobApps retrieval or networking as part of verification.
- Do not repeat the full test suite after a focused harness verifier unless code changed again.
- Do not raise word-count or bottom-whitespace limits merely to make the current artifact pass. A request to prioritize content over verification means run one focused verifier, not weaken its quality gate. Use the normal material thresholds; repair a concrete density defect, or report an intentional exception explicitly instead of silently relaxing the limit.

## Repeated harness warnings

A later turn may repeat the same `unverified` warning even when the preceding turn ran the required temporary verifier successfully. Treat the warning as a request for fresh evidence in the current turn: rerun the same focused verifier through a newly created `hermes-verify-*` tempfile, remove it, and report the new exit code. Do not argue from the prior transcript, broaden into a canonical suite run, or edit the materials again when no content changed.

## Reporting

Report this as **ad-hoc material/behavior verification, not canonical suite green**. Include:

- exit code
- focused test count when applicable
- page/word/whitespace results
- contamination and required-phrase result
- clean-folder result
- temp script removed

The final user-facing report should be one short line unless the user asks for the full verifier output.
