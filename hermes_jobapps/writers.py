"""Draft application materials from a structured role evaluation."""

from __future__ import annotations

import re
from typing import Any

from .knowledge import normalize_space


BANNED_TEXT = (
    "i am writing to express interest",
    "i would be excited",
    "i am thrilled",
    "cutting-edge",
    "fast-paced environment",
    "team player",
    "synergies",
    "utilize",
    "leveraging",
)


def draft_materials(
    job: dict[str, Any],
    evaluation: dict[str, Any],
    context: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    company = evaluation["facts"].get("company") or "the company"
    title = evaluation["facts"].get("title") or "the role"
    role_family = evaluation["role_family"]
    angle = evaluation["strongest_angle"]
    tailoring_targets = evaluation.get("tailoring_targets", []) or []
    learning_patterns = context.get("learning_patterns", []) or []
    profile = {item["fact_key"]: item["value"] for item in context.get("profile_facts", [])}
    name = profile.get("name", "Candidate")

    drafts = {
        "resume_notes": _resume_notes(role_family, angle, evaluation, tailoring_targets, learning_patterns),
        "cover_letter": _clean_banned(_cover_letter(company, title, role_family, angle, tailoring_targets, learning_patterns)),
        "short_answers": _short_answers(company, title, angle, tailoring_targets, learning_patterns),
        "outreach": _clean_banned(_outreach(company, title, angle, name, config, learning_patterns)),
    }
    return drafts


def _resume_notes(
    role_family: str,
    angle: str,
    evaluation: dict[str, Any],
    tailoring_targets: list[dict[str, Any]],
    learning_patterns: list[dict[str, Any]],
) -> list[str]:
    section_order = {
        "ai_agent_systems": "Education, Research, Projects, Experience, Skills",
        "ml_ds": "Education, Research, Projects, Experience, Skills",
        "research": "Education, Research, Projects, Experience, Skills",
        "data_engineering": "Education, Experience, Projects/Research, Skills",
        "data_analytics": "Education, Experience, Projects/Research, Skills",
        "full_stack": "Education, Experience, Projects, Research, Skills",
        "backend": "Education, Experience, Projects, Research, Skills",
        "mobile_ios": "Education, Projects, Experience, Skills",
    }.get(role_family, "Education, Experience, Projects/Research, Skills")

    notes = [
        f"Use section order: {section_order}.",
        f"Central angle: {angle}",
        "Rewrite bullets around mechanisms, not tool lists.",
    ]
    for target in tailoring_targets[:5]:
        requirement = normalize_space(str(target.get("requirement") or ""))
        portrayal = normalize_space(str(target.get("requested_portrayal") or ""))
        if requirement and portrayal:
            notes.append(f"Tailor to JD: {requirement} -> {portrayal}")
        elif requirement:
            notes.append(f"Tailor to JD: {requirement}")
    for pattern in learning_patterns[:4]:
        preference = normalize_space(str(pattern.get("preference") or ""))
        if preference:
            notes.append(f"Apply learned preference: {preference}")
    return notes


def _cover_letter(
    company: str,
    title: str,
    role_family: str,
    angle: str,
    tailoring_targets: list[dict[str, Any]],
    learning_patterns: list[dict[str, Any]],
) -> str:
    hook = {
        "ai_agent_systems": "The interesting part of agentic software is not the chat surface. It is the way state, tools, retrieval, and evaluation move through the system.",
        "backend": "Most production systems fail at the boundaries between services, data models, and configuration.",
        "full_stack": "Useful software usually starts with a workflow that is currently more painful than it needs to be.",
        "data_engineering": "Data quality problems usually begin at the point of collection, long before a report or model sees the data.",
        "data_analytics": "Good analysis is less about finding a chart and more about making the underlying question precise.",
        "ml_ds": "A model is only useful when the problem definition and evaluation metric are honest about the decision being made.",
        "mobile_ios": "The strongest privacy guarantee is a product shape that keeps sensitive data close to the device.",
    }.get(role_family, "The best engineering work starts by making the actual constraint visible.")

    tailoring_sentence = _tailoring_sentence(tailoring_targets)
    learning_sentence = _learning_sentence(learning_patterns)
    return "\n\n".join(
        [
            hook,
            (
                f"For the {title} role at {company}, I would anchor my application around this idea: "
                f"{angle} {tailoring_sentence}"
            ),
            (
                f"What stands out about {company} is the need for work that is specific enough to survive real use. "
                "That is the kind of engineering I am trying to keep doing: systems where the data model, user workflow, and technical constraints stay connected."
            ),
            (
                f"{learning_sentence} I would bring a practical habit of tracing requirements back to working systems, naming uncertainty honestly, and turning ambiguous problems into useful software. "
                "The next step I would want is a conversation about where this role needs judgment most."
            ),
        ]
    )


def _short_answers(
    company: str,
    title: str,
    angle: str,
    tailoring_targets: list[dict[str, Any]],
    learning_patterns: list[dict[str, Any]],
) -> dict[str, str]:
    tailoring_sentence = _tailoring_sentence(tailoring_targets)
    learning_sentence = _learning_sentence(learning_patterns)
    return {
        "why_this_role": (
            f"I am interested in the {title} role because the work appears to need {angle.lower()} "
            f"{tailoring_sentence}"
        ),
        "relevant_experience": learning_sentence.strip(),
        "why_company": (
            f"{company} looks like a place where the hard part is not only building features, but making the system useful under real constraints. "
            "That is the part of software I care about most."
        ),
    }


def _outreach(
    company: str,
    title: str,
    angle: str,
    name: str,
    config: dict[str, Any],
    learning_patterns: list[dict[str, Any]],
) -> str:
    first_name = name.split()[0] if name else "Applicant"
    days = config.get("followups", {}).get("networking_after_days", 5)
    learning_sentence = _learning_sentence(learning_patterns)
    return (
        "Hi [Name],\n\n"
        f"I came across the {title} role at {company} and noticed that the work seems close to {angle.lower()} "
        f"{learning_sentence}\n\n"
        "If you have time in the next few weeks, would you be open to a 20-minute conversation about how your team thinks about this problem?\n\n"
        f"Best,\n{first_name}\n\n"
        f"Follow up after {days} days if there is no response."
    )


def _tailoring_sentence(tailoring_targets: list[dict[str, Any]]) -> str:
    if not tailoring_targets:
        return ""
    target = tailoring_targets[0]
    requirement = normalize_space(str(target.get("requirement") or ""))
    portrayal = normalize_space(str(target.get("requested_portrayal") or ""))
    if requirement and portrayal:
        return f"The JD-specific target is {requirement}; I should portray it as {portrayal}"
    if requirement:
        return f"The JD-specific target is {requirement}."
    return ""


def _learning_sentence(learning_patterns: list[dict[str, Any]]) -> str:
    preferences = [normalize_space(str(item.get("preference") or "")) for item in learning_patterns]
    preferences = [item for item in preferences if item]
    if not preferences:
        return ""
    return "Learned preference: " + " ".join(preferences[:2])


def _first_person(text: str) -> str:
    cleaned = normalize_space(text)
    leading_action = re.match(r"^(Built|Designed|Implemented|Developed|Created|built|designed|implemented|developed|created)\b(.*)", cleaned)
    if leading_action:
        cleaned = f"I {leading_action.group(1).lower()}{leading_action.group(2)}"
    if not cleaned.lower().startswith("i "):
        cleaned = "I can point to this proof point: " + cleaned
    return cleaned[:520]


def _clean_banned(text: str) -> str:
    cleaned = text.replace("—", ",").replace("–", "-")
    for phrase in BANNED_TEXT:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
