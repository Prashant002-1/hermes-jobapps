#!/usr/bin/env python3
"""Ad-hoc verification helper for one resume/cover-letter material pair.

This is intended for Hermes coding-harness prompts that require a temporary
`hermes-verify-*` script. Copy or invoke this logic from a tempfile-created
script under the harness-provided temp root, not as a canonical project test.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hermes_jobapps.config import load_config  # noqa: E402
from hermes_jobapps.resume_qa import verify_resume_pdf  # noqa: E402

BAD_TERMS = [
    "Learned preference",
    "review_status",
    "tailoring_summary",
    "Resume Tailoring Build",
    "JD-specific",
    "Do not send without approval",
    "approval gate",
    "weak networking replies",
    "Anthropic AI Fluency",
]


def run(cmd: list[str], commands: list[list[str]], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    commands.append(cmd)
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def resolve_tool(name: str, search_paths: list[str]) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    for directory in search_paths:
        candidate = Path(os.path.expanduser(directory)) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise FileNotFoundError(f"Required tool not found: {name}")


def pdf_occupancy(pdf: Path, commands: list[list[str]], tools: dict[str, str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="hermes-material-render-") as tmp:
        output = Path(tmp) / "page"
        run(
            [
                tools["pdftoppm"],
                "-f",
                "1",
                "-singlefile",
                "-gray",
                "-r",
                "150",
                str(pdf),
                str(output),
            ],
            commands,
        )
        pgm = output.with_suffix(".pgm")
        with pgm.open("rb") as handle:
            if handle.readline().strip() != b"P5":
                raise ValueError(f"Unexpected render format: {pgm}")
            dimensions = handle.readline()
            while dimensions.startswith(b"#"):
                dimensions = handle.readline()
            width, height = map(int, dimensions.split())
            max_value = int(handle.readline())
            pixels = handle.read()
        if max_value != 255 or len(pixels) != width * height:
            raise ValueError(f"Invalid PGM render: {pgm}")
        content_rows = [
            row
            for row in range(height)
            if min(pixels[row * width : (row + 1) * width]) < 245
        ]
        if not content_rows:
            return {"rendered": True, "bottom_whitespace_pct": 100.0, "content_height_pct": 0.0}
        top, bottom = min(content_rows), max(content_rows)
        return {
            "rendered": True,
            "bottom_whitespace_pct": round((height - 1 - bottom) / height * 100, 2),
            "content_height_pct": round((bottom - top + 1) / height * 100, 2),
        }


def pdf_checks(
    pdf: Path,
    min_words: int,
    max_words: int,
    phrases: list[str],
    commands: list[list[str]],
    tools: dict[str, str],
) -> dict:
    info = run([tools["pdfinfo"], str(pdf)], commands).stdout
    text = run([tools["pdftotext"], str(pdf), "-"], commands).stdout
    pages_match = re.search(r"^Pages:\s+(\d+)", info, re.M)
    pages = int(pages_match.group(1)) if pages_match else None
    words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)
    normalized_text = " ".join(text.split()).lower()
    return {
        "pdf": str(pdf),
        "pages": pages,
        "word_count": len(words),
        "missing_required_phrases": [p for p in phrases if " ".join(p.split()).lower() not in normalized_text],
        "contamination": [t for t in BAD_TERMS if " ".join(t.split()).lower() in normalized_text],
        "word_count_diagnostic_range": [min_words, max_words],
        "word_count_in_diagnostic_range": min_words <= len(words) <= max_words,
        **pdf_occupancy(pdf, commands, tools),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a JobApps resume/cover-letter material pair.")
    parser.add_argument("--folder", required=True, help="Material folder containing source/PDF deliverables")
    parser.add_argument("--resume", required=True, help="Resume .typ path")
    parser.add_argument("--cover", required=True, help="Cover letter .typ or .tex path")
    parser.add_argument("--resume-phrase", action="append", default=[], help="Required phrase in resume PDF text")
    parser.add_argument("--cover-phrase", action="append", default=[], help="Required phrase in cover-letter PDF text")
    parser.add_argument("--resume-min-words", type=int, default=450, help="Diagnostic only; does not gate readiness")
    parser.add_argument("--resume-max-words", type=int, default=545, help="Diagnostic only; does not gate readiness")
    parser.add_argument("--cover-min-words", type=int, default=400)
    parser.add_argument("--cover-max-words", type=int, default=650)
    parser.add_argument("--resume-bottom-whitespace-target-in", type=float, default=0.65)
    parser.add_argument("--resume-bottom-whitespace-tolerance-in", type=float, default=0.10)
    parser.add_argument("--cover-max-bottom-whitespace", type=float, default=10.0)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    config = load_config()
    typst_config = config.get("typst", {})
    latex_config = config.get("latex", {})
    resume_config = config.get("resume_qa", {})
    search_paths = list(dict.fromkeys(
        list(resume_config.get("tool_paths", []))
        + list(typst_config.get("compiler_paths", []))
        + list(latex_config.get("compiler_paths", []))
    ))
    folder = Path(args.folder).resolve()
    resume = Path(args.resume).resolve()
    cover = Path(args.cover).resolve()
    if cover.suffix.lower() not in {".typ", ".tex"}:
        parser.error(f"unsupported cover-letter source format: {cover.suffix}")
    resume_pdf = resume.with_suffix(".pdf")
    cover_pdf = cover.with_suffix(".pdf")
    commands: list[list[str]] = []
    errors: list[str] = []

    if resume.parent != folder or cover.parent != folder:
        errors.append("resume and cover sources must live directly in --folder")
    if " - Resume - " not in resume.stem:
        errors.append(f"resume: unprofessional filename {resume.name!r}")
    if " - Cover Letter - " not in cover.stem:
        errors.append(f"cover_letter: unprofessional filename {cover.name!r}")

    try:
        tool_names = ["typst", "pdfinfo", "pdftotext", "pdftoppm"]
        if cover.suffix.lower() == ".tex":
            tool_names.append("tectonic")
        tools = {name: resolve_tool(name, search_paths) for name in tool_names}
        run([tools["typst"], "compile", str(resume), str(resume_pdf)], commands, timeout=args.timeout)
        if cover.suffix.lower() == ".typ":
            run([tools["typst"], "compile", str(cover), str(cover_pdf)], commands, timeout=args.timeout)
        else:
            with tempfile.TemporaryDirectory(prefix="hermes-verify-tectonic-") as tmp:
                run(
                    [tools["tectonic"], "--outdir", tmp, "--print", str(cover)],
                    commands,
                    timeout=args.timeout,
                )
                built = Path(tmp) / cover_pdf.name
                if built.exists():
                    shutil.copy2(built, cover_pdf)
                else:
                    errors.append(f"missing cover pdf build output: {built}")

        checks = {
            "resume": pdf_checks(resume_pdf, args.resume_min_words, args.resume_max_words, args.resume_phrase, commands, tools),
            "cover_letter": pdf_checks(cover_pdf, args.cover_min_words, args.cover_max_words, args.cover_phrase, commands, tools),
        }
        layout = verify_resume_pdf(
            resume_pdf,
            config=config,
            source_path=resume,
            typst_compiler=tools["typst"],
        )
        checks["resume"]["layout"] = layout
        if not layout.get("ready"):
            errors.append(f"resume: deterministic layout QA failed ({layout.get('status')})")
        for label, check in checks.items():
            if check["pages"] != 1:
                errors.append(f"{label}: expected 1 page, got {check['pages']}")
            if label != "resume" and not check["word_count_in_diagnostic_range"]:
                errors.append(f"{label}: word count {check['word_count']} outside expected range")
            if check["missing_required_phrases"]:
                errors.append(f"{label}: missing phrases {check['missing_required_phrases']}")
            if check["contamination"]:
                errors.append(f"{label}: contamination {check['contamination']}")
            if label == "resume":
                occupancy = ((layout.get("metrics") or {}).get("page_occupancy") or [{}])[0]
                measured_in = occupancy.get("bottom_whitespace_in")
                target_in = args.resume_bottom_whitespace_target_in
                minimum_in = target_in - args.resume_bottom_whitespace_tolerance_in
                maximum_in = target_in + args.resume_bottom_whitespace_tolerance_in
                check["bottom_whitespace_in"] = measured_in
                check["bottom_whitespace_target_in"] = target_in
                check["bottom_whitespace_accepted_range_in"] = [minimum_in, maximum_in]
                if measured_in is None or not minimum_in <= float(measured_in) <= maximum_in:
                    errors.append(
                        f"resume: bottom whitespace {measured_in!r}in outside "
                        f"{minimum_in:.3f}-{maximum_in:.3f}in target band"
                    )
            elif check["bottom_whitespace_pct"] > args.cover_max_bottom_whitespace:
                errors.append(
                    f"{label}: bottom whitespace {check['bottom_whitespace_pct']}% "
                    f"exceeds {args.cover_max_bottom_whitespace}%"
                )

        files = sorted(p.name for p in folder.iterdir())
        allowed = {resume.name, resume_pdf.name, cover.name, cover_pdf.name}
        disallowed = [name for name in files if name not in allowed]
        if disallowed:
            errors.append(f"disallowed artifacts: {disallowed}")
        checks["folder"] = {"path": str(folder), "files": files, "disallowed_artifacts": disallowed}
        print(json.dumps({"ok": not errors, "errors": errors, "checks": checks, "commands_run": commands}, indent=2))
        return 0 if not errors else 1
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "errors": ["command failed", exc.cmd, exc.stdout], "commands_run": commands}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
