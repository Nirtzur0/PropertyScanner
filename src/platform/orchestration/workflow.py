from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import structlog

from src.agentic.orchestrator import CognitiveOrchestrator
from src.agentic.plan import build_default_plan, coerce_plan
from src.platform.pipeline.state import PipelineStateService

logger = structlog.get_logger()


class Orchestrator:
    """
    Compatibility wrapper that runs the plan-executor cognitive stack.
    """

    def __init__(self, max_iterations: int = 20) -> None:
        self.cognitive = CognitiveOrchestrator(max_iterations=max_iterations)
        self.state_service = PipelineStateService()

    def _pipeline_status(self) -> Dict[str, Any]:
        try:
            return self.state_service.snapshot().to_dict()
        except Exception as e:
            return {"error": str(e), "needs_refresh": False, "reasons": ["pipeline_status_failed"]}

    def run_job(
        self,
        target_area: str = None,
        query: Optional[str] = None,
        strategy: str = "balanced",
    ) -> Dict[str, Any]:
        if not target_area:
            raise ValueError("target_area_required")

        query = query or f"Analyze listings for {target_area}"
        pipeline_status = self._pipeline_status()

        plan = build_default_plan(query, [target_area], pipeline_status=pipeline_status)
        plan = coerce_plan(plan, pipeline_status=pipeline_status)

        logger.info("orchestrator_plan_run", target_area=target_area)
        return self.cognitive.run(
            query=query,
            areas=[target_area],
            plan=plan.model_dump(mode="json"),
            strategy=strategy,
        )

    def run_batch(
        self,
        target_areas: List[str],
        max_workers: int = 3,
        strategy: str = "balanced",
    ) -> List[Dict[str, Any]]:
        """
        Runs multiple jobs in parallel (e.g. for different neighborhoods).
        """
        if not target_areas:
            return []

        logger.info("starting_batch_job", targets=target_areas, workers=max_workers)
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_area = {
                executor.submit(self.run_job, area, strategy=strategy): area
                for area in target_areas
            }

            for future in as_completed(future_to_area):
                area = future_to_area[future]
                try:
                    results.append(future.result())
                    logger.info("batch_job_completed", area=area)
                except Exception as e:
                    logger.error("batch_job_failed", area=area, error=str(e))
                    results.append({"error": str(e), "area": area})

        return results
