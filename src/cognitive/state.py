"""
Agent State Schema for LangGraph Cognitive Agent.
Defines the shared state that flows through the graph nodes.
"""
from typing import TypedDict, List, Optional, Annotated, Dict, Any
from operator import add


class AgentState(TypedDict):
    """
    Shared state for the cognitive property scanner agent.
    
    Fields annotated with `add` accumulate across graph steps.
    """
    # Input
    query: str
    target_areas: List[str]
    
    # Pipeline data (accumulated via reducer)
    # Pipeline data (accumulated via reducer)
    raw_listings: Annotated[List[Dict[str, Any]], add]
    canonical_listings: List[Dict[str, Any]]
    evaluations: List[Dict[str, Any]]
    
    # Agent reasoning
    messages: Annotated[List[Dict[str, Any]], add]
    current_stage: str
    next_action: str
    error_count: int
    
    # Metadata
    sources_crawled: List[str]
    listings_count: int
    enriched_count: int
    enrichment_status: str
    filtered_count: int
    strategy: str
    
    # Final output
    final_report: Optional[str]
