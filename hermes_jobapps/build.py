"""Compile Typst and TeX materials into PDFs and verify the result."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .resume_qa import verify_resume_pdf


def compile_typst_to_pdf(
    typst_path: str | Path,
    *,
    config: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
    layout_qa: bool = True,
) -> dict[str, Any]:
    """Compile a Typst material into its final sibling PDF and verify it.

    With layout_qa=False the PDF is still verified, but the resume layout
    gate is skipped and the result carries no verification.layout report.
    """

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

    rendered = completed.returncode == 0 and built_pdf_path.exists()
    verification: dict[str, Any] = {"status": "not_run"}
    layout_verification: dict[str, Any] = {"status": "not_run", "ready": False}
    if rendered:
        shutil.copy2(built_pdf_path, final_pdf_path)
        verification = verify_pdf(final_pdf_path, config=config)
        if layout_qa:
            layout_verification = verify_resume_pdf(
                final_pdf_path,
                config=config,
                source_path=source,
                typst_compiler=compiler,
                typst_env=_compile_env(search_paths, compiler),
            )
            verification["layout"] = layout_verification
    resume_qa_config = config.get("resume_qa", {}) if isinstance(config.get("resume_qa", {}), dict) else {}
    integrity_errors = _pdf_integrity_errors(verification, resume_qa_config) if rendered else ["pdf_not_rendered"]
    verification["integrity_errors"] = integrity_errors
    layout_required = layout_qa and bool(resume_qa_config.get("required", True))
    layout_ready = bool(layout_verification.get("ready"))
    ok = rendered and not integrity_errors and (layout_ready or not layout_required)
    if not rendered:
        status = "compile_failed"
    elif ok:
        status = "compiled"
    else:
        status = "verification_failed"
    if clean_build_dir:
        shutil.rmtree(build_dir, ignore_errors=True)
    if not rendered:
        next_step = "Open the compile errors, patch the Typst, and compile again."
    elif not layout_qa:
        next_step = (
            "PDF compiled, copied beside the Typst source, and verified."
            if ok
            else "Fix verification.integrity_errors and compile again."
        )
    elif ok:
        next_step = "PDF compiled, copied beside the Typst source, and passed deterministic layout QA."
    else:
        next_step = "Apply verification.layout.repair_plan, recompile, and stop after resume_qa.max_repair_iterations if defects remain."
    return {
        "ok": ok,
        "rendered": rendered,
        "status": status,
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
        "next_step": next_step,
    }


def compile_tex_to_pdf(
    tex_path: str | Path,
    *,
    config: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile a TeX material into its final sibling PDF and verify it.

    The function never installs tooling. A missing compiler is reported as a
    structured status. By default, compilation happens in an isolated build
    directory, the resulting PDF is copied beside the source .tex, and the
    temporary build directory is removed.
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


def _pdf_integrity_errors(verification: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if verification.get("status") != "checked":
        errors.append(f"verification_status:{verification.get('status')}")
    if verification.get("pdfinfo_exit") != 0:
        errors.append("pdfinfo_failed")
    if verification.get("pdftotext_exit") != 0:
        errors.append("pdftotext_failed")
    required_pages = int(settings.get("required_pages", 1))
    if verification.get("pages") != required_pages:
        errors.append(f"page_count:{verification.get('pages')}")
    minimum_words = int(settings.get("minimum_exported_words", 1))
    word_count = verification.get("word_count")
    if not isinstance(word_count, int) or word_count < minimum_words:
        errors.append(f"word_count:{word_count}")
    if verification.get("contamination"):
        errors.append("contamination_detected")
    return errors


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


def _resolve_compiler(name: str, search_paths: list[str]) -> str | None:
    candidate = Path(name).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return shutil.which(name, path=os.pathsep.join(search_paths))


_resolve_latex_compiler = _resolve_compiler


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
