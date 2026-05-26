"""Private seed import helpers for JobApps.

Imports are explicit structured records. Runtime code never depends on the
shape of a private HTML/profile file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import load_config, resolve_project_path
from .repository import JobRepository
from .runs import _extract_jobapps_records


IMPORT_MARKER = "JOBAPPS_IMPORT_RECORDS"


def load_import_records(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    if source_path.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = _extract_marked_json(text)
    return normalize_import_records(raw)


def import_private_seed(
    repo: JobRepository,
    path: str | Path,
    *,
    source: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    records = load_import_records(path)
    source_label = source or f"private_import:{Path(path).name}"
    imported: dict[str, list[dict[str, Any]]] = {"profile_facts": [], "proof_points": []}

    for fact in records["profile_facts"]:
        payload = {
            "fact_key": fact["fact_key"],
            "value": fact["value"],
            "category": fact.get("category", "profile"),
            "source": fact.get("source") or source_label,
            "confidence": float(fact.get("confidence", 1.0)),
        }
        imported["profile_facts"].append(payload if dry_run else repo.upsert_profile_fact(**payload))

    for proof in records["proof_points"]:
        payload = {
            "label": proof["label"],
            "summary": proof["summary"],
            "evidence": proof["evidence"],
            "role_family": proof.get("role_family", "other"),
            "tags": proof.get("tags", []),
            "source": proof.get("source") or source_label,
            "confidence": float(proof.get("confidence", 1.0)),
            "proof_id": proof.get("id"),
        }
        imported["proof_points"].append(payload if dry_run else repo.upsert_proof_point(**payload))

    return {
        "source": source_label,
        "dry_run": dry_run,
        "profile_facts": imported["profile_facts"],
        "proof_points": imported["proof_points"],
    }


def normalize_import_records(raw: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        raise ValueError("Import records must be a JSON object.")
    if isinstance(raw.get("jobapps_import"), dict):
        raw = raw["jobapps_import"]

    profile_facts = _records(raw.get("profile_facts"), ("fact_key", "value"))
    proof_points = _records(raw.get("proof_points"), ("label", "summary", "evidence"))
    if not profile_facts and not proof_points:
        raise ValueError("No profile_facts or proof_points found in import records.")
    return {"profile_facts": profile_facts, "proof_points": proof_points}


def _extract_marked_json(text: str) -> dict[str, Any]:
    marker_index = text.find(IMPORT_MARKER)
    if marker_index >= 0:
        start = text.find("{", marker_index)
        if start >= 0:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
            return value

    records = _extract_jobapps_records(text)
    if records:
        return records
    raise ValueError(
        f"Non-JSON imports must include a {IMPORT_MARKER} JSON block. "
        "Import useful private facts into structured records first."
    )


def _records(value: Any, required: tuple[str, ...]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{required[0]} records must be a list.")
    output = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Import record {index} must be an object.")
        missing = [key for key in required if not item.get(key)]
        if missing:
            raise ValueError(f"Import record {index} is missing: {', '.join(missing)}.")
        output.append(item)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Import private JobApps seed records into SQLite.")
    parser.add_argument("path", help="JSON, Markdown, text, or HTML file containing structured JobApps import records.")
    parser.add_argument("--db", default=None, help="SQLite path. Defaults to configured JobApps database.")
    parser.add_argument("--config", default=None, help="Optional local config JSON path.")
    parser.add_argument("--source", default=None, help="Source label stored on imported rows.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print records without writing.")
    args = parser.parse_args()

    config = load_config(args.config)
    db_path = args.db or config.get("database_path") or "data/hermes-jobapps.sqlite3"
    repo = JobRepository(resolve_project_path(db_path))
    result = import_private_seed(repo, args.path, source=args.source, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
