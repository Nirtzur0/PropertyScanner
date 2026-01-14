import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from src.core.domain.models import PropertyValuation, DBListing
from src.services.valuation import DealAnalysis

class ValuationPersister:
    def __init__(self, session: Session):
        self.session = session

    def get_latest_valuation(self, listing_id: str, max_age_days: int = 7) -> Optional[PropertyValuation]:
        """
        Retrieves the latest valuation for a listing if it's recent enough.
        Returns None if no valuation exists or if it's too old.
        """
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        
        return self.session.query(PropertyValuation)\
            .filter(PropertyValuation.listing_id == listing_id)\
            .filter(PropertyValuation.created_at >= cutoff)\
            .order_by(PropertyValuation.created_at.desc())\
            .first()

    def save_valuation(self, listing_id: str, analysis: DealAnalysis, model_version: str = "v1.0") -> PropertyValuation:
        """
        Persists a DealAnalysis result into the PropertyValuation table.
        """
        # Serialize evidence/complex types
        evidence_dict = {
            "thesis": analysis.investment_thesis,
            "projections": [p.dict() for p in analysis.projections],
            "rent_projections": [p.dict() for p in getattr(analysis, "rent_projections", [])],
            "yield_projections": [p.dict() for p in getattr(analysis, "yield_projections", [])],
            "signals": analysis.market_signals,
            "evidence": analysis.evidence.dict() if analysis.evidence else {}
        }

        # Calculate a simple confidence score (placeholder logic)
        confidence = 0.85 # Default high for now
        if analysis.market_signals.get("volatility", 0) > 0.2:
            confidence -= 0.1
        
        val = PropertyValuation(
            id=str(uuid.uuid4()),
            listing_id=listing_id,
            model_version=model_version,
            created_at=datetime.utcnow(),
            fair_value=analysis.fair_value_estimate,
            price_range_low=analysis.fair_value_estimate * 0.9, # precise range is in evidence projections if needed
            price_range_high=analysis.fair_value_estimate * 1.1,
            confidence_score=confidence,
            evidence=evidence_dict
        )
        
        self.session.add(val)
        self.session.commit()
        return val
