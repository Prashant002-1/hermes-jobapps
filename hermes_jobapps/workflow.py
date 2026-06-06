"""Local workflow helpers that prepare database state for Hermes."""

from __future__ import annotations

from typing import Any

from .prompts import build_opportunity_prompt
from .repository import JobRepository
from .tools import AgentToolbox


class JobAppsWorkflow:
    def __init__(self, repo: JobRepository, toolbox: AgentToolbox) -> None:
        self.repo = repo
        self.toolbox = toolbox

    def prepare_opportunity(self, job: dict[str, Any]) -> dict[str, Any]:
        run = self.repo.create_agent_run("Prepare opportunity for Hermes research, tailoring, and tracking.")
        run_id = run["id"]
        try:
            context = self.repo.career_context(use="resume")
            evaluation = self.toolbox.execute(
                "jobapps_evaluate_job",
                {"job": job, "context": context},
                run_id=run_id,
            )
            record = self.toolbox.execute(
                "jobapps_record_job",
                {"job": job, "evaluation": evaluation},
                run_id=run_id,
            )
            job_id = record["job"]["id"]
            self.repo.record_evaluation_signals(job_id, evaluation)
            self._record_tailoring_state(job_id, evaluation)
            self.repo.update_agent_run(run_id, job_id=job_id)
            prompt = build_opportunity_prompt(record["job"], context, evaluation)
            prompt_record = self.toolbox.execute(
                "jobapps_save_prompt",
                {
                    "job_id": job_id,
                    "prompt_type": "opportunity_research_tailor",
                    "prompt": prompt,
                    "context_snapshot": {"evaluation": evaluation},
                },
                run_id=run_id,
            )
            self.repo.update_agent_run(run_id, prompt_id=prompt_record["id"])
            self._create_default_progress(job_id, evaluation, run_id)
            finished = self.repo.finish_agent_run(run_id)
            record = self.repo.get_job(job_id)
            record["run"] = finished
            record["prompt_to_hermes"] = prompt_record
            record["tool_calls"] = list(reversed(self.repo.list_tool_calls(run_id=run_id)))
            return record
        except Exception:
            self.repo.finish_agent_run(run_id, status="failed")
            raise

    def _record_tailoring_state(self, job_id: str, evaluation: dict[str, Any]) -> None:
        for index, target in enumerate(evaluation.get("tailoring_targets", []) or []):
            requirement = self.repo.record_tailoring_requirement(
                job_id,
                str(target.get("requirement") or ""),
                source_text=str(target.get("requirement") or ""),
                category=str(target.get("category") or "general"),
                priority=float(target.get("priority") or max(0.35, 1.0 - index * 0.08)),
                status=str(target.get("status") or "targeted"),
                metadata={
                    "requested_portrayal": target.get("requested_portrayal", ""),
                    "proof_candidates": target.get("proof_candidates", []),
                },
            )
            proof_candidates = target.get("proof_candidates") or []
            proof_id = proof_candidates[0].get("proof_id") if proof_candidates else None
            self.repo.record_portrayal_decision(
                job_id,
                target="candidate_materials",
                after_text=str(target.get("requested_portrayal") or target.get("requirement") or ""),
                rationale=f"JD-grounded tailoring target: {target.get('requirement', '')}",
                requirement_id=requirement["id"],
                proof_id=proof_id,
                decision_type="jd_grounded_portrayal",
                source="local_prepare",
                metadata={"category": target.get("category"), "status": target.get("status")},
            )

    def _create_default_progress(self, job_id: str, evaluation: dict[str, Any], run_id: str) -> None:
        """Material preparation records artifacts/state only; it must not create dashboard Actions.

        Actions are reserved for real external work such as sending an outreach email or a
        due networking follow-up. Research, material review, generic submission reminders,
        and other obvious workflow steps stay in materials, events, notes, and job state.
        """
        return None
