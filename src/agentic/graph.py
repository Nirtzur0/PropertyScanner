"""
LangGraph Workflow for Cognitive Property Scanner.
Implements a plan-executor graph with deterministic run plans.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import structlog
from typing import Literal, Dict, Any, List, Optional, Tuple
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from src.agentic.state import AgentState
from src.agentic.plan import ActionType, AgentPlan, PlanStep, coerce_plan, default_action_budgets
from src.agentic.source_router import SourceRouter
from src.agentic.tools import (
    crawl_listings,
    normalize_listings,
    evaluate_listing,
    enrich_listings,
    filter_listings,
    preflight_pipeline,
    build_market_data_workflow,
    build_vector_index_workflow,
    train_model_workflow,
)
from src.platform.utils.llm import get_llm

logger = structlog.get_logger()


PLANNER_PROMPT = """You are the planning module for a property investment agent.
Return a single JSON object only (no markdown, no commentary, no extra keys).

Schema:
{{
  "objective": "<clear restatement of the user query>",
  "deterministic": true,
  "budgets": {{
    "max_steps": <int>,
    "max_action_calls": {default_budgets}
  }},
  "steps": [
    {{"action": "<action>", "params": {{"...": "..."}}, "rationale": "<optional>"}}
  ]
}}

Actions (use only these):
preflight, build_market_data, build_index, train_model,
crawl, normalize, enrich, filter, evaluate, quality_gate, report

Rules:
- deterministic must be true.
- If pipeline_status indicates needs_refresh, needs_crawl, needs_market_data,
  needs_index, or needs_training, include the required pipeline steps first.
- If pipeline_status contains an error, start with preflight.
- Include quality_gate immediately before report.
- End with report.
- Keep rationale to one short sentence when used.

Context:
query: {query}
target_areas: {target_areas}
pipeline_status: {pipeline_status}
strategy: {strategy}
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


def _query_requires_fresh_data(query: str) -> bool:
    tokens = (query or "").lower()
    freshness_terms = ["latest", "new", "fresh", "today", "this week", "recent", "just listed"]
    return any(term in tokens for term in freshness_terms)


def _plan_has_action(plan: AgentPlan, action: ActionType) -> bool:
    return any(step.action == action for step in plan.steps)


def create_initial_state(
    query: str,
    areas: List[str] = None,
    plan: Optional[Dict[str, Any]] = None,
    tool_budgets: Optional[Dict[str, int]] = None,
    strategy: str = "balanced",
    run_id: Optional[str] = None,
) -> AgentState:
    """Create initial state for a new agent run."""
    try:
        from src.platform.pipeline.state import PipelineStateService
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
        trace=[],
        current_stage="init",
        next_action="plan",
        error_count=0,
        errors=[],
        sources_crawled=[],
        listings_count=0,
        enriched_count=0,
        enrichment_status="pending",
        filtered_count=0,
        final_report=None,
        strategy=strategy,
        pipeline_status=pipeline_status,
        pipeline_checked=False,
        plan=plan,
        plan_step_index=0,
        plan_status="pending",
        tool_usage={},
        tool_budgets=tool_budgets or {},
        quality_checks=[],
        ui_blocks=[],
        run_id=run_id,
    )


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Plan a deterministic execution sequence and budgets."""
    try:
        pipeline_status = state.get("pipeline_status", {})
        incoming_plan = state.get("plan")

        if incoming_plan:
            plan = coerce_plan(incoming_plan, pipeline_status=pipeline_status)
        else:
            llm = get_llm(temperature=0)
            prompt = PLANNER_PROMPT.format(
                query=state["query"],
                target_areas=state["target_areas"],
                pipeline_status=pipeline_status,
                strategy=state.get("strategy", "balanced"),
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
            if not payload:
                raise ValueError("plan_payload_missing")

            plan = AgentPlan.model_validate(payload)

        plan = coerce_plan(plan, pipeline_status=pipeline_status)
        if _query_requires_fresh_data(state["query"]):
            if not _plan_has_action(plan, ActionType.PREFLIGHT) and not _plan_has_action(plan, ActionType.CRAWL):
                plan = plan.model_copy(update={"steps": [PlanStep(action=ActionType.PREFLIGHT)] + plan.steps})
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
    errors: List[str] = []

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
        errors.append(f"crawl:unresolved_areas:{','.join(unresolved_areas)}")
    if crawl_errors:
        logger.warning("crawl_source_failed", errors=crawl_errors)
        errors.append(f"crawl:errors:{','.join(crawl_errors)}")
    if not raw_listings:
        errors.append("crawl:no_listings")

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
        "errors": errors,
    }


def normalize_node(state: AgentState) -> Dict[str, Any]:
    """Normalize all raw listings."""
    logger.info("normalize_node_started", count=len(state["raw_listings"]))
    
    canonical_listings = []
    errors: List[str] = []
    
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
            else:
                errors.append(f"normalize:{source_id}:{result.get('errors')}")
                
        except Exception as e:
            logger.error("normalize_failed", source=source_id, error=str(e))
            errors.append(f"normalize:{source_id}:{e}")
            
    if not canonical_listings:
        errors.append("normalize:no_listings")

    return {
        "canonical_listings": canonical_listings,
        "listings_count": len(canonical_listings),
        "current_stage": "normalized",
        "messages": [{"role": "normalize", "content": f"Normalized {len(canonical_listings)} listings"}],
        "errors": errors,
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
                "messages": [{"role": "enrich", "content": f"Enriched {result.get('enriched_count', 0)} listings"}],
                "errors": [],
            }
        return {
            "enrichment_status": "failed",
            "current_stage": "enriched",
            "messages": [{"role": "enrich", "content": f"Enrichment failed: {result.get('errors')}"}],
            "errors": [f"enrich:{result.get('errors')}"],
        }

    except Exception as e:
        logger.error("enrich_node_failed", error=str(e))
        return {
            "enrichment_status": "failed",
            "current_stage": "enriched",
            "messages": [{"role": "enrich", "content": f"Enrichment failed: {str(e)}"}],
            "errors": [f"enrich:{str(e)}"],
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
                "messages": [{"role": "filter", "content": f"Filtered listings. Kept {result['count']}, Dropped {result.get('dropped_count', 0)}"}],
                "errors": [] if result["count"] > 0 else ["filter:no_listings"],
            }
        return {
            "current_stage": "filtered",
            "messages": [{"role": "filter", "content": f"Filter failed: {result.get('errors')}"}],
            "errors": [f"filter:{result.get('errors')}"],
        }
             
    except Exception as e:
        logger.error("filter_node_failed", error=str(e))
        return {
            "current_stage": "filtered",
            "messages": [{"role": "filter", "content": f"Filter failed: {str(e)}"}],
            "errors": [f"filter:{str(e)}"],
        }


def preflight_node(state: AgentState) -> Dict[str, Any]:
    """Refresh stale data/index/model artifacts before analysis."""
    logger.info("preflight_node_started")

    try:
        result = preflight_pipeline.invoke(
            {
                "skip_crawl": False,
                "skip_market_data": False,
                "skip_index": False,
                "skip_training": False,
            }
        )
        if result.get("status") == "success":
            from src.platform.pipeline.state import PipelineStateService

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
    errors: List[str] = []
    
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
            else:
                errors.append(f"evaluate:{listing.get('id', 'unknown')}")
                
        except Exception as e:
            logger.error("evaluate_failed", listing_id=listing.get("id"), error=str(e))
            errors.append(f"evaluate:{listing.get('id', 'unknown')}:{str(e)}")

    if not evaluations:
        errors.append("evaluate:no_results")
            
    return {
        "evaluations": evaluations,
        "current_stage": "evaluated",
        "messages": [{"role": "evaluate", "content": f"Evaluated {len(evaluations)} listings"}],
        "errors": errors,
    }


def report_node(state: AgentState) -> Dict[str, Any]:
    """Generate final investment report using LLM."""
    logger.info("report_node_started")
    
    try:
        llm = get_llm(temperature=0.3)

        ui_blocks = _build_ui_blocks(state)
        
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
        
        prompt = f"""You are writing an investment brief for a human reader.

Context:
Query: {state["query"]}
Listings found: {state["listings_count"]}
Evaluations completed: {len(state["evaluations"])}

Top opportunities (if any):
{deals_summary}

Write 2-3 short paragraphs:
1) Market overview and data coverage (note if coverage is thin or uneven).
2) Call out the top opportunities with score and thesis; if none, say so clearly.
3) Recommended next steps (refresh needs, data gaps, or due diligence priorities).

Use clear, professional language. Avoid bullet lists and headings.
"""
        
        response = llm.invoke([HumanMessage(content=prompt)])
        
        # Handle both ChatModel and LLM responses
        if hasattr(response, 'content'):
            report_text = response.content
        else:
            report_text = str(response)
        
        return {
            "final_report": report_text,
            "ui_blocks": ui_blocks,
            "current_stage": "complete",
            "messages": [{"role": "report", "content": "Report generated"}],
            "errors": [],
        }
        
    except Exception as e:
        logger.error("report_failed", error=str(e))
        raise


def _build_ui_blocks(state: AgentState) -> List[Dict[str, Any]]:
    evaluations = state.get("evaluations") or []
    top_evals = sorted(evaluations, key=lambda item: item.get("deal_score", 0), reverse=True)[:5]
    top_listing_ids = [e.get("listing_id") for e in top_evals if e.get("listing_id")]

    if not top_listing_ids:
        return []

    query = (state.get("query") or "").lower()
    blocks: List[Dict[str, Any]] = [
        {
            "type": "comparison_table",
            "title": "Top Deal Comparison",
            "listing_ids": top_listing_ids,
            "columns": ["Price", "Deal Score", "Yield %", "Value Delta %"],
        },
        {
            "type": "deal_score_chart",
            "title": "Deal Score Ranking",
            "listing_ids": top_listing_ids,
        },
    ]

    if "map" in query or "area" in query or "neighborhood" in query:
        blocks.append(
            {
                "type": "map_focus",
                "title": "Map Focus",
                "listing_ids": top_listing_ids,
                "zoom": 13,
            }
        )

    return blocks


def quality_gate_node(state: AgentState) -> Dict[str, Any]:
    """Run quality checks before reporting."""
    checks: List[Dict[str, Any]] = []
    errors: List[str] = []

    evaluations = state.get("evaluations") or []
    listings = state.get("canonical_listings") or []

    if not evaluations:
        errors.append("quality_gate:no_evaluations")
        checks.append({
            "check": "evaluations_present",
            "status": "fail",
            "detail": "No evaluated listings available for report.",
        })
    else:
        checks.append({
            "check": "evaluations_present",
            "status": "pass",
            "detail": f"{len(evaluations)} evaluations ready.",
        })

    listing_ids = set()
    for listing in listings:
        listing_id = listing.get("id") or listing.get("ID")
        if listing_id:
            listing_ids.add(str(listing_id))

    missing_listing_refs = []
    invalid_scores = []
    invalid_quantiles = []

    for evaluation in evaluations:
        listing_id = evaluation.get("listing_id")
        if listing_id and str(listing_id) not in listing_ids:
            missing_listing_refs.append(str(listing_id))

        score = evaluation.get("deal_score")
        if score is None or not isinstance(score, (int, float)) or score < 0 or score > 1:
            invalid_scores.append(str(listing_id or "unknown"))

        quantiles = evaluation.get("fair_value_quantiles") or {}
        try:
            p10 = float(quantiles.get("0.1"))
            p50 = float(quantiles.get("0.5"))
            p90 = float(quantiles.get("0.9"))
            if not (p10 <= p50 <= p90):
                invalid_quantiles.append(str(listing_id or "unknown"))
        except Exception:
            if quantiles:
                invalid_quantiles.append(str(listing_id or "unknown"))

    if missing_listing_refs:
        errors.append("quality_gate:missing_listings")
        checks.append({
            "check": "evaluation_listing_refs",
            "status": "fail",
            "detail": f"Missing listings for {len(missing_listing_refs)} evaluations.",
        })
    else:
        checks.append({
            "check": "evaluation_listing_refs",
            "status": "pass",
            "detail": "All evaluations map to canonical listings.",
        })

    if invalid_scores:
        errors.append("quality_gate:invalid_deal_scores")
        checks.append({
            "check": "deal_score_range",
            "status": "fail",
            "detail": f"Invalid deal_score values for {len(invalid_scores)} evaluations.",
        })
    else:
        checks.append({
            "check": "deal_score_range",
            "status": "pass",
            "detail": "Deal scores are within expected range.",
        })

    if invalid_quantiles:
        errors.append("quality_gate:invalid_quantiles")
        checks.append({
            "check": "fair_value_quantiles",
            "status": "fail",
            "detail": f"Invalid fair value quantiles for {len(invalid_quantiles)} evaluations.",
        })
    else:
        checks.append({
            "check": "fair_value_quantiles",
            "status": "pass",
            "detail": "Fair value quantiles are ordered.",
        })

    return {
        "quality_checks": checks,
        "current_stage": "quality_gate",
        "messages": [{"role": "quality_gate", "content": "Quality checks complete"}],
        "errors": errors,
    }


def _refresh_pipeline_status() -> Dict[str, Any]:
    try:
        from src.platform.pipeline.state import PipelineStateService

        return PipelineStateService().snapshot().to_dict()
    except Exception as e:
        return {"error": str(e), "needs_refresh": False, "reasons": ["pipeline_status_failed"]}


ACTION_TIMEOUTS = {
    "preflight": 1800,
    "build_market_data": 1200,
    "build_index": 1200,
    "train_model": 1800,
    "crawl": 900,
    "normalize": 300,
    "enrich": 300,
    "filter": 120,
    "evaluate": 600,
    "quality_gate": 60,
    "report": 180,
}


def _run_workflow_action(
    state: AgentState,
    tool,
    action_label: str,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    payload = dict(params or {})
    start_ts = time.monotonic()
    error_detail = None
    result = None
    timeout_s = ACTION_TIMEOUTS.get(action_label)
    try:
        if timeout_s:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(tool.invoke, payload)
                result = future.result(timeout=timeout_s)
        else:
            result = tool.invoke(payload)
    except FutureTimeoutError:
        error_detail = f"timeout_after_{timeout_s}s"
    except Exception as exc:
        error_detail = str(exc)

    success = False
    if error_detail is None:
        success = result.get("status") == "success"
        if not success:
            error_detail = result.get("error") or result.get("errors") or "tool_failed"

    content = f"{action_label} completed" if success else f"{action_label} failed: {error_detail}"
    duration_ms = int((time.monotonic() - start_ts) * 1000)
    trace_entry = {
        "action": action_label,
        "status": "success" if success else "failed",
        "duration_ms": duration_ms,
        "error": error_detail,
        "params": payload,
    }
    update = {
        "messages": [{"role": action_label, "content": content}],
        "current_stage": action_label,
        "pipeline_checked": True,
        "trace": [trace_entry],
        "errors": [] if success else [f"{action_label}:{error_detail}"],
    }
    if success:
        update["pipeline_status"] = _refresh_pipeline_status()
    return update, success


def _run_preflight_action(state: AgentState, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], bool]:
    payload = {
        "skip_crawl": False,
        "skip_market_data": False,
        "skip_index": False,
        "skip_training": False,
    }
    if params:
        payload.update(params)
    return _run_workflow_action(state, preflight_pipeline, "preflight", payload)


def _wrap_node(fn, action_label: Optional[str] = None):
    label = action_label or fn.__name__.replace("_node", "")

    def _runner(state: AgentState, params: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], bool]:
        start_ts = time.monotonic()
        timeout_s = ACTION_TIMEOUTS.get(label)
        error_detail = None
        update: Dict[str, Any] = {}

        try:
            if timeout_s:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(fn, state)
                    update = future.result(timeout=timeout_s)
            else:
                update = fn(state)
        except FutureTimeoutError:
            error_detail = f"timeout_after_{timeout_s}s"
            update = {"messages": [{"role": label, "content": f"{label} timed out"}], "errors": [error_detail]}
        except Exception as exc:
            error_detail = str(exc)
            update = {"messages": [{"role": label, "content": f"{label} failed"}], "errors": [error_detail]}

        errors = update.get("errors") or []
        success = not errors
        if errors and not error_detail:
            error_detail = "; ".join(str(err) for err in errors)

        duration_ms = int((time.monotonic() - start_ts) * 1000)
        trace_entry = {
            "action": label,
            "status": "success" if success else "failed",
            "duration_ms": duration_ms,
            "error": error_detail,
        }
        update["trace"] = [trace_entry]
        update["current_stage"] = update.get("current_stage", label)
        update["errors"] = errors if errors else []

        return update, success

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
    ActionType.BUILD_MARKET_DATA.value: lambda state, params: _run_workflow_action(
        state, build_market_data_workflow, "build_market_data", params
    ),
    ActionType.BUILD_INDEX.value: lambda state, params: _run_workflow_action(
        state, build_vector_index_workflow, "build_index", params
    ),
    ActionType.TRAIN_MODEL.value: lambda state, params: _run_workflow_action(
        state, train_model_workflow, "train_model", params
    ),
    ActionType.CRAWL.value: _wrap_node(crawl_node, "crawl"),
    ActionType.NORMALIZE.value: _wrap_node(normalize_node, "normalize"),
    ActionType.ENRICH.value: _wrap_node(enrich_node, "enrich"),
    ActionType.FILTER.value: _wrap_node(filter_node, "filter"),
    ActionType.EVALUATE.value: _wrap_node(evaluate_node, "evaluate"),
    ActionType.QUALITY_GATE.value: _wrap_node(quality_gate_node, "quality_gate"),
    ActionType.REPORT.value: _wrap_node(report_node, "report"),
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
