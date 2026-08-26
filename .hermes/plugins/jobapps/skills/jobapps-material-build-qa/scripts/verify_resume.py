#!/usr/bin/env python3
"""Compile one Typst resume and emit deterministic content and layout QA."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


for candidate in Path(__file__).resolve().parents:
    if (candidate / "hermes_jobapps").is_dir():
        sys.path.insert(0, str(candidate))
        break

from hermes_jobapps.config import load_config  # noqa: E402
from hermes_jobapps.latex import verify_pdf  # noqa: E402
from hermes_jobapps.resume_qa import verify_resume_pdf  # noqa: E402


BAD_TERMS = [
    "Learned preference",
    "review_status",
    "tailoring_summary",
    "Resume Tailoring Build",
    "JD-specific",
    "Anthropic AI Fluency",
    "Claude 101",
]


def run(command: list[str], commands: list[list[str]], *, timeout: int) -> str:
    commands.append(command)
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    ).stdout


def resolve_tool(name: str, search_paths: list[str]) -> str:
    for directory in search_paths:
        candidate = Path(os.path.expanduser(directory)) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise FileNotFoundError(f"Required tool not found: {name}")


def violation_error(violation: dict[str, Any]) -> str:
    target = violation.get("semantic_id") or violation.get("element_id") or violation.get("section") or f"page {violation.get('page')}"
    measurements = [
        f"{key}={value}"
        for key, value in violation.items()
        if key.endswith("_pt") or key.endswith("_ratio") or key.endswith("_count")
    ]
    suffix = f" ({', '.join(measurements)})" if measurements else ""
    return f"{violation['type']} at {target}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--resume", required=True)
    parser.add_argument("--phrase", action="append", default=[])
    parser.add_argument("--min-words", type=int, default=450)
    parser.add_argument("--max-words", type=int, default=545)
    parser.add_argument("--max-bottom-whitespace", type=float, default=8.0)
    parser.add_argument("--body-font", default="Avenir Next")
    parser.add_argument("--min-body-size", type=float, default=10.0)
    parser.add_argument("--report", type=Path, help="Optional path for the complete JSON QA report.")
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
    source = Path(args.resume).resolve()
    pdf = source.with_suffix(".pdf")
    report_path = args.report.expanduser().resolve() if args.report else None
    commands: list[list[str]] = []
    errors: list[str] = []

    if source.parent != folder:
        errors.append("resume source must live directly in --folder")
    if " - Resume - " not in source.stem:
        errors.append(f"resume: unprofessional filename {source.name!r}")

    try:
        typst = resolve_tool("typst", search_paths)
        pdftotext = resolve_tool("pdftotext", search_paths)
        pdf.unlink(missing_ok=True)
        run([typst, "compile", str(source), str(pdf)], commands, timeout=args.timeout)
        text = run([pdftotext, str(pdf), "-"], commands, timeout=args.timeout)
        integrity = verify_pdf(pdf, config=config)
        layout = verify_resume_pdf(
            pdf,
            config=config,
            source_path=source,
            typst_compiler=typst,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({
            "ok": False,
            "status": "tool_or_compile_failed",
            "error": str(exc),
            "commands_run": commands,
        }, indent=2))
        return 1

    words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)
    missing = [phrase for phrase in args.phrase if phrase.lower() not in text.lower()]
    contamination = sorted(set(integrity.get("contamination", [])) | {term for term in BAD_TERMS if term.lower() in text.lower()})
    page_metrics = layout.get("metrics", {}).get("page_occupancy", [])
    bottom_whitespace = round(page_metrics[0]["bottom_whitespace_ratio"] * 100, 2) if page_metrics else None
    files = sorted(path.name for path in folder.iterdir() if path.is_file())
    reported_files = list(files)
    if report_path is not None and report_path.parent == folder and report_path.name not in reported_files:
        reported_files.append(report_path.name)
        reported_files.sort()
    allowed_paths = {source, pdf}
    if report_path is not None:
        allowed_paths.add(report_path)
    disallowed = [
        path.name
        for path in folder.iterdir()
        if path.is_dir() or (path.is_file() and path.resolve() not in allowed_paths)
    ]
    source_text = source.read_text(encoding="utf-8")
    font_match = re.search(r'(?<![-\w])font\s*:\s*"([^"]+)"', source_text)
    size_match = re.search(r"(?<![-\w])font-size\s*:\s*([0-9.]+)pt", source_text)
    if size_match is None:
        size_match = re.search(r"set\s+text\([^)]*\bsize\s*:\s*([0-9.]+)pt", source_text)
    body_font = font_match.group(1) if font_match else None
    body_size = float(size_match.group(1)) if size_match else None
    font_contract = body_font == args.body_font and body_size is not None and body_size >= args.min_body_size

    errors.extend(violation_error(violation) for violation in layout.get("violations", []))
    if layout.get("status") != "passed" and not layout.get("violations"):
        errors.append(f"layout verification unavailable: {layout.get('status')}")
    if not args.min_words <= len(words) <= args.max_words:
        errors.append(f"word count {len(words)} outside expected range")
    if missing:
        errors.append(f"missing phrases: {missing}")
    if contamination:
        errors.append(f"contamination: {contamination}")
    if bottom_whitespace is not None and bottom_whitespace > args.max_bottom_whitespace:
        errors.append(f"bottom text whitespace {bottom_whitespace}% exceeds limit")
    if disallowed:
        errors.append(f"disallowed artifacts: {disallowed}")
    if not font_contract:
        errors.append(
            f"body typography contract missing: expected {args.body_font} at >= {args.min_body_size}pt, "
            f"found {body_font or 'unknown'} at {body_size if body_size is not None else 'unknown'}pt"
        )

    output = {
        "ok": not errors,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "checks": {
            "pages": integrity.get("pages"),
            "word_count": len(words),
            "bottom_text_whitespace_pct": bottom_whitespace,
            "missing_required_phrases": missing,
            "contamination": contamination,
            "font_contract": font_contract,
            "body_font": body_font,
            "body_size_pt": body_size,
            "clean_folder": not disallowed,
            "folder_files": reported_files,
        },
        "layout": layout,
        "repair_plan": layout.get("repair_plan", []),
        "commands_run": commands,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())