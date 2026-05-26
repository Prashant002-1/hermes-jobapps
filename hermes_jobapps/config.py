"""Configuration loading for Hermes JobApps."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "jobapps.default.json"


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load committed defaults, then overlay an optional local JSON config."""

    config = _read_json(DEFAULT_CONFIG_PATH)
    local_path = Path(
        path
        or os.environ.get("HERMES_JOBAPPS_CONFIG", PROJECT_ROOT / "config" / "jobapps.local.json")
    )
    if local_path.exists():
        config = _deep_merge(config, _read_json(local_path))

    db_override = os.environ.get("HERMES_JOBAPPS_DB")
    if db_override:
        config["database_path"] = db_override

    hermes_api_base = os.environ.get("HERMES_API_BASE")
    if hermes_api_base:
        config.setdefault("hermes", {})["api_base"] = hermes_api_base

    hermes_api_model = os.environ.get("HERMES_API_MODEL")
    if hermes_api_model:
        config.setdefault("hermes", {})["model"] = hermes_api_model

    hermes_api_key = os.environ.get("HERMES_API_KEY")
    if hermes_api_key:
        config.setdefault("hermes", {})["api_key"] = hermes_api_key

    return config


def resolve_project_path(value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def save_config_overlay(overlay: dict[str, Any], path: str | os.PathLike[str] | None = None) -> Path:
    """Write an overlay config to the local config path, preserving existing keys."""
    local_path = Path(
        path
        or os.environ.get("HERMES_JOBAPPS_CONFIG", PROJECT_ROOT / "config" / "jobapps.local.json")
    )
    existing: dict[str, Any] = {}
    if local_path.exists():
        existing = _read_json(local_path)
    merged = _deep_merge(existing, overlay)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2)
    return local_path
