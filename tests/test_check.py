from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import hermes_jobapps
from hermes_jobapps import resume_qa
from hermes_jobapps.check import check_material
from hermes_jobapps.workspace import Workspace, qa_report_path, qa_state


KINDS = ("resume", "cover_letter", "application_answers", "outreach")
RESUME_NAME = "Jordan Example - Resume - Northstar.typ"
LETTER_NAME = "Jordan Example - Cover Letter - Northstar.typ"


def normalize_kind(value: object) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key not in KINDS:
        raise ValueError(f"Unknown material kind: {value}")
    return key


def content_result(kind: str = "resume", *, review: bool = False) -> dict:
    findings = [
        {
            "rule": "unsupported_number",
            "severity": "error",
            "where": "line 14",
            "excerpt": "Cut review time by 73%",
            "fix": "Use a figure that appears in the evidence, or remove it.",
        },
        {
            "rule": "filler_phrase",
            "severity": "warning",
            "where": "line 9",
            "excerpt": "passionate about",
            "fix": "State the concrete interest instead.",
        },
    ]
    return {
        "kind": kind,
        "status": "review" if review else "pass",
        "summary": {
            "words": 412,
            "bullets": 14,
            "paragraphs": 0,
            "errors": 1 if review else 0,
            "warnings": 1 if review else 0,
            "notes": 0,
        },
        "findings": findings if review else [],
    }


def layout_report(violations: list[dict] | None = None, *, status: str = "") -> dict:
    violations = list(violations or [])
    return {
        "status": status or ("failed" if violations else "passed"),
        "ready": not violations and not status,
        "pages": [{"number": 1, "width": 612.0, "height": 792.0}],
        "line_count": 58,
        "violations": violations,
        "repair_plan": resume_qa._build_repair_plan(violations),
        "max_repair_iterations": 3,
        "metrics": {
            "normal_wrapped_overlap_pt": 1.2,
            "normal_wrapped_baseline_step_pt": 12.4,
            "collision_threshold_pt": 2.4,
            "section_spacing": [],
            "page_occupancy": [
                {
                    "page": 1,
                    "bottom_content_y_pt": 745.2,
                    "bottom_whitespace_pt": 46.8,
                    "bottom_whitespace_in": 0.65,
                    "bottom_whitespace_ratio": 0.0591,
                }
            ],
        },
        "artifact": {"pdf_sha256": "a" * 64, "source_sha256": "b" * 64},
        "pdf_path": "/tmp/resume.pdf",
        "tool": "/usr/local/bin/pdftotext",
        "bbox_exit": 0,
        "stderr": "",
        "telemetry": {"status": "collected", "regions": [], "command": ["typst", "eval"], "returncode": 0},
    }


def many_violations(path: Path) -> list[dict]:
    long_text = "Designed and shipped a retrieval evaluation harness covering ranking, grounding and latency " * 2
    violations: list[dict] = []
    for index in range(1, 21):
        violations.append(
            {
                "type": "short_final_line",
                "severity": "warning",
                "page": 1,
                "x_pt": 40.0,
                "y_pt": 100.0 + index * 14,
                "element_id": f"page-1-bullet-{index}",
                "final_text": f"{long_text} tail {index}",
                "final_word_count": 2,
                "width_utilization": 0.11,
                "repair_scope": "bullet_content",
                "recommended_action": "Shorten or rephrase this bullet enough to reclaim one line without changing its claims.",
                "semantic_id": f"experience-1-bullet-{index}",
                "semantic_kind": "bullet",
                "source_range": {"path": str(path), "line_start": 20 + index, "line_end": 20 + index},
            }
        )
    for index in range(1, 9):
        violations.append(
            {
                "type": "bullet_item_overlap",
                "severity": "error",
                "page": 1,
                "x_pt": 30.0,
                "y_pt": 400.0 + index * 12,
                "previous_text": f"{long_text} previous {index}",
                "next_text": f"• {long_text} next {index}",
                "vertical_overlap_pt": 6.0,
                "normal_wrapped_overlap_pt": 1.2,
                "repair_scope": "shared_list_style",
                "source_range": {"path": str(path), "line_start": 50 + index, "line_end": 50 + index},
            }
        )
    violations.append(
        {
            "type": "bottom_whitespace_out_of_range",
            "severity": "error",
            "page": 1,
            "direction": "too_small",
            "measured_bottom_whitespace_pt": 14.4,
            "measured_bottom_whitespace_in": 0.2,
            "target_bottom_whitespace_in": 0.65,
            "tolerance_in": 0.1,
            "accepted_range_in": [0.55, 0.75],
            "repair_scope": "document_density",
            "recommended_action": "Reduce density or restore spacing until the rendered bottom whitespace falls inside the target band.",
        }
    )
    violations.append(
        {
            "type": "weak_spacing_hierarchy",
            "severity": "warning",
            "page": 1,
            "x_pt": 24.0,
            "y_pt": 310.0,
            "section": "Selected Research",
            "previous_text": "Second result",
            "internal_gap_pt": 19.0,
            "section_gap_pt": 21.5,
            "gap_ratio": 0.884,
            "repair_scope": "semantic_spacing_tokens",
            "recommended_action": "Reduce the internal detail gap or increase the section transition gap so hierarchy is unmistakable.",
            "semantic_id": "selected-research-2",
            "semantic_kind": "section",
            "source_range": {"path": str(path), "line_start": 31, "line_end": 31},
        }
    )
    return violations


class FakeTypst:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.status = "ok"
        self.layout: dict | None = None
        self.contamination: list[str] = []
        self.pages = 1
        self.stderr = ""

    def __call__(self, typst_path, *, config=None, output_dir=None, layout_qa=True) -> dict:
        source = Path(typst_path)
        self.calls.append({"path": source, "config": config, "layout_qa": layout_qa})
        base = {"source_path": str(source), "typst_path": str(source)}
        if self.status == "missing_compiler":
            return {
                "ok": False,
                "status": "missing_compiler",
                **base,
                "compiler_candidates": ["typst"],
                "searched_paths": ["/usr/local/bin"],
                "next_step": "Install Typst or add it to typst.compiler_paths, then run compile again.",
            }
        command = ["/usr/local/bin/typst", "compile", str(source), str(source.parent / "build" / f"{source.stem}.pdf")]
        if self.status == "compile_failed":
            return {
                "ok": False,
                "rendered": False,
                "status": "compile_failed",
                **base,
                "pdf_path": "",
                "build_pdf_path": command[-1],
                "compiler": command[0],
                "command": command,
                "returncode": 1,
                "stdout": "",
                "stderr": self.stderr or "error: unknown variable: custom-titel\n  ┌─ resume.typ:22:1\n",
                "verification": {"status": "not_run", "integrity_errors": ["pdf_not_rendered"]},
                "next_step": "Open the compile errors, patch the Typst, and compile again.",
            }
        pdf = source.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-1.4 fake " + source.read_bytes())
        verification = {
            "status": "checked",
            "pdf_path": str(pdf),
            "exists": True,
            "pages": self.pages,
            "word_count": 412,
            "contamination": list(self.contamination),
            "pdfinfo_exit": 0,
            "pdftotext_exit": 0,
            "pdfinfo_stdout": f"Pages:           {self.pages}\n",
        }
        layout = (self.layout or layout_report()) if layout_qa else None
        if layout is not None:
            verification["layout"] = layout
        integrity = []
        if self.pages != 1:
            integrity.append(f"page_count:{self.pages}")
        if self.contamination:
            integrity.append("contamination_detected")
        verification["integrity_errors"] = integrity
        required = bool(((config or {}).get("resume_qa") or {}).get("required", True))
        ok = not integrity and (layout is None or layout["ready"] or not required)
        return {
            "ok": ok,
            "rendered": True,
            "status": "compiled" if ok else "verification_failed",
            **base,
            "pdf_path": str(pdf),
            "build_pdf_path": command[-1],
            "compiler": command[0],
            "command": command,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "verification": verification,
            "next_step": "PDF compiled.",
        }


class FakeTex:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.contamination: list[str] = []

    def __call__(self, tex_path, *, config=None, output_dir=None) -> dict:
        tex = Path(tex_path)
        self.calls.append({"path": tex, "config": config})
        pdf = tex.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF-1.4 fake")
        return {
            "ok": True,
            "status": "compiled",
            "tex_path": str(tex),
            "pdf_path": str(pdf),
            "build_pdf_path": str(tex.parent / "build" / f"{tex.stem}.pdf"),
            "log_path": "",
            "compiler": "/usr/local/bin/tectonic",
            "command": ["/usr/local/bin/tectonic", str(tex)],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "verification": {
                "status": "checked",
                "pdf_path": str(pdf),
                "exists": True,
                "pages": 1,
                "word_count": 318,
                "contamination": list(self.contamination),
                "pdfinfo_exit": 0,
                "pdftotext_exit": 0,
            },
            "next_step": "PDF compiled, copied beside the TeX source, and verified.",
        }


class CheckMaterialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace(Path(self.tmp.name) / "ws")
        self.ws.init(name="Jordan Example")
        self.ws.write(self.ws.profile_dir / "profile.md", {"name": "Jordan Example"}, "Targets applied AI roles.")
        self.ws.write(
            self.ws.evidence_dir / "atlas.md",
            {"title": "Atlas", "status": "active"},
            "Shipped the Atlas retrieval service.",
        )
        self.ws.write(
            self.ws.evidence_dir / "beacon.md",
            {"title": "Beacon", "status": "needs_review"},
            "Built the Beacon evaluation harness.",
        )
        self.ws.write(
            self.ws.evidence_dir / "old.md",
            {"title": "Old", "status": "retired"},
            "Retired claim that must stay out.",
        )
        job = self.ws.create_job(
            company="Northstar",
            title="AI Engineer",
            posting="Build agent systems for clinical teams.",
            body_sections={"Requirements": "- Python in production\n- Agent evaluation\n  - nested detail\nNot a bullet"},
            created_on="2026-11-01",
        )
        self.job_id = job["id"]
        self.folder = self.ws.job_dir(self.job_id)
        self.resume = self.folder / RESUME_NAME
        self.resume.write_text("#set page(paper: \"us-letter\")\nResume body\n", encoding="utf-8")
        self.letter = self.folder / LETTER_NAME
        self.letter.write_text("Dear Northstar team,\n", encoding="utf-8")

        self.content = mock.Mock(side_effect=lambda source, **kwargs: content_result(kwargs["kind"]))
        fake_module = types.ModuleType("hermes_jobapps.content_qa")
        fake_module.KINDS = KINDS
        fake_module.normalize_kind = normalize_kind
        fake_module.check_material = self.content
        self.typst = FakeTypst()
        self.tex = FakeTex()
        for patcher in (
            mock.patch.dict(sys.modules, {"hermes_jobapps.content_qa": fake_module}),
            mock.patch.object(hermes_jobapps, "content_qa", fake_module, create=True),
            mock.patch("hermes_jobapps.build.compile_typst_to_pdf", self.typst),
            mock.patch("hermes_jobapps.build.compile_tex_to_pdf", self.tex),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def relative(self, path: Path) -> str:
        return self.ws.relative(path)

    def content_review(self) -> None:
        self.content.side_effect = lambda source, **kwargs: content_result(kwargs["kind"], review=True)

    # -- path resolution -----------------------------------------------------

    def test_job_plus_file_name_resolves_inside_the_job_folder(self) -> None:
        result = check_material(self.ws, RESUME_NAME, job="northstar")

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["file"], f"jobs/{self.job_id}/{RESUME_NAME}")
        self.assertEqual(result["pdf"], f"jobs/{self.job_id}/{Path(RESUME_NAME).with_suffix('.pdf')}")
        self.assertEqual(self.typst.calls[0]["path"], self.resume.resolve())

    def test_workspace_relative_path_resolves_with_or_without_job(self) -> None:
        relative = f"jobs/{self.job_id}/{RESUME_NAME}"
        template = self.ws.templates_dir / "base-resume.md"
        template.write_text("# Resume\n", encoding="utf-8")

        direct = check_material(self.ws, relative)
        with_job = check_material(self.ws, relative, job=self.job_id)
        absolute = check_material(self.ws, str(self.resume))
        fallback = check_material(self.ws, "templates/base-resume.md", job=self.job_id)

        self.assertEqual(direct["file"], relative)
        self.assertEqual(with_job["file"], relative)
        self.assertEqual(absolute["file"], relative)
        self.assertEqual(fallback["file"], "templates/base-resume.md")

    def test_paths_cannot_escape_the_workspace(self) -> None:
        outside = Path(self.tmp.name) / "resume.typ"
        outside.write_text("outside", encoding="utf-8")

        for path, job in (
            ("../resume.typ", ""),
            (str(outside), ""),
            ("../../../resume.typ", self.job_id),
            (str(outside), self.job_id),
        ):
            with self.subTest(path=path, job=job):
                with self.assertRaises(ValueError):
                    check_material(self.ws, path, job=job)
        self.assertEqual(self.typst.calls, [])
        self.content.assert_not_called()
        self.assertFalse((Path(self.tmp.name) / "qa").exists())

    def test_missing_file_and_unknown_job(self) -> None:
        result = check_material(self.ws, "resume-v2.typ", job=self.job_id)

        self.assertEqual(
            result,
            {
                "ok": False,
                "error": f"File not found: jobs/{self.job_id}/resume-v2.typ",
                "hint": "Pass a path inside the workspace, or job plus the file name.",
            },
        )
        self.assertFalse(check_material(self.ws, "")["ok"])
        self.assertFalse(check_material(self.ws, f"jobs/{self.job_id}")["ok"])
        with self.assertRaises(KeyError):
            check_material(self.ws, RESUME_NAME, job="nobody")

    def test_pdf_path_switches_to_its_source(self) -> None:
        pdf_name = str(Path(RESUME_NAME).with_suffix(".pdf"))
        not_built_yet = check_material(self.ws, pdf_name, job=self.job_id)
        built = check_material(self.ws, f"jobs/{self.job_id}/{pdf_name}")
        (self.folder / "offer.pdf").write_bytes(b"%PDF")
        orphan = check_material(self.ws, "offer.pdf", job=self.job_id, kind="resume")
        missing = check_material(self.ws, "nothing.pdf", job=self.job_id)

        self.assertEqual(not_built_yet["file"], f"jobs/{self.job_id}/{RESUME_NAME}")
        self.assertEqual(built["file"], f"jobs/{self.job_id}/{RESUME_NAME}")
        self.assertEqual(
            orphan,
            {"ok": False, "error": "Check runs on the source file (.typ, .tex, .md, .txt), not the PDF."},
        )
        self.assertTrue(missing["error"].startswith("File not found"))

    def test_unsupported_source_format_is_refused(self) -> None:
        (self.folder / "resume.docx").write_bytes(b"PK\x03\x04")

        result = check_material(self.ws, "resume.docx", job=self.job_id)

        self.assertFalse(result["ok"])
        self.assertIn(".docx", result["error"])
        self.content.assert_not_called()

    # -- kind ----------------------------------------------------------------

    def test_kind_is_inferred_from_the_file_name(self) -> None:
        names = {
            "resume.md": "resume",
            "cover-letter.md": "cover_letter",
            "application-answers.md": "application_answers",
            "outreach-hiring-manager.txt": "outreach",
        }
        for name, expected in names.items():
            with self.subTest(name=name):
                (self.folder / name).write_text("Body\n", encoding="utf-8")
                result = check_material(self.ws, name, job=self.job_id)
                self.assertEqual(result["kind"], expected)
                self.assertEqual(self.content.call_args.kwargs["kind"], expected)

    def test_unknown_kind_needs_an_explicit_kind(self) -> None:
        for name in ("draft.md", "interview-prep.md"):
            (self.folder / name).write_text("Body\n", encoding="utf-8")
            with self.subTest(name=name):
                self.assertEqual(
                    check_material(self.ws, name, job=self.job_id),
                    {
                        "ok": False,
                        "error": "Cannot tell what kind of document this is.",
                        "hint": "Pass kind: resume, cover_letter, application_answers or outreach.",
                    },
                )
        self.content.assert_not_called()

        explicit = check_material(self.ws, "draft.md", job=self.job_id, kind="Cover Letter")
        invalid = check_material(self.ws, "draft.md", job=self.job_id, kind="poem")

        self.assertEqual(explicit["kind"], "cover_letter")
        self.assertFalse(invalid["ok"])
        self.assertIn("poem", invalid["error"])
        self.assertEqual(invalid["hint"], "Pass kind: resume, cover_letter, application_answers or outreach.")

    def test_explicit_kind_overrides_the_file_name(self) -> None:
        result = check_material(self.ws, RESUME_NAME, job=self.job_id, kind="outreach")

        self.assertEqual(result["kind"], "outreach")
        self.assertFalse(self.typst.calls[0]["layout_qa"])
        self.assertNotIn("layout", result)

    # -- build ---------------------------------------------------------------

    def test_resume_build_runs_layout_qa_and_cover_letter_build_skips_it(self) -> None:
        resume = check_material(self.ws, RESUME_NAME, job=self.job_id)
        letter = check_material(self.ws, LETTER_NAME, job=self.job_id)

        self.assertTrue(self.typst.calls[0]["layout_qa"])
        self.assertFalse(self.typst.calls[1]["layout_qa"])
        self.assertEqual(self.typst.calls[0]["config"]["resume_qa"]["required_pages"], 1)
        self.assertEqual(self.typst.calls[0]["config"]["workspace_path"], str(self.ws.root))
        self.assertEqual(
            resume["build"],
            {"ok": True, "status": "compiled", "compiler": "typst", "pages": 1, "words": 412},
        )
        self.assertEqual(
            resume["layout"],
            {"ready": True, "status": "passed", "violations_total": 0, "bottom_whitespace_in": 0.65},
        )
        self.assertEqual(resume["status"], "pass")
        self.assertIn("jobapps_track", resume["next"])
        self.assertEqual(letter["status"], "pass")
        self.assertNotIn("layout", letter)
        self.assertEqual(letter["kind"], "cover_letter")

    def test_tex_uses_the_tex_compiler_and_reports_contamination(self) -> None:
        tex = self.folder / "cover-letter.tex"
        tex.write_text("\\documentclass{letter}\n", encoding="utf-8")

        clean = check_material(self.ws, "cover-letter.tex", job=self.job_id)
        self.tex.contamination = ["Build Notes"]
        dirty = check_material(self.ws, "cover-letter.tex", job=self.job_id)

        self.assertEqual(self.typst.calls, [])
        self.assertEqual(self.tex.calls[0]["path"], tex.resolve())
        self.assertIn("latex", self.tex.calls[0]["config"])
        self.assertEqual(clean["build"], {"ok": True, "status": "compiled", "compiler": "tectonic", "pages": 1, "words": 318})
        self.assertEqual(clean["status"], "pass")
        self.assertEqual(self.content.call_args.kwargs["fmt"], "tex")
        self.assertEqual(dirty["status"], "fail")
        self.assertEqual(dirty["build"]["contamination"], ["Build Notes"])
        self.assertEqual(dirty["build"]["status"], "verification_failed")
        self.assertFalse(dirty["build"]["ok"])

    def test_markdown_and_text_skip_the_build(self) -> None:
        (self.folder / "application-answers.md").write_text("## Why us\n\nBecause.\n", encoding="utf-8")
        (self.folder / "outreach.txt").write_text("Hello\n", encoding="utf-8")

        answers = check_material(self.ws, "application-answers.md", job=self.job_id, max_chars=600)
        formats = [self.content.call_args.kwargs["fmt"]]
        outreach = check_material(self.ws, "outreach.txt", job=self.job_id)
        formats.append(self.content.call_args.kwargs["fmt"])

        self.assertEqual(self.typst.calls + self.tex.calls, [])
        self.assertEqual(formats, ["md", "text"])
        for result in (answers, outreach):
            self.assertEqual(result["status"], "pass")
            self.assertNotIn("build", result)
            self.assertNotIn("layout", result)
            self.assertNotIn("pdf", result)
        self.assertNotIn("PDF", answers["next"])

    def test_build_false_checks_content_only(self) -> None:
        result = check_material(self.ws, RESUME_NAME, job=self.job_id, build=False)

        self.assertEqual(self.typst.calls, [])
        self.assertEqual(result["build"], {"status": "skipped"})
        self.assertNotIn("pdf", result)
        self.assertEqual(result["status"], "pass")
        self.assertIn("not built", result["next"])
        self.assertNotIn("pdf_sha256", json.loads(qa_report_path(self.resume).read_text(encoding="utf-8")))

    # -- status --------------------------------------------------------------

    def test_status_precedence(self) -> None:
        failing_layout = layout_report(many_violations(self.resume)[:3])

        clean = check_material(self.ws, RESUME_NAME, job=self.job_id)
        self.content_review()
        content_only = check_material(self.ws, RESUME_NAME, job=self.job_id)
        self.typst.layout = failing_layout
        layout_and_content = check_material(self.ws, RESUME_NAME, job=self.job_id)
        self.typst.status = "compile_failed"
        build_and_content = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(clean["status"], "pass")
        self.assertEqual(content_only["status"], "review")
        self.assertIn("content findings", content_only["next"])
        self.assertEqual(content_only["content"], content_result(review=True))
        self.assertEqual(layout_and_content["status"], "fail")
        self.assertTrue(layout_and_content["build"]["ok"])
        self.assertEqual(layout_and_content["build"]["status"], "compiled")
        self.assertFalse(layout_and_content["layout"]["ready"])
        self.assertIn("layout repair plan", layout_and_content["next"])
        self.assertIn("content findings", layout_and_content["next"])
        self.assertEqual(build_and_content["status"], "fail")
        self.assertIn("build error", build_and_content["next"])
        self.assertNotIn("layout", build_and_content)
        self.assertNotIn("pdf", build_and_content)
        self.assertEqual(build_and_content["content"]["status"], "review")

    def test_layout_failure_alone_fails_a_resume(self) -> None:
        self.typst.layout = layout_report(many_violations(self.resume)[:1])

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["content"]["status"], "pass")
        self.assertIn("layout repair plan", result["next"])
        self.assertNotIn("content findings", result["next"])

    def test_layout_failure_is_advisory_when_layout_qa_is_not_required(self) -> None:
        self.ws.save_settings({"resume_qa": {"required": False}})
        self.typst.layout = layout_report(many_violations(self.resume)[:1])

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(result["status"], "review")
        self.assertFalse(result["layout"]["ready"])

    def test_layout_violation_without_a_repair_plan_points_at_the_violations(self) -> None:
        self.typst.layout = layout_report(many_violations(self.resume)[28:29])

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["layout"]["violations"][0]["type"], "bottom_whitespace_out_of_range")
        self.assertNotIn("repair_plan", result["layout"])
        self.assertIn("layout violations", result["next"])

    def test_unavailable_layout_verification_fails_with_a_reason(self) -> None:
        self.typst.layout = {
            "status": "verification_unavailable",
            "ready": False,
            "pdf_path": "/tmp/resume.pdf",
            "tool": None,
            "violations": [],
            "next_step": "Install Poppler pdftotext; layout QA cannot pass without final-PDF geometry.",
        }

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(result["status"], "fail")
        self.assertIn("layout.note", result["next"])
        self.assertEqual(
            result["layout"],
            {
                "ready": False,
                "status": "verification_unavailable",
                "violations_total": 0,
                "note": "Install Poppler pdftotext; layout QA cannot pass without final-PDF geometry.",
            },
        )

    def test_compile_failure_reports_a_clipped_error_tail(self) -> None:
        self.typst.status = "compile_failed"
        self.typst.stderr = "warning: noise\n" * 600 + "error: unknown variable: custom-titel\n  ┌─ resume.typ:22:1\n"

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["build"]["status"], "compile_failed")
        self.assertFalse(result["build"]["ok"])
        self.assertEqual(result["build"]["compiler"], "typst")
        self.assertLessEqual(len(result["build"]["error"]), 1200)
        self.assertTrue(result["build"]["error"].endswith("resume.typ:22:1"))
        self.assertNotIn("integrity_errors", result["build"])
        self.assertEqual(qa_state(self.resume)["state"], "fail")

    def test_missing_compiler_fails_with_a_clear_message(self) -> None:
        self.typst.status = "missing_compiler"

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["build"]["status"], "missing_compiler")
        self.assertFalse(result["build"]["ok"])
        self.assertIn("looked for typst", result["build"]["error"])
        self.assertIn("Install Typst", result["build"]["error"])
        self.assertIn("install", result["next"])
        self.assertNotIn("pdf", result)

    def test_pdf_contamination_and_integrity_errors_fail(self) -> None:
        self.typst.contamination = ["Central angle"]
        contaminated = check_material(self.ws, LETTER_NAME, job=self.job_id)
        self.typst.contamination = []
        self.typst.pages = 2
        two_pages = check_material(self.ws, LETTER_NAME, job=self.job_id)

        self.assertEqual(contaminated["status"], "fail")
        self.assertEqual(contaminated["build"]["contamination"], ["Central angle"])
        self.assertNotIn("integrity_errors", contaminated["build"])
        self.assertEqual(two_pages["status"], "fail")
        self.assertEqual(two_pages["build"]["integrity_errors"], ["page_count:2"])
        self.assertEqual(two_pages["build"]["status"], "verification_failed")
        self.assertIn("integrity_errors", two_pages["next"])

    # -- report --------------------------------------------------------------

    def test_report_is_saved_and_drives_qa_state(self) -> None:
        self.assertEqual(qa_state(self.resume)["state"], "none")

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)
        report_path = qa_report_path(self.resume)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        state = qa_state(self.resume)

        self.assertEqual(report_path, self.folder / "qa" / f"{RESUME_NAME}.json")
        self.assertEqual(state["state"], result["status"])
        self.assertEqual(state["state"], "pass")
        self.assertEqual(state["checked_at"], report["checked_at"])
        self.assertRegex(report["checked_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertEqual(
            set(report),
            {"checked_at", "file", "kind", "status", "source_sha256", "pdf_sha256", "build", "layout", "content"},
        )
        self.assertEqual(report["file"], RESUME_NAME)
        self.assertEqual(report["kind"], "resume")
        self.assertEqual(report["build"], result["build"])
        self.assertEqual(report["layout"], result["layout"])
        self.assertEqual(report["content"], result["content"])
        self.assertEqual(len(report["pdf_sha256"]), 64)
        materials = {item["name"]: item for item in self.ws.materials(self.job_id)}
        self.assertEqual(materials[RESUME_NAME]["qa"], "pass")

        self.content_review()
        self.assertEqual(check_material(self.ws, RESUME_NAME, job=self.job_id)["status"], "review")
        self.assertEqual(qa_state(self.resume)["state"], "review")

        self.resume.write_text("Edited after the check\n", encoding="utf-8")
        self.assertEqual(qa_state(self.resume)["state"], "stale")

        self.assertEqual(check_material(self.ws, RESUME_NAME, job=self.job_id)["status"], "review")
        self.assertEqual(qa_state(self.resume)["state"], "review")

    def test_report_for_unbuilt_formats_omits_build_keys(self) -> None:
        answers = self.folder / "application-answers.md"
        answers.write_text("Answer\n", encoding="utf-8")

        check_material(self.ws, "application-answers.md", job=self.job_id)
        report = json.loads(qa_report_path(answers).read_text(encoding="utf-8"))

        self.assertEqual(set(report), {"checked_at", "file", "kind", "status", "source_sha256", "content"})
        self.assertEqual(qa_state(answers)["state"], "pass")

    # -- content lint inputs -------------------------------------------------

    def test_content_lint_receives_source_job_context_and_evidence(self) -> None:
        check_material(self.ws, RESUME_NAME, job=self.job_id, max_chars=900)

        self.content.assert_called_once()
        args, kwargs = self.content.call_args
        self.assertEqual(args, (self.resume.read_text(encoding="utf-8"),))
        self.assertEqual(
            set(kwargs),
            {
                "kind",
                "fmt",
                "requirements",
                "job_description",
                "evidence_corpus",
                "company",
                "candidate_name",
                "max_chars",
                "config",
            },
        )
        self.assertEqual(kwargs["kind"], "resume")
        self.assertEqual(kwargs["fmt"], "typ")
        self.assertEqual(kwargs["requirements"], ["Python in production", "Agent evaluation"])
        self.assertEqual(kwargs["job_description"], "Build agent systems for clinical teams.")
        self.assertEqual(kwargs["company"], "Northstar")
        self.assertEqual(kwargs["candidate_name"], "Jordan Example")
        self.assertEqual(kwargs["max_chars"], 900)
        self.assertEqual(kwargs["config"]["writing"]["cover_letter_words"], [250, 420])
        corpus = kwargs["evidence_corpus"]
        self.assertTrue(corpus.startswith("Targets applied AI roles.\n"))
        self.assertIn("Shipped the Atlas retrieval service.", corpus)
        self.assertIn("Built the Beacon evaluation harness.", corpus)
        self.assertNotIn("Retired claim", corpus)

    def test_job_context_follows_the_file_location(self) -> None:
        other = self.ws.create_job(company="Fieldwork", title="Data Engineer", created_on="2026-11-02")
        other_resume = self.ws.job_dir(other["id"]) / "resume.md"
        other_resume.write_text("Resume\n", encoding="utf-8")
        loose = self.ws.templates_dir / "resume.md"
        loose.write_text("Resume\n", encoding="utf-8")

        check_material(self.ws, f"jobs/{other['id']}/resume.md", job=self.job_id)
        in_other_job = self.content.call_args.kwargs
        check_material(self.ws, "templates/resume.md")
        no_job = self.content.call_args.kwargs
        check_material(self.ws, "templates/resume.md", job=self.job_id)
        named_job = self.content.call_args.kwargs

        self.assertEqual(in_other_job["company"], "Fieldwork")
        self.assertEqual(in_other_job["job_description"], "")
        self.assertEqual(in_other_job["requirements"], [])
        self.assertEqual((no_job["company"], no_job["job_description"], no_job["requirements"]), ("", "", []))
        self.assertEqual(named_job["company"], "Northstar")
        self.assertEqual(named_job["requirements"], ["Python in production", "Agent evaluation"])

    # -- compactness ---------------------------------------------------------

    def test_failing_layout_result_stays_compact(self) -> None:
        violations = many_violations(self.resume)
        self.assertEqual(len(violations), 30)
        self.typst.layout = layout_report(violations)
        self.content_review()

        result = check_material(self.ws, RESUME_NAME, job=self.job_id)
        layout = result["layout"]

        self.assertEqual(result["status"], "fail")
        self.assertEqual(layout["violations_total"], 30)
        self.assertEqual(len(layout["violations"]), 12)
        self.assertLessEqual(len(layout["repair_plan"]), 6)
        self.assertLess(len(json.dumps(result)), 9000)
        self.assertEqual([item["severity"] for item in layout["violations"][:9]], ["error"] * 9)
        self.assertEqual(layout["violations"][9]["severity"], "warning")
        for item in layout["violations"]:
            self.assertLessEqual(len(item.get("text", "")), 120)
            self.assertFalse({"x_pt", "y_pt", "repair_scope", "source_range", "element_id"} & set(item))
        overlap = layout["violations"][0]
        self.assertEqual(overlap["type"], "bullet_item_overlap")
        self.assertEqual(overlap["page"], 1)
        self.assertEqual(overlap["line"], 51)
        self.assertNotIn("line_end", overlap)
        self.assertEqual(overlap["vertical_overlap_pt"], 6.0)
        self.assertEqual(overlap["normal_wrapped_overlap_pt"], 1.2)
        self.assertTrue(overlap["text"].startswith("• Designed and shipped"))
        self.assertLessEqual(len(overlap["previous_text"]), 80)
        whitespace = layout["violations"][8]
        self.assertEqual(whitespace["type"], "bottom_whitespace_out_of_range")
        self.assertEqual(whitespace["measured_bottom_whitespace_in"], 0.2)
        self.assertEqual(whitespace["accepted_range_in"], [0.55, 0.75])
        self.assertEqual(whitespace["direction"], "too_small")
        self.assertTrue(whitespace["fix"].startswith("Reduce density"))
        short = layout["violations"][9]
        self.assertEqual(short["type"], "short_final_line")
        self.assertEqual(short["region"], "experience-1-bullet-1")
        self.assertEqual(short["final_word_count"], 2)
        self.assertIn("fix", short)
        actions = {step["action"]: step for step in layout["repair_plan"]}
        self.assertEqual(
            set(actions),
            {"adjust_shared_list_style", "separate_spacing_hierarchy", "rewrite_short_final_lines"},
        )
        self.assertEqual(actions["adjust_shared_list_style"]["count"], 8)
        self.assertEqual(actions["adjust_shared_list_style"]["controls"], ["list.spacing", "par.leading"])
        self.assertIn("shared list macro", actions["adjust_shared_list_style"]["instruction"])
        self.assertEqual(actions["separate_spacing_hierarchy"]["targets"], ["Selected Research"])
        self.assertEqual(actions["rewrite_short_final_lines"]["count"], 20)
        self.assertEqual(len(actions["rewrite_short_final_lines"]["targets"]), 6)
        self.assertTrue(all(len(target) <= 60 for target in actions["rewrite_short_final_lines"]["targets"]))
        report = json.loads(qa_report_path(self.resume).read_text(encoding="utf-8"))
        self.assertEqual(report["layout"], layout)

    def test_result_has_no_empty_keys_and_no_raw_build_output(self) -> None:
        result = check_material(self.ws, RESUME_NAME, job=self.job_id)

        self.assertEqual(set(result), {"ok", "file", "kind", "status", "pdf", "build", "layout", "content", "next"})
        self.assertFalse({"command", "stdout", "stderr", "verification", "source_path"} & set(result["build"]))
        self.assertNotIn(str(self.ws.root), json.dumps({key: result[key] for key in ("file", "pdf", "build", "layout")}))


if __name__ == "__main__":
    unittest.main()
