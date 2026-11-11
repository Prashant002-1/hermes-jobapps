from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any
from xml.etree import ElementTree


_BULLET_MARKERS = {"•", "◦", "‣", "▪"}
_DEFAULT_SECTION_TITLES = {
    "Summary",
    "Professional Summary",
    "Experience",
    "Work Experience",
    "Education",
    "Projects",
    "Selected Project",
    "Selected Projects",
    "Research",
    "Skills",
    "Technical Skills",
    "Certifications",
    "Publications",
    "Awards",
    "Leadership",
}


TYPST_QA_PRELUDE = """#let qa-region(kind, id, body) = context {
  layout(size => {
    let measured = measure(body, width: size.width)
    metadata((jobapps_qa: true, kind: kind, id: id, width: measured.width, height: measured.height))
    body
  })
}
"""


_TYPST_TELEMETRY_QUERY = (
    'query(metadata).filter(it => it.value.at("jobapps_qa", default: false))'
    ".map(it => (value: it.value, position: it.location().position()))"
)


def query_typst_telemetry(
    source_path: str | Path,
    *,
    compiler: str,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Query semantic QA regions emitted by an instrumented Typst source."""

    source = Path(source_path)
    command = [compiler, "eval", _TYPST_TELEMETRY_QUERY, "--in", str(source), "--format", "json"]
    try:
        completed = subprocess.run(
            command,
            cwd=str(source.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "regions": [],
            "command": command,
            "stderr": str(exc.stderr or "")[-2000:],
        }
    if completed.returncode != 0:
        return {
            "status": "query_failed",
            "regions": [],
            "command": command,
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
        }
    try:
        raw_regions = json.loads(completed.stdout)
        regions = [_normalize_typst_region(item) for item in raw_regions]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return {
            "status": "invalid_output",
            "regions": [],
            "command": command,
            "returncode": completed.returncode,
            "parse_error": str(exc),
        }
    return {
        "status": "collected" if regions else "not_instrumented",
        "regions": regions,
        "command": command,
        "returncode": completed.returncode,
        "stderr": completed.stderr[-2000:],
    }


def _normalize_typst_region(item: dict[str, Any]) -> dict[str, Any]:
    value = item["value"]
    position = item["position"]
    return {
        "id": str(value["id"]),
        "kind": str(value["kind"]),
        "page": int(position["page"]),
        "x_pt": _typst_pt(position["x"]),
        "y_pt": _typst_pt(position["y"]),
        "width_pt": _typst_pt(value["width"]),
        "height_pt": _typst_pt(value["height"]),
    }


def _typst_pt(value: Any) -> float:
    text = str(value).strip()
    if not text.endswith("pt"):
        raise ValueError(f"Expected Typst pt length, got {text!r}")
    return float(text[:-2])


def verify_resume_pdf(
    pdf_path: str | Path,
    *,
    config: dict[str, Any] | None = None,
    source_path: str | Path | None = None,
    typst_compiler: str | None = None,
    typst_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Extract final PDF geometry once and return machine-actionable resume QA."""

    pdf = Path(pdf_path)
    if not pdf.exists():
        return {
            "status": "missing_pdf",
            "ready": False,
            "pdf_path": str(pdf),
            "violations": [],
            "next_step": "Compile the PDF before running resume layout QA.",
        }

    config = config or {}
    settings = config.get("resume_qa", {}) if isinstance(config.get("resume_qa", {}), dict) else {}
    tool_paths = _tool_paths(config, settings)
    tool = _resolve_tool(str(settings.get("pdftotext", "pdftotext")), tool_paths)
    if tool is None:
        return {
            "status": "verification_unavailable",
            "ready": False,
            "pdf_path": str(pdf),
            "tool": None,
            "violations": [],
            "next_step": "Install Poppler pdftotext; layout QA cannot pass without final-PDF geometry.",
        }

    timeout = int(settings.get("timeout_seconds", 30))
    try:
        completed = subprocess.run(
            [tool, "-bbox-layout", str(pdf), "-"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "verification_timeout",
            "ready": False,
            "pdf_path": str(pdf),
            "tool": tool,
            "bbox_exit": None,
            "stderr": str(exc.stderr or "")[-2000:],
            "violations": [],
            "next_step": "Inspect the PDF or increase resume_qa.timeout_seconds.",
        }

    if completed.returncode != 0:
        return {
            "status": "extraction_failed",
            "ready": False,
            "pdf_path": str(pdf),
            "tool": tool,
            "bbox_exit": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "violations": [],
            "next_step": "Fix the PDF or Poppler extraction failure before review.",
        }
    telemetry: dict[str, Any] = {"status": "not_requested", "regions": []}
    if source_path is not None and typst_compiler is not None:
        telemetry = query_typst_telemetry(
            source_path,
            compiler=typst_compiler,
            timeout=timeout,
            env=typst_env,
        )
    analysis_settings = dict(settings)
    analysis_settings["semantic_regions"] = telemetry["regions"]
    try:
        report = analyze_bbox_layout(completed.stdout, config=analysis_settings)
    except ElementTree.ParseError as exc:
        return {
            "status": "invalid_bbox_output",
            "ready": False,
            "pdf_path": str(pdf),
            "tool": tool,
            "bbox_exit": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "parse_error": str(exc),
            "violations": [],
            "next_step": "Inspect pdftotext bbox output; no visual pass may be recorded.",
        }
    if telemetry["regions"]:
        _attach_semantic_targets(report["violations"], telemetry["regions"])
    if source_path is not None:
        source = Path(source_path)
        report["violations"].extend(_source_typography_violations(source, settings))
        report["ready"] = not report["violations"]
        report["status"] = "passed" if report["ready"] else "failed"
        _attach_source_ranges(report["violations"], source)
    report["repair_plan"] = _build_repair_plan(report["violations"])
    report.update(
        {
            "artifact": {
                "pdf_sha256": _sha256_file(pdf),
                "source_sha256": _sha256_file(Path(source_path)) if source_path is not None else "",
            },
            "pdf_path": str(pdf),
            "tool": tool,
            "bbox_exit": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "telemetry": telemetry,
        }
    )
    return report


@dataclass(frozen=True)
class TextLine:
    page: int
    block: int
    index: int
    x0: float
    y0: float
    x1: float
    y1: float
    words: tuple[str, ...]

    @property
    def text(self) -> str:
        return " ".join(self.words)

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def starts_bullet(self) -> bool:
        return bool(self.words) and self.words[0] in _BULLET_MARKERS


def analyze_bbox_layout(bbox_xml: str, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analyze Poppler ``pdftotext -bbox-layout`` output for resume defects."""

    settings = config or {}
    lines, pages = _parse_bbox_layout(bbox_xml)
    violations: list[dict[str, Any]] = []
    required_pages = int(settings.get("required_pages", 1))
    if len(pages) != required_pages:
        violations.append(
            {
                "type": "page_count",
                "severity": "error",
                "actual_pages": len(pages),
                "required_pages": required_pages,
                "repair_scope": "document_fit",
                "recommended_action": "Reduce content or spacing without shrinking below the approved typography floor.",
            }
        )
    if not lines:
        violations.append(
            {
                "type": "missing_exported_text",
                "severity": "error",
                "repair_scope": "pdf_integrity",
                "recommended_action": "Fix PDF text export before layout or readiness can pass.",
            }
        )

    expected_width = float(settings.get("page_width_pt", 612.0))
    expected_height = float(settings.get("page_height_pt", 792.0))
    page_tolerance = float(settings.get("page_size_tolerance_pt", 2.0))
    for page in pages:
        if abs(page["width"] - expected_width) <= page_tolerance and abs(page["height"] - expected_height) <= page_tolerance:
            continue
        violations.append(
            {
                "type": "page_size",
                "severity": "error",
                "page": int(page["number"]),
                "actual_width_pt": page["width"],
                "actual_height_pt": page["height"],
                "expected_width_pt": expected_width,
                "expected_height_pt": expected_height,
                "repair_scope": "page_setup",
            }
        )

    page_dimensions = {int(page["number"]): page for page in pages}
    bounds_tolerance = float(settings.get("bounds_tolerance_pt", 0.5))
    for line in lines:
        page = page_dimensions[line.page]
        if (
            line.x0 >= -bounds_tolerance
            and line.y0 >= -bounds_tolerance
            and line.x1 <= page["width"] + bounds_tolerance
            and line.y1 <= page["height"] + bounds_tolerance
        ):
            continue
        violations.append(
            {
                "type": "text_out_of_bounds",
                "severity": "error",
                "page": line.page,
                "text": line.text,
                "bounds": [line.x0, line.y0, line.x1, line.y1],
                "page_bounds": [0.0, 0.0, page["width"], page["height"]],
                "repair_scope": "page_setup",
            }
        )

    bullet_groups = _bullet_groups(lines)
    within_item_overlaps = [
        max(0.0, previous.y1 - current.y0)
        for group in bullet_groups
        for previous, current in zip(group, group[1:])
    ]
    normal_overlap = median(within_item_overlaps) if within_item_overlaps else 0.0
    within_item_steps = [
        current.y0 - previous.y0
        for group in bullet_groups
        for previous, current in zip(group, group[1:])
        if current.y0 > previous.y0
    ]
    normal_baseline_step = median(within_item_steps) if within_item_steps else 0.0
    leading_factor = float(settings.get("maximum_intra_item_leading_factor", 1.35))
    leading_delta = float(settings.get("minimum_intra_item_leading_delta_pt", 2.0))
    if normal_baseline_step:
        for group_number, group in enumerate(bullet_groups, start=1):
            for line_number, (previous, current) in enumerate(zip(group, group[1:]), start=2):
                step = current.y0 - previous.y0
                if step <= normal_baseline_step * leading_factor or step - normal_baseline_step <= leading_delta:
                    continue
                violations.append(
                    {
                        "type": "inconsistent_intra_item_leading",
                        "severity": "error",
                        "page": current.page,
                        "x_pt": current.x0,
                        "y_pt": current.y0,
                        "element_id": f"page-{current.page}-bullet-{group_number}",
                        "line_number_within_item": line_number,
                        "previous_text": previous.text,
                        "next_text": current.text,
                        "measured_baseline_step_pt": round(step, 3),
                        "expected_baseline_step_pt": round(normal_baseline_step, 3),
                        "leading_ratio": round(step / normal_baseline_step, 3),
                        "repair_scope": "shared_paragraph_style",
                        "recommended_action": "Correct paragraph leading or the responsible local spacer; do not move unrelated items.",
                    }
                )
    minimum_overlap = float(settings.get("minimum_collision_pt", 2.0))
    relative_factor = float(settings.get("collision_relative_factor", 2.0))
    collision_threshold = max(minimum_overlap, normal_overlap * relative_factor)

    groups_by_block: dict[tuple[int, int], list[list[TextLine]]] = {}
    for group in bullet_groups:
        first = group[0]
        groups_by_block.setdefault((first.page, first.block), []).append(group)
    for groups in groups_by_block.values():
        item_boundaries = [
            (previous_group[-1], current_group[0], current_group[0].y0 - previous_group[-1].y1)
            for previous_group, current_group in zip(groups, groups[1:])
            if min(previous_group[-1].x1, current_group[0].x1)
            - max(previous_group[-1].x0, current_group[0].x0)
            > 0
        ]
        minimum_gap = float(settings.get("minimum_text_gap_pt", 1.0))
        for previous, current, gap in item_boundaries:
            if gap < 0 or gap >= minimum_gap:
                continue
            violations.append(
                {
                    "type": "near_collision",
                    "severity": "error",
                    "page": current.page,
                    "x_pt": current.x0,
                    "y_pt": current.y0,
                    "previous_text": previous.text,
                    "next_text": current.text,
                    "measured_gap_pt": round(gap, 3),
                    "minimum_gap_pt": minimum_gap,
                    "repair_scope": "shared_list_style",
                }
            )
        ordinary_gaps = [gap for _, _, gap in item_boundaries if gap >= minimum_gap]
        expected_item_gap = median(ordinary_gaps) if ordinary_gaps else 0.0
        gap_factor = float(settings.get("maximum_inter_item_gap_factor", 1.8))
        gap_delta = float(settings.get("minimum_inter_item_gap_delta_pt", 2.0))
        if len(ordinary_gaps) >= 3 and expected_item_gap:
            for previous, current, gap in item_boundaries:
                if gap < minimum_gap:
                    continue
                too_large = gap > expected_item_gap * gap_factor and gap - expected_item_gap > gap_delta
                too_small = gap * gap_factor < expected_item_gap and expected_item_gap - gap > gap_delta
                if not too_large and not too_small:
                    continue
                violations.append(
                    {
                        "type": "inconsistent_inter_item_gap",
                        "severity": "warning",
                        "page": current.page,
                        "x_pt": current.x0,
                        "y_pt": current.y0,
                        "previous_text": previous.text,
                        "next_text": current.text,
                        "measured_gap_pt": round(gap, 3),
                        "expected_gap_pt": round(expected_item_gap, 3),
                        "direction": "too_large" if too_large else "too_small",
                        "repair_scope": "shared_list_style",
                    }
                )
        for previous_group, current_group in zip(groups, groups[1:]):
            previous = previous_group[-1]
            current = current_group[0]
            horizontal_overlap = min(previous.x1, current.x1) - max(previous.x0, current.x0)
            if horizontal_overlap <= 0:
                continue
            overlap = max(0.0, previous.y1 - current.y0)
            if overlap <= collision_threshold:
                continue
            violations.append(
                {
                    "type": "bullet_item_overlap",
                    "severity": "error",
                    "page": current.page,
                    "x_pt": current.x0,
                    "y_pt": current.y0,
                    "previous_text": previous.text,
                    "next_text": current.text,
                    "vertical_overlap_pt": round(overlap, 3),
                    "normal_wrapped_overlap_pt": round(normal_overlap, 3),
                    "repair_scope": "shared_list_style",
                }
            )

    bullet_line_indices = {line.index for group in bullet_groups for line in group}
    minimum_overlap_ratio = float(settings.get("minimum_collision_height_ratio", 0.2))
    for previous, current in zip(lines, lines[1:]):
        if previous.page != current.page or previous.block != current.block:
            continue
        if previous.index in bullet_line_indices or current.index in bullet_line_indices:
            continue
        horizontal_overlap = min(previous.x1, current.x1) - max(previous.x0, current.x0)
        overlap = max(0.0, previous.y1 - current.y0)
        overlap_ratio = overlap / max(1.0, min(previous.height, current.height))
        if horizontal_overlap <= 0 or overlap <= minimum_overlap or overlap_ratio <= minimum_overlap_ratio:
            continue
        violations.append(
            {
                "type": "text_line_collision",
                "severity": "error",
                "page": current.page,
                "x_pt": current.x0,
                "y_pt": current.y0,
                "previous_text": previous.text,
                "next_text": current.text,
                "vertical_overlap_pt": round(overlap, 3),
                "overlap_ratio": round(overlap_ratio, 3),
                "repair_scope": "shared_row_style",
                "recommended_action": "Increase the shared row leading or spacing token rather than patching individual rows.",
            }
        )

    # Poppler block boundaries are extraction hints, not collision boundaries.
    # Compare text rectangles globally within each page so separate blocks cannot
    # hide a real rendered overlap. Side-by-side headings remain valid because
    # their horizontal rectangles do not intersect.
    for index, previous in enumerate(lines):
        for current in lines[index + 1 :]:
            if current.page != previous.page:
                if current.page > previous.page:
                    break
                continue
            if current.block == previous.block:
                continue
            vertical_overlap = min(previous.y1, current.y1) - max(previous.y0, current.y0)
            if vertical_overlap <= collision_threshold:
                continue
            horizontal_overlap = min(previous.x1, current.x1) - max(previous.x0, current.x0)
            if horizontal_overlap <= 0:
                continue
            overlap_ratio = vertical_overlap / max(1.0, min(previous.height, current.height))
            if overlap_ratio <= minimum_overlap_ratio:
                continue
            violations.append(
                {
                    "type": "cross_block_text_collision",
                    "severity": "error",
                    "page": current.page,
                    "x_pt": max(previous.x0, current.x0),
                    "y_pt": max(previous.y0, current.y0),
                    "previous_text": previous.text,
                    "next_text": current.text,
                    "vertical_overlap_pt": round(vertical_overlap, 3),
                    "horizontal_overlap_pt": round(horizontal_overlap, 3),
                    "overlap_ratio": round(overlap_ratio, 3),
                    "repair_scope": "responsible_layout_regions",
                    "recommended_action": "Repair the two responsible layout regions; Poppler block separation does not make their overlap safe.",
                }
            )

    page_widths = {int(page["number"]): page["width"] for page in pages}
    short_line_max_words = int(settings.get("short_final_line_max_words", 2))
    short_line_max_width = float(settings.get("short_final_line_max_width_ratio", 0.25))
    right_margin = float(settings.get("right_margin_pt", 24.0))
    for group_number, group in enumerate(bullet_groups, start=1):
        if len(group) < 2:
            continue
        final = group[-1]
        available_width = max(1.0, page_widths[final.page] - final.x0 - right_margin)
        width_utilization = (final.x1 - final.x0) / available_width
        if len(final.words) > short_line_max_words or width_utilization > short_line_max_width:
            continue
        violations.append(
            {
                "type": "short_final_line",
                "severity": "warning",
                "page": final.page,
                "x_pt": final.x0,
                "y_pt": final.y0,
                "element_id": f"page-{final.page}-bullet-{group_number}",
                "final_text": final.text,
                "final_word_count": len(final.words),
                "width_utilization": round(width_utilization, 3),
                "repair_scope": "bullet_content",
                "recommended_action": "Shorten or rephrase this bullet enough to reclaim one line without changing its claims.",
            }
        )

    paragraph_left_tolerance = float(settings.get("paragraph_left_edge_tolerance_pt", 2.0))
    paragraph_groups: list[list[TextLine]] = []
    active_paragraph: list[TextLine] | None = None
    active_paragraph_key: tuple[int, int] | None = None
    for line in lines:
        if line.index in bullet_line_indices:
            active_paragraph = None
            active_paragraph_key = None
            continue
        key = (line.page, line.block)
        if (
            active_paragraph is not None
            and key == active_paragraph_key
            and abs(line.x0 - active_paragraph[-1].x0) <= paragraph_left_tolerance
        ):
            active_paragraph.append(line)
            continue
        active_paragraph = [line]
        active_paragraph_key = key
        paragraph_groups.append(active_paragraph)

    for group_number, group in enumerate(paragraph_groups, start=1):
        if len(group) < 2:
            continue
        final = group[-1]
        available_width = max(1.0, page_widths[final.page] - final.x0 - right_margin)
        width_utilization = (final.x1 - final.x0) / available_width
        if len(final.words) > short_line_max_words or width_utilization > short_line_max_width:
            continue
        violations.append(
            {
                "type": "short_final_line",
                "severity": "warning",
                "page": final.page,
                "x_pt": final.x0,
                "y_pt": final.y0,
                "element_id": f"page-{final.page}-paragraph-{group_number}",
                "final_text": final.text,
                "final_word_count": len(final.words),
                "width_utilization": round(width_utilization, 3),
                "repair_scope": "paragraph_content",
                "recommended_action": "Shorten or rephrase this paragraph enough to reclaim one line without changing its claims.",
            }
        )

    cross_block_max_step = float(settings.get("cross_block_continuation_max_step_pt", 18.0))
    for continuation_number, (previous, current) in enumerate(zip(lines, lines[1:]), start=1):
        baseline_step = current.y0 - previous.y0
        if (
            previous.page != current.page
            or previous.block == current.block
            or previous.index in bullet_line_indices
            or current.index in bullet_line_indices
            or abs(current.x0 - previous.x0) > paragraph_left_tolerance
            or baseline_step <= 0
            or baseline_step > cross_block_max_step
            or not previous.text.rstrip().endswith((",", ";"))
        ):
            continue
        available_width = max(1.0, page_widths[current.page] - current.x0 - right_margin)
        width_utilization = (current.x1 - current.x0) / available_width
        if len(current.words) > short_line_max_words or width_utilization > short_line_max_width:
            continue
        violations.append(
            {
                "type": "short_final_line",
                "severity": "warning",
                "page": current.page,
                "x_pt": current.x0,
                "y_pt": current.y0,
                "element_id": f"page-{current.page}-continuation-{continuation_number}",
                "final_text": current.text,
                "final_word_count": len(current.words),
                "width_utilization": round(width_utilization, 3),
                "repair_scope": "paragraph_content",
                "recommended_action": "Shorten or reorder this wrapped row so the continuation does not occupy a line by itself.",
            }
        )

    section_titles = set(settings.get("section_titles") or _DEFAULT_SECTION_TITLES)
    semantic_section_lines: dict[int, dict[str, Any]] = {}
    heading_tolerance = float(settings.get("semantic_heading_tolerance_pt", 4.0))
    for region in settings.get("semantic_regions") or []:
        if region.get("kind") != "section":
            continue
        candidates = [
            line
            for line in lines
            if line.page == region.get("page")
            and abs(line.y0 - float(region.get("y_pt", 0.0))) <= heading_tolerance
            and min(line.x1, float(region.get("x_pt", 0.0)) + float(region.get("width_pt", 0.0)))
            - max(line.x0, float(region.get("x_pt", 0.0)))
            > 0
        ]
        if candidates:
            heading = min(candidates, key=lambda line: abs(line.y0 - float(region.get("y_pt", 0.0))))
            semantic_section_lines[heading.index] = region
    section_line_indices = {
        line.index for line in lines if line.text in section_titles
    } | set(semantic_section_lines)
    hierarchy_ratio = float(settings.get("maximum_internal_to_section_gap_ratio", 0.8))
    hierarchy_metrics: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if line.index not in section_line_indices or index < 2:
            continue
        if not any(previous.index in section_line_indices and previous.page == line.page for previous in lines[:index]):
            continue
        previous = lines[index - 1]
        previous_internal = lines[index - 2]
        if previous.page != line.page or previous_internal.page != line.page:
            continue
        if previous_internal.index in section_line_indices:
            continue
        internal_gap = previous.y0 - previous_internal.y0
        section_gap = line.y0 - previous.y0
        if internal_gap <= 0 or section_gap <= 0:
            continue
        ratio = internal_gap / section_gap
        hierarchy_metrics.append(
            {
                "section": line.text,
                "internal_gap_pt": round(internal_gap, 3),
                "section_gap_pt": round(section_gap, 3),
                "gap_ratio": round(ratio, 3),
            }
        )
        if ratio <= hierarchy_ratio:
            continue
        violation = {
                "type": "weak_spacing_hierarchy",
                "severity": "warning",
                "page": line.page,
                "x_pt": line.x0,
                "y_pt": line.y0,
                "section": line.text,
                "previous_text": previous.text,
                "internal_gap_pt": round(internal_gap, 3),
                "section_gap_pt": round(section_gap, 3),
                "gap_ratio": round(ratio, 3),
                "repair_scope": "semantic_spacing_tokens",
                "recommended_action": "Reduce the internal detail gap or increase the section transition gap so hierarchy is unmistakable.",
            }
        semantic_region = semantic_section_lines.get(line.index)
        if semantic_region:
            violation["semantic_id"] = semantic_region["id"]
            violation["semantic_kind"] = semantic_region["kind"]
        violations.append(violation)

    page_occupancy = []
    target_bottom_whitespace_in = settings.get("bottom_whitespace_target_in")
    bottom_whitespace_tolerance_in = float(settings.get("bottom_whitespace_tolerance_in", 0.10))
    for page in pages:
        page_number = int(page["number"])
        page_lines = [line for line in lines if line.page == page_number]
        bottom = max((line.y1 for line in page_lines), default=0.0)
        bottom_whitespace_pt = max(0.0, page["height"] - bottom)
        bottom_whitespace_in = bottom_whitespace_pt / 72.0
        bottom_whitespace_ratio = bottom_whitespace_pt / page["height"]
        page_occupancy.append(
            {
                "page": page_number,
                "bottom_content_y_pt": round(bottom, 3),
                "bottom_whitespace_pt": round(bottom_whitespace_pt, 3),
                "bottom_whitespace_in": round(bottom_whitespace_in, 3),
                "bottom_whitespace_ratio": round(bottom_whitespace_ratio, 4),
            }
        )
        if target_bottom_whitespace_in is not None:
            target = float(target_bottom_whitespace_in)
            minimum = target - bottom_whitespace_tolerance_in
            maximum = target + bottom_whitespace_tolerance_in
            direction = (
                "too_small"
                if bottom_whitespace_in < minimum
                else "too_large"
                if bottom_whitespace_in > maximum
                else ""
            )
            if direction:
                action = (
                    "Reduce density or restore spacing until the rendered bottom whitespace falls inside the target band."
                    if direction == "too_small"
                    else "Add or restore grounded content until the rendered bottom whitespace falls inside the target band."
                )
                violations.append(
                    {
                        "type": "bottom_whitespace_out_of_range",
                        "severity": "error",
                        "page": page_number,
                        "direction": direction,
                        "measured_bottom_whitespace_pt": round(bottom_whitespace_pt, 3),
                        "measured_bottom_whitespace_in": round(bottom_whitespace_in, 3),
                        "target_bottom_whitespace_in": round(target, 3),
                        "tolerance_in": round(bottom_whitespace_tolerance_in, 3),
                        "accepted_range_in": [round(minimum, 3), round(maximum, 3)],
                        "repair_scope": "document_density",
                        "recommended_action": action,
                    }
                )

    return {
        "status": "failed" if violations else "passed",
        "ready": not violations,
        "pages": pages,
        "line_count": len(lines),
        "violations": violations,
        "repair_plan": _build_repair_plan(violations),
        "max_repair_iterations": int(settings.get("max_repair_iterations", 3)),
        "metrics": {
            "normal_wrapped_overlap_pt": round(normal_overlap, 3),
            "normal_wrapped_baseline_step_pt": round(normal_baseline_step, 3),
            "collision_threshold_pt": round(collision_threshold, 3),
            "section_spacing": hierarchy_metrics,
            "page_occupancy": page_occupancy,
        },
    }


def compare_layout_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    unavailable_statuses = {
        "verification_unavailable",
        "verification_timeout",
        "extraction_failed",
        "invalid_bbox_output",
        "missing_pdf",
    }
    after_status = str(after.get("status") or "")
    if after_status in unavailable_statuses or "violations" not in after:
        return {
            "resolved": [],
            "introduced": [
                {
                    "type": "verification_unavailable",
                    "severity": "error",
                    "status": after_status or "missing_report",
                }
            ],
            "persistent": list(before.get("violations") or []),
            "regression_free": False,
            "before_violation_count": len(before.get("violations") or []),
            "after_violation_count": 0,
        }
    before_by_key = _violations_by_key(before.get("violations", []))
    after_by_key = _violations_by_key(after.get("violations", []))
    resolved: list[dict[str, Any]] = []
    introduced: list[dict[str, Any]] = []
    persistent: list[dict[str, Any]] = []
    for key in before_by_key.keys() | after_by_key.keys():
        before_items = before_by_key.get(key, [])
        after_items = after_by_key.get(key, [])
        shared_count = min(len(before_items), len(after_items))
        persistent.extend(after_items[:shared_count])
        resolved.extend(before_items[shared_count:])
        introduced.extend(after_items[shared_count:])
    return {
        "resolved": resolved,
        "introduced": introduced,
        "persistent": persistent,
        "regression_free": not introduced,
        "before_violation_count": sum(len(items) for items in before_by_key.values()),
        "after_violation_count": sum(len(items) for items in after_by_key.values()),
    }


def evaluate_repair_progress(reports: list[dict[str, Any]], *, max_iterations: int = 3) -> dict[str, Any]:
    if not reports:
        return {"should_stop": True, "stop_reason": "missing_report", "comparison": None}
    latest = reports[-1]
    unavailable_statuses = {
        "verification_unavailable",
        "verification_timeout",
        "extraction_failed",
        "invalid_bbox_output",
        "missing_pdf",
    }
    if str(latest.get("status") or "") in unavailable_statuses or "violations" not in latest:
        comparison = compare_layout_reports(reports[-2], latest) if len(reports) >= 2 else None
        return {"should_stop": True, "stop_reason": "verification_unavailable", "comparison": comparison}
    if latest.get("ready"):
        comparison = compare_layout_reports(reports[-2], latest) if len(reports) >= 2 else None
        return {"should_stop": True, "stop_reason": "passed", "comparison": comparison}
    if len(reports) < 2:
        return {"should_stop": False, "stop_reason": "continue", "comparison": None}
    comparison = compare_layout_reports(reports[-2], latest)
    if comparison["introduced"]:
        return {"should_stop": True, "stop_reason": "regression_introduced", "comparison": comparison}
    if not comparison["resolved"] and _reports_equivalent(reports[-2], latest):
        return {"should_stop": True, "stop_reason": "no_measurable_progress", "comparison": comparison}
    if len(reports) - 1 >= max_iterations:
        return {"should_stop": True, "stop_reason": "max_iterations_reached", "comparison": comparison}
    return {"should_stop": False, "stop_reason": "continue", "comparison": comparison}


def _violation_key(violation: dict[str, Any]) -> str:
    target = (
        violation.get("semantic_id")
        or violation.get("element_id")
        or violation.get("section")
        or violation.get("next_text")
        or violation.get("final_text")
        or violation.get("text")
        or f"page-{violation.get('page', 'document')}"
    )
    return f"{violation.get('type')}|{target}"


def _violations_by_key(violations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for violation in violations:
        grouped.setdefault(_violation_key(violation), []).append(violation)
    return grouped


def _reports_equivalent(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return json.dumps(before.get("violations", []), sort_keys=True) == json.dumps(
        after.get("violations", []), sort_keys=True
    )


def _attach_semantic_targets(violations: list[dict[str, Any]], regions: list[dict[str, Any]]) -> None:
    for violation in violations:
        if violation.get("semantic_id"):
            continue
        if "x_pt" not in violation or "y_pt" not in violation:
            continue
        x = float(violation["x_pt"])
        y = float(violation["y_pt"])
        tolerance = 8.0
        candidates = [
            region
            for region in regions
            if region["page"] == violation.get("page")
            and _distance_to_interval(x, region["x_pt"], region["x_pt"] + region["width_pt"]) <= tolerance
            and _distance_to_interval(y, region["y_pt"], region["y_pt"] + region["height_pt"]) <= tolerance
        ]
        if not candidates:
            continue
        region = min(
            candidates,
            key=lambda item: (
                _distance_to_interval(x, item["x_pt"], item["x_pt"] + item["width_pt"]) ** 2
                + _distance_to_interval(y, item["y_pt"], item["y_pt"] + item["height_pt"]) ** 2,
                item["width_pt"] * item["height_pt"],
            ),
        )
        violation["semantic_id"] = region["id"]
        violation["semantic_kind"] = region["kind"]


def _distance_to_interval(value: float, lower: float, upper: float) -> float:
    return max(lower - value, 0.0, value - upper)


def _attach_source_ranges(violations: list[dict[str, Any]], source_path: Path) -> None:
    try:
        source_lines = source_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    normalized_lines = [_normalize_search_text(line) for line in source_lines]
    for violation in violations:
        candidates = [
            violation.get("semantic_id"),
            violation.get("section"),
            violation.get("next_text"),
            violation.get("final_text"),
            violation.get("text"),
            violation.get("previous_text"),
        ]
        line_number = next(
            (
                index
                for candidate in candidates
                if candidate
                for index in _matching_source_lines(_normalize_search_text(str(candidate)), normalized_lines)
            ),
            None,
        )
        if line_number is None:
            continue
        violation["source_range"] = {
            "path": str(source_path),
            "line_start": line_number + 1,
            "line_end": line_number + 1,
        }


def _source_typography_violations(source_path: Path, settings: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError:
        return [
            {
                "type": "source_unavailable",
                "severity": "error",
                "repair_scope": "source_integrity",
            }
        ]
    if "resume.with(" not in source:
        return []
    violations: list[dict[str, Any]] = []
    required_font = str(settings.get("required_body_font") or "")
    minimum_size = float(settings.get("minimum_body_font_size_pt", 10.0))
    font_match = re.search(r'(?m)^\s*font:\s*"([^"]+)"\s*,', source)
    size_match = re.search(r"(?m)^\s*font-size:\s*([0-9]+(?:\.[0-9]+)?)pt\s*,", source)
    actual_font = font_match.group(1) if font_match else ""
    actual_size = float(size_match.group(1)) if size_match else None
    if required_font and actual_font != required_font:
        violations.append(
            {
                "type": "body_font_mismatch",
                "severity": "error",
                "actual_font": actual_font or None,
                "required_font": required_font,
                "repair_scope": "shared_typography",
            }
        )
    if actual_size is None or actual_size < minimum_size:
        violations.append(
            {
                "type": "body_font_below_minimum",
                "severity": "error",
                "actual_size_pt": actual_size,
                "minimum_size_pt": minimum_size,
                "repair_scope": "shared_typography",
            }
        )
    return violations


def _normalize_search_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _matching_source_lines(candidate: str, normalized_lines: list[str]) -> list[int]:
    if not candidate:
        return []
    exact = [index for index, line in enumerate(normalized_lines) if candidate in line]
    if exact:
        return exact
    words = candidate.split()
    fragments = [" ".join(words[: min(6, len(words))]), " ".join(words[-min(6, len(words)) :])]
    return [
        index
        for index, line in enumerate(normalized_lines)
        if any(len(fragment.split()) >= 2 and fragment in line for fragment in fragments)
    ]


def _build_repair_plan(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    page_counts = [item for item in violations if item["type"] == "page_count"]
    if page_counts:
        plan.append(
            {
                "action": "refit_document",
                "repair_scope": "document_fit",
                "violation_count": len(page_counts),
                "instruction": "Use the measured defect targets to reclaim space; preserve the approved typography floor.",
            }
        )

    page_setup = [item for item in violations if item["type"] in {"page_size", "text_out_of_bounds"}]
    if page_setup:
        plan.append(
            {
                "action": "correct_page_setup",
                "repair_scope": "page_setup",
                "violation_count": len(page_setup),
                "typst_controls": ["page.paper", "page.margin"],
                "instruction": "Correct page size or margins before changing content.",
            }
        )

    list_spacing = [
        item
        for item in violations
        if item["type"] in {"bullet_item_overlap", "near_collision", "inconsistent_inter_item_gap"}
    ]
    if list_spacing:
        plan.append(
            {
                "action": "adjust_shared_list_style",
                "repair_scope": "shared_list_style",
                "violation_count": len(list_spacing),
                "typst_controls": ["list.spacing", "par.leading"],
                "instruction": "Change the shared list macro once, then recompile. Do not patch bullets individually.",
            }
        )

    intra_item_leading = [item for item in violations if item["type"] == "inconsistent_intra_item_leading"]
    if intra_item_leading:
        plan.append(
            {
                "action": "normalize_wrapped_line_leading",
                "repair_scope": "shared_paragraph_style",
                "violation_count": len(intra_item_leading),
                "typst_controls": ["par.leading", "local v()"],
                "instruction": "Normalize wrapped-line leading and remove only the responsible local spacer.",
            }
        )

    row_collisions = [
        item
        for item in violations
        if item["type"] in {"text_line_collision", "cross_block_text_collision"}
    ]
    if row_collisions:
        plan.append(
            {
                "action": "adjust_shared_row_style",
                "repair_scope": "shared_row_style",
                "violation_count": len(row_collisions),
                "typst_controls": ["par.leading", "block.spacing"],
                "instruction": "Increase the shared row rhythm once, then recompile.",
            }
        )

    hierarchy = [item for item in violations if item["type"] == "weak_spacing_hierarchy"]
    if hierarchy:
        plan.append(
            {
                "action": "separate_spacing_hierarchy",
                "repair_scope": "semantic_spacing_tokens",
                "violation_count": len(hierarchy),
                "sections": [item["section"] for item in hierarchy],
                "typst_controls": ["detail_gap", "section_gap"],
                "instruction": "Use distinct semantic spacing tokens; do not add another local negative v().",
            }
        )

    short_lines = [item for item in violations if item["type"] == "short_final_line"]
    if short_lines:
        plan.append(
            {
                "action": "rewrite_short_final_lines",
                "repair_scope": "bullet_content",
                "violation_count": len(short_lines),
                "targets": [
                    {
                        "element_id": item["element_id"],
                        "final_text": item["final_text"],
                        "final_word_count": item["final_word_count"],
                    }
                    for item in short_lines
                ],
                "instruction": "Ask the content repairer to reclaim one line while preserving truth and meaning, then recompile.",
            }
        )
    return plan


def _parse_bbox_layout(bbox_xml: str) -> tuple[list[TextLine], list[dict[str, float]]]:
    root = ElementTree.fromstring(bbox_xml)
    lines: list[TextLine] = []
    pages: list[dict[str, float]] = []
    line_index = 0
    for page_number, page_element in enumerate(root.findall(".//{*}page"), start=1):
        pages.append(
            {
                "number": page_number,
                "width": float(page_element.attrib["width"]),
                "height": float(page_element.attrib["height"]),
            }
        )
        for block_number, block in enumerate(page_element.findall(".//{*}block")):
            for line in block.findall("{*}line"):
                words = tuple("".join(word.itertext()).strip() for word in line.findall("{*}word"))
                words = tuple(word for word in words if word)
                lines.append(
                    TextLine(
                        page=page_number,
                        block=block_number,
                        index=line_index,
                        x0=float(line.attrib["xMin"]),
                        y0=float(line.attrib["yMin"]),
                        x1=float(line.attrib["xMax"]),
                        y1=float(line.attrib["yMax"]),
                        words=words,
                    )
                )
                line_index += 1
    return lines, pages


def _bullet_groups(lines: list[TextLine]) -> list[list[TextLine]]:
    groups: list[list[TextLine]] = []
    active: list[TextLine] | None = None
    active_key: tuple[int, int] | None = None
    for line in lines:
        key = (line.page, line.block)
        if line.starts_bullet:
            active = [line]
            active_key = key
            groups.append(active)
        elif active is not None and key == active_key:
            active.append(line)
        else:
            active = None
            active_key = None
    return groups


def _tool_paths(config: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for values in (
        settings.get("tool_paths", []),
        (config.get("typst") or {}).get("compiler_paths", []),
        (config.get("latex") or {}).get("compiler_paths", []),
        os.environ.get("PATH", "").split(os.pathsep),
    ):
        if isinstance(values, str):
            values = [values]
        for value in values:
            path = str(Path(value).expanduser())
            if path and path not in paths:
                paths.append(path)
    return paths


def _resolve_tool(name: str, search_paths: list[str]) -> str | None:
    candidate = Path(name).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return shutil.which(name, path=os.pathsep.join(search_paths))


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
