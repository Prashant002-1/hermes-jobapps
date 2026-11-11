from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes_jobapps import submission_qa
from hermes_jobapps.submission_qa import check_submission, company_key
from hermes_jobapps.workspace import Workspace


class SubmissionCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmp.name) / "ws")
        self.ws.init(name="Jordan Example")
        self.ws.set_meta(
            self.ws.profile_dir / "profile.md", {"email": "jordan@example.com", "phone": "(555) 010-2030"}
        )
        self.ws.write(
            self.ws.evidence_dir / "harbor.md",
            {"title": "Platform Engineer", "organization": "Harborline Systems", "status": "active"},
            "Built ingestion on Lakeside Cloud.",
        )
        self.job = self.ws.create_job(company="Northstar Labs, Inc.", title="Backend Engineer")["id"]
        self.ws.create_job(company="Fieldwork Analytics", title="Data Engineer")
        self.ws.create_job(company="Meridian", title="Engineer")
        self.ws.create_job(company="Loop", title="Engineer")
        self.ws.create_job(company="Harborline Systems", title="Engineer")
        self.source = self.ws.job_dir(self.job) / "Jordan Example - Cover Letter - Northstar.typ"
        self.source.write_text("x", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def check(self, plain: str, kind: str = "cover_letter", **extra):
        return check_submission(
            self.ws, source=extra.pop("source", self.source), plain=plain, kind=kind, job_id=self.job,
            company="Northstar Labs, Inc.", **extra,
        )

    def rules(self, result) -> dict[str, str]:
        return {item["rule"]: item["severity"] for item in result.get("findings", [])}


class WrongCompanyTests(SubmissionCase):
    def test_another_tracked_employer_in_a_letter_is_an_error(self) -> None:
        result = self.check("Dear Fieldwork Analytics team, I would like to join Northstar Labs.")
        self.assertEqual(self.rules(result), {"wrong_company": "error"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("Fieldwork Analytics", result["findings"][0]["fix"])

    def test_a_passing_mention_is_only_a_warning(self) -> None:
        result = self.check("I led a migration similar to one Meridian published last year.", kind="resume")
        self.assertEqual(self.rules(result).get("wrong_company"), "warning")

    def test_own_company_past_employers_and_short_common_names_are_not_flagged(self) -> None:
        text = (
            "Dear Northstar Labs team. At Harborline Systems I built ingestion on Lakeside Cloud. "
            "I kept every service in the loop and Loop through each case. Meridianal is not a match."
        )
        self.assertNotIn("wrong_company", self.rules(self.check(text)))

    def test_company_key_strips_legal_suffixes(self) -> None:
        self.assertEqual(company_key("Northstar Labs, Inc."), "Northstar")
        self.assertEqual(company_key("Fieldwork LLC"), "Fieldwork")
        self.assertEqual(company_key("Acme Holdings Co."), "Acme")


class ContactAndTypoTests(SubmissionCase):
    def test_resume_with_a_different_email_or_phone_fails(self) -> None:
        result = self.check("Jordan Example | jordan@exmaple.com | 555-010-2039", kind="resume")
        self.assertEqual([item["rule"] for item in result["findings"]], ["contact_mismatch", "contact_mismatch"])
        self.assertEqual(result["status"], "fail")

    def test_resume_matching_the_profile_is_clean(self) -> None:
        result = self.check("Jordan Example | jordan@example.com | +1 555.010.2030", kind="resume")
        self.assertEqual(result, {"status": "pass"})

    def test_resume_without_an_email_is_a_warning(self) -> None:
        self.assertEqual(self.rules(self.check("Jordan Example", kind="resume")), {"contact_missing": "warning"})

    def test_contact_in_template_variables_counts_when_no_pdf_was_built(self) -> None:
        result = self.check("Jordan Example", kind="resume", raw='#let email = "jordan@example.com"')
        self.assertEqual(result, {"status": "pass"})

    def test_letters_are_not_required_to_carry_contact_details(self) -> None:
        self.assertEqual(self.check("Dear Northstar Labs team, thank you."), {"status": "pass"})

    def test_doubled_words(self) -> None:
        result = self.check("I built the the pipeline that that team had had in mind.")
        self.assertEqual(self.rules(result), {"doubled_word": "warning"})
        self.assertEqual(len(result["findings"]), 1)

    def test_draft_file_names_get_a_note(self) -> None:
        draft = self.source.with_name("cover letter draft v2.typ")
        draft.write_text("x", encoding="utf-8")
        result = self.check("Dear Northstar Labs team.", source=draft)
        self.assertEqual(self.rules(result), {"file_name": "note"})
        self.assertEqual(result["status"], "pass")


class ResumePageTests(SubmissionCase):
    REQUIREMENTS = ["Build Python data pipelines on Airflow", "Operate PostgreSQL at scale with Terraform"]

    def test_relevance_buried_below_the_top_third_is_noted(self) -> None:
        filler = "Coordinated volunteer schedules and wrote newsletters for the campus club. " * 12
        relevant = "Built Python pipelines on Airflow and operated PostgreSQL with Terraform at scale. "
        buried = self.check("jordan@example.com " + filler + relevant, kind="resume", requirements=self.REQUIREMENTS)
        self.assertEqual(self.rules(buried).get("buried_relevance"), "note")
        leading = self.check("jordan@example.com " + relevant + filler, kind="resume", requirements=self.REQUIREMENTS)
        self.assertNotIn("buried_relevance", self.rules(leading))

    def test_pdf_text_checks(self) -> None:
        pdf = self.source.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF")
        good = "Jordan Example\njordan@example.com\n\nExperience\n" + "Built a thing that worked well. " * 12 + "\nEducation\nSkills\n"
        cases = {
            "clean": (good, {}),
            "empty": ("  \n", {"ats_unreadable": "error"}),
            "image_only": ("", {"ats_unreadable": "error"}),
            "ligature": (good.replace("worked", "con\ufb01gured"), {"ats_garbled_text": "warning"}),
            "no_email": (good.replace("jordan@example.com", ""), {"contact_missing": "warning", "ats_contact_unreadable": "warning"}),
            "no_sections": (good.replace("Experience", "Things").replace("Education", "More").replace("Skills", "Etc"), {"ats_sections": "note"}),
        }
        for name, (extracted, expected) in cases.items():
            with self.subTest(name=name), patch.object(submission_qa, "pdf_text", return_value=extracted):
                result = self.check("jordan@example.com", kind="resume", pdf=pdf)
                self.assertEqual(self.rules(result), expected)
        with patch.object(submission_qa, "pdf_text", return_value=good):
            ats = self.check("x", kind="resume", pdf=pdf)["ats"]
        self.assertTrue(ats["email_readable"])
        self.assertEqual(ats["sections"], ["experience", "education", "skills"])

    def test_missing_pdftotext_skips_ats_checks(self) -> None:
        pdf = self.source.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF")
        with patch("hermes_jobapps.build._resolve_compiler", return_value=None):
            result = self.check("jordan@example.com", kind="resume", pdf=pdf)
        self.assertNotIn("ats", result)


if __name__ == "__main__":
    unittest.main()
