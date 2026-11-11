"""Fail when a tracked file contains something that must not be published.

Generic patterns (home-directory paths, personal email addresses, API keys,
database files) always apply. Add personal terms, one per line, to the ignored file
private/denylist.txt to also catch your own name, employers and so on.

Usage: python3 scripts/check_public_tree.py [--ref <git ref>]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERSONAL_EMAIL_RE = re.compile(
    r"@(?:gmail|googlemail|outlook|hotmail|live|yahoo|icloud|me|proton|protonmail|pm|aol|fastmail)\.[a-z.]+$|\.edu$",
    re.IGNORECASE,
)
DOTENV = "." + "env"
FORBIDDEN_PATHS = re.compile(
    r"(^|/)(data|private|work|exports|materials)/|\.sqlite3?$|\.db$|(^|/)" + re.escape(DOTENV) + r"|jobapps\.local\."
)
PATTERNS = {
    "home directory path": re.compile(r"/(?:Users|home)/(?!you\b|name\b|runner\b)[A-Za-z0-9._-]+/"),
    "api key": re.compile(r"\b(?:sk-(?:proj|ant)-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone number": re.compile(r"(?<![\d.])\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"),
}
ALLOWED_PHONE = re.compile(r"555[\s.-]?01\d{2}|\(?555\)?[\s.-]\d{3}[\s.-]\d{4}")
SELF = "scripts/check_public_tree.py"
ATTRIBUTION_FILES = {"plugin.yaml", "README.md", "LICENSE", "dashboard/manifest.json"}


def tracked(ref: str | None) -> list[str]:
    command = ["git", "ls-tree", "-r", "--name-only", ref] if ref else ["git", "ls-files"]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()


def read(path: str, ref: str | None) -> str:
    if ref:
        done = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, check=False)
        return done.stdout.decode("utf-8", errors="ignore")
    target = ROOT / path
    if target.is_symlink() or not target.is_file():
        return ""
    return target.read_text(encoding="utf-8", errors="ignore")


def denylist() -> list[re.Pattern[str]]:
    source = ROOT / "private" / "denylist.txt"
    if not source.is_file():
        return []
    terms = [line.strip() for line in source.read_text(encoding="utf-8").splitlines()]
    patterns = []
    for term in terms:
        if not term or term.startswith("#"):
            continue
        exact_case = term.upper() == term and any(char.isalpha() for char in term)
        patterns.append(
            re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", 0 if exact_case else re.IGNORECASE)
        )
    return patterns


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="Check the tree of this git ref instead of the working files.")
    args = parser.parse_args()
    personal = denylist()
    problems: list[str] = []
    for path in tracked(args.ref):
        if FORBIDDEN_PATHS.search(path):
            problems.append(f"{path}: private path is tracked")
            continue
        if path == SELF or path.endswith((".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2")):
            continue
        for number, line in enumerate(read(path, args.ref).splitlines(), 1):
            for label, pattern in PATTERNS.items():
                for match in pattern.finditer(line):
                    text = match.group(0)
                    if label == "email address" and not PERSONAL_EMAIL_RE.search(text):
                        continue
                    if label == "phone number" and ALLOWED_PHONE.search(text):
                        continue
                    problems.append(f"{path}:{number}: {label}: {text}")
            if path in ATTRIBUTION_FILES:
                continue
            for pattern in personal:
                match = pattern.search(line)
                if match:
                    problems.append(f"{path}:{number}: personal term: {match.group(0)}")
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s) in {len(tracked(args.ref))} tracked files" + ("" if personal else " (no private/denylist.txt)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
