from typing import Any, Dict, List, Optional
from src.agents.base import BaseAgent, AgentResponse
from src.services.market_analytics import MarketAnalyticsService
from src.core.domain.schema import CanonicalListing, MarketProfile
import structlog

logger = structlog.get_logger(__name__)

from src.services.forecasting import ForecastingService

class MarketDynamicsAgent(BaseAgent):
    """
    Agent responsible for analyzing market trends and providing valuation projections.
    Orchestrates MarketAnalytics (Snapshot Stats) and ForecastingService (Time Series ML).
    """
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="MarketDynamicsAgent", config=config or {})
        self.analytics_service = MarketAnalyticsService()
        self.forecasting_service = ForecastingService()

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """
        Input: {'listing': CanonicalListing} or {'listings': List[CanonicalListing]}
        Output: MarketProfile or List[MarketProfile]
        """
        target = input_payload.get("listing")
        targets = input_payload.get("listings", [])
        
        if target:
            targets = [target]
            
        profiles = []
        errors = []
        
        for listing in targets:
            try:
                # Ensure it's a CanonicalListing object
                if isinstance(listing, dict):
                    listing = CanonicalListing(**listing)
                
                # 1. Get Current Snapshot Stats (Momentum, Liquidity)
                profile = self.analytics_service.analyze_listing(listing)
                
                # 2. Get Forward-Looking Projections (ML Forecast)
                # Use region metrics to project THIS specific property's value
                if listing.price > 0:
                    projections = self.forecasting_service.forecast_property(
                        region_id=listing.location.city if listing.location else "unknown",
                        current_value=listing.price,
                        horizons_months=[12, 36, 60] # 1, 3, 5 years
                    )
                    profile.projections = projections
                
                profiles.append(profile)
            except Exception as e:
                logger.error("market_analysis_failed", listing_id=getattr(listing, 'id', 'unknown'), error=str(e))
                errors.append(str(e))

        return AgentResponse(
            status="success" if profiles else "failure",
            data=profiles if len(profiles) > 1 else (profiles[0] if profiles else None),
            errors=errors
        )
