"""
Tool Wrappers for LangGraph.
Wraps existing agents and services as LangChain tools.
"""
import structlog
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = structlog.get_logger()


# ============ Input Schemas (for structured tool calls) ============

class CrawlInput(BaseModel):
    """Input for crawling tools."""
    search_path: str = Field(description="Search path or URL for crawling listings")
    source_id: str = Field(default="idealista_es", description="Source identifier")


class NormalizeInput(BaseModel):
    """Input for normalization tool."""
    raw_listings: List[Dict[str, Any]] = Field(description="Raw listing data to normalize")
    source_id: str = Field(description="Source identifier for normalization rules")


class EvaluateInput(BaseModel):
    """Input for evaluation tool."""
    listing: Dict[str, Any] = Field(description="Canonical listing to evaluate")
    num_comps: int = Field(default=10, description="Number of comparables to consider")


class EnrichInput(BaseModel):
    """Input for enrichment tool."""
    listings: List[Dict[str, Any]] = Field(description="List of canonical listings to enrich")


class RetrieveCompsInput(BaseModel):
    """Input for comparable retrieval."""
    listing: Dict[str, Any] = Field(description="Listing to find comparables for")
    k: int = Field(default=10, description="Number of comparables to retrieve")
    max_radius_km: float = Field(default=5.0, description="Maximum search radius in km")


# ============ Tools ============

@tool(args_schema=CrawlInput)
def crawl_listings(search_path: str, source_id: str = "idealista_es") -> Dict[str, Any]:
    """
    Crawl property listings from a specified source.
    
    Use this tool when you need to fetch new property listings from real estate websites.
    Supports idealista_es and pisos_es sources.
    
    Returns a dict with 'status', 'data' (list of raw listings), and 'errors'.
    """
    from src.utils.config import ConfigLoader
    from src.utils.compliance import ComplianceManager
    from src.agents.factory import AgentFactory
    
    try:
        config_loader = ConfigLoader()
        sources = config_loader.sources
        
        # Find source config
        source_conf = next(
            (s for s in sources.get('sources', []) if s['id'] == source_id),
            {"id": source_id, "base_url": "https://www.idealista.com"}
        )
        
        user_agent = config_loader.agents.get("defaults", {}).get("uastring", "PropertyScanner/1.0")
        compliance = ComplianceManager(user_agent)
        
        crawler = AgentFactory.create_crawler(source_id, source_conf, compliance)
        
        input_payload = {
            "search_path": search_path,
            "start_url": search_path
        }
        
        result = crawler.run(input_payload)
        
        # Convert RawListing objects to dicts
        listings_data = []
        for listing in result.data or []:
            if hasattr(listing, 'model_dump'):
                listings_data.append(listing.model_dump())
            elif isinstance(listing, dict):
                listings_data.append(listing)
                
        return {
            "status": result.status,
            "data": listings_data,
            "count": len(listings_data),
            "errors": result.errors
        }
        
    except Exception as e:
        logger.error("crawl_tool_failed", error=str(e))
        return {
            "status": "failure",
            "data": [],
            "count": 0,
            "errors": [str(e)]
        }


@tool(args_schema=NormalizeInput)
def normalize_listings(raw_listings: List[Dict[str, Any]], source_id: str) -> Dict[str, Any]:
    """
    Normalize raw listings to canonical format.
    
    Use this tool after crawling to convert raw HTML/JSON data into structured listings.
    
    Returns a dict with 'status', 'data' (list of canonical listings), and 'errors'.
    """
    from src.agents.factory import AgentFactory
    from src.core.domain.schema import RawListing
    
    try:
        normalizer = AgentFactory.create_normalizer(source_id)
        
        # Convert dicts back to RawListing objects if needed
        raw_objs = []
        for r in raw_listings:
            if isinstance(r, dict):
                raw_objs.append(RawListing(**r))
            else:
                raw_objs.append(r)
        
        result = normalizer.run({"raw_listings": raw_objs})
        
        # Convert CanonicalListing objects to dicts
        listings_data = []
        for listing in result.data or []:
            if hasattr(listing, 'model_dump'):
                listings_data.append(listing.model_dump())
            elif isinstance(listing, dict):
                listings_data.append(listing)
                
        return {
            "status": result.status,
            "data": listings_data,
            "count": len(listings_data),
            "errors": result.errors
        }
        
    except Exception as e:
        logger.error("normalize_tool_failed", error=str(e))
        return {
            "status": "failure",
            "data": [],
            "count": 0,
            "errors": [str(e)]
        }


@tool(args_schema=EvaluateInput)
def evaluate_listing(listing: Dict[str, Any], num_comps: int = 10) -> Dict[str, Any]:
    """
    Evaluate a property listing for investment potential.
    
    Use this tool to get fair value estimates, deal scores, and investment analysis.
    
    Returns a dict with evaluation results including deal_score and investment_thesis.
    """
    from src.agents.analysts.evaluation_agent import EvaluationAgent
    
    try:
        agent = EvaluationAgent()
        result = agent.run({
            "listing": listing,
            "num_comps": num_comps
        })
        
        return {
            "status": result.status,
            "data": result.data,
            "errors": result.errors
        }
        
    except Exception as e:
        logger.error("evaluate_tool_failed", error=str(e))
        return {
            "status": "failure",
            "data": None,
            "errors": [str(e)]
        }


@tool(args_schema=EnrichInput)
def enrich_listings(listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Enrich listings with additional location data (e.g., city).

    Use this tool after normalization to ensure listings have correct city information
    before evaluation.

    Returns a dict with 'status', 'data' (enriched listings), and 'enriched_count'.
    """
    from src.services.enrichment_service import EnrichmentService

    try:
        service = EnrichmentService()
        enriched_count = 0
        enriched_listings = []

        for listing_dict in listings:
            # We work with the dict directly to modify it
            # Ensure we don't modify the input in place if we want to be safe, but here it's fine
            listing_copy = listing_dict.copy()

            location = listing_copy.get('location')
            if location and isinstance(location, dict):
                lat = location.get('lat')
                lon = location.get('lon')
                city = location.get('city')

                if lat and lon and (not city or city == "Unknown"):
                    try:
                        new_city = service.get_city(lat, lon)
                        if new_city and new_city != "Unknown":
                            location['city'] = new_city
                            enriched_count += 1
                    except Exception as e:
                        logger.warning("enrich_single_failed", lat=lat, lon=lon, error=str(e))

            enriched_listings.append(listing_copy)

        return {
            "status": "success",
            "data": enriched_listings,
            "count": len(enriched_listings),
            "enriched_count": enriched_count
        }

    except Exception as e:
        logger.error("enrich_tool_failed", error=str(e))
        return {
            "status": "failure",
            "data": listings, # Return original on failure
            "count": len(listings),
            "enriched_count": 0,
            "errors": [str(e)]
        }


@tool(args_schema=RetrieveCompsInput)
def retrieve_comparables(
    listing: Dict[str, Any], 
    k: int = 10, 
    max_radius_km: float = 5.0
) -> Dict[str, Any]:
    """
    Retrieve comparable listings for analysis.
    
    Use this tool to find similar properties for comparison-based valuation.
    
    Returns a dict with 'comps' list and similarity scores.
    """
    from src.services.retrieval import CompRetriever
    from src.core.domain.schema import CanonicalListing
    
    try:
        retriever = CompRetriever()
        
        # Convert dict to CanonicalListing
        if isinstance(listing, dict):
            canonical = CanonicalListing(**listing)
        else:
            canonical = listing
            
        comps = retriever.retrieve_comps(
            target=canonical,
            k=k,
            max_radius_km=max_radius_km
        )
        
        comps_data = [c.model_dump() for c in comps]
        
        return {
            "status": "success",
            "comps": comps_data,
            "count": len(comps_data)
        }
        
    except Exception as e:
        logger.error("retrieve_comps_failed", error=str(e))
        return {
            "status": "failure",
            "comps": [],
            "count": 0,
            "error": str(e)
        }


# Tool registry
TOOLS = [
    crawl_listings,
    normalize_listings,
    enrich_listings,
    evaluate_listing,
    retrieve_comparables
]
