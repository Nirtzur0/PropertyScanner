"""
LangGraph Workflow for Cognitive Property Scanner.
Implements a supervisor-based graph with conditional routing.
"""
import os
import structlog
from typing import Literal, Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.cognitive.state import AgentState
from src.cognitive.tools import TOOLS, crawl_listings, normalize_listings, evaluate_listing, enrich_listings, filter_listings

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



# System prompt for the supervisor
# System prompt for the supervisor
SUPERVISOR_PROMPT = """You are a property investment analyst agent. Your job is to help users find and evaluate real estate opportunities.

You have access to the following tools:
- crawl_listings: Fetch property listings from real estate websites
- normalize_listings: Convert raw listings to structured format
- enrich_listings: Add location details (city) to listings
- filter_listings: Remove low-quality listings (QC)
- evaluate_listing: Analyze a listing for investment potential
- retrieve_comparables: Find similar properties for comparison

Based on the current state, decide what action to take next.

Current state:
- Query: {query}
- Target areas: {target_areas}
- Sources crawled: {sources_crawled}
- Raw listings found: {raw_count}
- Canonical Listings (Normalized): {listings_count}
- Enriched listings: {enriched_count}
- Enrichment status: {enrichment_status}
- Filtered listings count: {filtered_count}
- Evaluations completed: {evaluations_count}

Typical flow: Crawl -> Normalize -> Enrich -> Filter -> Evaluate -> Report

If you have unprocessed raw listings, choose "normalize".
If you have normalized listings but status is pending, choose "enrich".
If you have enriched listings, choose "filter".
If you have filtered listings, choose "evaluate".
If you have evaluations, generate a final report.

Respond with one of: "crawl", "normalize", "enrich", "filter", "evaluate", "report", or "end"
"""


def create_initial_state(query: str, areas: List[str] = None) -> AgentState:
    """Create initial state for a new agent run."""
    return AgentState(
        query=query,
        target_areas=areas or [],
        raw_listings=[],
        canonical_listings=[],
        evaluations=[],
        messages=[],
        current_stage="init",
        next_action="crawl",
        error_count=0,
        sources_crawled=[],
        listings_count=0,
        enriched_count=0,
        enrichment_status="pending",
        filtered_count=0,
        final_report=None,
        strategy="balanced"
    )


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    LLM-powered supervisor that decides the next action.
    Uses GPT-4 to reason about what to do next.
    """
    try:
        llm = get_llm(temperature=0)
        
        prompt = SUPERVISOR_PROMPT.format(
            query=state["query"],
            target_areas=state["target_areas"],
            sources_crawled=state["sources_crawled"],
            raw_count=len(state["raw_listings"]),
            listings_count=state["listings_count"],
            enriched_count=state.get("enriched_count", 0),
            enrichment_status=state.get("enrichment_status", "pending"),
            filtered_count=state.get("filtered_count", 0),
            evaluations_count=len(state["evaluations"])
        )
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"What should be the next action? Current stage: {state['current_stage']}")
        ]
        
        response = llm.invoke(messages)
        
        # Handle both ChatModel (returns AIMessage) and LLM (returns string)
        if hasattr(response, 'content'):
            decision = response.content.strip().lower()
        else:
            decision = str(response).strip().lower()
        
        # Parse decision
        if "crawl" in decision:
            next_action = "crawl"
            # Prevent infinite loop if we already have raw listings
            if len(state["raw_listings"]) > 0 and state["listings_count"] == 0:
                 next_action = "normalize"
        elif "normalize" in decision:
            next_action = "normalize"
            # Prevent infinite loop if we already normalized
            if state["listings_count"] > 0:
                next_action = "enrich"
        elif "enrich" in decision:
            next_action = "enrich"
            if state.get("enrichment_status") == "success":
                next_action = "filter"
        elif "filter" in decision:
            next_action = "filter"
            if state.get("filtered_count", 0) > 0:
                next_action = "evaluate"
        elif "evaluate" in decision:
            next_action = "evaluate"
            if len(state["evaluations"]) > 0:
                next_action = "report"
        elif "report" in decision:
            next_action = "report"
        else:
            next_action = "end"
            
        logger.info("supervisor_decision", decision=next_action, raw=decision)
        
        return {
            "next_action": next_action,
            "current_stage": "supervisor",
            "messages": [{"role": "supervisor", "content": decision}]
        }
        
    except Exception as e:
        logger.error("supervisor_failed", error=str(e))
        raise



def crawl_node(state: AgentState) -> Dict[str, Any]:
    """Execute crawling based on target areas."""
    logger.info("crawl_node_started", areas=state["target_areas"])
    
    raw_listings = []
    sources_crawled = list(state["sources_crawled"])
    
    # Determine search path
    areas = state["target_areas"]
    if not areas:
        raise ValueError("target_areas_required")
    
    for area in areas:
        try:
            # Determine source
            if "idealista" in area:
                source_id = "idealista_es"
            else:
                source_id = "pisos_es"
                
            result = crawl_listings.invoke({
                "search_path": area,
                "source_id": source_id
            })
            
            if result["status"] == "success":
                raw_listings.extend(result["data"])
                sources_crawled.append(source_id)
                
        except Exception as e:
            logger.error("crawl_failed", area=area, error=str(e))
            
    return {
        "raw_listings": raw_listings,
        "sources_crawled": sources_crawled,
        "current_stage": "crawled",
        "messages": [{"role": "crawl", "content": f"Crawled {len(raw_listings)} listings"}]
    }


def normalize_node(state: AgentState) -> Dict[str, Any]:
    """Normalize all raw listings."""
    logger.info("normalize_node_started", count=len(state["raw_listings"]))
    
    canonical_listings = []
    
    # Group by source
    by_source: Dict[str, List] = {}
    for raw in state["raw_listings"]:
        source_id = raw.get("source_id", "idealista_es")
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


def route_supervisor(state: AgentState) -> Literal["crawl", "normalize", "enrich", "filter", "evaluate", "report", "end"]:
    """Route based on supervisor decision."""
    return state.get("next_action", "end")


def create_cognitive_graph():
    """Build and compile the LangGraph workflow."""
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("crawl", crawl_node)
    graph.add_node("normalize", normalize_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("filter", filter_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("report", report_node)
    
    # Conditional routing from supervisor
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "crawl": "crawl",
            "normalize": "normalize",
            "enrich": "enrich",
            "filter": "filter",
            "evaluate": "evaluate",
            "report": "report",
            "end": END
        }
    )
    
    # All action nodes return to supervisor
    graph.add_edge("crawl", "supervisor")
    graph.add_edge("normalize", "supervisor")
    graph.add_edge("enrich", "supervisor")
    graph.add_edge("filter", "supervisor")
    graph.add_edge("evaluate", "supervisor")
    graph.add_edge("report", END)
    
    # Entry point
    graph.set_entry_point("supervisor")
    
    return graph.compile()
