"""
Cognitive Orchestrator: LangGraph-powered agent for property analysis.
Replaces the static pipeline with an intelligent, adaptive workflow.
"""
import structlog
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.agentic.graph import create_cognitive_graph, create_initial_state

logger = structlog.get_logger()


class CognitiveOrchestrator:
    """
    LangGraph-powered cognitive agent for property analysis.
    
    Unlike the static Orchestrator, this agent:
    - Uses LLM reasoning to decide next actions
    - Adapts based on intermediate results  
    - Can recover from errors intelligently
    - Generates natural language reports
    
    Usage:
        orchestrator = CognitiveOrchestrator()
        result = orchestrator.run("Find undervalued apartments in Madrid")
        print(result["final_report"])
    """
    
    def __init__(self, max_iterations: int = 20):
        """
        Initialize the cognitive orchestrator.
        
        Args:
            max_iterations: Maximum graph iterations to prevent infinite loops
        """
        self.max_iterations = max_iterations
        self._graph = None
        
    @property
    def graph(self):
        """Lazy-load the graph to avoid slow startup."""
        if self._graph is None:
            logger.info("initializing_cognitive_graph")
            self._graph = create_cognitive_graph()
        return self._graph
        
    def run(
        self, 
        query: str, 
        areas: Optional[List[str]] = None,
        stream: bool = False,
        plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run the cognitive agent with a natural language query.
        
        Args:
            query: Natural language query (e.g., "Find investment opportunities in Barcelona")
            areas: Optional list of search paths/URLs to crawl
            stream: If True, yield intermediate states
            plan: Optional deterministic plan override
            
        Returns:
            Final state dict containing:
            - final_report: Natural language analysis
            - evaluations: List of deal analyses
            - canonical_listings: All processed listings
            - messages: Agent reasoning trace
        """
        logger.info("cognitive_run_started", query=query, areas=areas)

        if not areas:
            raise ValueError("areas_required")

        plan_payload = plan
        if plan is not None and hasattr(plan, "model_dump"):
            plan_payload = plan.model_dump(mode="json")

        initial_state = create_initial_state(query, areas, plan=plan_payload)
        
        config = {
            "recursion_limit": self.max_iterations
        }
        
        if stream:
            return self._run_streaming(initial_state, config)
        else:
            return self._run_batch(initial_state, config)
            
    def _run_batch(self, initial_state: Dict, config: Dict) -> Dict[str, Any]:
        """Execute graph in batch mode."""
        try:
            final_state = self.graph.invoke(initial_state, config)
            logger.info(
                "cognitive_run_completed",
                listings=final_state.get("listings_count", 0),
                evaluations=len(final_state.get("evaluations", []))
            )
            return final_state
            
        except Exception as e:
            logger.error("cognitive_run_failed", error=str(e))
            return {
                "error": str(e),
                "final_report": f"Analysis failed: {e}",
                "evaluations": [],
                "canonical_listings": []
            }
            
    def _run_streaming(self, initial_state: Dict, config: Dict):
        """Execute graph with streaming updates."""
        try:
            for state in self.graph.stream(initial_state, config):
                yield state
        except Exception as e:
            logger.error("cognitive_stream_failed", error=str(e))
            yield {"error": str(e)}
            
    def run_batch_areas(
        self, 
        query: str, 
        areas: List[str],
        parallel: bool = False
    ) -> Dict[str, Any]:
        """
        Run analysis across multiple areas.
        
        Args:
            query: Base query
            areas: List of search paths
            parallel: Whether to run in parallel
            
        Returns:
            Aggregated results from all areas
        """
        if not parallel or not areas or len(areas) <= 1:
            return self.run(query, areas)

        results = []
        with ThreadPoolExecutor(max_workers=min(len(areas), 10)) as executor:
            future_to_area = {
                executor.submit(self.run, query, [area]): area
                for area in areas
            }

            for future in as_completed(future_to_area):
                area = future_to_area[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error("parallel_area_failed", area=area, error=str(e))
                    results.append({
                        "error": str(e),
                        "final_report": f"Analysis failed for {area}: {e}",
                        "evaluations": [],
                        "canonical_listings": []
                    })

        # Aggregate results
        aggregated_results = {
            "final_report": "",
            "evaluations": [],
            "canonical_listings": [],
            "messages": []
        }

        reports = []
        for res in results:
            if "evaluations" in res:
                aggregated_results["evaluations"].extend(res["evaluations"])
            if "canonical_listings" in res:
                aggregated_results["canonical_listings"].extend(res["canonical_listings"])
            if "messages" in res:
                aggregated_results["messages"].extend(res["messages"])
            if "final_report" in res:
                reports.append(res["final_report"])

        # Combine reports
        aggregated_results["final_report"] = "\n\n---\n\n".join(reports)

        return aggregated_results
