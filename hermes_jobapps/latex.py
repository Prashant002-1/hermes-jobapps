"""LaTeX artifact helpers for resume and cover-letter builds."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import resolve_project_path


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def build_resume_tex(job: dict[str, Any], evaluation: dict[str, Any], drafts: dict[str, Any]) -> str:
    """Legacy compatibility wrapper. Resume tailoring artifacts are Typst-first now."""

    from .typst import build_resume_typst

    return build_resume_typst(job, evaluation, drafts)


def build_cover_letter_tex(job: dict[str, Any], evaluation: dict[str, Any], drafts: dict[str, Any]) -> str:
    title = latex_escape(evaluation.get("facts", {}).get("title") or job.get("title") or "Target Role")
    company = latex_escape(evaluation.get("facts", {}).get("company") or job.get("company") or "Company")
    content = latex_escape(str(drafts.get("cover_letter") or ""))
    paragraphs = "\n\n".join(_clean_paragraph(line) for line in content.split("\n\n") if line.strip())
    return rf"""\documentclass[11pt]{{letter}}
\usepackage[margin=0.9in]{{geometry}}
\pagenumbering{{gobble}}

\begin{{document}}

\begin{{letter}}{{{company}\\Hiring Team}}
\opening{{Dear Hiring Team,}}

{paragraphs}

\closing{{Sincerely,\\Applicant Name}}
\end{{letter}}

% Target role: {title}
% This file is generated as a reviewable LaTeX artifact. Do not send without approval.
\end{{document}}
"""


def write_material_artifact(job_id: str, filename: str, content: str, root: str = "data/materials") -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", job_id)
    safe_name = safe_material_filename(filename)
    root_path = resolve_project_path(root).expanduser()
    path = _safe_material_artifact_path(root_path, safe_id, safe_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def job_material_filename(job: dict[str, Any], material_kind: str, extension: str = "tex") -> str:
    """Build a human-readable, submission-ready material filename."""

    company = _human_filename_part(str(job.get("company") or "Company"), fallback="Company")
    title = _human_filename_part(str(job.get("title") or job.get("role") or "Role"), fallback="Role")
    artifact = _material_filename_label(material_kind)
    ext = _safe_extension(extension)
    return safe_material_filename(f"Applicant Name - {artifact} - {company} - {title}.{ext}")


def safe_material_filename(filename: str) -> str:
    """Strip unsafe filesystem characters while keeping a human filename."""

    name = str(filename or "Material.txt")
    name = re.sub(r"[/\\]+", " ", name)
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", name)
    stem, suffix = _split_extension(name)
    stem = _human_filename_part(stem, fallback="Material", max_chars=180)
    extension = _safe_extension(suffix.lstrip(".") or "txt")
    return f"{stem}.{extension}"


def _material_filename_label(material_kind: str) -> str:
    labels = {
        "cover_letter": "Cover Letter",
        "outreach": "Outreach",
        "outreach_draft": "Outreach Draft",
        "resume": "Resume",
        "resume_notes": "Resume Notes",
        "resume_tailoring": "Resume",
        "short_answers": "Short Answers",
    }
    return labels.get(str(material_kind or "material"), _title_label(str(material_kind or "material")))


def _human_filename_part(value: str, *, fallback: str, max_chars: int = 72) -> str:
    text = str(value or "")
    text = text.replace("&", " and ")
    text = re.sub(r"[/\\:]+", " ", text)
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"[<>\"|?*]+", "", text)
    text = re.sub(r"[(),;]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    text = text or fallback
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rsplit(" ", 1)[0].strip(" -")
    return clipped or text[:max_chars].strip(" -") or fallback


def _title_label(value: str) -> str:
    words = re.sub(r"[^A-Za-z0-9]+", " ", value).strip().split()
    return " ".join(word[:1].upper() + word[1:].lower() for word in words) or "Material"


def _safe_extension(value: str) -> str:
    ext = re.sub(r"[^A-Za-z0-9]+", "", str(value or "").lstrip(".")).lower()
    return ext or "txt"


def _split_extension(name: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)(\.[A-Za-z0-9]{1,8})$", name.strip())
    if not match:
        return name, ""
    return match.group(1), match.group(2)


def _safe_material_artifact_path(root_path: Path, safe_id: str, safe_name: str) -> Path:
    """Return an app-owned material path without following child symlinks.

    The app writes generated TeX into ``materials_path/<job_id>/<filename>``.
    If an attacker or stale local state turns that job directory into a symlink,
    a normal ``Path.write_text`` would silently write outside materials_path.
    Resolve the candidate before writing and reject any existing symlink
    component under the configured root.
    """

    root_path.mkdir(parents=True, exist_ok=True)
    resolved_root = root_path.resolve(strict=True)
    output_dir = root_path / safe_id
    candidate = output_dir / safe_name
    current = root_path
    for part in (safe_id, safe_name):
        current = current / part
        if current.is_symlink():
            raise ValueError("Material artifact paths may not include symlink components.")
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Material artifact path must stay inside the configured materials_path.") from exc
    return candidate


def compile_tex_to_pdf(
    tex_path: str | Path,
    *,
    config: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile a TeX material into its final sibling PDF and verify it.

    The function never installs tooling. Missing compilers are reported as a
    structured status so the cockpit can show the blocked state clearly. By
    default, compilation happens in an isolated build directory, the resulting
    PDF is copied beside the source .tex, and the temporary build directory is
    removed.
    """

    config = config or {}
    latex_config = config.get("latex", {}) if isinstance(config.get("latex", {}), dict) else {}
    compiler_order = latex_config.get("compiler_order") or ["tectonic", "latexmk", "xelatex", "pdflatex"]
    compiler_order = [str(item) for item in compiler_order]
    timeout = int(latex_config.get("timeout_seconds", 60))
    tex = Path(tex_path)
    if not tex.exists():
        return {
            "ok": False,
            "status": "missing_source",
            "tex_path": str(tex),
            "compiler_candidates": compiler_order,
            "next_step": "Create or save the TeX material before compiling.",
        }

    search_paths = _latex_search_paths(latex_config)
    compiler = next(
        (resolved for name in compiler_order if (resolved := _resolve_latex_compiler(name, search_paths))),
        None,
    )
    if compiler is None:
        return {
            "ok": False,
            "status": "missing_compiler",
            "tex_path": str(tex),
            "compiler_candidates": compiler_order,
            "searched_paths": search_paths,
            "next_step": "Install a TeX compiler such as tectonic or MacTeX, then run compile again.",
        }

    build_dir = Path(output_dir) if output_dir else tex.parent / "build"
    clean_build_dir = output_dir is None
    build_dir.mkdir(parents=True, exist_ok=True)
    command = _compile_command(compiler, tex, build_dir)
    try:
        completed = subprocess.run(
            command,
            cwd=str(tex.parent),
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
            "tex_path": str(tex),
            "compiler": compiler,
            "command": command,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "next_step": "Review the TeX source or increase the compile timeout.",
        }

    built_pdf_path = build_dir / f"{tex.stem}.pdf"
    log_path = build_dir / f"{tex.stem}.log"
    final_pdf_path = tex.with_suffix(".pdf")
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
        "tex_path": str(tex),
        "pdf_path": str(final_pdf_path) if final_pdf_path.exists() else "",
        "build_pdf_path": str(built_pdf_path),
        "log_path": str(log_path) if log_path.exists() else "",
        "compiler": compiler,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-6000:],
        "stderr": completed.stderr[-6000:],
        "verification": verification,
        "next_step": "PDF compiled, copied beside the TeX source, and verified." if ok else "Open the compile log/errors, patch the TeX, and compile again.",
    }


def verify_pdf(pdf_path: str | Path, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verify a compiled PDF using local PDF tools when available."""

    config = config or {}
    latex_config = config.get("latex", {}) if isinstance(config.get("latex", {}), dict) else {}
    search_paths = _latex_search_paths(latex_config)
    timeout = int(latex_config.get("timeout_seconds", 60))
    pdf = Path(pdf_path)
    result: dict[str, Any] = {
        "status": "missing_pdf" if not pdf.exists() else "checked",
        "pdf_path": str(pdf),
        "exists": pdf.exists(),
        "pages": None,
        "word_count": None,
        "contamination": [],
        "pdfinfo_exit": None,
        "pdftotext_exit": None,
    }
    if not pdf.exists():
        return result

    pdfinfo = _resolve_latex_compiler("pdfinfo", search_paths)
    if pdfinfo:
        info = subprocess.run([pdfinfo, str(pdf)], capture_output=True, text=True, timeout=timeout, check=False)
        result["pdfinfo_exit"] = info.returncode
        result["pdfinfo_stdout"] = info.stdout[-2000:]
        match = re.search(r"^Pages:\s*(\d+)\s*$", info.stdout, flags=re.MULTILINE)
        if match:
            result["pages"] = int(match.group(1))

    pdftotext = _resolve_latex_compiler("pdftotext", search_paths)
    if pdftotext:
        text = subprocess.run([pdftotext, str(pdf), "-"], capture_output=True, text=True, timeout=timeout, check=False)
        result["pdftotext_exit"] = text.returncode
        extracted = text.stdout if text.returncode == 0 else ""
        result["word_count"] = len(re.findall(r"\b[\w'-]+\b", extracted))
        result["contamination"] = _contamination_terms(extracted)
    if result["pdfinfo_exit"] is None and result["pdftotext_exit"] is None:
        result["status"] = "verification_tools_missing"
    return result


def _contamination_terms(text: str) -> list[str]:
    terms = [
        "Learned preference",
        "approval gate",
        "review_status",
        "tailoring_summary",
        "weak networking replies",
        "operational example",
        "JD-specific",
        "Frame experience truthfully",
        "Resume Tailoring Build",
        "Central angle",
        "Changes To Make",
        "Requirement To Proof Map",
        "Build Notes",
    ]
    return [term for term in terms if term.lower() in text.lower()]


def _latex_search_paths(latex_config: dict[str, Any]) -> list[str]:
    configured = latex_config.get("compiler_paths") or []
    if isinstance(configured, str):
        configured = [configured]
    paths: list[str] = []
    for item in configured:
        _append_path(paths, item)
    for env_var in ("TEX_COMPILER_DIR", "TEXLIVE_BINDIR", "HOMEBREW_PREFIX"):
        value = os.environ.get(env_var)
        if not value:
            continue
        _append_path(paths, value)
        if env_var == "HOMEBREW_PREFIX":
            _append_path(paths, Path(value) / "bin")
    for item in (
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/Library/TeX/texbin",
        "/usr/texbin",
    ):
        _append_path(paths, item)
    texlive_root = Path("/usr/local/texlive")
    if texlive_root.exists():
        for bindir in sorted(texlive_root.glob("*/bin/*"), reverse=True):
            _append_path(paths, bindir)
    for item in os.environ.get("PATH", "").split(os.pathsep):
        _append_path(paths, item)
    return paths


def _append_path(paths: list[str], value: str | Path) -> None:
    if not value:
        return
    path = str(Path(value).expanduser())
    if path not in paths:
        paths.append(path)


def _resolve_latex_compiler(name: str, search_paths: list[str]) -> str | None:
    candidate = Path(name).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    found = shutil.which(name, path=os.pathsep.join(search_paths))
    return found


def _compile_env(search_paths: list[str], compiler: str) -> dict[str, str]:
    env = os.environ.copy()
    compiler_dir = str(Path(compiler).parent)
    path_items = [compiler_dir, *search_paths, env.get("PATH", "")]
    env["PATH"] = os.pathsep.join(item for item in path_items if item)
    return env


def _compile_command(compiler: str, tex: Path, build_dir: Path) -> list[str]:
    if Path(compiler).name == "tectonic":
        return [compiler, "--keep-logs", "--keep-intermediates", "--outdir", str(build_dir), str(tex)]
    if Path(compiler).name == "latexmk":
        return [
            compiler,
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-outdir={build_dir}",
            str(tex),
        ]
    return [
        compiler,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={build_dir}",
        str(tex),
    ]


def _clean_paragraph(value: str) -> str:
    return value.strip().replace("\n", " ")
