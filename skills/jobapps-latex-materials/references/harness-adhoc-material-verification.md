# Harness Ad-hoc Material Verification

Use this only when the coding harness explicitly marks edited `.typ`/`.tex` or related code paths `unverified` because it did not recognize a canonical test/build command. This is a harness requirement, not a normal extra JobApps review stage.

## Fast path: one terminal call

The reusable verifier already lives at `scripts/verify_material_pair.py` inside this skill. Do not allocate a path, write a second full verifier, run it, and clean it up through four separate tool calls.

For a material-only warning, use one `terminal` call that:

1. creates the required OS-safe path with `mktemp`/`tempfile` and the `hermes-verify-` prefix under the exact harness temp root;
2. copies the reusable verifier to that path;
3. installs a shell `trap` to delete it;
4. runs it once against the changed pair with the required phrase/word/whitespace arguments;
5. confirms the script was removed.

Conceptual command shape:

```bash
set -euo pipefail
VERIFY=$(python3 -c 'import os,tempfile; fd,p=tempfile.mkstemp(prefix="hermes-verify-",suffix=".py",dir="<HARNESS_TEMP_ROOT>"); os.close(fd); print(p)')
trap 'rm -f "$VERIFY"' EXIT
cp '<SKILL_DIR>/scripts/verify_material_pair.py' "$VERIFY"
python3 "$VERIFY" --folder '<MATERIAL_DIR>' --resume '<RESUME.typ>' --cover '<LETTER.tex>' <focused thresholds/phrases>
rm -f "$VERIFY"
trap - EXIT
test ! -e "$VERIFY"
```

This satisfies the temp-script contract in one tool round trip. `cp` is intentional here: it avoids the file-writer guard on system temp paths and avoids regenerating the same verifier logic.

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

## Do not duplicate work

- Do not run manual compile, then the reusable verifier, then another handwritten ad-hoc verifier. The reusable verifier is the compile/QA run.
- Do not render with both `qlmanage` and `pdftoppm`; use the verifier's single render path.
- Do not measure live database payloads in every material verification; regression tests cover tool contracts.
- Do not run broad JobApps retrieval or networking as part of verification.
- Do not repeat the full test suite after a focused harness verifier unless code changed again.

## Reporting

Report this as **ad-hoc material/behavior verification, not canonical suite green**. Include:

- exit code
- focused test count when applicable
- page/word/whitespace results
- contamination and required-phrase result
- clean-folder result
- temp script removed

The final user-facing report should be one short line unless the user asks for the full verifier output.
