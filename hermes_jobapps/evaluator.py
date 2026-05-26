"""Deterministic first-pass role evaluation.

Hermes can replace or refine this transition later, but the contract should stay
structured: database context in, traceable evaluation out.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .knowledge import normalize_space


ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ai_agent_systems": (
        "agent",
        "agents",
        "llm",
        "rag",
        "retrieval",
        "tool",
        "tools",
        "evaluation",
        "eval",
        "embeddings",
        "vector",
        "prompt",
        "workflow",
        "ai engineer",
    ),
    "backend": (
        "backend",
        "api",
        "distributed",
        "service",
        "services",
        "database",
        "auth",
        "cloud",
        "infrastructure",
        "configuration",
        "server",
        "microservice",
    ),
    "full_stack": (
        "full-stack",
        "full stack",
        "react",
        "typescript",
        "frontend",
        "backend",
        "web app",
        "ui",
        "node",
        "next.js",
    ),
    "data_engineering": (
        "data engineer",
        "etl",
        "pipeline",
        "pipelines",
        "warehouse",
        "airflow",
        "dbt",
        "sql",
        "postgresql",
        "spark",
        "data quality",
    ),
    "data_analytics": (
        "analyst",
        "analytics",
        "dashboard",
        "reporting",
        "tableau",
        "power bi",
        "metrics",
        "insights",
        "stakeholder",
    ),
    "ml_ds": (
        "machine learning",
        "ml",
        "data science",
        "model",
        "classification",
        "prediction",
        "xgboost",
        "pytorch",
        "tensorflow",
        "statistics",
    ),
    "mobile_ios": (
        "ios",
        "swift",
        "swiftui",
        "mobile",
        "watchos",
        "healthkit",
        "app store",
    ),
    "devops_it": (
        "devops",
        "sre",
        "ci/cd",
        "kubernetes",
        "docker",
        "observability",
        "datadog",
        "terraform",
        "linux",
    ),
    "research": (
        "research",
        "scientist",
        "publication",
        "experiment",
        "ablation",
        "benchmark",
        "paper",
        "prototype",
    ),
}

STOPWORDS = {
    "about",
    "across",
    "after",
    "also",
    "and",
    "are",
    "build",
    "can",
    "for",
    "from",
    "have",
    "into",
    "our",
    "that",
    "the",
    "their",
    "this",
    "with",
    "will",
    "work",
    "you",
    "your",
}

SPONSOR_BLOCKER_PATTERNS = (
    r"no (?:visa )?sponsorship",
    r"not sponsor",
    r"unable to sponsor",
    r"cannot sponsor",
    r"must be (?:a )?u\.?s\.? citizen",
    r"must be authorized to work .* without sponsorship",
    r"authorization .* without .* sponsorship",
    r"green card (?:holder|required)",
)

SPONSOR_CLEAR_PATTERNS = (
    r"visa sponsorship (?:is )?available",
    r"will sponsor",
    r"sponsorship available",
    r"open to sponsorship",
)


def _criteria_patterns(criteria_list: list[dict[str, Any]], area: str, ctype: str, severity: str | None = None) -> list[str]:
    """Extract raw patterns from config criteria for a given area and type."""
    patterns: list[str] = []
    for c in criteria_list:
        if c.get("area") != area or c.get("type") != ctype:
            continue
        if severity is not None and c.get("severity") != severity:
            continue
        for p in c.get("patterns", []):
            patterns.append(p)
    return patterns


def _criteria_threshold(criteria_list: list[dict[str, Any]], area: str, ctype: str) -> int | None:
    """Extract a numeric threshold from config criteria."""
    for c in criteria_list:
        if c.get("area") == area and c.get("type") == ctype and "threshold" in c:
            return int(c["threshold"])
    return None


def evaluate_job(
    job: dict[str, Any],
    context: dict[str, Any],
    config: dict[str, Any],
    job_id: str | None = None,
) -> dict[str, Any]:
    description = normalize_space(job.get("description", ""))
    combined = normalize_space(
        " ".join(
            str(job.get(key, ""))
            for key in ("title", "company", "location", "url", "description", "user_notes")
        )
    )
    if len(description) < 80:
        raise ValueError("Add a fuller job description before evaluating.")

    facts = extract_job_facts(job, combined, config)
    role_family = classify_role_family(combined)
    requirements = extract_requirements(job.get("description", ""))
    blocker_flags = collect_blocker_flags(facts)
    risks = collect_risks(facts, combined)
    decision = "skip" if blocker_flags else "apply"
    strongest_angle = choose_angle(role_family, config)
    tailoring_targets = build_tailoring_targets(requirements, role_family)

    evaluation = {
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_mode": "blocker_preflight",
        "fit_assumption": "user_provided_jd_implies_apply_intent",
        "decision": decision,
        "role_family": role_family,
        "sponsorship_risk": facts["sponsorship_risk"],
        "location_risk": facts["location_risk"],
        "seniority_risk": facts["seniority_risk"],
        "effort_risk": facts["effort_risk"],
        "blocker_flags": blocker_flags,
        "strongest_angle": strongest_angle,
        "facts": facts,
        "top_requirements": requirements,
        "tailoring_targets": tailoring_targets,
        "risks": risks,
        "evidence": build_evidence(facts),
        "materials_needed": ["resume_notes", "cover_letter", "short_answers", "outreach"],
        "approval_required_for": config.get("rules", {}).get("require_approval_for", []),
    }
    evaluation["next_action"] = choose_next_action(evaluation)
    return evaluation


def extract_job_facts(job: dict[str, Any], combined: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    criteria_list = (config or {}).get("criteria", {}).get("blockers", [])
    lowered = combined.lower()

    # Sponsorship
    sponsor_blockers = _criteria_patterns(criteria_list, "sponsorship", "pattern", "blocker")
    sponsor_clear = _criteria_patterns(criteria_list, "sponsorship", "pattern", "clear")
    if not sponsor_blockers:
        sponsor_blockers = list(SPONSOR_BLOCKER_PATTERNS)
    if not sponsor_clear:
        sponsor_clear = list(SPONSOR_CLEAR_PATTERNS)

    sponsorship_evidence = find_evidence_sentence(combined, ("sponsor", "visa", "authorization", "citizen"))
    # Config patterns are plain substring matches; hardcoded patterns are regex.
    if sponsor_blockers and any(term in lowered for term in sponsor_blockers):
        sponsorship_risk = "blocker"
    elif sponsor_clear and any(term in lowered for term in sponsor_clear):
        sponsorship_risk = "clear"
    elif any(re.search(pattern, lowered) for pattern in SPONSOR_BLOCKER_PATTERNS):
        sponsorship_risk = "blocker"
    elif any(re.search(pattern, lowered) for pattern in SPONSOR_CLEAR_PATTERNS):
        sponsorship_risk = "clear"
    elif any(word in lowered for word in ("sponsor", "visa", "authorization", "citizen")):
        sponsorship_risk = "unknown"
    else:
        sponsorship_risk = "unknown"

    # Location
    location_text = normalize_space(str(job.get("location") or ""))
    if not location_text:
        location_text = find_evidence_sentence(combined, ("remote", "hybrid", "onsite", "relocation", "location"))
    location_lower = location_text.lower()
    location_clear = _criteria_patterns(criteria_list, "location", "pattern", "clear")
    location_flag = _criteria_patterns(criteria_list, "location", "pattern", "flag")
    if not location_clear:
        location_clear = ["remote", "hybrid", "new york", "new jersey", "nyc"]
    if not location_flag:
        location_flag = ["onsite", "relocation required", "must relocate"]
    if any(term in location_lower for term in location_clear):
        location_risk = "clear"
    elif any(term in location_lower for term in location_flag):
        location_risk = "unknown"
    else:
        location_risk = "unknown"

    # Seniority
    seniority_evidence = find_evidence_sentence(combined, ("senior", "staff", "principal", "lead", "years", "new grad", "intern"))
    years_required = [int(value) for value in re.findall(r"\b([3-9]|1[0-5])\+?\s+years\b", lowered)]
    years_threshold = _criteria_threshold(criteria_list, "seniority", "years")
    if years_threshold is None:
        years_threshold = 5

    seniority_blocker_titles = _criteria_patterns(criteria_list, "seniority", "title", "blocker")
    if not seniority_blocker_titles:
        seniority_blocker_titles = ["staff engineer", "principal engineer", "director"]

    if any(term in lowered for term in seniority_blocker_titles):
        seniority_risk = "blocker"
    elif years_required and max(years_required) >= years_threshold:
        seniority_risk = "blocker"
    elif years_required and max(years_required) >= 3:
        seniority_risk = "stretch"
    elif any(term in lowered for term in ("new grad", "entry level", "intern", "junior", "associate")):
        seniority_risk = "clear"
    else:
        seniority_risk = "unknown"

    effort_evidence = find_evidence_sentence(combined, ("assessment", "take-home", "portfolio", "cover letter", "question"))
    effort_risk = "heavy" if any(term in lowered for term in ("take-home", "assessment", "case study")) else "normal"

    return {
        "title": normalize_space(str(job.get("title") or guess_title(combined))),
        "company": normalize_space(str(job.get("company") or "Unknown company")),
        "location": location_text or "Unknown",
        "url": normalize_space(str(job.get("url") or "")),
        "sponsorship_evidence": sponsorship_evidence or "No sponsorship language found.",
        "sponsorship_risk": sponsorship_risk,
        "location_evidence": location_text or "No clear location policy found.",
        "location_risk": location_risk,
        "seniority_evidence": seniority_evidence or "No seniority requirement found.",
        "seniority_risk": seniority_risk,
        "effort_evidence": effort_evidence or "No unusual application effort found.",
        "effort_risk": effort_risk,
    }


def classify_role_family(text: str) -> str:
    lowered = text.lower()
    scores = {
        family: sum(1 for keyword in keywords if keyword in lowered)
        for family, keywords in ROLE_KEYWORDS.items()
    }
    family, score = max(scores.items(), key=lambda item: item[1])
    return family if score else "other"


def extract_requirements(description: str, limit: int = 8) -> list[str]:
    raw_lines = [
        normalize_space(re.sub(r"^[*\-•\d.)\s]+", "", line))
        for line in description.splitlines()
    ]
    candidates: list[str] = []
    requirement_terms = (
        "experience",
        "build",
        "develop",
        "design",
        "maintain",
        "must",
        "required",
        "responsible",
        "knowledge",
        "proficiency",
        "familiar",
        "work with",
        "collaborate",
    )
    for line in raw_lines:
        if len(line) < 18 or len(line) > 220:
            continue
        lowered = line.lower()
        if any(term in lowered for term in requirement_terms):
            candidates.append(line)

    if len(candidates) < 4:
        sentences = re.split(r"(?<=[.!?])\s+", normalize_space(description))
        for sentence in sentences:
            if 30 <= len(sentence) <= 220 and any(term in sentence.lower() for term in requirement_terms):
                candidates.append(sentence)

    return _dedupe(candidates)[:limit]


def build_tailoring_targets(
    requirements: list[str],
    role_family: str,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for index, requirement in enumerate(requirements):
        targets.append(
            {
                "requirement": requirement,
                "category": category_for_requirement(requirement, role_family),
                "priority": round(max(0.35, 1.0 - index * 0.08), 2),
                "requested_portrayal": requested_portrayal_for(requirement, role_family),
                "status": "needs_story",
            }
        )
    return targets


def category_for_requirement(requirement: str, role_family: str) -> str:
    lowered = requirement.lower()
    if any(term in lowered for term in ("agent", "llm", "rag", "retrieval", "tool", "evaluation", "eval")):
        return "agent_systems"
    if any(term in lowered for term in ("api", "postgres", "database", "backend", "service")):
        return "backend_systems"
    if any(term in lowered for term in ("communicat", "collaborat", "stakeholder")):
        return "communication"
    return role_family or "general"


def requested_portrayal_for(requirement: str, role_family: str) -> str:
    base = {
        "ai_agent_systems": "Frame the strongest project as an agentic system with state, tools, retrieval, and verification.",
        "backend": "Frame experience around reliable APIs, data contracts, and operational clarity.",
        "full_stack": "Frame experience around end-to-end workflow ownership and user-visible system behavior.",
        "data_engineering": "Frame experience around data quality, pipelines, and reproducible outputs.",
        "ml_ds": "Frame experience around problem definition, evaluation, and production constraints.",
    }.get(role_family, "Frame experience truthfully around the JD's requested outcome.")
    return f"{base} JD target: {truncate(requirement, 180)}"


def collect_blocker_flags(facts: dict[str, Any]) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    if facts.get("sponsorship_risk") == "blocker":
        flags.append(
            {
                "area": "sponsorship",
                "severity": "blocker",
                "evidence": facts.get("sponsorship_evidence", ""),
                "action": "skip unless the user explicitly overrides work-authorization risk",
            }
        )
    if facts.get("seniority_risk") == "blocker":
        flags.append(
            {
                "area": "seniority",
                "severity": "blocker",
                "evidence": facts.get("seniority_evidence", ""),
                "action": "skip unless the user explicitly wants a reach application",
            }
        )
    if facts.get("location_risk") == "blocker":
        flags.append(
            {
                "area": "location",
                "severity": "blocker",
                "evidence": facts.get("location_evidence", ""),
                "action": "skip unless location constraints are resolved",
            }
        )
    return flags


def choose_angle(role_family: str, config: dict[str, Any]) -> str:
    angle_by_family = {
        "ai_agent_systems": "Agentic systems with traceable state, tool use, retrieval, and evaluation.",
        "backend": "Reliable backend systems where contracts, configuration, and data flow stay explicit.",
        "full_stack": "Workflow-first full-stack systems with useful interfaces and grounded data models.",
        "data_engineering": "Data quality at the collection layer, then reliable pipelines and reporting.",
        "data_analytics": "Messy operational data turned into clear, repeatable analysis.",
        "ml_ds": "ML work framed through problem definition, evaluation, and honest model limits.",
        "mobile_ios": "Privacy-conscious mobile systems that keep sensitive data close to the device.",
        "devops_it": "Operational reliability through visible configuration, logs, and approval boundaries.",
        "research": "Applied research translated into useful engineering systems.",
        "other": "Truthful fit through the strongest matching project and a narrow next action.",
    }
    return angle_by_family.get(role_family, angle_by_family["other"])


def choose_next_action(evaluation: dict[str, Any]) -> str:
    if evaluation["decision"] == "skip":
        return "Record the skip reason and move on."
    if evaluation["sponsorship_risk"] == "unknown":
        return "Run a quick sponsorship check, then tailor the resume only if the signal stays positive."
    return "Tailor the resume, review drafts, and approve any external outreach or submission manually."


def build_evidence(facts: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "label": "Sponsorship",
            "value": facts["sponsorship_risk"],
            "source": facts["sponsorship_evidence"],
        },
        {
            "label": "Location",
            "value": facts["location_risk"],
            "source": facts["location_evidence"],
        },
        {
            "label": "Seniority",
            "value": facts["seniority_risk"],
            "source": facts["seniority_evidence"],
        },
    ]


def collect_risks(facts: dict[str, Any], combined: str) -> list[str]:
    risks: list[str] = []
    lowered = combined.lower()
    high_salary_start = _salary_starts_at_120k_plus(combined)
    west_coast = _has_west_coast_signal(combined)
    if facts["sponsorship_risk"] == "blocker":
        risks.append("Work authorization appears to be a blocker. Default skip unless manually overridden.")
    elif facts["sponsorship_risk"] == "unknown":
        risks.append("Sponsorship is unknown. Check company sponsorship history before deep tailoring.")
    if high_salary_start:
        risks.append("$120k+ starting salary is a competition signal, not an automatic priority.")
    if high_salary_start and west_coast:
        risks.append("High-pay West Coast role: treat as a competition signal. Prioritize networking before deep tailoring.")
    if facts["seniority_risk"] == "stretch":
        risks.append("Seniority may be a stretch. Use the strongest matching proof point and avoid overclaiming.")
    if facts["effort_risk"] == "heavy":
        risks.append("Application effort looks heavy. Do not spend time unless fit is clearly above threshold.")
    if "security clearance" in lowered:
        risks.append("Security clearance language may imply a work-authorization blocker.")
    return risks or ["No major blocker found in the pasted description."]


def _salary_starts_at_120k_plus(text: str) -> bool:
    values = _salary_values(text)
    return bool(values and min(values) >= 120_000)


def _salary_values(text: str) -> list[int]:
    values: list[int] = []
    for match in re.finditer(r"\$\s*(\d{2,3})(?:,(\d{3}))?\s*([kK])?", text or ""):
        head = int(match.group(1))
        thousands = match.group(2)
        suffix = match.group(3)
        if thousands:
            values.append(int(f"{head}{thousands}"))
        elif suffix or head >= 50:
            values.append(head * 1000)
    return values


def _has_west_coast_signal(text: str) -> bool:
    lowered = (text or "").lower()
    terms = (
        "west coast",
        "san francisco",
        "san jose",
        "bay area",
        "palo alto",
        "mountain view",
        "sunnyvale",
        "cupertino",
        "menlo park",
        "redwood city",
        "los angeles",
        "seattle",
        "california",
    )
    return any(term in lowered for term in terms) or bool(re.search(r"\bca\b", lowered))


def keywords_for(text: str) -> set[str]:
    normalized = re.sub(r"[-/]", " ", text.lower())
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]{2,}", normalized)
    keywords: set[str] = set()
    for word in words:
        cleaned = word.strip(".,;:()[]{}")
        if cleaned in STOPWORDS:
            continue
        keywords.add(cleaned)
        if len(cleaned) > 4 and cleaned.endswith("s"):
            keywords.add(cleaned[:-1])
    return keywords


def find_evidence_sentence(text: str, terms: tuple[str, ...]) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        lowered = sentence.lower()
        if any(term in lowered for term in terms):
            return truncate(normalize_space(sentence), 240)
    return ""


def guess_title(text: str) -> str:
    first_line = normalize_space(text.split("\n", 1)[0])
    if 3 <= len(first_line) <= 90:
        return first_line
    return "Untitled role"


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    clipped = text[: limit - 1].rsplit(" ", 1)[0]
    return clipped + "."


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output
