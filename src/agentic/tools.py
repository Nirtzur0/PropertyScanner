"""
Tool Wrappers for LangGraph.
Wraps existing agents and services as LangChain tools.
"""
import structlog
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from src.interfaces.api.pipeline import get_pipeline_api

logger = structlog.get_logger()


# ============ Input Schemas (for structured tool calls) ============

class CrawlInput(BaseModel):
    """Input for crawling tools."""
    search_path: str = Field(description="Search path or URL for crawling listings")
    source_id: str = Field(default="idealista", description="Source identifier")


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


class FilterInput(BaseModel):
    """Input for filtering tool."""
    listings: List[Dict[str, Any]] = Field(description="List of canonical listings to filter")


class PipelineStatusInput(BaseModel):
    """Input for pipeline status tool."""
    pass


class PreflightInput(BaseModel):
    """Input for preflight tool."""
    skip_crawl: bool = Field(default=False, description="Skip crawl backfill")
    skip_market_data: bool = Field(default=False, description="Skip market data rebuild")
    skip_index: bool = Field(default=False, description="Skip vector index rebuild")
    skip_training: bool = Field(default=False, description="Skip model training")


class MarketDataWorkflowInput(BaseModel):
    """Input for market data workflow tool."""
    skip_macro: bool = Field(default=False, description="Skip macro indicator refresh")
    skip_market_indices: bool = Field(default=False, description="Skip market indices recompute")
    skip_hedonic: bool = Field(default=False, description="Skip hedonic indices recompute")
    city: Optional[str] = Field(default=None, description="Optional city filter for hedonic recompute")


class IndexWorkflowInput(BaseModel):
    """Input for index rebuild tool."""
    listing_type: str = Field(default="sale", description="Listing type filter: sale, rent, or all")
    limit: int = Field(default=0, description="Max listings to index (0 = all)")
    clear: bool = Field(default=False, description="Clear existing index before rebuild")


class TrainWorkflowInput(BaseModel):
    """Input for training workflow tool."""
    epochs: int = Field(default=50, description="Training epochs")
    listing_type: str = Field(default="sale", description="Listing type filter for training")
    no_vlm: bool = Field(default=False, description="Disable VLM during training")


# ============ Tools ============

@tool(args_schema=CrawlInput)
def crawl_listings(search_path: str, source_id: str = "idealista") -> Dict[str, Any]:
    """
    Crawl property listings from a specified source.
    
    Use this tool when you need to fetch new property listings from real estate websites.
    Supports idealista, idealista_it, pisos, rightmove_uk, zoopla_uk, and immobiliare_it sources.
    
    Returns a dict with 'status', 'data' (list of raw listings), and 'errors'.
    """
    from src.platform.utils.config import ConfigLoader
    from src.platform.settings import SourceConfig
    from src.platform.utils.compliance import ComplianceManager
    from src.listings.agents.factory import AgentFactory
    
    try:
        config_loader = ConfigLoader()
        sources = config_loader.sources.sources

        # Find source config
        source_conf = next(
            (s for s in sources if s.id == source_id),
            SourceConfig(id=source_id, base_url="https://www.idealista.com"),
        )

        user_agent = config_loader.agents.defaults.uastring
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
    from src.listings.agents.factory import AgentFactory
    from src.platform.domain.schema import RawListing
    from src.listings.services.feature_sanitizer import sanitize_listing_dict, sanitize_listing_features
    
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
                sanitize_listing_features(listing)
                listings_data.append(listing.model_dump())
            elif isinstance(listing, dict):
                listings_data.append(sanitize_listing_dict(listing))
                
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
    from src.agentic.agents.evaluation_agent import EvaluationAgent
    
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
    from src.listings.services.enrichment_service import EnrichmentService

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
    from src.valuation.services.retrieval import CompRetriever
    from src.platform.domain.schema import CanonicalListing
    
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


@tool(args_schema=FilterInput)
def filter_listings(listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Filter out low-quality listings before evaluation.
    
    Removes listings with:
    - No Price or Price = 0
    - No Surface Area or Surface Area = 0
    - Empty Title
    
    Returns a dict with 'status', 'data' (filtered listings), and 'dropped_count'.
    """
    try:
        filtered_listings = []
        dropped_count = 0
        
        for listing in listings:
            # Check price
            price = listing.get('price', 0)
            if not price or price <= 0:
                dropped_count += 1
                continue
                
            # Check area (sqm) -> important for valuation
            sqm = listing.get('surface_area_sqm', 0)
            if not sqm or sqm <= 0:
                dropped_count += 1
                continue
                
            # Check title
            title = listing.get('title', "")
            if not title:
                dropped_count += 1
                continue
                
            filtered_listings.append(listing)
            
        return {
            "status": "success",
            "data": filtered_listings,
            "count": len(filtered_listings),
            "dropped_count": dropped_count
        }
        
    except Exception as e:
        logger.error("filter_tool_failed", error=str(e))
        return {
            "status": "failure",
            "data": listings, # Return original on failure to be safe
            "count": len(listings),
            "dropped_count": 0,
            "errors": [str(e)]
        }


@tool(args_schema=PipelineStatusInput)
def pipeline_status() -> Dict[str, Any]:
    """
    Inspect pipeline freshness (listings, indices, index, model).
    Returns a dict with 'status' and 'data' containing the pipeline snapshot.
    """
    from src.platform.pipeline.state import PipelineStateService

    try:
        state = PipelineStateService().snapshot()
        return {"status": "success", "data": state.to_dict()}
    except Exception as e:
        logger.error("pipeline_status_failed", error=str(e))
        return {"status": "failure", "error": str(e)}


@tool(args_schema=PreflightInput)
def preflight_pipeline(
    skip_crawl: bool = False,
    skip_market_data: bool = False,
    skip_index: bool = False,
    skip_training: bool = False,
) -> Dict[str, Any]:
    """
    Run the preflight pipeline to refresh stale data and artifacts.
    """
    try:
        api = get_pipeline_api()
        result = api.preflight(
            skip_crawl=skip_crawl,
            skip_market_data=skip_market_data,
            skip_index=skip_index,
            skip_training=skip_training,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error("preflight_failed", error=str(e))
        return {"status": "failure", "error": str(e)}


@tool(args_schema=MarketDataWorkflowInput)
def build_market_data_workflow(
    skip_macro: bool = False,
    skip_market_indices: bool = False,
    skip_hedonic: bool = False,
    city: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build macro data and market/hedonic indices.
    """
    try:
        api = get_pipeline_api()
        api.build_market_data(
            skip_macro=skip_macro,
            skip_market_indices=skip_market_indices,
            skip_hedonic=skip_hedonic,
            city=city,
        )
        return {"status": "success", "city": city}
    except Exception as e:
        logger.error("market_data_workflow_failed", error=str(e))
        return {"status": "failure", "error": str(e)}


@tool(args_schema=IndexWorkflowInput)
def build_vector_index_workflow(
    listing_type: str = "sale",
    limit: int = 0,
    clear: bool = False,
) -> Dict[str, Any]:
    """
    Build the vector index for retrieval.
    """
    try:
        api = get_pipeline_api()
        count = api.build_vector_index(listing_type=listing_type, limit=limit, clear=clear)
        return {"status": "success", "indexed": count}
    except Exception as e:
        logger.error("index_workflow_failed", error=str(e))
        return {"status": "failure", "error": str(e)}


@tool(args_schema=TrainWorkflowInput)
def train_model_workflow(
    epochs: int = 50,
    listing_type: str = "sale",
    no_vlm: bool = False,
) -> Dict[str, Any]:
    """
    Train the fusion model.
    """
    try:
        api = get_pipeline_api()
        history = api.train_model(epochs=epochs, listing_type=listing_type, use_vlm=not no_vlm)
        return {"status": "success", "folds": len(history)}
    except Exception as e:
        logger.error("train_workflow_failed", error=str(e))
        return {"status": "failure", "error": str(e)}


# Tool registry
TOOLS = [
    crawl_listings,
    normalize_listings,
    enrich_listings,
    filter_listings,
    evaluate_listing,
    retrieve_comparables,
    pipeline_status,
    preflight_pipeline,
    build_market_data_workflow,
    build_vector_index_workflow,
    train_model_workflow,
]
