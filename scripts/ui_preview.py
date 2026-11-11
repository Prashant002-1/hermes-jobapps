"""Open the cockpit on a throwaway workspace filled with invented sample data.

    python3 scripts/ui_preview.py [--port 8876] [--open]

Nothing here touches a real workspace: the sample lives in a temporary folder
that is removed when the server stops.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_jobapps.server import serve  # noqa: E402
from hermes_jobapps.workspace import Workspace, sha256_file  # noqa: E402


POSTING = """**About the team**

{company} builds tools that field teams use every day. We are hiring a {title} to work across research, design and delivery.

**What you will do**

- Own a product area from first sketch to release
- Run research with the people who use the product
  - Site visits twice a quarter
  - Remote interviews most weeks
- Work closely with engineering on the design system

**What we look for**

1. Four or more years building complex tools
2. Strong prototyping skills, in code or in design tools
3. Clear writing

Read more at https://{slug}.example/careers.
"""

PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 55>>stream\nBT /F1 24 Tf 72 700 Td (Jordan Example - sample page) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)


def seed(root: Path) -> Workspace:
    ws = Workspace(root)
    ws.init(name="Jordan Example")
    today = date.today()

    def iso(offset: int) -> str:
        return (today + timedelta(days=offset)).isoformat()

    def job(company: str, title: str, status: str, created: int, *, location: str = "Remote", sections=None, **meta) -> str:
        slug = company.lower().replace(" ", "")
        record = ws.create_job(
            company=company,
            title=title,
            status=status,
            location=location,
            url=f"https://{slug}.example/jobs/{abs(created)}",
            posting=POSTING.format(company=company, title=title.lower(), slug=slug),
            created_on=iso(created),
            notes=meta.pop("notes", ""),
            extra_meta=meta,
            body_sections=sections,
        )
        return record["id"]

    def material(job_id: str, name: str, qa: str = "", *, pdf: bool = True) -> None:
        path = ws.job_dir(job_id) / name
        path.write_text("= Jordan Example\n\nProduct designer with six years in planning tools.\n", encoding="utf-8")
        if pdf:
            path.with_suffix(".pdf").write_bytes(PDF)
        if qa:
            report = {
                "status": "pass" if qa == "stale" else qa,
                "source_sha256": "0" * 64 if qa == "stale" else sha256_file(path),
                "checked_at": iso(0),
            }
            (path.parent / "qa").mkdir(exist_ok=True)
            (path.parent / "qa" / f"{name}.json").write_text(json.dumps(report), encoding="utf-8")

    fieldwork = job(
        "Fieldwork",
        "Product Designer",
        "ready",
        -6,
        decision="apply",
        role_family="product_design",
        referral="Sam Patel",
        next_action="Finish the application answers",
        next_action_due=iso(1),
        notes="Sam mentioned the team is five people and ships every two weeks.",
        sections={
            "Assessment": "- Decision: apply\n- Workplace: remote\n- Salary: listed",
            "Strategy": "**Thesis:** a designer who has already rebuilt scheduling for field teams.\n\n"
            "**Proof:** the Harbor scheduling redesign and the research practice at Meridian.\n\n"
            "**Way in:** Sam Patel on the design team.",
            "Requirements": "- Four or more years building complex tools\n- Strong prototyping skills\n- Clear writing",
            "Application questions": "- Why Fieldwork?\n- Describe a tool you redesigned.",
            "Research": "Series B, about 80 people. The design team reports to product.\n\nSee https://fieldwork.example/blog.",
        },
    )
    material(fieldwork, "Jordan Example - Resume - Fieldwork.typ", "pass")
    material(fieldwork, "Jordan Example - Cover Letter - Fieldwork.typ", "review")
    material(fieldwork, "application-answers.md", "", pdf=False)
    material(fieldwork, "outreach-sam.md", "stale", pdf=False)
    (ws.job_dir(fieldwork) / "portfolio.pdf").write_bytes(PDF)

    northstar = job(
        "Northstar", "Senior Product Designer", "new", -2, location="New York, NY", decision="apply",
        role_family="product_design", priority="high", next_action="Draft the resume", next_action_due=iso(3),
        sections={"Assessment": "- Decision: apply\n- Workplace: hybrid", "Requirements": "- Systems thinking\n- Clear writing"},
    )
    material(northstar, "resume.typ", "fail")
    job("Meridian", "Design Engineer", "new", -1, location="Remote", decision="pending", role_family="design_engineering")
    job("Lantern", "UX Researcher", "new", -9, location="Chicago, IL", decision="apply", role_family="research")

    job("Common Ground", "Staff Designer", "interviewing", -24, location="Brooklyn, NY", applied_on=iso(-20),
        role_family="product_design", next_action="Prepare the portfolio review", next_action_due=iso(-1))
    job("Tidewater", "Lead Product Designer", "offer", -40, location="Remote", applied_on=iso(-36),
        role_family="product_design", next_action="Reply to the offer", next_action_due=iso(2))

    applied = [
        ("Harbor", "Product Designer", -12, "product_design", "Portland, OR", "Send Riley the portfolio link", 4),
        ("Brightline", "Design Engineer", -18, "design_engineering", "Remote", "Check on the application", 6),
        ("Cedar Systems", "Product Designer", -27, "product_design", "Austin, TX", "", 0),
        ("Quill", "UX Researcher", -45, "research", "Remote", "", 0),
        ("Granite", "Product Designer", -63, "product_design", "Denver, CO", "", 0),
    ]
    for company, title, when, family, location, step, due in applied:
        extra = {"next_action": step, "next_action_due": iso(due)} if step else {}
        job(company, title, "applied", when - 3, location=location, applied_on=iso(when), role_family=family, **extra)

    job("Oakridge", "Product Designer", "rejected", -70, location="Remote", applied_on=iso(-66), role_family="product_design")
    job("Pinecrest", "Design Engineer", "closed", -90, location="Seattle, WA", applied_on=iso(-85), role_family="design_engineering")
    job("Driftwood", "Visual Designer", "skipped", -15, location="London, UK", decision="skip", role_family="visual_design")

    people = [
        ("Sam Patel", "Fieldwork", "Design Lead", "sam@fieldwork.example", "contacted", 4, "Met at a local design meetup. Offered to refer."),
        ("Alex Rivera", "Northstar", "Product Designer", "", "to_contact", None, "Former teammate who joined last spring."),
        ("Jamie Chen", "Common Ground", "Design Manager", "jamie@commonground.example", "follow_up", -1, "Hiring manager for the staff role."),
        ("Morgan Lee", "Tidewater", "Head of Design", "", "replied", None, "Sent the offer details."),
        ("Riley Stone", "Harbor", "Recruiter", "riley@harbor.example", "paused", None, "Recruiter for the Portland team."),
    ]
    for name, company, role, email, status, touch, why in people:
        ws.create_person(
            name=name, company=company, role=role, email=email, why=why, status=status,
            linkedin=f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}-example",
            next_touch=iso(touch) if touch is not None else "",
        )

    leads = [
        ("Meridian", "Senior Product Designer", "Remote", -1, "new", "apply"),
        ("Harbor", "Design Systems Lead", "Portland, OR", -3, "shortlisted", "apply"),
        ("Lantern", "Principal Designer", "Chicago, IL", -5, "new", "pending"),
        ("Granite", "Design Director", "London, UK", -8, "new", "skip"),
    ]
    for company, title, location, found, status, preflight in leads:
        ws.create_lead(
            company=company, title=title, location=location, status=status, found_on=iso(found),
            url=f"https://{company.lower()}.example/jobs/{abs(found)}", posting=f"{company} is hiring a {title.lower()}.",
            extra_meta={"preflight": preflight},
        )

    evidence = [
        ("harbor-scheduling-redesign", "Harbor scheduling redesign", "project", "active", ["design", "research"],
         "Rebuilt the scheduling flow with the field team.\n\n## Results\n\n- Cut scheduling time by **38%**\n- Shipped in three releases\n\n## Method\n\n1. Shadowed dispatchers\n2. Prototyped in code"),
        ("meridian-research-practice", "Research practice at Meridian", "role", "active", ["research"],
         "Started the weekly interview programme and the shared findings library."),
        ("design-system", "Design system at Lantern", "project", "needs_review", ["systems"],
         "Owned the component library across web and mobile."),
        ("early-internship", "Internship", "role", "retired", [], "Summer internship in a studio."),
    ]
    for slug, title, kind, status, tags, body in evidence:
        ws.write(ws.evidence_dir / f"{slug}.md", {"title": title, "type": kind, "status": status, "tags": tags}, f"# {title}\n\n{body}")

    ws.write(
        ws.profile_dir / "profile.md",
        {"name": "Jordan Example", "email": "jordan@example.org", "location": "Brooklyn, NY"},
        "# Jordan Example\n\nProduct designer with six years in planning and scheduling tools.\n\n"
        "## Looking for\n\n- Senior or staff product design roles\n- Remote, or New York\n\n## Constraints\n\n- No relocation",
    )
    ws.write(ws.profile_dir / "voice.md", {}, "# Voice\n\nPlain sentences. Concrete nouns. No superlatives.\n\n- Say what was built and what changed\n- One idea per sentence")
    ws.write(ws.profile_dir / "playbook.md", {}, "# Playbook\n\n## All documents\n\n- Use the reader's words for their product\n\n## Resume\n\n- One page\n- Lead with the scheduling work")
    return ws


def _stop(*_: object) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGTERM, _stop)
    parser = argparse.ArgumentParser(description="Run the cockpit on disposable sample data.")
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--open", action="store_true", help="Open a browser window.")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="jobapps-preview-") as folder:
        try:
            serve(seed(Path(folder) / "JobApps"), port=args.port, open_browser=args.open)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
