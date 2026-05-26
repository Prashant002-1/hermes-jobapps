"""Optional importer helpers for legacy private HTML seed files.

These helpers should not be used as the runtime source of truth. Import useful
facts/proof into the JobApps database, then run workflows from structured rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


PRIVATE_FACT_MARKERS = (
    "phone",
    "email",
    "linkedin",
    "github",
    "portfolio",
    "letterboxd",
)


@dataclass(frozen=True)
class ProfileKnowledge:
    path: Path
    text: str
    facts: dict[str, str]
    proof_snippets: list[str]

    @classmethod
    def load(cls, path: str | Path) -> "ProfileKnowledge":
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Private seed file not found: {source}")
        html = source.read_text(encoding="utf-8")
        text = html_to_text(html)
        return cls(
            path=source,
            text=text,
            facts=extract_profile_facts(text),
            proof_snippets=extract_proof_snippets(text),
        )


class _TextExtractor(HTMLParser):
    block_tags = {"p", "li", "h1", "h2", "h3", "h4", "dt", "dd", "tr", "div", "section"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if not self._skip_depth and tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            cleaned = data.strip()
            if cleaned:
                self.parts.append(cleaned + " ")


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    lines = []
    for line in "".join(parser.parts).splitlines():
        cleaned = normalize_space(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_profile_facts(text: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    if email:
        facts["email"] = email.group(0)

    name = re.search(r"\bName\b\s+(.+?)(?:\s+Phone\b|\s+Email\b|\n)", text, re.IGNORECASE)
    if name:
        facts["name"] = normalize_space(name.group(1))

    target = re.search(r"Targeting\s+(.+?)(?:\n|$)", text, re.IGNORECASE)
    if target:
        facts["targeting"] = normalize_space(target.group(1))

    return facts


def extract_proof_snippets(text: str) -> list[str]:
    blocks = [normalize_space(block) for block in text.splitlines()]
    snippets: list[str] = []
    signal_words = (
        "built",
        "implemented",
        "designed",
        "developed",
        "research",
        "pipeline",
        "postgresql",
        "react",
        "python",
        "agent",
        "retrieval",
        "data",
        "model",
        "api",
        "backend",
        "frontend",
        "swift",
        "ios",
        "azure",
        "rag",
        "llm",
        "tool-calling",
        "pgvector",
    )

    for block in blocks:
        lowered = block.lower()
        if len(block) < 70 or any(marker in lowered for marker in PRIVATE_FACT_MARKERS):
            continue
        if any(word in lowered for word in signal_words):
            snippets.append(block)

    return _dedupe(snippets)[:80]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output
