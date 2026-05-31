"""Material workbench helpers for app-owned JobApps artifacts."""

from __future__ import annotations

import difflib
from typing import Any

from .latex import latex_escape


def build_full_resume_tex(
    *,
    name: str = "Prashant Shah",
    headline: str = "AI Engineer focused on agentic systems",
    sections: list[dict[str, Any]] | None = None,
) -> str:
    """Build a compact full-resume LaTeX artifact from explicit sections."""

    section_blocks = []
    for section in sections or []:
        title = latex_escape(str(section.get("title") or "Section"))
        raw_items = section.get("items") or []
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        items = "\n".join(f"  \\item {latex_escape(str(item))}" for item in raw_items if str(item).strip())
        if not items:
            continue
        section_blocks.append(
            f"\\section*{{{title}}}\n\\begin{{itemize}}\n{items}\n\\end{{itemize}}"
        )
    if not section_blocks:
        section_blocks.append(
            "\\section*{Review Notes}\n\\begin{itemize}\n"
            "  \\item Add user-confirmed projects, experience, education, and skills before external use.\n"
            "\\end{itemize}"
        )

    return rf"""\documentclass[10pt]{{article}}
\usepackage[margin=0.62in]{{geometry}}
\usepackage{{enumitem}}
\setlist[itemize]{{leftmargin=*, itemsep=2pt, topsep=2pt}}
\pagenumbering{{gobble}}

\begin{{document}}

\begin{{center}}
{{\Large \textbf{{{latex_escape(name)}}}}}\\
{latex_escape(headline)}
\end{{center}}

{chr(10).join(section_blocks)}

% JobApps full resume artifact. Do not externally submit until approved.
\end{{document}}
"""


def build_full_cover_letter_tex(
    *,
    body: str,
    company: str = "Hiring Team",
    role_title: str = "Target Role",
    name: str = "Prashant Shah",
) -> str:
    """Build a send-reviewable LaTeX cover-letter artifact from explicit body text."""

    paragraphs = [line.strip().replace("\n", " ") for line in str(body).split("\n\n") if line.strip()]
    content = "\n\n".join(latex_escape(paragraph) for paragraph in paragraphs)
    if not content:
        content = latex_escape("Add a user-approved cover-letter body before external use.")
    return rf"""\documentclass[11pt]{{letter}}
\usepackage[margin=0.9in]{{geometry}}
\pagenumbering{{gobble}}

\begin{{document}}
\begin{{letter}}{{{latex_escape(company)}\\Hiring Team}}
\opening{{Dear Hiring Team,}}

{content}

\closing{{Sincerely,\\{latex_escape(name)}}}
\end{{letter}}

% Target role: {latex_escape(role_title)}
% JobApps cover-letter artifact. Do not externally send until approved.
\end{{document}}
"""


def patch_text(content: str, old_string: str, new_string: str, *, replace_all: bool = False) -> str:
    if not old_string:
        raise ValueError("old_string is required for material patching.")
    count = content.count(old_string)
    if count == 0:
        raise ValueError("old_string was not found in the material content.")
    if count > 1 and not replace_all:
        raise ValueError("old_string is not unique. Pass replace_all=true or provide more context.")
    return content.replace(old_string, new_string, -1 if replace_all else 1)


def text_diff(before: str, after: str, *, fromfile: str = "before", tofile: str = "after") -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )
