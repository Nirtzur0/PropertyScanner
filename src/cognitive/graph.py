"""
LangGraph Workflow for Cognitive Property Scanner.
Implements a plan-executor graph with deterministic run plans.
"""
import json
import os
import structlog
from typing import Literal, Dict, Any, List, Optional, Tuple
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from src.cognitive.state import AgentState
from src.cognitive.plan import ActionType, AgentPlan, build_default_plan, coerce_plan, default_action_budgets
from src.cognitive.source_router import SourceRouter
from src.cognitive.tools import (
    crawl_listings,
    normalize_listings,
    evaluate_listing,
    enrich_listings,
    filter_listings,
    preflight_pipeline,
    harvest_pipeline,
    build_market_data_workflow,
    build_vector_index_workflow,
    train_model_workflow,
)

logger = structlog.get_logger()


def get_llm(temperature: float = 0):
    """
    Get LLM instance with automatic provider detection.
    Priority: Ollama (local, fast) > Gemini (GOOGLE_API_KEY) > OpenAI (OPENAI_API_KEY)
    """
    # Try Ollama first (local, no API costs)
    try:
        from langchain_community.llms import Ollama
        logger.info("using_ollama_llm")
        return Ollama(model="gpt-oss:latest", temperature=temperature)
    except Exception as e:
        logger.warning("ollama_init_failed", error=str(e))
    
    # Try Gemini
    if os.getenv("GOOGLE_API_KEY"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            logger.info("using_gemini_llm")
            # Try gemini-1.5-pro or gemini-2.0-flash-exp
            return ChatGoogleGenerativeAI(
                model="gemini-2.0-flash-exp",
                temperature=temperature,
                google_api_key=os.getenv("GOOGLE_API_KEY")
            )
        except Exception as e:
            logger.warning("gemini_init_failed", error=str(e))
    
    # Fallback to OpenAI
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        logger.info("using_openai_llm")
        return ChatOpenAI(model="gpt-4o-mini", temperature=temperature)
    
    raise RuntimeError("No LLM provider available. Install Ollama, set GOOGLE_API_KEY, or set OPENAI_API_KEY")

PLANNER_PROMPT = """You are a workflow planner for a property investment agent.
Return a JSON plan only (no markdown, no commentary).

JSON schema:
{{
  "objective": "<string>",
  "deterministic": true,
  "budgets": {{
    "max_steps": <int>,
    "max_action_calls": {default_budgets}
  }},
  "steps": [
    {{"action": "<action>", "params": {{"...": "..."}}, "rationale": "<optional>"}}
  ]
}}

Available actions:
preflight, harvest, build_market_data, build_index, train_model,
crawl, normalize, enrich, filter, evaluate, report

Rules:
- Use deterministic plans only.
- If pipeline_status indicates refresh needed, include missing pipeline actions first.
- End with report.

Context:
query: {query}
target_areas: {target_areas}
pipeline_status: {pipeline_status}
"""


def _parse_plan_payload(content: str) -> Optional[Dict[str, Any]]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def create_initial_state(
    query: str,
    areas: List[str] = None,
    plan: Optional[Dict[str, Any]] = None,
    tool_budgets: Optional[Dict[str, int]] = None,
) -> AgentState:
    """Create initial state for a new agent run."""
    try:
        from src.services.pipeline_state import PipelineStateService
        pipeline_status = PipelineStateService().snapshot().to_dict()
    except Exception as e:
        pipeline_status = {"error": str(e), "needs_refresh": False, "reasons": ["pipeline_status_failed"]}

    return AgentState(
        query=query,
        target_areas=areas or [],
        raw_listings=[],
        canonical_listings=[],
        evaluations=[],
        messages=[],
        current_stage="init",
        next_action="plan",
        error_count=0,
        sources_crawled=[],
        listings_count=0,
        enriched_count=0,
        enrichment_status="pending",
        filtered_count=0,
        final_report=None,
        strategy="balanced",
        pipeline_status=pipeline_status,
        pipeline_checked=False,
        plan=plan,
        plan_step_index=0,
        plan_status="pending",
        tool_usage={},
        tool_budgets=tool_budgets or {},
    )


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Plan a deterministic execution sequence and budgets."""
    try:
        pipeline_status = state.get("pipeline_status", {})
        incoming_plan = state.get("plan")

        if incoming_plan:
            plan = coerce_plan(incoming_plan, pipeline_status=pipeline_status)
        else:
            try:
                llm = get_llm(temperature=0)
                prompt = PLANNER_PROMPT.format(
                    query=state["query"],
                    target_areas=state["target_areas"],
                    pipeline_status=pipeline_status,
                    default_budgets=json.dumps(default_action_budgets()),
                )
                messages = [
                    SystemMessage(content=prompt),
                    HumanMessage(content="Generate the plan JSON."),
                ]
                response = llm.invoke(messages)

                if hasattr(response, "content"):
                    content = response.content
                else:
                    content = str(response)

                payload = _parse_plan_payload(content)
                if payload:
                    try:
                        plan = AgentPlan.model_validate(payload)
                    except Exception as e:
                        logger.warning("plan_payload_invalid", error=str(e))
                        plan = build_default_plan(
                            state["query"],
                            state["target_areas"],
                            pipeline_status=pipeline_status,
                        )
                else:
                    logger.warning("plan_payload_missing")
                    plan = build_default_plan(
                        state["query"],
                        state["target_areas"],
                        pipeline_status=pipeline_status,
                    )
            except Exception as e:
                logger.warning("planner_llm_failed", error=str(e))
                plan = build_default_plan(
                    state["query"],
                    state["target_areas"],
                    pipeline_status=pipeline_status,
                )

        plan = coerce_plan(plan, pipeline_status=pipeline_status)
        plan_payload = plan.model_dump(mode="json")
        tool_budgets = plan_payload.get("budgets", {}).get("max_action_calls", {}) or {}
        tool_usage = {action: 0 for action in tool_budgets.keys()}
        plan_status = "completed" if not plan_payload.get("steps") else "active"

        return {
            "plan": plan_payload,
            "plan_step_index": 0,
            "plan_status": plan_status,
            "tool_budgets": tool_budgets,
            "tool_usage": tool_usage,
            "current_stage": "planner",
            "messages": [{"role": "planner", "content": "plan ready"}],
        }
    except Exception as e:
        logger.error("planner_failed", error=str(e))
        raise



def crawl_node(state: AgentState) -> Dict[str, Any]:
    """Execute crawling based on target areas."""
    logger.info("crawl_node_started", areas=state["target_areas"])
    
    raw_listings = []
    seen_keys = set()
    sources_crawled = list(state["sources_crawled"])
    router = SourceRouter()
    unresolved_areas = []
    crawl_errors = []

    def _listing_key(raw: Dict[str, Any]) -> Optional[str]:
        for key in ("id", "external_id", "url"):
            value = raw.get(key)
            if value:
                return str(value)
        return None
    
    # Determine search path
    areas = state["target_areas"]
    if not areas:
        raise ValueError("target_areas_required")
    
    for area in areas:
        try:
            targets = router.resolve(area)
            if not targets:
                unresolved_areas.append(area)
                continue

            for target in targets:
                result = crawl_listings.invoke({
                    "search_path": target.search_path,
                    "source_id": target.source_id,
                })

                if result["status"] == "success":
                    for item in result["data"]:
                        key = _listing_key(item)
                        if key and key in seen_keys:
                            continue
                        if key:
                            seen_keys.add(key)
                        raw_listings.append(item)
                    if target.source_id not in sources_crawled:
                        sources_crawled.append(target.source_id)
                else:
                    crawl_errors.append(f"{target.source_id}:{area}")
                
        except Exception as e:
            logger.error("crawl_failed", area=area, error=str(e))
            crawl_errors.append(f"{area}:{e}")

    if unresolved_areas:
        logger.warning("crawl_source_unresolved", areas=unresolved_areas)
    if crawl_errors:
        logger.warning("crawl_source_failed", errors=crawl_errors)

    messages = [{
        "role": "crawl",
        "content": f"Crawled {len(raw_listings)} listings",
    }]
    if unresolved_areas:
        messages.append({
            "role": "crawl",
            "content": f"Unresolved areas: {', '.join(unresolved_areas)}",
        })
    if crawl_errors:
        messages.append({
            "role": "crawl",
            "content": f"Crawl errors: {', '.join(crawl_errors)}",
        })

    return {
        "raw_listings": raw_listings,
        "sources_crawled": sources_crawled,
        "current_stage": "crawled",
        "messages": messages,
    }


def normalize_node(state: AgentState) -> Dict[str, Any]:
    """Normalize all raw listings."""
    logger.info("normalize_node_started", count=len(state["raw_listings"]))
    
    canonical_listings = []
    
    # Group by source
    by_source: Dict[str, List] = {}
    for raw in state["raw_listings"]:
        source_id = raw.get("source_id", "idealista")
        if source_id not in by_source:
            by_source[source_id] = []
        by_source[source_id].append(raw)
    
    for source_id, raws in by_source.items():
        try:
            result = normalize_listings.invoke({
                "raw_listings": raws,
                "source_id": source_id
            })
            
            if result["status"] in ["success", "partial"]:
                canonical_listings.extend(result["data"])
                
        except Exception as e:
            logger.error("normalize_failed", source=source_id, error=str(e))
            
    return {
        "canonical_listings": canonical_listings,
        "listings_count": len(canonical_listings),
        "current_stage": "normalized",
        "messages": [{"role": "normalize", "content": f"Normalized {len(canonical_listings)} listings"}]
    }


def enrich_node(state: AgentState) -> Dict[str, Any]:
    """Enrich listings with location data."""
    logger.info("enrich_node_started", count=len(state["canonical_listings"]))

    try:
        result = enrich_listings.invoke({
            "listings": state["canonical_listings"]
        })

        if result["status"] == "success":
            return {
                "canonical_listings": result["data"], # Replace with enriched versions
                "enriched_count": result.get("enriched_count", 0),
                "enrichment_status": "success",
                "current_stage": "enriched",
                "messages": [{"role": "enrich", "content": f"Enriched {result.get('enriched_count', 0)} listings"}]
            }
        else:
            return {
                 "enrichment_status": "failed",
                 "messages": [{"role": "enrich", "content": f"Enrichment failed: {result.get('errors')}"}]
            }

    except Exception as e:
        logger.error("enrich_node_failed", error=str(e))
        return {
            "enrichment_status": "failed",
            "messages": [{"role": "enrich", "content": f"Enrichment failed: {str(e)}"}]
        }


def filter_node(state: AgentState) -> Dict[str, Any]:
    """Filter low-quality listings (QC)."""
    logger.info("filter_node_started", count=len(state["canonical_listings"]))
    
    try:
        result = filter_listings.invoke({
            "listings": state["canonical_listings"]
        })
        
        if result["status"] == "success":
            return {
                "canonical_listings": result["data"], # Replace with filtered list
                "filtered_count": result["count"], # Current valid count
                "listings_count": result["count"], # Update main count too
                "current_stage": "filtered",
                "messages": [{"role": "filter", "content": f"Filtered listings. Kept {result['count']}, Dropped {result.get('dropped_count', 0)}"}]
            }
        else:
             return {
                 "messages": [{"role": "filter", "content": f"Filter failed: {result.get('errors')}"}]
             }
             
    except Exception as e:
        logger.error("filter_node_failed", error=str(e))
        return {
            "messages": [{"role": "filter", "content": f"Filter failed: {str(e)}"}]
        }


def preflight_node(state: AgentState) -> Dict[str, Any]:
    """Refresh stale data/index/model artifacts before analysis."""
    logger.info("preflight_node_started")

    try:
        result = preflight_pipeline.invoke(
            {
                "skip_harvest": False,
                "skip_market_data": False,
                "skip_index": False,
                "skip_training": False,
            }
        )
        if result.get("status") == "success":
            from src.services.pipeline_state import PipelineStateService

            pipeline_status = PipelineStateService().snapshot().to_dict()
            return {
                "pipeline_status": pipeline_status,
                "pipeline_checked": True,
                "current_stage": "preflight",
                "messages": [{"role": "preflight", "content": "Pipeline refreshed"}],
            }

        return {
            "pipeline_checked": True,
            "messages": [{"role": "preflight", "content": f"Preflight failed: {result.get('error')}"}],
        }

    except Exception as e:
        logger.error("preflight_node_failed", error=str(e))
        return {
            "pipeline_checked": True,
            "messages": [{"role": "preflight", "content": f"Preflight failed: {str(e)}"}],
        }


def evaluate_node(state: AgentState) -> Dict[str, Any]:
    """Evaluate listings for investment potential."""
    logger.info("evaluate_node_started", count=len(state["canonical_listings"]))
    
    evaluations = []
    
    # Evaluate top N listings (avoid rate limits)
    max_to_evaluate = min(len(state["canonical_listings"]), 10)
    
    strategy = state.get("strategy")
    if not strategy:
        raise ValueError("strategy_required")

    for listing in state["canonical_listings"][:max_to_evaluate]:
        try:
            result = evaluate_listing.invoke({
                "listing": listing,
                "num_comps": 5,
                "strategy": strategy
            })
            
            if result["status"] == "success" and result["data"]:
                evaluations.append(result["data"])
                
        except Exception as e:
            logger.error("evaluate_failed", listing_id=listing.get("id"), error=str(e))
            
    return {
        "evaluations": evaluations,
        "current_stage": "evaluated",
        "messages": [{"role": "evaluate", "content": f"Evaluated {len(evaluations)} listings"}]
    }


def report_node(state: AgentState) -> Dict[str, Any]:
    """Generate final investment report using LLM."""
    logger.info("report_node_started")
    
    try:
        llm = get_llm(temperature=0.3)
        
        # Prepare data summary
        top_deals = sorted(
            state["evaluations"],
            key=lambda x: x.get("deal_score", 0),
            reverse=True
        )[:5]
        
        deals_summary = "\n".join([
            f"- {e.get('listing_id', 'N/A')}: Score {e.get('deal_score', 0):.2f}, {e.get('investment_thesis', 'No thesis')}"
            for e in top_deals
        ])
        
        prompt = f"""Generate a concise investment report based on the following analysis:

Query: {state["query"]}
Total listings found: {state["listings_count"]}
Evaluations completed: {len(state["evaluations"])}

Top Investment Opportunities:
{deals_summary}

Write a professional investment brief (2-3 paragraphs) summarizing:
1. Market overview based on listings found
2. Top opportunities and why they're interesting
3. Recommendations for next steps
"""
        
        response = llm.invoke([HumanMessage(content=prompt)])
        
        # Handle both ChatModel and LLM responses
        if hasattr(response, 'content'):
            report_text = response.content
        else:
            report_text = str(response)
        
        return {
            "final_report": report_text,
            "current_stage": "complete",
            "messages": [{"role": "report", "content": "Report generated"}]
        }
        
    except Exception as e:
        logger.error("report_failed", error=str(e))
        raise


def _refresh_pipeline_status() -> Dict[str, Any]:
    try:
        from src.services.pipeline_state import PipelineStateService

        return PipelineStateService().snapshot().to_dict()
    except Exception as e:
        return {"error": str(e), "needs_refresh": False, "reasons": ["pipeline_status_failed"]}


def _run_workflow_action(
    state: AgentState,
    tool,
    action_label: str,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    payload = dict(params or {})
    result = tool.invoke(payload)
    success = result.get("status") == "success"
    content = f"{action_label} completed" if success else f"{action_label} failed: {result.get('error')}"
    update = {
        "messages": [{"role": action_label, "content": content}],
        "current_stage": action_label,
        "pipeline_checked": True,
    }
    if success:
        update["pipeline_status"] = _refresh_pipeline_status()
    return update, success


def _run_preflight_action(state: AgentState, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], bool]:
    payload = {
        "skip_harvest": False,
        "skip_market_data": False,
        "skip_index": False,
        "skip_training": False,
    }
    if params:
        payload.update(params)
    return _run_workflow_action(state, preflight_pipeline, "preflight", payload)


def _wrap_node(fn):
    def _runner(state: AgentState, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], bool]:
        return fn(state), True

    return _runner


def executor_node(state: AgentState) -> Dict[str, Any]:
    """Execute the next step in the deterministic plan."""
    plan_data = state.get("plan") or {}
    steps = plan_data.get("steps") or []
    step_index = state.get("plan_step_index", 0)

    budgets_data = plan_data.get("budgets") or {}
    max_steps = budgets_data.get("max_steps")
    if max_steps is not None and step_index >= max_steps:
        return {
            "plan_status": "budget_exhausted",
            "current_stage": "executor",
            "messages": [{"role": "executor", "content": "plan step budget exhausted"}],
        }

    if step_index >= len(steps):
        return {
            "plan_status": "completed",
            "current_stage": "executor",
            "messages": [{"role": "executor", "content": "plan complete"}],
        }

    step = steps[step_index]
    if isinstance(step, dict):
        action = step.get("action")
        params = step.get("params") or {}
    else:
        action = getattr(step, "action", None)
        params = getattr(step, "params", {}) or {}

    if isinstance(action, ActionType):
        action = action.value

    tool_budgets = state.get("tool_budgets") or {}
    tool_usage = dict(state.get("tool_usage") or {})
    budget = tool_budgets.get(action)

    if budget is not None and tool_usage.get(action, 0) >= budget:
        return {
            "plan_status": "budget_exhausted",
            "current_stage": "executor",
            "messages": [{"role": "executor", "content": f"budget exhausted for {action}"}],
        }

    runner = ACTION_RUNNERS.get(action)
    if not runner:
        return {
            "plan_status": "failed",
            "current_stage": "executor",
            "messages": [{"role": "executor", "content": f"unknown action {action}"}],
        }

    update, success = runner(state, params)
    tool_usage[action] = tool_usage.get(action, 0) + 1
    update["tool_usage"] = tool_usage
    update["plan_step_index"] = step_index + 1
    if "current_stage" not in update:
        update["current_stage"] = f"execute:{action}"

    messages = list(update.get("messages", []))
    if not success:
        messages.append({"role": "executor", "content": f"action {action} failed"})
        update["plan_status"] = "failed"
        update["error_count"] = state.get("error_count", 0) + 1
    else:
        update["plan_status"] = "active"

    update["messages"] = messages

    if update["plan_step_index"] >= len(steps) and success:
        update["plan_status"] = "completed"

    return update


ACTION_RUNNERS = {
    ActionType.PREFLIGHT.value: _run_preflight_action,
    ActionType.HARVEST.value: lambda state, params: _run_workflow_action(state, harvest_pipeline, "harvest", params),
    ActionType.BUILD_MARKET_DATA.value: lambda state, params: _run_workflow_action(
        state, build_market_data_workflow, "build_market_data", params
    ),
    ActionType.BUILD_INDEX.value: lambda state, params: _run_workflow_action(
        state, build_vector_index_workflow, "build_index", params
    ),
    ActionType.TRAIN_MODEL.value: lambda state, params: _run_workflow_action(
        state, train_model_workflow, "train_model", params
    ),
    ActionType.CRAWL.value: _wrap_node(crawl_node),
    ActionType.NORMALIZE.value: _wrap_node(normalize_node),
    ActionType.ENRICH.value: _wrap_node(enrich_node),
    ActionType.FILTER.value: _wrap_node(filter_node),
    ActionType.EVALUATE.value: _wrap_node(evaluate_node),
    ActionType.REPORT.value: _wrap_node(report_node),
}


def route_executor(state: AgentState) -> Literal["executor", "end"]:
    status = state.get("plan_status")
    if status in {"completed", "failed", "budget_exhausted"}:
        return "end"
    return "executor"


def create_cognitive_graph():
    """Build and compile the LangGraph workflow."""
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)

    graph.add_edge("planner", "executor")
    graph.add_conditional_edges(
        "executor",
        route_executor,
        {
            "executor": "executor",
            "end": END,
        },
    )

    graph.set_entry_point("planner")

    return graph.compile()
