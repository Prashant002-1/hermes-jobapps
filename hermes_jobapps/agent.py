"""Agent-centric workflow orchestration for Hermes JobApps."""

from __future__ import annotations

from typing import Any

from .workflow import JobAppsWorkflow


class JobAppsAgent(JobAppsWorkflow):
    """Backward-compatible alias for the local workflow preparer."""

    def run_opportunity(self, job: dict[str, Any]) -> dict[str, Any]:
        return self.prepare_opportunity(job)
