from __future__ import annotations

import json
import unittest

from hermes_jobapps import content_qa
from hermes_jobapps.content_qa import (
    KINDS,
    RULE_IDS,
    check_material,
    extract_material_text,
    normalize_kind,
    rules_for,
)


STRONG_BULLET = (
    "Rebuilt the nightly ingestion job as incremental loads, cutting a 6-hour run to 40 minutes "
    "so analysts start with fresh data"
)
STRONG_CORPUS = "The nightly ingestion job was a 6-hour run. After the rebuild it takes 40 minutes."

CLEAN_BULLETS = (
    STRONG_BULLET,
    "Designed a retrieval pipeline with pgvector that cut lookup latency from 900 ms to 120 ms",
    "Wrote the on-call runbook that replaced tribal knowledge, letting new engineers resolve alerts without escalation",
    "Migrated billing exports to an idempotent queue, which prevented duplicate invoices during retries",
)

TYPST_RESUME = r"""#import "template.typ": *
#set page(margin: 0.5in)
#show link: underline
#let work-heading(title, company, dates) = {
  grid(
    columns: (1fr, auto),
    [*#title* at #company],
    [#dates],
  )
  // - comment that looks like a bullet
}
/* block comment
- hidden bullet
*/
= Experience
#work-heading("Software Engineer", "Northstar", "2022 - 2024")
- Rebuilt the nightly ingestion job as incremental loads so analysts start with fresh data
- Wrote the #link("https://example.com/tool")[migration tool] in *Rust* for C\# services \& _batch_ jobs \
  that replaced manual exports
#compact-work-heading(
  "Data Analyst",
  "Fieldwork",
  dates: "2020 - 2022",
)
#block[
  + Shipped #emph[weekly] reports used by #text(weight: "bold", fill: rgb("#333"))[finance]
]

Jordan Example builds data tools
for small teams.
"""

TEX_RESUME = r"""\documentclass{article}
\usepackage{hyperref} % preamble comment
\begin{document}
\section{Experience}
\textbf{Northstar} \hfill 2022 - 2024 \\
\begin{itemize}
  \item Built the \textbf{billing} export % hidden note
    for 100\% of invoices \& refunds
  \item Documented it in \href{https://example.com}{the handbook}
\end{itemize}
\vspace{4pt}

Closing paragraph with~a tie and \emph{emphasis}.
\end{document}
"""

LETTER_SENTENCE = "The export service rebuilt at Fieldwork now runs every night without manual restarts."


def _letter(*, opening: str = "", company: str = "Northstar", sentences: int = 22) -> str:
    body = " ".join([LETTER_SENTENCE] * sentences)
    first = opening or f"The billing platform team at {company} is solving a problem that matches recent work."
    return "\n\n".join(
        [
            "Dear Hiring Manager,",
            first,
            body,
            "Thank you for your time and consideration.",
            "Sincerely,\nJordan Example",
        ]
    )


def _bullets(*lines: str) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _rules(result: dict) -> list[str]:
    return [finding["rule"] for finding in result["findings"]]


def _only(result: dict, rule: str) -> list[dict]:
    return [finding for finding in result["findings"] if finding["rule"] == rule]


class NormalizeKindTests(unittest.TestCase):
    def test_maps_tolerant_aliases(self):
        cases = {
            "resume": "resume",
            "CV": "resume",
            "resume_tailoring": "resume",
            "Resume Draft": "resume",
            "cover": "cover_letter",
            "cover-letter": "cover_letter",
            "letter": "cover_letter",
            "answer": "application_answers",
            "short_answer": "application_answers",
            "essay": "application_answers",
            "question": "application_answers",
            "application_answers": "application_answers",
            "outreach": "outreach",
            "email": "outreach",
            "LinkedIn": "outreach",
            "message": "outreach",
            "networking": "outreach",
            "referral": "outreach",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_kind(value), expected)

    def test_unknown_or_empty_raises_with_known_kinds(self):
        for value in ("", None, "spreadsheet"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as raised:
                    normalize_kind(value)
                for kind in KINDS:
                    self.assertIn(kind, str(raised.exception))

    def test_rules_for_returns_only_applicable_ids(self):
        resume = rules_for("cv")
        self.assertIn("weak_opener", resume)
        self.assertIn("scaffolding_leak", resume)
        self.assertNotIn("generic_enthusiasm", resume)
        self.assertNotIn("stock_opener", resume)

        letter = rules_for("cover letter")
        self.assertIn("jd_regurgitation", letter)
        self.assertIn("generic_enthusiasm", letter)
        self.assertNotIn("weak_opener", letter)
        self.assertNotIn("over_limit", letter)

        self.assertEqual(
            rules_for("application_answers"),
            ("scaffolding_leak", "unverified_number", "ai_tell", "generic_enthusiasm", "over_limit"),
        )
        self.assertEqual(
            rules_for("outreach"),
            (
                "scaffolding_leak",
                "unverified_number",
                "ai_tell",
                "generic_enthusiasm",
                "stock_opener",
                "too_long",
                "no_clear_ask",
            ),
        )

    def test_rule_ids_cover_every_kind_without_duplicates(self):
        self.assertEqual(len(RULE_IDS), len(set(RULE_IDS)))
        self.assertEqual(set(RULE_IDS), {rule for kind in KINDS for rule in rules_for(kind)})
        self.assertEqual(
            set(RULE_IDS),
            {
                "scaffolding_leak",
                "unverified_number",
                "ai_tell",
                "weak_opener",
                "manufactured_ending",
                "stack_inventory",
                "no_consequence",
                "first_person",
                "repeated_lead_verb",
                "bullet_length",
                "double_hyphen",
                "tense_mix",
                "generic_enthusiasm",
                "company_missing",
                "jd_regurgitation",
                "letter_length",
                "opens_with_name_or_role_recital",
                "over_limit",
                "stock_opener",
                "too_long",
                "no_clear_ask",
            },
        )


class ExtractionTests(unittest.TestCase):
    def test_typst_skips_definitions_and_comments_and_unwraps_markup(self):
        extracted = extract_material_text(TYPST_RESUME, "typst")

        self.assertEqual(
            extracted["bullets"],
            [
                {
                    "text": "Rebuilt the nightly ingestion job as incremental loads so analysts start with fresh data",
                    "line": 17,
                },
                {
                    "text": "Wrote the migration tool in Rust for C# services & batch jobs that replaced manual exports",
                    "line": 18,
                },
                {"text": "Shipped weekly reports used by finance", "line": 26},
            ],
        )
        self.assertEqual(
            extracted["paragraphs"],
            [{"text": "Jordan Example builds data tools for small teams.", "line": 29}],
        )
        self.assertEqual(
            extracted["plain"].split("\n"),
            [
                "Experience",
                "Software Engineer",
                "Northstar",
                "2022 - 2024",
                "Rebuilt the nightly ingestion job as incremental loads so analysts start with fresh data",
                "Wrote the migration tool in Rust for C# services & batch jobs that replaced manual exports",
                "Data Analyst",
                "Fieldwork",
                "2020 - 2022",
                "Shipped weekly reports used by finance",
                "Jordan Example builds data tools for small teams.",
            ],
        )
        for hidden in ("grid", "columns", "hidden bullet", "comment that looks", "template.typ", "margin"):
            self.assertNotIn(hidden, extracted["plain"])

    def test_typst_heading_calls_reach_plain_only(self):
        extracted = extract_material_text(
            '#work-heading("Software Engineer", "Northstar", location: "Remote")\n- Shipped the export service\n',
            "typ",
        )
        texts = [unit["text"] for unit in extracted["bullets"] + extracted["paragraphs"]]
        self.assertEqual(texts, ["Shipped the export service"])
        self.assertIn("Software Engineer", extracted["plain"])
        self.assertIn("Northstar", extracted["plain"])
        self.assertIn("Remote", extracted["plain"])

    def test_typst_escapes_and_dollar_and_at_signs_become_literal(self):
        extracted = extract_material_text(r"- Saved \$400 for jordan\@example.com \#1 \& more" + "\n", "typ")
        self.assertEqual(extracted["bullets"][0]["text"], "Saved $400 for jordan@example.com #1 & more")

    def test_tex_items_commands_comments_and_body_range(self):
        extracted = extract_material_text(TEX_RESUME, "latex")

        self.assertEqual(
            extracted["bullets"],
            [
                {"text": "Built the billing export for 100% of invoices & refunds", "line": 7},
                {"text": "Documented it in the handbook", "line": 9},
            ],
        )
        self.assertEqual(
            extracted["paragraphs"],
            [
                {"text": "Northstar 2022 - 2024", "line": 5},
                {"text": "Closing paragraph with a tie and emphasis.", "line": 13},
            ],
        )
        self.assertEqual(extracted["plain"].split("\n")[0], "Experience")
        for hidden in ("hidden note", "preamble comment", "hyperref", "itemize", "vspace", "example.com", "\\"):
            self.assertNotIn(hidden, extracted["plain"])

    def test_markdown_bullets_headings_and_soft_wrapped_paragraphs(self):
        source = (
            "# Jordan Example\n"
            "\n"
            "Builds data tools\n"
            "for **small** teams.\n"
            "\n"
            "## Experience\n"
            "- Shipped the [export service](https://example.com)\n"
            "  used by finance\n"
            "* Wrote `runbooks`\n"
            "1. Mentored interns\n"
        )
        extracted = extract_material_text(source, "markdown")

        self.assertEqual(
            extracted["bullets"],
            [
                {"text": "Shipped the export service used by finance", "line": 7},
                {"text": "Wrote runbooks", "line": 9},
                {"text": "Mentored interns", "line": 10},
            ],
        )
        self.assertEqual(
            extracted["paragraphs"], [{"text": "Builds data tools for small teams.", "line": 3}]
        )
        self.assertEqual(extracted["plain"].split("\n")[0], "Jordan Example")
        self.assertIn("Experience", extracted["plain"].split("\n"))

    def test_plain_text_bullet_markers_and_unknown_format_fallback(self):
        source = "Dear Team,\n\nFirst line\nsecond line.\n\n• Dot bullet\n– Dash bullet\n- Hyphen bullet\n"
        for fmt in ("text", "txt", "plain", "docx", ""):
            with self.subTest(fmt=fmt):
                extracted = extract_material_text(source, fmt)
                self.assertEqual(
                    [bullet["text"] for bullet in extracted["bullets"]],
                    ["Dot bullet", "Dash bullet", "Hyphen bullet"],
                )
                self.assertEqual([bullet["line"] for bullet in extracted["bullets"]], [6, 7, 8])
                self.assertEqual(
                    extracted["paragraphs"],
                    [{"text": "Dear Team,", "line": 1}, {"text": "First line second line.", "line": 3}],
                )
                self.assertEqual(
                    extracted["plain"],
                    "Dear Team,\nFirst line second line.\nDot bullet\nDash bullet\nHyphen bullet",
                )

    def test_typst_multiline_show_rule_and_letter_paragraphs(self):
        source = (
            '#import "letter.typ": letter\n'
            "#show: letter.with(\n"
            '  sender: "Jordan Example",\n'
            '  recipient: "Northstar Hiring Team",\n'
            ")\n"
            "\n"
            "Dear Northstar Hiring Team,\n"
            "\n"
            "The export service rebuilt at Fieldwork \\\n"
            "now runs every night. // drafting note\n"
            "\n"
            "Sincerely, \\\n"
            "Jordan Example\n"
        )
        extracted = extract_material_text(source, "typ")

        self.assertEqual(extracted["bullets"], [])
        self.assertEqual(
            extracted["paragraphs"],
            [
                {"text": "Dear Northstar Hiring Team,", "line": 7},
                {"text": "The export service rebuilt at Fieldwork now runs every night.", "line": 9},
                {"text": "Sincerely, Jordan Example", "line": 12},
            ],
        )
        self.assertNotIn("recipient", extracted["plain"])
        self.assertNotIn("drafting note", extracted["plain"])

    def test_tex_fragment_and_macro_items(self):
        source = (
            "\\resumeSubheading{Software Engineer}{2022 - 2024}\n"
            "\\resumeItemListStart\n"
            "  \\resumeItem{Rebuilt the \\textit{nightly} ingestion job}\n"
            "  \\resumeItem{Wrote contract tests for 3 consumers}\n"
            "\\resumeItemListEnd\n"
        )
        extracted = extract_material_text(source, "tex")

        self.assertEqual(
            extracted["bullets"],
            [
                {"text": "Rebuilt the nightly ingestion job", "line": 3},
                {"text": "Wrote contract tests for 3 consumers", "line": 4},
            ],
        )
        self.assertEqual(extracted["paragraphs"], [])
        self.assertEqual(extracted["plain"].split("\n")[0], "Software Engineer 2022 - 2024")

    def test_empty_source_extracts_nothing(self):
        self.assertEqual(extract_material_text("", "typ"), {"bullets": [], "paragraphs": [], "plain": ""})


class SharedRuleTests(unittest.TestCase):
    def test_strong_bullet_with_evidence_produces_no_findings(self):
        result = check_material(_bullets(STRONG_BULLET), kind="resume", evidence_corpus=STRONG_CORPUS)

        self.assertEqual(result["findings"], [])
        self.assertEqual(result["status"], "pass")

    def test_clean_resume_bullets_produce_no_findings(self):
        result = check_material(_bullets(*CLEAN_BULLETS), kind="resume")
        self.assertEqual(result["findings"], [])

    def test_scaffolding_leak_flags_placeholders_and_internal_terms(self):
        leaks = (
            "TODO confirm the launch date with the platform team lead",
            "Cut build time by XX% after replacing the cache layer",
            "Grew weekly signups by N% through onboarding fixes",
            "Excited about the mission at [Company] and its roadmap",
            "Dear [Hiring Manager], the export work maps to this role",
            "Shipped [insert metric here] to the finance team",
            "Would love to join <company> on the data team",
            "As an AI, I cannot verify this claim about the export",
            "As a language model I drafted this section for the role",
            "This proof point shows the export service rebuild",
            "Covers the tailoring requirement about streaming systems",
            "Matches the JD emphasis on reliability for exports",
            "An ATS-friendly summary of the export service work",
            "Added for keyword coverage of the streaming stack",
            "Lorem ipsum dolor sit amet for the export service",
        )
        for leak in leaks:
            with self.subTest(leak=leak):
                result = check_material(leak, kind="cover_letter")
                found = _only(result, "scaffolding_leak")
                self.assertEqual(len(found), 1, result["findings"])
                self.assertEqual(found[0]["severity"], "error")
                self.assertEqual(result["status"], "review")

    def test_scaffolding_leak_ignores_markup_and_legitimate_text(self):
        typst = (
            "#block[\n"
            "  - Worked as an AI engineer on retrieval, which cut review time for the support team\n"
            "]\n"
            "#align(center)[Northstar]\n"
        )
        self.assertNotIn("scaffolding_leak", _rules(check_material(typst, kind="resume", fmt="typ")))
        for clean in (
            "Completed a JD/MBA program before moving into product analytics",
            "Cited in the survey [1] on retrieval systems for support teams",
            "Works as an AI researcher on evaluation for retrieval systems",
        ):
            with self.subTest(clean=clean):
                self.assertNotIn("scaffolding_leak", _rules(check_material(clean, kind="outreach")))

    def test_scaffolding_leak_in_typst_heading_reports_line(self):
        result = check_material(
            '#work-heading("Software Engineer", "[Company]", "2022")\n- Shipped the export service used by finance\n',
            kind="resume",
            fmt="typ",
        )
        found = _only(result, "scaffolding_leak")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["where"], "line 1")
        self.assertIn("[Company]", found[0]["excerpt"])

    def test_unverified_number_fires_for_missing_percentage(self):
        result = check_material(
            _bullets("Reduced costs by 35% after consolidating the reporting warehouses"),
            kind="resume",
            evidence_corpus="Consolidated the reporting warehouses in 2023.",
        )
        found = _only(result, "unverified_number")

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "warning")
        self.assertIn("35%", found[0]["excerpt"])
        self.assertIn("35%", found[0]["fix"])
        self.assertIn(
            "Confirm the figure with the candidate or remove the precision; never invent metrics.",
            found[0]["fix"],
        )

    def test_unverified_number_is_skipped_without_corpus(self):
        result = check_material(
            _bullets("Reduced costs by 35% after consolidating the reporting warehouses"), kind="resume"
        )
        self.assertNotIn("unverified_number", _rules(result))

    def test_unverified_number_ignores_non_claims(self):
        lines = (
            "Maintained the export service from 2019 to 2023 and presented it in 2024",
            "Ported the scheduler to Python 3.11, which removed the legacy runtime",
            "Evaluated GPT-4 prompts stored on S3 and EC2 with OAuth2 and i18n support, v2",
            "Graduated with a GPA of 3.85/4.0 in 2021",
            "Reach Jordan Example at (555) 010-0199 or 555-010-0142",
            "Typeset the report at 10.5pt after the 2nd review at 221 Main Street",
            "Released on March 15 for Java 17 services and ISO 27001 audits",
        )
        for line in lines:
            with self.subTest(line=line):
                result = check_material(_bullets(line), kind="resume", evidence_corpus="Verified facts only.")
                self.assertNotIn("unverified_number", _rules(result))

    def test_unverified_number_matches_normalized_corpus_forms(self):
        corpus = (
            "Latency fell 40 percent. Revenue impact was 2 million dollars. The app serves 50,000 users. "
            "Throughput grew 3 times. The team owned 14 pipelines and 1,200 dashboards."
        )
        lines = (
            "Cut latency by 40% with a read-through cache",
            "Protected $2M in annual revenue by fixing billing retries",
            "Scaled the app to 50K users on a single region",
            "Raised throughput 3× by batching writes",
            "Owned 14 pipelines and 1,200 dashboards for the finance group",
        )
        result = check_material(_bullets(*lines), kind="resume", evidence_corpus=corpus)
        self.assertNotIn("unverified_number", _rules(result))

    def test_unverified_number_respects_unit_class(self):
        result = check_material(
            _bullets("Cut latency by 40% with a read-through cache"),
            kind="resume",
            evidence_corpus="The batch now finishes in 40 minutes.",
        )
        self.assertEqual(len(_only(result, "unverified_number")), 1)

    def test_unverified_number_covers_each_claim_shape(self):
        claims = {
            "Raised throughput 10x by batching writes": "10x",
            "Protected $15,000 in monthly revenue with retries": "$15,000",
            "Scaled the app to 2M+ sessions on one region": "2M+",
            "Onboarded 100+ analysts to the metrics layer": "100+",
            "Supported 120 users during the migration window": "120",
            "Led a 12-person migration crew across two offices": "12",
        }
        for line, surface in claims.items():
            with self.subTest(line=line):
                result = check_material(_bullets(line), kind="resume", evidence_corpus="Verified facts only.")
                found = _only(result, "unverified_number")
                self.assertEqual(len(found), 1, result["findings"])
                self.assertIn(f'"{surface}"', found[0]["fix"])

    def test_unverified_number_reports_distinct_values_once_and_caps_at_eight(self):
        repeated = check_material(
            _bullets(
                "Cut latency by 35% with a read-through cache",
                "Kept the 35% latency gain after the regional failover",
            ),
            kind="resume",
            evidence_corpus="Verified facts only.",
        )
        self.assertEqual(len(_only(repeated, "unverified_number")), 1)

        many = check_material(
            _bullets(*[f"Cut latency by {value}% with a read-through cache" for value in range(11, 23)]),
            kind="resume",
            evidence_corpus="Verified facts only.",
        )
        self.assertEqual(len(_only(many, "unverified_number")), 8)

    def test_ai_tell_reports_each_phrase_once_with_merged_positions(self):
        result = check_material(
            _bullets(
                "Leveraged Kafka to replay failed billing events, which removed manual reconciliation",
                "Wrote the on-call runbook that replaced tribal knowledge without escalation",
                "Leveraging the same queue, shipped robust retries that prevented duplicate invoices",
            ),
            kind="resume",
        )
        found = _only(result, "ai_tell")

        self.assertEqual([finding["where"] for finding in found], ["bullets 1, 3", "bullet 3 (line 3)"])
        self.assertTrue(all(finding["severity"] == "note" for finding in found))
        self.assertIn("Leveraged", found[0]["fix"])
        self.assertIn("robust", found[1]["fix"])
        self.assertEqual(result["status"], "pass")

    def test_ai_tell_catalogue(self):
        phrases = (
            "We delve into retrieval quality every week",
            "A rich tapestry of services supports the export",
            "The launch is a testament to careful planning",
            "In today's fast-paced market the export matters",
            "The ever-evolving data stack needs owners",
            "Helped teams navigate the complexities of billing",
            "The work sits at the intersection of data and product",
            "It's worth noting that the export runs nightly",
            "The service not only exports invoices but also reconciles refunds",
            "The export seamlessly connects to the ledger",
            "The team utilized a queue for retries",
            "Jordan spearheaded the export rebuild",
            "The teams found synergies across billing",
            "A cutting-edge retrieval system backs the search",
            "A state-of-the-art retrieval system backs the search",
            "A robust retry layer backs the export",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                result = check_material(phrase, kind="application_answers")
                self.assertEqual(len(_only(result, "ai_tell")), 1, result["findings"])

    def test_ai_tell_ignores_plain_writing_and_leverage_as_noun(self):
        for clean in (
            "The retry layer gave the finance team more leverage in vendor negotiations",
            "Modeled a leveraged buyout for the finance course capstone",
            "The export runs nightly and reconciles refunds before analysts start",
        ):
            with self.subTest(clean=clean):
                self.assertNotIn("ai_tell", _rules(check_material(clean, kind="application_answers")))


class ResumeRuleTests(unittest.TestCase):
    def test_weak_opener(self):
        openers = (
            "Responsible for maintaining the export service that finance adopted",
            "Worked on the export service that finance adopted",
            "Helped to migrate the export service that finance adopted",
            "Assisted with the export migration that finance adopted",
            "Participated in the export migration that finance adopted",
            "Involved in the export migration that finance adopted",
            "Tasked with the export migration that finance adopted",
            "Duties included the export migration that finance adopted",
            "In charge of the export migration that finance adopted",
            "Contributed to the export migration that finance adopted",
            "Exposure to the export migration that finance adopted",
            "Familiar with the export migration that finance adopted",
            "Gained experience with the export migration that finance adopted",
        )
        for opener in openers:
            with self.subTest(opener=opener):
                found = _only(check_material(_bullets(opener), kind="resume"), "weak_opener")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["severity"], "warning")
                self.assertEqual(found[0]["where"], "bullet 1 (line 1)")
                self.assertEqual(found[0]["fix"], "Lead with what you built or decided, then the consequence.")

        self.assertNotIn("weak_opener", _rules(check_material(_bullets(*CLEAN_BULLETS), kind="resume")))

    def test_manufactured_ending(self):
        endings = (
            "Refactored the export service, improving overall efficiency",
            "Rewrote the scheduler core, enhancing reliability",
            "Automated the weekly report, increasing productivity",
            "Introduced a ticket template, streamlining workflows",
            "Tuned the query planner, optimizing performance",
            "Added integration tests across services, ensuring quality",
            "Partnered with finance on reporting, driving business value",
        )
        for ending in endings:
            with self.subTest(ending=ending):
                result = check_material(_bullets(ending), kind="resume")
                found = _only(result, "manufactured_ending")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["severity"], "warning")
                self.assertIn("Name the actual consequence", found[0]["fix"])
                self.assertNotIn("no_consequence", _rules(result))

    def test_manufactured_ending_allows_measured_or_specific_outcomes(self):
        result = check_material(
            _bullets(
                "Tuned the query planner, improving performance of the nightly export from 50 to 12 minutes",
                *CLEAN_BULLETS,
            ),
            kind="resume",
        )
        self.assertNotIn("manufactured_ending", _rules(result))

    def test_stack_inventory_fires_on_technology_lists(self):
        for line in (
            "Built a dashboard using React, Node.js, PostgreSQL, Docker, and AWS",
            "Developed billing services in Python, Go, Rust, and Kotlin",
            "React, Node.js, PostgreSQL, Docker, AWS, Terraform",
        ):
            with self.subTest(line=line):
                found = _only(check_material(_bullets(line), kind="resume"), "stack_inventory")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["severity"], "warning")
                self.assertIn("Skills section carries the inventory", found[0]["fix"])

    def test_stack_inventory_ignores_mechanism_bullets_and_non_technology_lists(self):
        for line in (
            "Designed a retrieval pipeline with pgvector that cut lookup latency from 900 ms to 120 ms",
            "Partnered with Marketing, Sales, Finance, and Legal to launch the pricing page",
            "Ran user interviews in Boston, Denver, Austin, and Chicago that reshaped onboarding",
            "Presented at Northstar Data Summit, Fieldwork Research Day, and Regional Analytics Forum",
            "Presented findings in Q1, Q2, Q3, and Q4 reviews that reshaped the roadmap",
            "Launched billing in US, EU, UK, and APAC regions without a freeze",
        ):
            with self.subTest(line=line):
                self.assertNotIn("stack_inventory", _rules(check_material(_bullets(line), kind="resume")))

    def test_stack_inventory_skips_skills_section_and_labelled_lines(self):
        source = (
            "## Skills\n"
            "- Python, Go, Rust, Kotlin, PostgreSQL, Docker\n"
            "\n"
            "## Experience\n"
            f"- {STRONG_BULLET}\n"
            "- Languages: Python, Go, Rust, Kotlin, TypeScript\n"
        )
        self.assertEqual(check_material(source, kind="resume", fmt="md")["findings"], [])

    def test_plain_text_section_titles_scope_evidence_rules(self):
        source = (
            "EXPERIENCE\n"
            f"- {STRONG_BULLET}\n"
            "\n"
            "EDUCATION\n"
            "- Dean's List 2022\n"
            "\n"
            "TECHNICAL SKILLS\n"
            "- Familiar with Python, Go, Rust, Kotlin, PostgreSQL\n"
        )
        result = check_material(source, kind="resume")

        self.assertEqual(result["findings"], [])
        self.assertEqual(result["summary"]["paragraphs"], 0)
        self.assertEqual(result["summary"]["bullets"], 3)

    def test_no_consequence(self):
        result = check_material(
            _bullets("Maintained the export service for the finance reporting group", *CLEAN_BULLETS),
            kind="resume",
        )
        found = _only(result, "no_consequence")

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "note")
        self.assertEqual(found[0]["where"], "bullet 1 (line 1)")
        self.assertEqual(
            found[0]["fix"],
            "Consequence is implicit; state what changed because of this work (quantification optional).",
        )
        self.assertEqual(result["status"], "pass")

    def test_no_consequence_skips_short_or_consequential_bullets(self):
        result = check_material(
            _bullets(
                "Maintained the export service",
                "Maintained the export service for 3 finance reporting groups",
                "Maintained the export service so finance closes the books unassisted",
                "Maintained the export service, enabling finance to close the books unassisted",
                "Moved finance reporting from spreadsheets to the export service",
            ),
            kind="resume",
        )
        self.assertNotIn("no_consequence", _rules(result))

    def test_first_person(self):
        for line in (
            "I rebuilt the export service that finance adopted",
            "Rebuilt the export service that our finance group adopted",
            "Rebuilt the export service so we could close the books unassisted",
            "Rebuilt the export service, where I've since removed manual restarts",
        ):
            with self.subTest(line=line):
                found = _only(check_material(_bullets(line), kind="resume"), "first_person")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["severity"], "warning")

        paragraph = check_material("Engineer who ships data tools; my focus is billing systems.", kind="resume")
        self.assertEqual(_only(paragraph, "first_person")[0]["where"], "paragraph 1 (line 1)")

    def test_first_person_ignores_numerals_and_abbreviations(self):
        source = (
            "Software Engineer I at Northstar, Portland, ME\n\n"
            "me@example.com | my.site@example.com | example.com/me\n\n"
            "- Shipped Phase I of the export service that finance adopted\n"
            "- Wrote the WE-42 runbook that replaced tribal knowledge\n"
        )
        self.assertNotIn("first_person", _rules(check_material(source, kind="resume")))
        letter = check_material(_letter(opening="I rebuilt the export service at Fieldwork."), kind="cover_letter")
        self.assertNotIn("first_person", _rules(letter))

    def test_repeated_lead_verb(self):
        result = check_material(
            _bullets(
                "Built the export service that finance adopted",
                CLEAN_BULLETS[1],
                "Built the retry queue that prevented duplicate invoices",
                "Built the on-call runbook that replaced tribal knowledge",
            ),
            kind="resume",
        )
        found = _only(result, "repeated_lead_verb")

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "note")
        self.assertEqual(found[0]["where"], "bullets 1, 3, 4")
        self.assertIn("Built", found[0]["excerpt"])

        twice = check_material(
            _bullets(
                "Built the export service that finance adopted",
                "Built the retry queue that prevented duplicate invoices",
            ),
            kind="resume",
        )
        self.assertNotIn("repeated_lead_verb", _rules(twice))

    def test_bullet_length(self):
        long_bullet = "Rebuilt the export service so finance closes the books unassisted " + " ".join(
            ["and reconciles refunds"] * 13
        )
        result = check_material(_bullets("Shipped the export", long_bullet, *CLEAN_BULLETS), kind="resume")
        found = _only(result, "bullet_length")

        self.assertEqual([finding["where"] for finding in found], ["bullet 1 (line 1)", "bullet 2 (line 2)"])
        self.assertIn("Too thin to carry evidence.", found[0]["fix"])
        self.assertIn("Split or cut; one mechanism and one consequence per bullet.", found[1]["fix"])
        self.assertTrue(all(finding["severity"] == "note" for finding in found))
        self.assertNotIn("bullet_length", _rules(check_material(_bullets(*CLEAN_BULLETS), kind="resume")))

    def test_double_hyphen_only_when_configured(self):
        source = (
            '#work-heading("Software Engineer", "Northstar", "2022 -- 2024")\n'
            f"- {STRONG_BULLET}\n"
            '#work-heading("Data Analyst", "Fieldwork", "2020 -- 2022")\n'
        )
        config = {"writing": {"single_hyphen_ranges": True}}

        found = _only(check_material(source, kind="resume", fmt="typ", config=config), "double_hyphen")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "warning")
        self.assertEqual(found[0]["where"], "lines 1, 3")
        self.assertIn("2022 -- 2024", found[0]["excerpt"])

        for other in (None, {}, {"writing": {"single_hyphen_ranges": False}}, {"writing": "invalid"}):
            with self.subTest(config=other):
                result = check_material(source, kind="resume", fmt="typ", config=other)
                self.assertNotIn("double_hyphen", _rules(result))

        clean = check_material(source.replace("--", "-"), kind="resume", fmt="typ", config=config)
        self.assertNotIn("double_hyphen", _rules(clean))

    def test_tense_mix(self):
        bullets = [
            "Rebuilt the export service that finance adopted",
            "Designed the retry queue that prevented duplicate invoices",
            "Maintains the on-call runbook that replaced tribal knowledge",
            "Migrated billing exports without downtime for the ledger",
            "Wrote the reconciliation job that removed manual checks",
            "Automated the weekly report that finance adopted",
            "Leading the warehouse migration that replaced nightly dumps",
            "Shipped the audit log that prevented silent edits",
        ]
        found = _only(check_material(_bullets(*bullets), kind="resume"), "tense_mix")

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "note")
        self.assertEqual(found[0]["where"], "bullets 3, 7")
        self.assertEqual(found[0]["excerpt"], '"Maintains", "Leading"')
        self.assertIn("past tense", found[0]["fix"])

    def test_tense_mix_stays_quiet_when_consistent_or_unsure(self):
        past = [
            "Rebuilt the export service that finance adopted",
            "Designed the retry queue that prevented duplicate invoices",
            "Migrated billing exports without downtime for the ledger",
            "Wrote the reconciliation job that removed manual checks",
            "Automated the weekly report that finance adopted",
            "Shipped the audit log that prevented silent edits",
        ]
        current_role = [
            "Maintains the on-call runbook that replaced tribal knowledge",
            "Leads the warehouse migration that replaced nightly dumps",
        ]
        one_outlier = ["Leading the warehouse migration that replaced nightly dumps"]
        for bullets in (past, current_role + past, past[:3] + one_outlier + past[3:]):
            with self.subTest(first=bullets[0], count=len(bullets)):
                self.assertNotIn("tense_mix", _rules(check_material(_bullets(*bullets), kind="resume")))


class CoverLetterRuleTests(unittest.TestCase):
    def test_clean_letter_passes(self):
        result = check_material(_letter(), kind="cover_letter", company="Northstar, Inc.")

        self.assertEqual(result["findings"], [])
        self.assertEqual(result["status"], "pass")

    def test_generic_enthusiasm(self):
        phrases = (
            "I am very excited to apply for this role.",
            "I'm thrilled to submit this application.",
            "I am writing to express interest in the platform team.",
            "Jordan is passionate about data tooling.",
            "This is a dream role for a data engineer.",
            "The background is a perfect fit.",
            "The background is a strong fit for the platform team.",
            "Northstar is an esteemed company in payments.",
            "Thrives in a fast-paced environment.",
            "I believe I would be an asset to the team.",
            "Ready to hit the ground running on billing.",
            "Known to think outside the box on billing.",
            "A team player on every project.",
            "Happy to wear many hats on a small team.",
        )
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                found = _only(check_material(_letter(opening=phrase), kind="cover_letter"), "generic_enthusiasm")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["severity"], "warning")
                self.assertEqual(found[0]["where"], "paragraph 2 (line 3)")

    def test_closing_thanks_is_not_generic_enthusiasm(self):
        letter = _letter()
        self.assertIn("Thank you for your time and consideration.", letter)
        self.assertNotIn("generic_enthusiasm", _rules(check_material(letter, kind="cover_letter")))

    def test_company_missing_and_present(self):
        missing = check_material(_letter(company="the company"), kind="cover_letter", company="Northstar, Inc.")
        found = _only(missing, "company_missing")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "warning")
        self.assertEqual(found[0]["where"], "letter")
        self.assertIn("Northstar, Inc.", found[0]["excerpt"])

        for company in ("Northstar, Inc.", "NORTHSTAR LLC", "Northstar Corp.", "northstar ltd"):
            with self.subTest(company=company):
                present = check_material(_letter(), kind="cover_letter", company=company)
                self.assertNotIn("company_missing", _rules(present))

        possessive = check_material(
            _letter(opening="Northstar's billing platform matches recent work on exports."),
            kind="cover_letter",
            company="Northstar, Inc.",
        )
        self.assertNotIn("company_missing", _rules(possessive))
        self.assertNotIn("company_missing", _rules(check_material(_letter(company="the company"), kind="cover_letter")))

    def test_jd_regurgitation(self):
        job_description = (
            "About the role. You will design and operate reliable data pipelines that serve "
            "product analytics teams across the company. You will also mentor engineers."
        )
        copied = _letter(
            opening=(
                "At Northstar the plan is to design and operate reliable data pipelines that serve "
                "product analytics teams, building on the Fieldwork export."
            )
        )
        found = _only(
            check_material(copied, kind="cover_letter", job_description=job_description), "jd_regurgitation"
        )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "warning")
        self.assertEqual(found[0]["where"], "paragraph 2 (line 3)")
        self.assertEqual(
            found[0]["excerpt"],
            "design and operate reliable data pipelines that serve product analytics teams",
        )
        self.assertIn("11 consecutive words", found[0]["fix"])

        short_overlap = _letter(opening="At Northstar the plan is to design and operate reliable data pipelines daily.")
        result = check_material(short_overlap, kind="cover_letter", job_description=job_description)
        self.assertNotIn("jd_regurgitation", _rules(result))

    def test_jd_regurgitation_is_case_and_punctuation_insensitive_and_capped(self):
        runs = [
            f"own the {topic} roadmap and ship measured improvements every single quarter"
            for topic in ("billing", "ledger", "search", "export")
        ]
        job_description = ". ".join(runs)
        letter = "\n\n".join(f"Ready to {run.upper().replace(' and ', ', and ')}!" for run in runs)
        found = _only(
            check_material(letter, kind="cover_letter", job_description=job_description), "jd_regurgitation"
        )
        self.assertEqual(len(found), 3)

    def test_letter_length_uses_default_and_configured_range(self):
        short = _only(check_material(_letter(sentences=3), kind="cover_letter"), "letter_length")
        self.assertEqual(len(short), 1)
        self.assertEqual(short[0]["severity"], "note")
        self.assertEqual(short[0]["where"], "letter")
        self.assertIn("250-420", short[0]["fix"])
        self.assertIn("diagnostic, not a target", short[0]["fix"])
        words = int(short[0]["excerpt"].split()[0])
        self.assertIn(f"{words} words", short[0]["fix"])
        self.assertLess(words, 250)

        long = _only(check_material(_letter(sentences=40), kind="cover_letter"), "letter_length")
        self.assertEqual(len(long), 1)

        self.assertNotIn("letter_length", _rules(check_material(_letter(), kind="cover_letter")))
        config = {"writing": {"cover_letter_words": [40, 90]}}
        configured = check_material(_letter(sentences=3), kind="cover_letter", config=config)
        self.assertNotIn("letter_length", _rules(configured))
        over = _only(check_material(_letter(), kind="cover_letter", config=config), "letter_length")
        self.assertIn("40-90", over[0]["fix"])

    def test_opens_with_name_or_role_recital(self):
        for opening in (
            "My name is Jordan Example and the billing platform is the draw.",
            "I am a recent computer science graduate with internship experience.",
            "I'm a backend engineer who rebuilt billing exports.",
        ):
            with self.subTest(opening=opening):
                found = _only(
                    check_material(_letter(opening=opening), kind="cover_letter"),
                    "opens_with_name_or_role_recital",
                )
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["severity"], "note")
                self.assertEqual(found[0]["where"], "paragraph 2 (line 3)")

        inline = check_material(
            "Dear Dr. Rivera, my name is Jordan Example and the billing platform is the draw.",
            kind="cover_letter",
        )
        self.assertIn("opens_with_name_or_role_recital", _rules(inline))
        self.assertNotIn("opens_with_name_or_role_recital", _rules(check_material(_letter(), kind="cover_letter")))


class ApplicationAnswerRuleTests(unittest.TestCase):
    def test_over_limit(self):
        answer = "The export service rebuilt at Fieldwork runs nightly without manual restarts."
        result = check_material(answer, kind="application_answers", max_chars=40)
        found = _only(result, "over_limit")

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "error")
        self.assertEqual(found[0]["where"], "answer")
        self.assertIn(str(len(answer)), found[0]["excerpt"])
        self.assertIn("40", found[0]["excerpt"])
        self.assertIn(str(len(answer) - 40), found[0]["fix"])
        self.assertEqual(result["status"], "review")

    def test_within_limit_or_no_limit_is_clean(self):
        answer = "The export service rebuilt at Fieldwork runs nightly without manual restarts."
        for limit in (len(answer), 500, None):
            with self.subTest(limit=limit):
                result = check_material(answer, kind="short_answer", max_chars=limit)
                self.assertEqual(result["findings"], [])

    def test_over_limit_counts_blank_lines_in_plain_text(self):
        answer = "First paragraph here.\n\nSecond paragraph here."
        result = check_material(answer, kind="application_answers", max_chars=len(answer) - 1)
        self.assertIn("over_limit", _rules(result))

    def test_generic_enthusiasm_applies_to_answers(self):
        result = check_material("I am excited to apply because billing is a dream job.", kind="essay")
        self.assertEqual(len(_only(result, "generic_enthusiasm")), 2)
        self.assertNotIn("weak_opener", rules_for("essay"))


class OutreachRuleTests(unittest.TestCase):
    CLEAN = (
        "Hi Rivera,\n\n"
        "Your talk on idempotent billing queues changed how the Fieldwork export handles retries. "
        "Would you be open to a 15-minute call about how Northstar staffs that team?\n\n"
        "Jordan Example"
    )

    def test_clean_outreach_passes(self):
        result = check_material(self.CLEAN, kind="outreach")
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["status"], "pass")

    def test_stock_opener(self):
        openers = (
            "I hope this message finds you well.",
            "I hope you're doing well.",
            "I hope you are doing well.",
            "My name is Jordan Example.",
            "I came across your profile last week.",
            "I wanted to reach out about Northstar.",
            "Sorry to bother you with this.",
        )
        for opener in openers:
            with self.subTest(opener=opener):
                found = _only(check_material(f"{opener} {self.CLEAN}", kind="outreach"), "stock_opener")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["severity"], "warning")

    def test_too_long_warns_over_150_and_notes_from_110(self):
        ask = "Could you share how the team is staffed?"
        filler = "The export now runs nightly."

        def message(words: int) -> str:
            base = ask.split()
            text = " ".join(base + (filler.split() * 40)[: words - len(base)])
            return text

        over = _only(check_material(message(151), kind="outreach"), "too_long")
        self.assertEqual([finding["severity"] for finding in over], ["warning"])
        self.assertEqual(over[0]["excerpt"], "151 words")
        self.assertEqual(over[0]["where"], "message")

        for words in (110, 150):
            with self.subTest(words=words):
                note = _only(check_material(message(words), kind="outreach"), "too_long")
                self.assertEqual([finding["severity"] for finding in note], ["note"])

        self.assertNotIn("too_long", _rules(check_material(message(109), kind="outreach")))

    def test_no_clear_ask(self):
        statement = "Your talk on idempotent billing queues changed how the Fieldwork export handles retries."
        found = _only(check_material(statement, kind="outreach"), "no_clear_ask")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "note")
        self.assertEqual(found[0]["where"], "message")
        self.assertEqual(found[0]["excerpt"], statement)

        signed = check_material(f"Hi Rivera,\n\n{statement}\n\nThanks,\nJordan", kind="outreach")
        self.assertEqual(_only(signed, "no_clear_ask")[0]["excerpt"], statement)

        for ask in (
            "Is the team hiring?",
            "Would you be open to a short call.",
            "Could you point to the right person.",
            "Can you share the team structure.",
            "Would it be possible to talk next week.",
            "Happy to send a short summary first.",
            "Let me know if a call works.",
        ):
            with self.subTest(ask=ask):
                self.assertNotIn("no_clear_ask", _rules(check_material(f"{statement} {ask}", kind="outreach")))

    def test_generic_enthusiasm_applies_to_outreach(self):
        result = check_material(f"Billing is a dream job. {self.CLEAN}", kind="linkedin")
        self.assertEqual(len(_only(result, "generic_enthusiasm")), 1)


class CoverageTests(unittest.TestCase):
    MATERIAL = _bullets(
        "Built an Airflow pipeline that loads billing data nightly so analysts start with fresh numbers",
        "Deployed the scheduler on Kubernetes, which removed the shared cron host",
    )

    def test_absent_without_requirements_or_job_description(self):
        self.assertNotIn("coverage", check_material(self.MATERIAL, kind="resume"))

    def test_requirement_coverage_with_stemming(self):
        requirements = [
            "Experience building data pipelines with Airflow",
            "Strong knowledge of Kubernetes and Terraform",
            "Proficiency deploying gRPC services with Kafka and Terraform",
            "Excellent communication skills",
        ]
        result = check_material(self.MATERIAL, kind="resume", requirements=requirements)
        coverage = result["coverage"]

        self.assertEqual(coverage["requirements_total"], 4)
        self.assertEqual(coverage["requirements_covered"], 2)
        self.assertEqual(
            coverage["uncovered"],
            [
                {
                    "requirement": "Proficiency deploying gRPC services with Kafka and Terraform",
                    "missing_terms": ["grpc", "services", "kafka", "terraform"],
                },
                {"requirement": "Excellent communication skills", "missing_terms": ["communication"]},
            ],
        )
        self.assertEqual(coverage["note"], "Add a missing term only where verified experience supports it.")
        self.assertNotIn("jd_terms_missing", coverage)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["status"], "pass")

    def test_requirement_clip_and_missing_term_cap(self):
        requirement = "Operate " + ", ".join(f"platform{index}" for index in range(40))
        coverage = check_material(self.MATERIAL, kind="resume", requirements=[requirement])["coverage"]

        self.assertEqual(coverage["requirements_covered"], 0)
        self.assertEqual(len(coverage["uncovered"][0]["missing_terms"]), 5)
        self.assertLessEqual(len(coverage["uncovered"][0]["requirement"]), 160)
        self.assertTrue(coverage["uncovered"][0]["requirement"].endswith("…"))

    def test_stemming_variants_match(self):
        pairs = (
            ("pipelines", "pipeline"),
            ("deploying", "deployed"),
            ("services", "service"),
            ("fine-tuning", "fine-tuned"),
            ("queries", "query"),
            ("APIs", "api"),
            ("c++", "C++"),
            ("node.js", "Node.js"),
            ("CI/CD", "ci and cd"),
        )
        for required, written in pairs:
            with self.subTest(required=required):
                coverage = check_material(
                    f"Notes about {written} for the ledger group", kind="outreach", requirements=[required]
                )["coverage"]
                self.assertEqual(coverage["requirements_covered"], 1, coverage)

    def test_jd_terms_missing_orders_by_frequency_then_alphabet(self):
        job_description = (
            "We run Kafka and gRPC services on Kubernetes. Kafka experience is required.\n"
            "You will tune Postgres queries and write Terraform modules with node.js tooling.\n"
            "Our queries and modules matter. Northstar values careful billing work.\n"
        )
        result = check_material(
            self.MATERIAL, kind="resume", job_description=job_description, company="Northstar"
        )
        coverage = result["coverage"]

        self.assertEqual(
            coverage["jd_terms_missing"],
            ["kafka", "grpc", "node.js", "postgres", "terraform"],
        )
        self.assertNotIn("requirements_total", coverage)
        self.assertEqual(coverage["note"], "Add a missing term only where verified experience supports it.")
        self.assertEqual(result["findings"], [])

    def test_jd_terms_missing_skips_boilerplate_locations_and_company(self):
        job_description = (
            "Data Platform Engineer\n"
            "Northstar - Springfield, IL (Hybrid)\n"
            "Northstar is an Equal Opportunity Employer.\n"
            "- 3+ years of experience with Flink\n"
            "- Bachelor's degree in Computer Science\n"
        )
        coverage = check_material(
            self.MATERIAL, kind="resume", job_description=job_description, company="Northstar, Inc."
        )["coverage"]

        self.assertEqual(coverage["jd_terms_missing"], ["flink"])

    def test_jd_terms_missing_is_capped_at_fifteen(self):
        terms = [f"platform{index:02d}" for index in range(20)]
        coverage = check_material(self.MATERIAL, kind="resume", job_description=" ".join(terms))["coverage"]

        self.assertEqual(coverage["jd_terms_missing"], terms[:15])


class OutputContractTests(unittest.TestCase):
    MIXED = _bullets(
        "Maintained the export service for the finance reporting group",
        "Responsible for the export migration that finance adopted",
        "Shipped the [insert metric] dashboard that finance adopted",
        STRONG_BULLET,
        "Worked on the retry queue that prevented duplicate invoices",
        "TODO describe the ledger migration that finance adopted",
    )

    def test_status_and_summary_match_findings(self):
        result = check_material(self.MIXED, kind="resume")

        self.assertEqual(result["kind"], "resume")
        self.assertEqual(result["status"], "review")
        self.assertEqual(result["summary"]["bullets"], 6)
        self.assertEqual(result["summary"]["paragraphs"], 0)
        self.assertEqual(result["summary"]["words"], sum(len(line.split()) for line in self.MIXED.splitlines()) - 6)
        for key, severity in (("errors", "error"), ("warnings", "warning"), ("notes", "note")):
            self.assertEqual(
                result["summary"][key],
                sum(1 for finding in result["findings"] if finding["severity"] == severity),
            )
        self.assertEqual(result["summary"]["errors"], 2)
        self.assertEqual(result["summary"]["warnings"], 2)
        self.assertEqual(result["summary"]["notes"], 1)
        self.assertNotIn("findings_truncated", result)
        self.assertNotIn("coverage", result)
        for finding in result["findings"]:
            self.assertEqual(set(finding), {"rule", "severity", "where", "excerpt", "fix"})
            self.assertIn(finding["rule"], RULE_IDS)
            self.assertTrue(finding["excerpt"])
            self.assertTrue(finding["fix"])

    def test_notes_alone_keep_status_pass(self):
        result = check_material(
            _bullets("Maintained the export service for the finance reporting group"), kind="resume"
        )
        self.assertEqual(result["summary"]["notes"], 1)
        self.assertEqual(result["status"], "pass")

    def test_findings_sort_by_severity_then_position(self):
        result = check_material(self.MIXED, kind="resume")

        self.assertEqual(
            [(finding["rule"], finding["where"]) for finding in result["findings"]],
            [
                ("scaffolding_leak", "bullet 3 (line 3)"),
                ("scaffolding_leak", "bullet 6 (line 6)"),
                ("weak_opener", "bullet 2 (line 2)"),
                ("weak_opener", "bullet 5 (line 5)"),
                ("no_consequence", "bullet 1 (line 1)"),
            ],
        )

    def test_max_findings_truncates_and_reports_overflow(self):
        full = check_material(self.MIXED, kind="resume")
        result = check_material(self.MIXED, kind="resume", max_findings=2)

        self.assertEqual(result["findings"], full["findings"][:2])
        self.assertEqual(result["findings_truncated"], 3)
        self.assertEqual(result["summary"], full["summary"])
        self.assertEqual(result["status"], "review")

        none = check_material(self.MIXED, kind="resume", max_findings=0)
        self.assertEqual(none["findings"], [])
        self.assertEqual(none["findings_truncated"], 5)

        unlimited = check_material(self.MIXED, kind="resume", max_findings=None)
        self.assertEqual(unlimited["findings"], full["findings"])
        self.assertNotIn("findings_truncated", unlimited)

    def test_excerpt_is_clipped_to_140_characters(self):
        long_bullet = "Responsible for " + " ".join(["the export migration that finance adopted"] * 8)
        result = check_material(_bullets(long_bullet), kind="resume")
        excerpt = _only(result, "weak_opener")[0]["excerpt"]

        self.assertEqual(len(excerpt), 140)
        self.assertTrue(excerpt.endswith("…"))
        self.assertTrue(excerpt.startswith("Responsible for"))

    def test_excerpt_window_quotes_text_deep_in_long_paragraph(self):
        paragraph = " ".join([LETTER_SENTENCE] * 6) + " I am passionate about billing systems."
        found = _only(check_material(paragraph, kind="cover_letter"), "generic_enthusiasm")

        self.assertLessEqual(len(found[0]["excerpt"]), 140)
        self.assertIn("passionate about", found[0]["excerpt"])
        self.assertTrue(found[0]["excerpt"].startswith("…"))

    def test_fourteen_bullet_resume_report_is_compact_json(self):
        bullets = [
            STRONG_BULLET,
            "Designed a retrieval pipeline with pgvector that cut lookup latency from 900 ms to 120 ms",
            "Wrote the on-call runbook that replaced tribal knowledge without escalation",
            "Migrated billing exports to an idempotent queue, which prevented duplicate invoices",
            "Responsible for maintaining the export service that finance adopted",
            "Built a dashboard using React, Node.js, PostgreSQL, Docker, and AWS",
            "Automated the weekly report, improving overall efficiency",
            "Maintained the ledger service for the finance reporting group",
            "Leveraged Kafka to replay failed billing events, which removed manual reconciliation",
            "Reduced warehouse costs by 35% after consolidating reporting clusters",
            "Shipped the audit log that prevented silent edits to invoices",
            "Presented the retry design at the Fieldwork engineering forum",
            "Replaced nightly dumps with change capture so dashboards stay current",
            "Mentored two interns who shipped the refund reconciliation job",
        ]
        result = check_material(
            _bullets(*bullets),
            kind="resume",
            evidence_corpus=STRONG_CORPUS + " Lookup latency went from 900 ms to 120 ms.",
            requirements=["Experience with Kubernetes and Terraform", "Build reliable data pipelines"],
            job_description="We run Kafka and gRPC services. Kafka and Terraform experience is required.",
            company="Northstar",
            candidate_name="Jordan Example",
        )
        payload = json.dumps(result)

        self.assertEqual(result["summary"]["bullets"], 14)
        self.assertEqual(
            sorted(_rules(result)),
            [
                "ai_tell",
                "manufactured_ending",
                "no_consequence",
                "stack_inventory",
                "unverified_number",
                "weak_opener",
            ],
        )
        self.assertEqual(result["coverage"]["requirements_covered"], 1)
        self.assertLess(len(payload.encode("utf-8")), 5000)
        self.assertEqual(json.loads(payload), result)

    def test_every_kind_serializes_and_accepts_empty_source(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                result = check_material("", kind=kind, requirements=["Kubernetes"], job_description="Kafka Kafka")
                json.dumps(result)
                self.assertEqual(result["kind"], kind)
                self.assertEqual(result["summary"]["words"], 0)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            check_material("text", kind="spreadsheet")

    def test_output_is_deterministic(self):
        first = json.dumps(check_material(self.MIXED, kind="resume", job_description="Kafka Kafka gRPC"))
        second = json.dumps(check_material(self.MIXED, kind="resume", job_description="Kafka Kafka gRPC"))
        self.assertEqual(first, second)

    def test_module_is_standard_library_only(self):
        with open(content_qa.__file__, encoding="utf-8") as handle:
            source = handle.read()
        imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
        self.assertEqual(
            imports,
            [
                "from __future__ import annotations",
                "import re",
                "from dataclasses import dataclass",
                "from typing import Any, Callable",
            ],
        )


if __name__ == "__main__":
    unittest.main()
