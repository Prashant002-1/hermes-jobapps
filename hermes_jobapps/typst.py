"""Typst artifact helpers for JobApps resume builds."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .latex import verify_pdf


def typst_escape(value: str) -> str:
    """Escape user/job text for Typst markup content blocks."""

    replacements = {
        "\\": r"\\",
        "#": r"\#",
        "[": r"\[",
        "]": r"\]",
        "*": r"\*",
        "_": r"\_",
        "`": r"\`",
        "$": r"\$",
    }
    return "".join(replacements.get(char, char) for char in str(value))


def typst_string(value: str) -> str:
    """Return a quoted Typst string literal."""

    text = str(value or "")
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{text}"'


def build_resume_typst(job: dict[str, Any], evaluation: dict[str, Any], drafts: dict[str, Any]) -> str:
    """Build the local prepare resume artifact as Typst, not LaTeX."""

    title = evaluation.get("facts", {}).get("title") or job.get("title") or "Target Role"
    company = evaluation.get("facts", {}).get("company") or job.get("company") or "Company"
    angle = evaluation.get("strongest_angle", "")
    notes = drafts.get("resume_notes") or []
    if not isinstance(notes, list):
        notes = [str(notes)]
    note_items = "\n".join(f"  - {typst_escape(str(note))}" for note in notes if str(note).strip())
    if not note_items:
        note_items = "  - Add user-confirmed resume content before external use."
    matches = "\n".join(
        f"  - {typst_escape(str(match.get('requirement', '')))} — {typst_escape(str(match.get('proof_point', '')))}"
        for match in evaluation.get("must_have_matches", [])[:5]
        if str(match.get("requirement", "")).strip() or str(match.get("proof_point", "")).strip()
    )
    if not matches:
        matches = "  - No mapped requirements were generated yet."
    return f"""#import "@preview/simple-technical-resume:0.1.1": *

#show: resume.with(
  paper: "us-letter",
  top-margin: 0.32in,
  bottom-margin: 0.18in,
  left-margin: 0.42in,
  right-margin: 0.42in,
  font: "New Computer Modern",
  font-size: 9.65pt,
  personal-info-font-size: 9.3pt,
  author-position: center,
  personal-info-position: center,
  author-name: "Prashant Shah",
  email: "applicant@example.com",
  linkedin-user-id: "prashant210",
  github-username: "Prashant002-1",
)

#custom-title({typst_string(f"Resume Notes: {title} at {company}")})[
  *Central angle:* {typst_escape(str(angle))}
]

#custom-title("Changes To Make")[
{note_items}
]

#custom-title("Requirement To Proof Map")[
{matches}
]
"""


def build_full_resume_typst(
    *,
    name: str = "Prashant Shah",
    headline: str = "AI Engineer focused on agentic systems",
    sections: list[dict[str, Any]] | None = None,
) -> str:
    """Build a compact full-resume Typst artifact from explicit sections."""

    section_blocks: list[str] = []
    for section in sections or []:
        title = str(section.get("title") or "Section")
        raw_items = section.get("items") or []
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        items = "\n".join(f"  - {typst_escape(str(item))}" for item in raw_items if str(item).strip())
        if not items:
            continue
        section_blocks.append(f"#custom-title({typst_string(title)})[\n{items}\n]")
    if not section_blocks:
        section_blocks.append(
            "#custom-title(\"Review Notes\")[\n"
            "  - Add user-confirmed projects, experience, education, and skills before external use.\n"
            "]"
        )

    return f"""#import "@preview/simple-technical-resume:0.1.1": *

#show: resume.with(
  paper: "us-letter",
  top-margin: 0.32in,
  bottom-margin: 0.18in,
  left-margin: 0.42in,
  right-margin: 0.42in,
  font: "New Computer Modern",
  font-size: 9.65pt,
  personal-info-font-size: 9.3pt,
  author-position: center,
  personal-info-position: center,
  author-name: {typst_string(name)},
  email: "applicant@example.com",
  linkedin-user-id: "prashant210",
  github-username: "Prashant002-1",
)

#align(center)[{typst_escape(headline)}]

{chr(10).join(section_blocks)}
"""


def compile_typst_to_pdf(
    typst_path: str | Path,
    *,
    config: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile a Typst material into its final sibling PDF and verify it."""

    config = config or {}
    typst_config = config.get("typst", {}) if isinstance(config.get("typst", {}), dict) else {}
    compiler_order = typst_config.get("compiler_order") or [typst_config.get("compiler") or "typst"]
    compiler_order = [str(item) for item in compiler_order if str(item or "").strip()]
    timeout = int(typst_config.get("timeout_seconds", config.get("latex", {}).get("timeout_seconds", 60) if isinstance(config.get("latex", {}), dict) else 60))
    source = Path(typst_path)
    if not source.exists():
        return {
            "ok": False,
            "status": "missing_source",
            "source_path": str(source),
            "typst_path": str(source),
            "compiler_candidates": compiler_order,
            "next_step": "Create or save the Typst material before compiling.",
        }

    search_paths = _typst_search_paths(typst_config, config)
    compiler = next((resolved for name in compiler_order if (resolved := _resolve_compiler(name, search_paths))), None)
    if compiler is None:
        return {
            "ok": False,
            "status": "missing_compiler",
            "source_path": str(source),
            "typst_path": str(source),
            "compiler_candidates": compiler_order,
            "searched_paths": search_paths,
            "next_step": "Install Typst or add it to typst.compiler_paths, then run compile again.",
        }

    build_dir = Path(output_dir) if output_dir else source.parent / "build"
    clean_build_dir = output_dir is None
    build_dir.mkdir(parents=True, exist_ok=True)
    built_pdf_path = build_dir / f"{source.stem}.pdf"
    final_pdf_path = source.with_suffix(".pdf")
    command = [compiler, "compile", str(source), str(built_pdf_path)]
    try:
        completed = subprocess.run(
            command,
            cwd=str(source.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_compile_env(search_paths, compiler),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "status": "timeout",
            "source_path": str(source),
            "typst_path": str(source),
            "compiler": compiler,
            "command": command,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "next_step": "Review the Typst source or increase the compile timeout.",
        }

    ok = completed.returncode == 0 and built_pdf_path.exists()
    verification: dict[str, Any] = {"status": "not_run"}
    if ok:
        shutil.copy2(built_pdf_path, final_pdf_path)
        verification = verify_pdf(final_pdf_path, config=config)
    if clean_build_dir:
        shutil.rmtree(build_dir, ignore_errors=True)
    return {
        "ok": ok,
        "status": "compiled" if ok else "compile_failed",
        "source_path": str(source),
        "typst_path": str(source),
        "pdf_path": str(final_pdf_path) if final_pdf_path.exists() else "",
        "build_pdf_path": str(built_pdf_path),
        "compiler": compiler,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-6000:],
        "stderr": completed.stderr[-6000:],
        "verification": verification,
        "next_step": "PDF compiled, copied beside the Typst source, and verified." if ok else "Open the compile errors, patch the Typst, and compile again.",
    }


def _typst_search_paths(typst_config: dict[str, Any], config: dict[str, Any]) -> list[str]:
    configured = typst_config.get("compiler_paths") or []
    if isinstance(configured, str):
        configured = [configured]
    paths: list[str] = []
    for item in configured:
        _append_path(paths, item)
    latex_config = config.get("latex", {}) if isinstance(config.get("latex", {}), dict) else {}
    for item in latex_config.get("compiler_paths") or []:
        _append_path(paths, item)
    for env_var in ("TYPST_COMPILER_DIR", "HOMEBREW_PREFIX"):
        value = os.environ.get(env_var)
        if not value:
            continue
        _append_path(paths, value)
        if env_var == "HOMEBREW_PREFIX":
            _append_path(paths, Path(value) / "bin")
    for item in ("/opt/homebrew/bin", "/usr/local/bin", "/Library/TeX/texbin"):
        _append_path(paths, item)
    for item in os.environ.get("PATH", "").split(os.pathsep):
        _append_path(paths, item)
    return paths


def _append_path(paths: list[str], value: str | Path) -> None:
    if not value:
        return
    path = str(Path(value).expanduser())
    if path not in paths:
        paths.append(path)


def _resolve_compiler(name: str, search_paths: list[str]) -> str | None:
    candidate = Path(name).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return shutil.which(name, path=os.pathsep.join(search_paths))


def _compile_env(search_paths: list[str], compiler: str) -> dict[str, str]:
    env = os.environ.copy()
    compiler_dir = str(Path(compiler).parent)
    path_items = [compiler_dir, *search_paths, env.get("PATH", "")]
    env["PATH"] = os.pathsep.join(item for item in path_items if item)
    return env
