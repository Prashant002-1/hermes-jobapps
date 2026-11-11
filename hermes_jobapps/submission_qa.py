"""Checks for the mistakes that sink an application outright.

These are separate from the writing lint: another employer's name left in a
letter, contact details that differ from the profile, a PDF whose text an
applicant tracking system cannot read, and a resume that buries what the role
asks for. Every rule is deterministic and quotes what it found.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .workspace import Workspace, clip


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)")
_DOUBLED_RE = re.compile(r"\b([A-Za-z]{2,})\s+\1\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z][a-z0-9+#.]{2,}")
_COMPANY_SUFFIX_RE = re.compile(
    r"[,\s]+(inc|llc|ltd|corp|corporation|co|company|plc|gmbh|group|holdings|technologies|labs)\.?$", re.IGNORECASE
)
_TARGETING = r"(?:dear|at|join|joining|to|with|for|about|why)\s+(?:the\s+)?"
_LIGATURES = ("\ufb00", "\ufb01", "\ufb02", "\ufb03", "\ufb04", "\ufffd", "(cid:")
_SECTION_WORDS = ("experience", "education", "skills", "projects", "employment", "work history")
_ALLOWED_DOUBLES = {"had", "that", "is", "do", "so", "no", "bye", "very"}
_DRAFT_NAME_RE = re.compile(r"(draft|copy|untitled|\(\d+\)|\bv\d+\b|final[\s_\-]*final)", re.IGNORECASE)
_STOPWORDS = frozenset(
    """
    the and for with that this from your you our are will have has was were their they them into over under about
    experience ability strong excellent work working team teams including required preferred plus years year skills
    knowledge understanding role candidate responsibilities requirements qualifications must using build building
    develop developing design support related ensure other such well able new can may all any not but who what when
    """.split()
)
TOP_SHARE = 0.35


def company_key(name: str) -> str:
    """Company name without legal suffixes, for comparison."""
    text = " ".join(str(name or "").split())
    previous = None
    while previous != text:
        previous = text
        text = _COMPANY_SUFFIX_RE.sub("", text).strip(" ,.")
    return text


def pdf_text(pdf: Path, settings: dict[str, Any]) -> str | None:
    """Text as an applicant tracking system would extract it, or None when it cannot be read here."""
    from .build import _latex_search_paths, _resolve_compiler

    latex = settings.get("latex") if isinstance(settings.get("latex"), dict) else {}
    tool = _resolve_compiler("pdftotext", _latex_search_paths(latex))
    if not tool or not pdf.is_file():
        return None
    try:
        done = subprocess.run([tool, "-layout", str(pdf), "-"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def _finding(rule: str, severity: str, excerpt: str, fix: str) -> dict[str, str]:
    return {"rule": rule, "severity": severity, "excerpt": clip(excerpt, 140), "fix": fix}


def _around(text: str, start: int, end: int, pad: int = 50) -> str:
    return text[max(0, start - pad) : min(len(text), end + pad)]


def _other_companies(ws: Workspace, job_id: str, own_company: str, known_text: str) -> list[str]:
    own = company_key(own_company).lower()
    known = known_text.lower()
    names: dict[str, str] = {}
    for record in ws.jobs():
        if record["id"] == job_id:
            continue
        name = company_key(str(record.get("company") or ""))
        key = name.lower()
        if not name or key.startswith("unknown") or key in names:
            continue
        if own and (key in own or own in key):
            continue
        single_word = " " not in name
        if single_word and len(name) < 6 and name.isalpha():
            continue
        if key in known:
            continue
        names[key] = name
    return sorted(names.values(), key=len, reverse=True)


def _wrong_company(text: str, kind: str, others: list[str]) -> list[dict[str, str]]:
    findings = []
    for name in others:
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])")
        match = pattern.search(text)
        if not match:
            continue
        targeted = re.search(rf"{_TARGETING}{re.escape(name)}(?![A-Za-z0-9])", text, re.IGNORECASE) or re.search(
            rf"{re.escape(name)}(?:'s|’s)\b", text
        )
        severity = "error" if kind != "resume" and targeted else "warning"
        findings.append(
            _finding(
                "wrong_company",
                severity,
                _around(text, match.start(), match.end()),
                f"This names {name}, another employer you are tracking. Remove it unless it is intentional.",
            )
        )
        if len(findings) >= 3:
            break
    return findings


def _digits(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits[-10:] if len(digits) >= 10 else digits


def _contact(text: str, kind: str, profile: dict[str, Any]) -> list[dict[str, str]]:
    findings = []
    email = str(profile.get("email") or "").strip().lower()
    phone = _digits(str(profile.get("phone") or ""))
    found_emails = {item.lower().rstrip(".") for item in _EMAIL_RE.findall(text)}
    found_phones = {_digits(item) for item in _PHONE_RE.findall(text)}
    if email:
        stray = sorted(found_emails - {email})
        if kind == "resume" and email not in found_emails:
            if stray:
                findings.append(
                    _finding(
                        "contact_mismatch",
                        "error",
                        stray[0],
                        f"The resume shows {stray[0]} but the profile email is {email}. Use the profile address.",
                    )
                )
            else:
                findings.append(
                    _finding("contact_missing", "warning", "", f"No email address is readable in the resume. Add {email}.")
                )
    if phone and kind == "resume" and found_phones and phone not in found_phones:
        findings.append(
            _finding(
                "contact_mismatch",
                "error",
                sorted(found_phones)[0],
                "The phone number differs from profile/profile.md. Use the profile number or update the profile.",
            )
        )
    return findings


def _doubled(text: str) -> list[dict[str, str]]:
    findings = []
    for match in _DOUBLED_RE.finditer(text):
        if match.group(1).lower() in _ALLOWED_DOUBLES:
            continue
        findings.append(
            _finding("doubled_word", "warning", _around(text, match.start(), match.end(), 30), "Delete the repeated word.")
        )
        if len(findings) >= 3:
            break
    return findings


def _terms(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if word not in _STOPWORDS}


def _top_of_page(text: str, requirements: list[str]) -> list[dict[str, str]]:
    wanted: set[str] = set()
    for requirement in requirements[:6]:
        wanted |= _terms(requirement)
    body = text.strip()
    if len(wanted) < 4 or len(body) < 600:
        return []
    top = _terms(body[: int(len(body) * TOP_SHARE)])
    everywhere = _terms(body)
    covered_all = len(wanted & everywhere) / len(wanted)
    covered_top = len(wanted & top) / len(wanted)
    if covered_all >= 0.4 and covered_top < covered_all * 0.5:
        missing = sorted((wanted & everywhere) - top)[:6]
        return [
            _finding(
                "buried_relevance",
                "note",
                ", ".join(missing),
                "A reader decides in the top third of the page. Move the experience that covers these terms up, "
                "or state the match in the summary.",
            )
        ]
    return []


def _ats(extracted: str, profile: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    findings = []
    lowered = extracted.lower()
    sections = [word for word in _SECTION_WORDS if re.search(rf"(?m)^\s*{re.escape(word)}\b", lowered)]
    email = str(profile.get("email") or "").strip().lower()
    summary: dict[str, Any] = {
        "chars": len(extracted.strip()),
        "email_readable": bool(email and email in lowered) if email else bool(_EMAIL_RE.search(extracted)),
        "sections": sections,
    }
    if summary["chars"] < 200:
        findings.append(
            _finding(
                "ats_unreadable",
                "error",
                "",
                "Almost no text can be extracted from the PDF. Applicant tracking systems will see an empty resume: "
                "use real text, not images or outlined fonts.",
            )
        )
        return summary, findings
    garbled = [mark for mark in _LIGATURES if mark in extracted]
    if garbled:
        index = extracted.find(garbled[0])
        findings.append(
            _finding(
                "ats_garbled_text",
                "warning",
                _around(extracted, index, index + 1, 25),
                "The PDF text contains ligatures or unmapped glyphs that parsers misread. Turn ligatures off or change the font.",
            )
        )
    if not summary["email_readable"]:
        findings.append(
            _finding(
                "ats_contact_unreadable",
                "warning",
                "",
                "The email address cannot be read from the PDF text. Write it as plain text, not only as a link or icon.",
            )
        )
    if not sections:
        findings.append(
            _finding(
                "ats_sections",
                "note",
                "",
                "No standard section heading (Experience, Education, Skills) was found in the PDF text. "
                "Parsers rely on ordinary headings.",
            )
        )
    return summary, findings


def check_submission(
    ws: Workspace,
    *,
    source: Path,
    plain: str,
    kind: str,
    job_id: str = "",
    company: str = "",
    requirements: list[str] | None = None,
    pdf: Path | None = None,
    settings: dict[str, Any] | None = None,
    raw: str = "",
) -> dict[str, Any]:
    """Return {"status", "findings", "ats"} for one document.

    raw is the unprocessed source; it stands in for the PDF text when no PDF
    could be read, because contact details often live in template variables.
    """
    settings = settings or {}
    profile = ws.profile_meta()
    extracted = pdf_text(pdf, settings) if pdf else None
    visible = extracted if extracted and extracted.strip() else plain
    known_text = ws.profile_text("profile") + "\n" + "\n".join(str(item.get("body") or "") for item in ws.evidence())
    known_text += "\n" + "\n".join(
        " ".join(str(item.get(key) or "") for key in ("title", "organization")) for item in ws.evidence()
    )

    findings: list[dict[str, str]] = []
    if job_id:
        findings += _wrong_company(visible, kind, _other_companies(ws, job_id, company, known_text))
    findings += _contact(visible if extracted and extracted.strip() else f"{plain}\n{raw}", kind, profile)
    findings += _doubled(plain)
    result: dict[str, Any] = {}
    if kind == "resume":
        findings += _top_of_page(visible, list(requirements or []))
        if extracted is not None:
            result["ats"], ats_findings = _ats(extracted, profile)
            findings += ats_findings
    if _DRAFT_NAME_RE.search(source.stem):
        findings.append(
            _finding(
                "file_name",
                "note",
                source.name,
                "Rename before sending: employers see the file name. Use Name - Resume - Company - Role.",
            )
        )
    order = {"error": 0, "warning": 1, "note": 2}
    findings.sort(key=lambda item: order[item["severity"]])
    severities = {item["severity"] for item in findings}
    result["status"] = "fail" if "error" in severities else "review" if "warning" in severities else "pass"
    if findings:
        result["findings"] = findings
    return result
