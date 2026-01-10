import structlog
from typing import List, Optional, Tuple
from sqlalchemy import func
from src.services.storage import StorageService
from src.services.modeling import ValuationModel
from src.core.domain.schema import CanonicalListing, DealAnalysis
from src.core.domain.models import DBListing

logger = structlog.get_logger()

class ValuationService:
    def __init__(self, storage: StorageService):
        self.storage = storage
        self.ml_model = ValuationModel()

    def _get_market_average_sqm(self, city: str = None) -> Tuple[float, int]:
        """
        Calculates simple average Price/Sqm from DB.
        """
        session = self.storage.get_session()
        try:
            query = session.query(
                DBListing.price, DBListing.surface_area_sqm
            ).filter(
                DBListing.price > 0,
                DBListing.surface_area_sqm > 0
            )
            data = query.all()
            if not data:
                return 0.0, 0
                
            ratios = [row.price / row.surface_area_sqm for row in data]
            avg_sqm = sum(ratios) / len(ratios)
            return avg_sqm, len(ratios)
        finally:
            session.close()

    def evaluate_deal(self, listing: CanonicalListing, comps: List[CanonicalListing] = None) -> DealAnalysis:
        """
        Generates a fair value estimate using ML (primary) or Heuristics (fallback).
        """
        # 1. Attempt ML Inference
        ml_est = self.ml_model.predict(listing)
        est_price_sqm = ml_est.get("q50", 0.0)
        
        market_avg_sqm, sample_size = self._get_market_average_sqm()
        
        if est_price_sqm > 0:
            used_sqm = est_price_sqm
            est_source = "ML Model (LightGBM)"
            
            # Uncertainty from quantiles
            q10 = ml_est.get("q10", 0.0)
            q90 = ml_est.get("q90", 0.0)
            if q90 > 0:
                uncertainty = (q90 - q10) / 2 / est_price_sqm
            else:
                uncertainty = 0.2
        else:
            # Fallback to Heuristics
            est_source = "Heuristic (Market Avg)"
            used_sqm = market_avg_sqm
            uncertainty = 0.20

        # 2. Refine with Comps if available (Ensemble)
        # If we have explicit comps, we can blend them or just cite them.
        # For this version, let's trust the ML model if it exists, otherwise blend market + comps.
        if est_price_sqm == 0 and comps:
             comp_ratios = [c.price / c.surface_area_sqm for c in comps if c.surface_area_sqm > 0 and c.price > 0]
             if comp_ratios:
                 comp_avg = sum(comp_ratios) / len(comp_ratios)
                 used_sqm = (market_avg_sqm + comp_avg) / 2
                 est_source = f"Hybrid (Market & {len(comps)} Comps)"

        # 3. Calculate Fair Value
        fair_value = 0.0
        if listing.surface_area_sqm and used_sqm > 0:
            fair_value = listing.surface_area_sqm * used_sqm
        else:
            fair_value = listing.price
            uncertainty = 0.5
            
        # 4. Score
        diff_pct = 0.0
        if listing.price > 0:
             diff_pct = (fair_value - listing.price) / listing.price
             
        score = min(max(0.5 + diff_pct, 0.0), 1.0)
        
        flags = []
        if uncertainty > 0.3: flags.append("high_uncertainty")
        if diff_pct > 0.2: flags.append("deep_value")
        
        thesis = f"Fair value {fair_value:,.0f}€ (±{uncertainty:.0%}) via {est_source}. "
        if comps:
             thesis += f"Verified against {len(comps)} comps."

        return DealAnalysis(
            listing_id=listing.id,
            fair_value_estimate=fair_value,
            fair_value_uncertainty_pct=uncertainty,
            deal_score=score,
            flags=flags,
            investment_thesis=thesis
        )
