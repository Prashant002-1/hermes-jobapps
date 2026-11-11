from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import hermes_jobapps
from hermes_jobapps.build import _pdf_integrity_errors, compile_typst_to_pdf
from hermes_jobapps.resume_qa import (
    TYPST_QA_PRELUDE,
    analyze_bbox_layout,
    compare_layout_reports,
    evaluate_repair_progress,
    query_typst_telemetry,
    verify_resume_pdf,
)


RESUME_FIXTURE = (
    '#import "@preview/simple-technical-resume:0.1.1": *\n\n'
    + TYPST_QA_PRELUDE
    + """
#show: resume.with(
  paper: "us-letter",
  top-margin: 0.32in,
  bottom-margin: 0.18in,
  left-margin: 0.42in,
  right-margin: 0.42in,
  font: "Libertinus Serif",
  font-size: 10pt,
  personal-info-font-size: 9.3pt,
  author-position: center,
  personal-info-position: center,
  author-name: "Jordan Example",
  email: "jordan@example.com",
)

#qa-region("section", "unusual-field-work-1")[
#custom-title("Unusual Field Work")[
  - #qa-region("bullet", "unusual-field-work-1-bullet-1")[First result]
  - #qa-region("bullet", "unusual-field-work-1-bullet-2")[Second result]
]
#v(0.40em)
]
#qa-region("section", "selected-research-2")[
#custom-title("Selected Research")[
  - #qa-region("bullet", "selected-research-2-bullet-1")[Research result]
]
#v(0.40em)
]
"""
)

ONE_LINE_BBOX = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow><block>
<line xMin="24" yMin="10" xMax="300" yMax="24"><word xMin="24" yMin="10" xMax="100" yMax="24">Resume</word></line>
</block></flow></page></doc></body></html>"""


def default_settings() -> dict:
    path = Path(hermes_jobapps.__file__).parent / "resources" / "defaults.json"
    return json.loads(path.read_text())


def write_fake_pdftotext(root: Path, bbox: str) -> None:
    pdftotext = root / "pdftotext"
    pdftotext.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"print({bbox!r} if '-bbox-layout' in sys.argv else 'Resume words')\n",
        encoding="utf-8",
    )
    pdftotext.chmod(0o755)


def write_fake_toolchain(root: Path, bbox: str) -> dict:
    typst = root / "typst"
    typst.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "if sys.argv[1] == 'compile':\n"
        "    pathlib.Path(sys.argv[-1]).write_bytes(b'%PDF-1.4 fake')\n"
        "else:\n"
        "    print('[]')\n",
        encoding="utf-8",
    )
    typst.chmod(0o755)
    pdfinfo = root / "pdfinfo"
    pdfinfo.write_text("#!/bin/sh\nprintf 'Pages:           1\\n'\n", encoding="utf-8")
    pdfinfo.chmod(0o755)
    write_fake_pdftotext(root, bbox)
    return {
        "typst": {"compiler_order": ["typst"], "compiler_paths": [str(root)], "timeout_seconds": 5},
        "latex": {"compiler_paths": [str(root)], "timeout_seconds": 5},
        "resume_qa": {"tool_paths": [str(root)], "required": True, "timeout_seconds": 5},
    }


def package_unavailable(stderr: str) -> bool:
    return "@preview" in stderr or "package" in stderr.lower()


class ResumeGeometryTests(unittest.TestCase):
    def test_default_config_enforces_deterministic_resume_qa(self) -> None:
        config = default_settings()

        self.assertTrue(config["resume_qa"]["required"])
        self.assertEqual(config["resume_qa"]["required_pages"], 1)
        self.assertEqual(config["resume_qa"]["required_body_font"], "")
        self.assertEqual(config["resume_qa"]["minimum_body_font_size_pt"], 10)
        self.assertEqual(config["resume_qa"]["max_repair_iterations"], 3)
        self.assertEqual(config["resume_qa"]["page_width_pt"], 612)
        self.assertEqual(config["resume_qa"]["page_height_pt"], 792)

    @unittest.skipUnless(shutil.which("typst"), "Typst is not installed")
    def test_instrumented_resume_reports_sections_and_bullets_without_fixed_section_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "resume.typ"
            source.write_text(RESUME_FIXTURE, encoding="utf-8")

            result = query_typst_telemetry(source, compiler=shutil.which("typst") or "typst", timeout=30)

        if result["status"] == "query_failed" and package_unavailable(result.get("stderr", "")):
            self.skipTest("The Typst resume package is not available offline")
        self.assertEqual(result["status"], "collected", result)
        regions = {(region["kind"], region["id"]) for region in result["regions"]}
        self.assertEqual(
            regions,
            {
                ("section", "unusual-field-work-1"),
                ("bullet", "unusual-field-work-1-bullet-1"),
                ("bullet", "unusual-field-work-1-bullet-2"),
                ("section", "selected-research-2"),
                ("bullet", "selected-research-2-bullet-1"),
            },
        )
        self.assertTrue(all(region["page"] == 1 and region["height_pt"] > 0 for region in result["regions"]))

    def _source_violations(self, source_text: str, resume_qa: dict) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdf = root / "resume.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            source = root / "resume.typ"
            source.write_text(source_text, encoding="utf-8")
            write_fake_pdftotext(root, ONE_LINE_BBOX)

            report = verify_resume_pdf(
                pdf,
                config={"resume_qa": {"tool_paths": [str(root)], "timeout_seconds": 5, **resume_qa}},
                source_path=source,
            )

        self.assertIn(report["status"], {"passed", "failed"}, report)
        return report["violations"]

    def test_required_body_font_is_enforced_when_configured(self) -> None:
        mismatched = self._source_violations(RESUME_FIXTURE, {"required_body_font": "Atkinson Hyperlegible"})
        matching = self._source_violations(RESUME_FIXTURE, {"required_body_font": "Libertinus Serif"})

        mismatch = next(item for item in mismatched if item["type"] == "body_font_mismatch")
        self.assertEqual(mismatch["actual_font"], "Libertinus Serif")
        self.assertEqual(mismatch["required_font"], "Atkinson Hyperlegible")
        self.assertEqual(mismatch["repair_scope"], "shared_typography")
        self.assertEqual(matching, [])

    def test_empty_required_body_font_skips_font_check_but_keeps_minimum_size(self) -> None:
        small = RESUME_FIXTURE.replace("  font-size: 10pt,", "  font-size: 9pt,")
        self.assertNotEqual(small, RESUME_FIXTURE)

        for resume_qa in ({"required_body_font": ""}, {}, default_settings()["resume_qa"]):
            with self.subTest(resume_qa=sorted(resume_qa)):
                settings = {key: value for key, value in resume_qa.items() if key != "bottom_whitespace_target_in"}
                self.assertEqual(self._source_violations(RESUME_FIXTURE, settings), [])
                types = [item["type"] for item in self._source_violations(small, settings)]
                self.assertEqual(types, ["body_font_below_minimum"])

    def test_reports_inter_item_overlap_relative_to_normal_wrapped_lines(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block xMin="24" yMin="10" xMax="588" yMax="58">
          <line xMin="30" yMin="10" xMax="560" yMax="24"><word xMin="30" yMin="10" xMax="35" yMax="24">•</word><word xMin="40" yMin="10" xMax="90" yMax="24">First</word></line>
          <line xMin="40" yMin="23" xMax="520" yMax="37"><word xMin="40" yMin="23" xMax="120" yMax="37">continuation</word></line>
          <line xMin="30" yMin="31" xMax="550" yMax="45"><word xMin="30" yMin="31" xMax="35" yMax="45">•</word><word xMin="40" yMin="31" xMax="100" yMax="45">Second</word></line>
          <line xMin="40" yMin="44" xMax="500" yMax="58"><word xMin="40" yMin="44" xMax="130" yMax="58">continuation</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        overlap = [item for item in report["violations"] if item["type"] == "bullet_item_overlap"]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0]["vertical_overlap_pt"], 6.0)
        self.assertEqual(overlap[0]["previous_text"], "continuation")
        self.assertEqual(overlap[0]["next_text"], "• Second")
        self.assertFalse(
            any(
                item["previous_text"] == "• First" and item["next_text"] == "continuation"
                for item in report["violations"]
            )
        )

    def test_reports_abnormal_leading_inside_a_wrapped_bullet(self) -> None:
        bbox = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow><block>
        <line xMin="30" yMin="10" xMax="560" yMax="20"><word xMin="30" yMin="10" xMax="35" yMax="20">•</word><word xMin="40" yMin="10" xMax="90" yMax="20">First</word></line>
        <line xMin="40" yMin="22" xMax="520" yMax="32"><word xMin="40" yMin="22" xMax="120" yMax="32">normal</word></line>
        <line xMin="40" yMin="34" xMax="500" yMax="44"><word xMin="40" yMin="34" xMax="120" yMax="44">normal</word></line>
        <line xMin="30" yMin="50" xMax="560" yMax="60"><word xMin="30" yMin="50" xMax="35" yMax="60">•</word><word xMin="40" yMin="50" xMax="100" yMax="60">Second</word></line>
        <line xMin="40" yMin="62" xMax="520" yMax="72"><word xMin="40" yMin="62" xMax="120" yMax="72">normal</word></line>
        <line xMin="40" yMin="80" xMax="500" yMax="90"><word xMin="40" yMin="80" xMax="140" yMax="90">too-far</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        violation = next(item for item in report["violations"] if item["type"] == "inconsistent_intra_item_leading")
        self.assertEqual(violation["measured_baseline_step_pt"], 18.0)
        self.assertEqual(violation["expected_baseline_step_pt"], 12.0)
        self.assertEqual(violation["line_number_within_item"], 3)

    def test_reports_inconsistent_inter_item_gap_without_overlap(self) -> None:
        bbox = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow><block>
        <line xMin="30" yMin="10" xMax="560" yMax="20"><word xMin="30" yMin="10" xMax="35" yMax="20">•</word><word xMin="40" yMin="10" xMax="90" yMax="20">One</word></line>
        <line xMin="30" yMin="24" xMax="560" yMax="34"><word xMin="30" yMin="24" xMax="35" yMax="34">•</word><word xMin="40" yMin="24" xMax="90" yMax="34">Two</word></line>
        <line xMin="30" yMin="38" xMax="560" yMax="48"><word xMin="30" yMin="38" xMax="35" yMax="48">•</word><word xMin="40" yMin="38" xMax="100" yMax="48">Three</word></line>
        <line xMin="30" yMin="60" xMax="560" yMax="70"><word xMin="30" yMin="60" xMax="35" yMax="70">•</word><word xMin="40" yMin="60" xMax="90" yMax="70">Four</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        violation = next(item for item in report["violations"] if item["type"] == "inconsistent_inter_item_gap")
        self.assertEqual(violation["measured_gap_pt"], 12.0)
        self.assertEqual(violation["expected_gap_pt"], 4.0)
        self.assertEqual(violation["direction"], "too_large")

    def test_reports_near_collision_before_boxes_overlap(self) -> None:
        bbox = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow><block>
        <line xMin="30" yMin="10" xMax="560" yMax="20"><word xMin="30" yMin="10" xMax="35" yMax="20">•</word><word xMin="40" yMin="10" xMax="90" yMax="20">One</word></line>
        <line xMin="30" yMin="20.5" xMax="560" yMax="30.5"><word xMin="30" yMin="20.5" xMax="35" yMax="30.5">•</word><word xMin="40" yMin="20.5" xMax="90" yMax="30.5">Two</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        violation = next(item for item in report["violations"] if item["type"] == "near_collision")
        self.assertEqual(violation["measured_gap_pt"], 0.5)
        self.assertEqual(violation["minimum_gap_pt"], 1.0)

    def test_side_by_side_bullets_do_not_report_vertical_collision(self) -> None:
        bbox = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow><block>
        <line xMin="30" yMin="10" xMax="250" yMax="24"><word xMin="30" yMin="10" xMax="35" yMax="24">•</word><word xMin="40" yMin="10" xMax="90" yMax="24">Left</word></line>
        <line xMin="330" yMin="11" xMax="560" yMax="25"><word xMin="330" yMin="11" xMax="335" yMax="25">•</word><word xMin="340" yMin="11" xMax="400" yMax="25">Right</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        self.assertFalse(any(item["type"] in {"bullet_item_overlap", "near_collision"} for item in report["violations"]))

    def test_compares_repairs_and_stops_on_regression_or_no_progress(self) -> None:
        before = {
            "ready": False,
            "violations": [
                {"type": "bullet_item_overlap", "semantic_id": "experience-1", "severity": "error", "vertical_overlap_pt": 5.0},
                {"type": "short_final_line", "element_id": "bullet-2", "severity": "warning", "final_word_count": 2},
            ],
        }
        after = {
            "ready": False,
            "violations": [
                {"type": "short_final_line", "element_id": "bullet-2", "severity": "warning", "final_word_count": 2},
                {"type": "weak_spacing_hierarchy", "section": "Skills", "severity": "warning", "gap_ratio": 0.9},
            ],
        }

        comparison = compare_layout_reports(before, after)
        regression = evaluate_repair_progress([before, after], max_iterations=3)
        no_progress = evaluate_repair_progress([before, before], max_iterations=3)

        self.assertEqual([item["type"] for item in comparison["resolved"]], ["bullet_item_overlap"])
        self.assertEqual([item["type"] for item in comparison["introduced"]], ["weak_spacing_hierarchy"])
        self.assertEqual([item["type"] for item in comparison["persistent"]], ["short_final_line"])
        self.assertFalse(comparison["regression_free"])
        self.assertTrue(regression["should_stop"])
        self.assertEqual(regression["stop_reason"], "regression_introduced")
        self.assertTrue(no_progress["should_stop"])
        self.assertEqual(no_progress["stop_reason"], "no_measurable_progress")

    def test_reports_short_final_line_in_wrapped_bullet(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block xMin="24" yMin="10" xMax="588" yMax="37">
          <line xMin="30" yMin="10" xMax="570" yMax="24"><word xMin="30" yMin="10" xMax="35" yMax="24">•</word><word xMin="40" yMin="10" xMax="90" yMax="24">Built</word></line>
          <line xMin="40" yMin="23" xMax="140" yMax="37"><word xMin="40" yMin="23" xMax="100" yMax="37">data-quality</word><word xMin="105" yMin="23" xMax="140" yMax="37">checks.</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        short_lines = [item for item in report["violations"] if item["type"] == "short_final_line"]
        self.assertEqual(len(short_lines), 1)
        self.assertEqual(short_lines[0]["final_text"], "data-quality checks.")
        self.assertEqual(short_lines[0]["final_word_count"], 2)
        self.assertLess(short_lines[0]["width_utilization"], 0.2)
        self.assertEqual(short_lines[0]["repair_scope"], "bullet_content")

    def test_reports_short_final_line_in_wrapped_paragraph(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block xMin="24" yMin="10" xMax="588" yMax="52">
          <line xMin="24" yMin="10" xMax="570" yMax="24"><word xMin="24" yMin="10" xMax="90" yMax="24">Software</word><word xMin="95" yMin="10" xMax="150" yMax="24">engineer</word></line>
          <line xMin="24" yMin="23" xMax="560" yMax="37"><word xMin="24" yMin="23" xMax="90" yMax="37">Portfolio</word><word xMin="95" yMin="23" xMax="140" yMax="37">shows</word></line>
          <line xMin="24" yMin="36" xMax="90" yMax="50"><word xMin="24" yMin="36" xMax="90" yMax="50">transition.</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        short_lines = [item for item in report["violations"] if item["type"] == "short_final_line"]
        self.assertEqual(len(short_lines), 1)
        self.assertEqual(short_lines[0]["final_text"], "transition.")
        self.assertEqual(short_lines[0]["final_word_count"], 1)
        self.assertLess(short_lines[0]["width_utilization"], 0.2)
        self.assertEqual(short_lines[0]["repair_scope"], "paragraph_content")

    def test_reports_short_continuation_line_split_across_blocks(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow>
          <block><line xMin="24" yMin="10" xMax="570" yMax="24"><word xMin="24" yMin="10" xMax="150" yMax="24">Applications</word><word xMin="155" yMin="10" xMax="570" yMax="24">PostgreSQL,</word></line></block>
          <block><line xMin="24" yMin="23" xMax="80" yMax="37"><word xMin="24" yMin="23" xMax="80" yMax="37">Drizzle</word></line></block>
        </flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        short_lines = [item for item in report["violations"] if item["type"] == "short_final_line"]
        self.assertEqual(len(short_lines), 1)
        self.assertEqual(short_lines[0]["final_text"], "Drizzle")
        self.assertEqual(short_lines[0]["repair_scope"], "paragraph_content")

    def test_reports_bottom_whitespace_above_target_band(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block>
          <line xMin="24" yMin="716" xMax="300" yMax="730"><word xMin="24" yMin="716" xMax="100" yMax="730">Northstar</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(
            bbox,
            config={"bottom_whitespace_target_in": 0.65, "bottom_whitespace_tolerance_in": 0.10},
        )

        violations = [item for item in report["violations"] if item["type"] == "bottom_whitespace_out_of_range"]
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["direction"], "too_large")
        self.assertAlmostEqual(violations[0]["measured_bottom_whitespace_in"], 0.861, places=3)
        self.assertEqual(violations[0]["repair_scope"], "document_density")

    def test_reports_bottom_whitespace_below_target_band(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block>
          <line xMin="24" yMin="746" xMax="300" yMax="760"><word xMin="24" yMin="746" xMax="100" yMax="760">Northstar</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(
            bbox,
            config={"bottom_whitespace_target_in": 0.65, "bottom_whitespace_tolerance_in": 0.10},
        )

        violations = [item for item in report["violations"] if item["type"] == "bottom_whitespace_out_of_range"]
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["direction"], "too_small")
        self.assertAlmostEqual(violations[0]["measured_bottom_whitespace_in"], 0.444, places=3)
        self.assertEqual(violations[0]["repair_scope"], "document_density")

    def test_accepts_bottom_whitespace_inside_target_band(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block>
          <line xMin="24" yMin="731.2" xMax="300" yMax="745.2"><word xMin="24" yMin="731.2" xMax="100" yMax="745.2">Northstar</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(
            bbox,
            config={"bottom_whitespace_target_in": 0.65, "bottom_whitespace_tolerance_in": 0.10},
        )

        violations = [item for item in report["violations"] if item["type"] == "bottom_whitespace_out_of_range"]
        self.assertEqual(violations, [])
        self.assertEqual(report["metrics"]["page_occupancy"][0]["bottom_whitespace_in"], 0.65)

    def test_reports_internal_spacing_that_matches_a_section_transition(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow>
          <block><line xMin="24" yMin="10" xMax="120" yMax="27"><word xMin="24" yMin="10" xMax="120" yMax="27">Education</word></line></block>
          <block>
            <line xMin="24" yMin="35" xMax="300" yMax="49"><word xMin="24" yMin="35" xMax="110" yMax="49">College</word></line>
            <line xMin="24" yMin="49" xMax="330" yMax="63"><word xMin="24" yMin="49" xMax="110" yMax="63">Degree</word></line>
            <line xMin="24" yMin="68" xMax="350" yMax="82"><word xMin="24" yMin="68" xMax="150" yMax="82">Recognitions</word></line>
          </block>
          <block><line xMin="24" yMin="89.5" xMax="180" yMax="106.5"><word xMin="24" yMin="89.5" xMax="180" yMax="106.5">Selected Project</word></line></block>
        </flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        hierarchy = [item for item in report["violations"] if item["type"] == "weak_spacing_hierarchy"]
        self.assertEqual(len(hierarchy), 1)
        self.assertEqual(hierarchy[0]["section"], "Selected Project")
        self.assertEqual(hierarchy[0]["internal_gap_pt"], 19.0)
        self.assertEqual(hierarchy[0]["section_gap_pt"], 21.5)
        self.assertGreater(hierarchy[0]["gap_ratio"], 0.8)
        self.assertEqual(hierarchy[0]["repair_scope"], "semantic_spacing_tokens")

    def test_spacing_hierarchy_skips_one_item_preceding_section(self) -> None:
        bbox = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow>
        <block><line xMin="30" yMin="90" xMax="120" yMax="104"><word xMin="30" yMin="90" xMax="120" yMax="104">Education</word></line></block>
        <block><line xMin="30" yMin="110" xMax="500" yMax="124"><word xMin="30" yMin="110" xMax="500" yMax="124">Bachelor of Science</word></line></block>
        <block><line xMin="30" yMin="126" xMax="160" yMax="140"><word xMin="30" yMin="126" xMax="160" yMax="140">Technical Skills</word></line></block>
        </flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox, config={"section_titles": ["Education", "Technical Skills"]})

        self.assertFalse(any(item["type"] == "weak_spacing_hierarchy" for item in report["violations"]))

    def test_semantic_regions_enable_hierarchy_checks_for_custom_section_titles(self) -> None:
        bbox = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow>
        <block><line xMin="30" yMin="70" xMax="180" yMax="84"><word xMin="30" yMin="70" xMax="180" yMax="84">Unusual Field Work</word></line></block>
        <block><line xMin="40" yMin="90" xMax="500" yMax="104"><word xMin="40" yMin="90" xMax="500" yMax="104">First result</word></line></block>
        <block><line xMin="40" yMin="106" xMax="500" yMax="120"><word xMin="40" yMin="106" xMax="500" yMax="120">Second result</word></line></block>
        <block><line xMin="30" yMin="122" xMax="180" yMax="136"><word xMin="30" yMin="122" xMax="180" yMax="136">Selected Research</word></line></block>
        </flow></page></doc></body></html>"""
        regions = [
            {"id": "unusual-field-work-1", "kind": "section", "page": 1, "x_pt": 30.0, "y_pt": 70.0, "width_pt": 550.0, "height_pt": 50.0},
            {"id": "selected-research-2", "kind": "section", "page": 1, "x_pt": 30.0, "y_pt": 122.0, "width_pt": 550.0, "height_pt": 30.0},
        ]

        report = analyze_bbox_layout(bbox, config={"semantic_regions": regions})
        violation = next(item for item in report["violations"] if item["type"] == "weak_spacing_hierarchy")

        self.assertEqual(violation["semantic_id"], "selected-research-2")
        self.assertEqual(violation["section"], "Selected Research")

    def test_pdf_integrity_gate_rejects_empty_or_contaminated_export(self) -> None:
        errors = _pdf_integrity_errors(
            {
                "status": "checked",
                "pdfinfo_exit": 0,
                "pdftotext_exit": 0,
                "pages": 1,
                "word_count": 0,
                "contamination": ["review_status"],
            },
            {"required_pages": 1, "minimum_exported_words": 1},
        )

        self.assertIn("word_count:0", errors)
        self.assertIn("contamination_detected", errors)

    def test_reports_tightly_packed_non_bullet_rows(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow>
          <block>
            <line xMin="24" yMin="10" xMax="400" yMax="24"><word xMin="24" yMin="10" xMax="90" yMax="24">Languages:</word></line>
            <line xMin="24" yMin="21" xMax="420" yMax="35"><word xMin="24" yMin="21" xMax="110" yMax="35">Frameworks:</word></line>
            <line xMin="24" yMin="32" xMax="410" yMax="46"><word xMin="24" yMin="32" xMax="80" yMax="46">Cloud:</word></line>
          </block>
        </flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        collisions = [item for item in report["violations"] if item["type"] == "text_line_collision"]
        self.assertEqual(len(collisions), 2)
        self.assertEqual(collisions[0]["vertical_overlap_pt"], 3.0)
        self.assertGreater(collisions[0]["overlap_ratio"], 0.2)
        self.assertEqual(collisions[0]["repair_scope"], "shared_row_style")

    def test_reports_collision_between_separate_poppler_blocks(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow>
          <block><line xMin="30" yMin="10" xMax="400" yMax="24"><word xMin="30" yMin="10" xMax="90" yMax="24">First block</word></line></block>
          <block><line xMin="30" yMin="17" xMax="410" yMax="31"><word xMin="30" yMin="17" xMax="100" yMax="31">Second block</word></line></block>
        </flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        collisions = [item for item in report["violations"] if item["type"] == "cross_block_text_collision"]
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]["vertical_overlap_pt"], 7.0)
        self.assertGreater(collisions[0]["horizontal_overlap_pt"], 300.0)
        self.assertEqual(collisions[0]["repair_scope"], "responsible_layout_regions")

    def test_verify_resume_pdf_runs_bbox_extraction_and_returns_diagnostics(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block>
          <line xMin="30" yMin="10" xMax="560" yMax="24"><word xMin="30" yMin="10" xMax="35" yMax="24">•</word><word xMin="40" yMin="10" xMax="90" yMax="24">First</word></line>
          <line xMin="40" yMin="23" xMax="520" yMax="37"><word xMin="40" yMin="23" xMax="120" yMax="37">continuation</word></line>
          <line xMin="30" yMin="31" xMax="550" yMax="45"><word xMin="30" yMin="31" xMax="35" yMax="45">•</word><word xMin="40" yMin="31" xMax="100" yMax="45">Second</word></line>
        </block></flow></page></doc></body></html>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdf = root / "resume.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            source = root / "resume.typ"
            source.write_text("#compact[First continuation]\n#compact[Second]\n", encoding="utf-8")
            pdftotext = root / "pdftotext"
            pdftotext.write_text(
                "#!/usr/bin/env python3\n"
                f"print({bbox!r})\n",
                encoding="utf-8",
            )
            pdftotext.chmod(0o755)
            typst = root / "typst"
            typst.write_text(
                "#!/usr/bin/env python3\n"
                "print('[{\"value\":{\"jobapps_qa\":true,\"kind\":\"experience\",\"id\":\"northstar\",\"width\":\"560pt\",\"height\":\"60pt\"},\"position\":{\"page\":1,\"x\":\"24pt\",\"y\":\"0pt\"}}]')\n",
                encoding="utf-8",
            )
            typst.chmod(0o755)

            report = verify_resume_pdf(
                pdf,
                config={"resume_qa": {"tool_paths": [str(root)], "timeout_seconds": 5}},
                source_path=source,
                typst_compiler=str(typst),
            )

            expected_source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            expected_pdf_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()

        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["ready"])
        self.assertEqual(report["bbox_exit"], 0)
        self.assertEqual(Path(report["tool"]).name, "pdftotext")
        overlap = next(item for item in report["violations"] if item["type"] == "bullet_item_overlap")
        self.assertEqual(report["telemetry"]["status"], "collected")
        self.assertEqual(overlap["semantic_id"], "northstar")
        self.assertEqual(overlap["semantic_kind"], "experience")
        self.assertEqual(overlap["source_range"]["line_start"], 2)
        self.assertEqual(report["artifact"]["source_sha256"], expected_source_hash)
        self.assertEqual(report["artifact"]["pdf_sha256"], expected_pdf_hash)

    def test_report_comparison_preserves_duplicate_violation_instances(self) -> None:
        duplicate = {
            "type": "text_line_collision",
            "semantic_id": "skills",
            "previous_text": "Languages",
            "next_text": "Frameworks",
        }
        before = {"ready": False, "violations": [dict(duplicate), dict(duplicate)]}
        after = {"ready": False, "violations": [dict(duplicate)]}

        comparison = compare_layout_reports(before, after)

        self.assertEqual(len(comparison["resolved"]), 1)
        self.assertEqual(len(comparison["persistent"]), 1)
        self.assertEqual(len(comparison["introduced"]), 0)

    def test_report_comparison_fails_closed_when_after_report_is_unavailable(self) -> None:
        before = {"status": "failed", "ready": False, "violations": [{"type": "near_collision", "page": 1}]}
        after = {"status": "verification_unavailable", "ready": False, "violations": []}

        comparison = compare_layout_reports(before, after)
        progress = evaluate_repair_progress([before, after])

        self.assertFalse(comparison["regression_free"])
        self.assertEqual(comparison["introduced"][0]["type"], "verification_unavailable")
        self.assertTrue(progress["should_stop"])
        self.assertEqual(progress["stop_reason"], "verification_unavailable")

    def test_repair_plan_collapses_repeated_bullet_collisions_into_one_style_edit(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block>
          <line xMin="30" yMin="10" xMax="560" yMax="24"><word xMin="30" yMin="10" xMax="35" yMax="24">•</word><word xMin="40" yMin="10" xMax="90" yMax="24">First</word></line>
          <line xMin="30" yMin="18" xMax="550" yMax="32"><word xMin="30" yMin="18" xMax="35" yMax="32">•</word><word xMin="40" yMin="18" xMax="100" yMax="32">Second</word></line>
          <line xMin="30" yMin="26" xMax="540" yMax="40"><word xMin="30" yMin="26" xMax="35" yMax="40">•</word><word xMin="40" yMin="26" xMax="90" yMax="40">Third</word></line>
        </block></flow></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        style_repairs = [item for item in report["repair_plan"] if item["action"] == "adjust_shared_list_style"]
        self.assertEqual(len(style_repairs), 1)
        self.assertEqual(style_repairs[0]["violation_count"], 2)
        self.assertEqual(style_repairs[0]["typst_controls"], ["list.spacing", "par.leading"])
        self.assertEqual(report["max_repair_iterations"], 3)

    def test_reports_wrong_page_count_and_text_outside_page(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
        <page width="612" height="792"><flow><block>
          <line xMin="24" yMin="10" xMax="588" yMax="24"><word xMin="24" yMin="10" xMax="100" yMax="24">Page one</word></line>
        </block></flow></page>
        <page width="612" height="792"><flow><block>
          <line xMin="24" yMin="790" xMax="588" yMax="804"><word xMin="24" yMin="790" xMax="100" yMax="804">Overflow</word></line>
        </block></flow></page>
        </doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        types = {item["type"] for item in report["violations"]}
        self.assertIn("page_count", types)
        self.assertIn("text_out_of_bounds", types)
        actions = {item["action"] for item in report["repair_plan"]}
        self.assertIn("refit_document", actions)
        self.assertIn("correct_page_setup", actions)
        self.assertFalse(report["ready"])

    def test_empty_exported_geometry_is_not_ready(self) -> None:
        bbox = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow/></page></doc></body></html>"""

        report = analyze_bbox_layout(bbox)

        self.assertFalse(report["ready"])
        self.assertIn("missing_exported_text", {item["type"] for item in report["violations"]})

    def test_query_typst_telemetry_normalizes_semantic_regions(self) -> None:
        telemetry = """[{"value":{"jobapps_qa":true,"kind":"bullet","id":"experience-1-bullet-2","width":"520.5pt","height":"26.4pt"},"position":{"page":1,"x":"40pt","y":"210.25pt"}}]"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "resume.typ"
            source.write_text("Hello", encoding="utf-8")
            typst = root / "typst"
            typst.write_text(
                "#!/usr/bin/env python3\n"
                f"print({telemetry!r})\n",
                encoding="utf-8",
            )
            typst.chmod(0o755)

            result = query_typst_telemetry(source, compiler=str(typst), timeout=5)

        self.assertEqual(result["status"], "collected")
        self.assertEqual(
            result["regions"],
            [
                {
                    "id": "experience-1-bullet-2",
                    "kind": "bullet",
                    "page": 1,
                    "x_pt": 40.0,
                    "y_pt": 210.25,
                    "width_pt": 520.5,
                    "height_pt": 26.4,
                }
            ],
        )

    @unittest.skipUnless(shutil.which("typst"), "Typst is not installed")
    def test_typst_qa_prelude_emits_measured_semantic_region(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "resume.typ"
            source.write_text(
                TYPST_QA_PRELUDE + '\n#qa-region("section", "experience")[Hello world]\n',
                encoding="utf-8",
            )

            result = query_typst_telemetry(source, compiler=shutil.which("typst") or "typst", timeout=30)

        self.assertEqual(result["status"], "collected", result)
        self.assertEqual(result["regions"][0]["id"], "experience")
        self.assertEqual(result["regions"][0]["kind"], "section")
        self.assertGreater(result["regions"][0]["width_pt"], 0)
        self.assertGreater(result["regions"][0]["height_pt"], 0)

    def test_typst_compile_refuses_readiness_when_layout_gate_fails(self) -> None:
        bbox = """<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page width="612" height="792"><flow><block>
        <line xMin="30" yMin="10" xMax="560" yMax="24"><word xMin="30" yMin="10" xMax="35" yMax="24">•</word><word xMin="40" yMin="10" xMax="90" yMax="24">First</word></line>
        <line xMin="40" yMin="23" xMax="520" yMax="37"><word xMin="40" yMin="23" xMax="120" yMax="37">continuation</word></line>
        <line xMin="30" yMin="31" xMax="550" yMax="45"><word xMin="30" yMin="31" xMax="35" yMax="45">•</word><word xMin="40" yMin="31" xMax="100" yMax="45">Second</word></line>
        </block></flow></page></doc></body></html>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "resume.typ"
            source.write_text("Hello", encoding="utf-8")
            config = write_fake_toolchain(root, bbox)

            result = compile_typst_to_pdf(source, config=config)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "verification_failed")
        self.assertTrue(result["rendered"])
        self.assertEqual(result["verification"]["layout"]["status"], "failed")
        self.assertTrue(Path(result["pdf_path"]).name.endswith(".pdf"))
        self.assertIn("repair_plan", result["verification"]["layout"])

    def test_typst_compile_without_layout_qa_verifies_pdf_and_skips_layout_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "cover-letter.typ"
            source.write_text("Hello", encoding="utf-8")
            config = write_fake_toolchain(root, "<not-valid-bbox")

            result = compile_typst_to_pdf(source, config=config, layout_qa=False)
            pdf_exists = Path(result["pdf_path"]).is_file()
            build_dir_exists = (root / "build").exists()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "compiled")
        self.assertTrue(result["rendered"])
        self.assertTrue(pdf_exists)
        self.assertFalse(build_dir_exists)
        self.assertNotIn("layout", result["verification"])
        self.assertEqual(result["verification"]["pages"], 1)
        self.assertEqual(result["verification"]["word_count"], 2)
        self.assertEqual(result["verification"]["integrity_errors"], [])

    @unittest.skipUnless(shutil.which("typst") and shutil.which("pdftotext"), "Typst or Poppler is not installed")
    def test_real_typst_compile_runs_layout_qa_on_instrumented_resume(self) -> None:
        config = default_settings()
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "resume.typ"
            source.write_text(RESUME_FIXTURE, encoding="utf-8")

            result = compile_typst_to_pdf(source, config=config)
            if not result.get("rendered") and package_unavailable(result.get("stderr", "")):
                self.skipTest("The Typst resume package is not available offline")
            strict = dict(config, resume_qa={**config["resume_qa"], "required_body_font": "Atkinson Hyperlegible"})
            strict_result = compile_typst_to_pdf(source, config=strict)
            letter_result = compile_typst_to_pdf(source, config=config, layout_qa=False)
            pdf_exists = Path(result["pdf_path"]).is_file()

        self.assertTrue(result["rendered"], result)
        self.assertTrue(pdf_exists)
        verification = result["verification"]
        self.assertEqual(verification["pages"], 1)
        self.assertEqual(verification["integrity_errors"], [])
        layout = verification["layout"]
        self.assertEqual(layout["telemetry"]["status"], "collected")
        self.assertIn("unusual-field-work-1", {region["id"] for region in layout["telemetry"]["regions"]})
        types = {item["type"] for item in layout["violations"]}
        self.assertNotIn("body_font_mismatch", types)
        self.assertNotIn("body_font_below_minimum", types)
        self.assertEqual(result["ok"], layout["ready"])
        self.assertEqual(result["status"], "compiled" if layout["ready"] else "verification_failed")

        strict_types = {item["type"] for item in strict_result["verification"]["layout"]["violations"]}
        self.assertIn("body_font_mismatch", strict_types)
        self.assertFalse(strict_result["ok"])

        self.assertTrue(letter_result["ok"], letter_result)
        self.assertEqual(letter_result["status"], "compiled")
        self.assertNotIn("layout", letter_result["verification"])


if __name__ == "__main__":
    unittest.main()
