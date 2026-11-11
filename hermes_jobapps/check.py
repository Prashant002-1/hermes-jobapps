"""Build one material file, lint its content, and save the QA report beside it."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import build as _build
from . import submission_qa
from .workspace import atomic_write, clip, material_kind, qa_report_path, section, sha256_file


_FORMATS = {".typ": "typ", ".tex": "tex", ".md": "md", ".markdown": "md", ".txt": "text"}
_PDF_SOURCE_SUFFIXES = (".typ", ".tex", ".md")
_KIND_HINT = "Pass kind: resume, cover_letter, application_answers or outreach."
_MAX_VIOLATIONS = 12
_MAX_REPAIR_STEPS = 6
_MAX_REPAIR_TARGETS = 6
_BUILD_ERROR_CHARS = 1200

_VIOLATION_VALUE_KEYS = (
    "direction",
    "actual_pages",
    "required_pages",
    "measured_baseline_step_pt",
    "expected_baseline_step_pt",
    "measured_gap_pt",
    "minimum_gap_pt",
    "expected_gap_pt",
    "vertical_overlap_pt",
    "normal_wrapped_overlap_pt",
    "final_word_count",
    "width_utilization",
    "gap_ratio",
    "measured_bottom_whitespace_in",
    "accepted_range_in",
    "actual_font",
    "required_font",
    "actual_size_pt",
    "minimum_size_pt",
    "actual_width_pt",
    "actual_height_pt",
    "expected_width_pt",
    "expected_height_pt",
)


def check_material(
    ws: Any,
    path: str,
    *,
    kind: str = "",
    job: str = "",
    max_chars: int | None = None,
    build: bool = True,
) -> dict[str, Any]:
    """Build and check one material file inside the workspace.

    Returns a compact result for the agent and saves the same findings to
    the file's QA report, which is what workspace.qa_state reads.
    """

    from . import content_qa

    job_id = str(ws.resolve_job(job)["id"]) if str(job or "").strip() else ""
    source, error = _locate(ws, path, job_id)
    if source is None:
        return error
    fmt = _FORMATS.get(source.suffix.lower())
    if fmt is None:
        return {"ok": False, "error": f"Check reads .typ, .tex, .md or .txt files, not {source.suffix or 'this file'}."}

    if str(kind or "").strip():
        try:
            resolved_kind = content_qa.normalize_kind(kind)
        except ValueError as exc:
            return {"ok": False, "error": clip(str(exc) or f"Unknown kind: {kind}", 200), "hint": _KIND_HINT}
    else:
        resolved_kind = material_kind(source.name)
    if resolved_kind in {"interview", "other"}:
        return {"ok": False, "error": "Cannot tell what kind of document this is.", "hint": _KIND_HINT}

    settings = ws.settings()
    context = _job_context(ws, source, job_id)
    text = source.read_text(encoding="utf-8", errors="replace")
    source_sha256 = sha256_file(source)

    built: dict[str, Any] | None = None
    if build and fmt == "typ":
        built = _build.compile_typst_to_pdf(source, config=settings, layout_qa=(resolved_kind == "resume"))
    elif build and fmt == "tex":
        built = _build.compile_tex_to_pdf(source, config=settings)

    build_summary: dict[str, Any] = {}
    layout_summary: dict[str, Any] = {}
    pdf: Path | None = None
    if built is not None:
        build_summary = _compact_build(built)
        verification = built.get("verification")
        layout = verification.get("layout") if isinstance(verification, dict) else None
        if resolved_kind == "resume" and isinstance(layout, dict):
            layout_summary = _compact_layout(layout)
        if _compiled(built) and source.with_suffix(".pdf").is_file():
            pdf = source.with_suffix(".pdf")
    elif fmt in {"typ", "tex"}:
        build_summary = {"status": "skipped"}

    content = content_qa.check_material(
        text,
        kind=resolved_kind,
        fmt=fmt,
        requirements=context.get("requirements", []),
        job_description=context.get("posting", ""),
        evidence_corpus=_evidence_corpus(ws),
        company=context.get("company", ""),
        candidate_name=str(ws.profile_meta().get("name") or ""),
        max_chars=max_chars,
        config=settings,
    )
    if not isinstance(content, dict):
        content = {}

    extract = getattr(content_qa, "extract_material_text", None)
    plain = str(extract(text, fmt).get("plain") or "") if callable(extract) else text
    submission = submission_qa.check_submission(
        ws,
        source=source,
        plain=plain,
        kind=resolved_kind,
        job_id=context.get("job_id", ""),
        company=context.get("company", ""),
        requirements=context.get("requirements", []),
        pdf=pdf,
        settings=settings,
        raw=text,
    )
    submission_status = submission.pop("status", "pass")

    resume_qa = settings.get("resume_qa") if isinstance(settings.get("resume_qa"), dict) else {}
    build_failed = built is not None and not build_summary.get("ok")
    layout_failed = bool(layout_summary) and not layout_summary.get("ready")
    content_review = content.get("status") == "review" or submission_status != "pass"
    if build_failed or submission_status == "fail" or (layout_failed and bool(resume_qa.get("required", True))):
        status = "fail"
    elif content_review or layout_failed:
        status = "review"
    else:
        status = "pass"

    report = _prune(
        {
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "file": source.name,
            "kind": resolved_kind,
            "status": status,
            "source_sha256": source_sha256,
            "pdf_sha256": sha256_file(pdf) if pdf else "",
            "build": build_summary,
            "layout": layout_summary,
            "content": content,
            "submission": submission,
        }
    )
    atomic_write(qa_report_path(source), json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    return _prune(
        {
            "ok": True,
            "file": ws.relative(source),
            "kind": resolved_kind,
            "status": status,
            "pdf": ws.relative(pdf) if pdf else "",
            "build": build_summary,
            "layout": layout_summary,
            "content": content,
            "submission": submission,
            "next": _next_step(
                built=built,
                build_summary=build_summary,
                layout_summary=layout_summary,
                content_review=content_review,
                pdf=pdf,
                max_attempts=int(resume_qa.get("max_repair_iterations", 3)),
                submission_failed=submission_status == "fail",
            ),
        }
    )


def _locate(ws: Any, path: str, job_id: str) -> tuple[Path | None, dict[str, Any]]:
    text = str(path or "").strip()
    candidates: list[Path] = []
    if job_id and text and not Path(text).expanduser().is_absolute():
        try:
            candidates.append(ws.inside(ws.job_dir(job_id) / text))
        except ValueError:
            pass
    candidates.append(ws.inside(text))
    for candidate in candidates:
        if candidate.suffix.lower() == ".pdf":
            for suffix in _PDF_SOURCE_SUFFIXES:
                if candidate.with_suffix(suffix).is_file():
                    return candidate.with_suffix(suffix), {}
        elif candidate.is_file():
            return candidate, {}
    if any(candidate.suffix.lower() == ".pdf" and candidate.is_file() for candidate in candidates):
        return None, {"ok": False, "error": "Check runs on the source file (.typ, .tex, .md, .txt), not the PDF."}
    return None, {
        "ok": False,
        "error": f"File not found: {clip(ws.relative(candidates[0]), 200)}",
        "hint": "Pass a path inside the workspace, or job plus the file name.",
    }


def _job_context(ws: Any, source: Path, job_id: str) -> dict[str, Any]:
    owners: list[str] = []
    try:
        parts = source.relative_to(ws.jobs_dir.resolve()).parts
    except ValueError:
        parts = ()
    if len(parts) >= 2:
        owners.append(parts[0])
    if job_id and job_id not in owners:
        owners.append(job_id)
    for owner in owners:
        try:
            doc = ws.job_doc(owner)
        except KeyError:
            continue
        posting = section(doc.body, "Posting").strip()
        if re.fullmatch(r"_[^\n]*_", posting):
            posting = ""
        requirements = [
            line[2:].strip()
            for line in section(doc.body, "Requirements").splitlines()
            if line.startswith("- ") and line[2:].strip()
        ]
        return {
            "job_id": owner,
            "posting": posting,
            "requirements": requirements,
            "company": str(doc.meta.get("company") or ""),
        }
    return {}


def _evidence_corpus(ws: Any) -> str:
    bodies = [str(item.get("body") or "") for item in ws.evidence()]
    return ws.profile_text("profile") + "\n" + "\n".join(bodies)


def _compiled(built: dict[str, Any]) -> bool:
    return bool(built.get("rendered", built.get("ok")))


def _compact_build(built: dict[str, Any]) -> dict[str, Any]:
    verification = built.get("verification") if isinstance(built.get("verification"), dict) else {}
    compiled = _compiled(built)
    contamination = [clip(term, 80) for term in verification.get("contamination") or []]
    integrity = [
        clip(item, 80)
        for item in (verification.get("integrity_errors") or [] if compiled else [])
        if item != "contamination_detected"
    ]
    ok = compiled and not contamination and not integrity
    status = str(built.get("status") or "")
    if compiled:
        status = "compiled" if ok else "verification_failed"
    return _prune(
        {
            "ok": ok,
            "status": status,
            "compiler": Path(str(built.get("compiler") or "")).name,
            "pages": verification.get("pages"),
            "words": verification.get("word_count"),
            "error": "" if compiled else _build_error(built),
            "integrity_errors": integrity,
            "contamination": contamination,
        }
    )


def _build_error(built: dict[str, Any]) -> str:
    status = built.get("status")
    next_step = str(built.get("next_step") or "").strip()
    if status == "missing_compiler":
        names = ", ".join(str(name) for name in built.get("compiler_candidates") or []) or "none configured"
        return _tail(f"Compiler not found (looked for {names}). {next_step}".strip())
    output = str(built.get("stderr") or "").strip() or str(built.get("stdout") or "").strip()
    if status == "timeout":
        return _tail(f"{output}\nCompile timed out. {next_step}".strip())
    return _tail(output or next_step or f"Build failed: {status}")


def _tail(text: str) -> str:
    text = text.strip()
    if len(text) <= _BUILD_ERROR_CHARS:
        return text
    return "…" + text[-(_BUILD_ERROR_CHARS - 1) :]


def _compact_layout(layout: dict[str, Any]) -> dict[str, Any]:
    violations = [item for item in layout.get("violations") or [] if isinstance(item, dict)]
    errors_first = sorted(violations, key=lambda item: item.get("severity") != "error")
    steps = [item for item in layout.get("repair_plan") or [] if isinstance(item, dict)]
    metrics = layout.get("metrics") if isinstance(layout.get("metrics"), dict) else {}
    occupancy = metrics.get("page_occupancy") or []
    last_page = occupancy[-1] if occupancy and isinstance(occupancy[-1], dict) else {}
    return _prune(
        {
            "ready": bool(layout.get("ready")),
            "status": str(layout.get("status") or ""),
            "violations_total": len(violations),
            "violations": [_compact_violation(item) for item in errors_first[:_MAX_VIOLATIONS]],
            "repair_plan": [_compact_repair_step(item) for item in steps[:_MAX_REPAIR_STEPS]],
            "bottom_whitespace_in": last_page.get("bottom_whitespace_in"),
            "note": "" if violations or layout.get("ready") else clip(layout.get("next_step"), 200),
        }
    )


def _compact_violation(violation: dict[str, Any]) -> dict[str, Any]:
    text = next(
        (violation[key] for key in ("final_text", "next_text", "text", "section") if violation.get(key)),
        "",
    )
    previous = violation.get("previous_text") or ""
    item: dict[str, Any] = {
        "type": violation.get("type"),
        "severity": violation.get("severity"),
        "page": violation.get("page"),
        "text": clip(text, 120),
        "previous_text": clip(previous, 80) if previous != text else "",
    }
    for key in _VIOLATION_VALUE_KEYS:
        item[key] = violation.get(key)
    item["region"] = clip(violation.get("semantic_id"), 80)
    source_range = violation.get("source_range") if isinstance(violation.get("source_range"), dict) else {}
    item["line"] = source_range.get("line_start")
    if source_range.get("line_end") != source_range.get("line_start"):
        item["line_end"] = source_range.get("line_end")
    item["fix"] = clip(violation.get("recommended_action"), 160)
    return _prune(item)


def _compact_repair_step(step: dict[str, Any]) -> dict[str, Any]:
    targets = step.get("sections") or [
        target.get("final_text") for target in step.get("targets") or [] if isinstance(target, dict)
    ]
    return _prune(
        {
            "action": step.get("action"),
            "count": step.get("violation_count"),
            "controls": [clip(control, 40) for control in step.get("typst_controls") or []],
            "instruction": clip(step.get("instruction"), 200),
            "targets": [clip(target, 60) for target in targets[:_MAX_REPAIR_TARGETS] if target],
        }
    )


def _next_step(
    *,
    built: dict[str, Any] | None,
    build_summary: dict[str, Any],
    layout_summary: dict[str, Any],
    content_review: bool,
    pdf: Path | None,
    max_attempts: int,
    submission_failed: bool = False,
) -> str:
    if built is not None and not _compiled(built):
        if built.get("status") == "missing_compiler":
            return "The compiler is missing: tell the user what to install (see build.error), then re-run the check."
        return "Fix the build error in the source and re-run the check."
    if built is not None and not build_summary.get("ok"):
        return "Fix the PDF problems listed under build (integrity_errors, contamination) and re-run the check."
    if layout_summary and not layout_summary.get("ready"):
        if layout_summary.get("repair_plan"):
            action = "Apply the layout repair plan"
        elif layout_summary.get("violations"):
            action = "Fix the listed layout violations"
        else:
            action = "Resolve the problem in layout.note"
        also = " and repair the listed content findings" if content_review else ""
        return (
            f"{action}{also}, then re-run the check; "
            f"if it still fails after {max_attempts} attempts, stop and show the user what remains."
        )
    if submission_failed:
        return "Fix the errors under submission first: they would sink the application. Then re-run the check."
    if content_review:
        return "Repair the listed content findings, and anything under submission, then re-run the check."
    if pdf is not None:
        return "Clean. Tell the user the PDF path; mark the job ready with jobapps_track when they have reviewed it."
    if build_summary.get("status") == "skipped":
        return "Content is clean, but the PDF was not built: re-run the check with build enabled before review."
    return "Clean. Show the user the file; mark the job ready with jobapps_track when they have reviewed it."


def _prune(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None and value != "" and value != [] and value != {}}
