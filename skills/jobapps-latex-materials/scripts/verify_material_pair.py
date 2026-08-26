#!/usr/bin/env python3
"""Ad-hoc verification helper for one resume/cover-letter material pair.

This is intended for Hermes coding-harness prompts that require a temporary
`hermes-verify-*` script. Copy or invoke this logic from a tempfile-created
script under the harness-provided temp root, not as a canonical project test.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

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

TOOL_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/Library/TeX/texbin")


def resolve_tool(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    for directory in TOOL_DIRS:
        candidate = Path(directory) / name
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"Required tool not found: {name}")


def run(cmd: list[str], commands: list[list[str]]) -> subprocess.CompletedProcess[str]:
    commands.append(cmd)
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def pdf_occupancy(pdf: Path, commands: list[list[str]]) -> dict:
    with tempfile.TemporaryDirectory(prefix="hermes-material-render-") as tmp:
        output = Path(tmp) / "page"
        run(
            [
                resolve_tool("pdftoppm"),
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
) -> dict:
    info = run([resolve_tool("pdfinfo"), str(pdf)], commands).stdout
    text = run([resolve_tool("pdftotext"), str(pdf), "-"], commands).stdout
    pages_match = re.search(r"^Pages:\s+(\d+)", info, re.M)
    pages = int(pages_match.group(1)) if pages_match else None
    words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)
    return {
        "pdf": str(pdf),
        "pages": pages,
        "word_count": len(words),
        "missing_required_phrases": [p for p in phrases if p.lower() not in text.lower()],
        "contamination": [t for t in BAD_TERMS if t.lower() in text.lower()],
        "word_count_diagnostic_range": [min_words, max_words],
        "word_count_in_diagnostic_range": min_words <= len(words) <= max_words,
        **pdf_occupancy(pdf, commands),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a JobApps resume/cover-letter material pair.")
    parser.add_argument("--folder", required=True, help="Material folder containing source/PDF deliverables")
    parser.add_argument("--resume", required=True, help="Resume .typ path")
    parser.add_argument("--cover", required=True, help="Cover letter .tex path")
    parser.add_argument("--resume-phrase", action="append", default=[], help="Required phrase in resume PDF text")
    parser.add_argument("--cover-phrase", action="append", default=[], help="Required phrase in cover-letter PDF text")
    parser.add_argument("--resume-min-words", type=int, default=450, help="Diagnostic only; does not gate readiness")
    parser.add_argument("--resume-max-words", type=int, default=545, help="Diagnostic only; does not gate readiness")
    parser.add_argument("--cover-min-words", type=int, default=400)
    parser.add_argument("--cover-max-words", type=int, default=650)
    parser.add_argument("--resume-bottom-whitespace-target-in", type=float, default=0.65)
    parser.add_argument("--resume-bottom-whitespace-tolerance-in", type=float, default=0.10)
    parser.add_argument("--cover-max-bottom-whitespace", type=float, default=10.0)
    args = parser.parse_args()

    folder = Path(args.folder)
    resume = Path(args.resume)
    cover = Path(args.cover)
    resume_pdf = resume.with_suffix(".pdf")
    cover_pdf = cover.with_suffix(".pdf")
    commands: list[list[str]] = []
    errors: list[str] = []

    try:
        run([resolve_tool("typst"), "compile", str(resume), str(resume_pdf)], commands)
        with tempfile.TemporaryDirectory(prefix="hermes-verify-tectonic-") as tmp:
            run([resolve_tool("tectonic"), "--outdir", tmp, "--print", str(cover)], commands)
            built = Path(tmp) / cover_pdf.name
            if built.exists():
                shutil.copy2(built, cover_pdf)
            else:
                errors.append(f"missing cover pdf build output: {built}")

        checks = {
            "resume": pdf_checks(resume_pdf, args.resume_min_words, args.resume_max_words, args.resume_phrase, commands),
            "cover_letter": pdf_checks(cover_pdf, args.cover_min_words, args.cover_max_words, args.cover_phrase, commands),
        }
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
                measured_in = check["bottom_whitespace_pct"] / 100.0 * 11.0
                minimum_in = args.resume_bottom_whitespace_target_in - args.resume_bottom_whitespace_tolerance_in
                maximum_in = args.resume_bottom_whitespace_target_in + args.resume_bottom_whitespace_tolerance_in
                check["bottom_whitespace_in"] = round(measured_in, 3)
                check["bottom_whitespace_target_in"] = args.resume_bottom_whitespace_target_in
                check["bottom_whitespace_accepted_range_in"] = [round(minimum_in, 3), round(maximum_in, 3)]
                if not minimum_in <= measured_in <= maximum_in:
                    errors.append(
                        f"resume: bottom whitespace {measured_in:.3f}in outside "
                        f"{minimum_in:.3f}-{maximum_in:.3f}in target band"
                    )
            elif check["bottom_whitespace_pct"] > args.cover_max_bottom_whitespace:
                errors.append(
                    f"{label}: bottom whitespace {check['bottom_whitespace_pct']}% "
                    f"exceeds {args.cover_max_bottom_whitespace}%"
                )

        files = sorted(p.name for p in folder.iterdir())
        disallowed = [f for f in files if Path(f).suffix not in {".typ", ".tex", ".pdf"}]
        if disallowed:
            errors.append(f"disallowed artifacts: {disallowed}")
        checks["folder"] = {"path": str(folder), "files": files, "disallowed_artifacts": disallowed}
        print(json.dumps({"ok": not errors, "errors": errors, "checks": checks, "commands_run": commands}, indent=2))
        return 0 if not errors else 1
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(json.dumps({
            "ok": False,
            "errors": ["tool or command failed", str(exc), getattr(exc, "stdout", None)],
            "commands_run": commands,
        }, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
