import uuid
from datetime import timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session
from src.platform.domain.models import PropertyValuation
from src.valuation.services.valuation import DealAnalysis
from src.platform.utils.time import utcnow


class ValuationPersister:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _clamp(value: float, low: float = 0.05, high: float = 0.99) -> float:
        return max(low, min(high, value))

    @classmethod
    def _confidence_from_uncertainty(cls, uncertainty_pct: float) -> float:
        normalized = min(max(uncertainty_pct, 0.0), 0.40) / 0.40
        return cls._clamp(1.0 - normalized, 0.05, 1.0)

    @staticmethod
    def _confidence_from_calibration_status(status: str) -> float:
        mapping = {
            "calibrated": 1.0,
            "bootstrap": 0.75,
            "partial": 0.65,
            "uncalibrated": 0.45,
        }
        return mapping.get(status, 0.5)

    @staticmethod
    def _confidence_from_comp_count(comp_count: int) -> float:
        if comp_count >= 10:
            return 1.0
        if comp_count >= 5:
            return 0.85
        if comp_count >= 3:
            return 0.70
        if comp_count >= 1:
            return 0.55
        return 0.40

    @classmethod
    def _derive_confidence(cls, analysis: DealAnalysis) -> Tuple[float, Dict[str, object]]:
        evidence = analysis.evidence
        calibration_status = (evidence.calibration_status if evidence else "uncalibrated").lower()
        calibration_component = cls._confidence_from_calibration_status(calibration_status)

        comp_count = len(evidence.top_comps) if evidence and evidence.top_comps else 0
        comp_support_component = cls._confidence_from_comp_count(comp_count)

        uncertainty_pct = float(max(0.0, float(analysis.fair_value_uncertainty_pct or 0.0)))
        interval_component = cls._confidence_from_uncertainty(uncertainty_pct)

        projection_scores = [
            float(p.confidence_score)
            for p in (
                list(analysis.projections)
                + list(getattr(analysis, "rent_projections", []))
                + list(getattr(analysis, "yield_projections", []))
            )
            if 0.0 <= float(p.confidence_score) <= 1.0
        ]
        projection_component = (
            float(sum(projection_scores) / len(projection_scores))
            if projection_scores
            else interval_component
        )

        market_signals = analysis.market_signals or {}
        volatility = float(market_signals.get("volatility", 0.0) or 0.0)
        volatility = cls._clamp(volatility, 0.0, 1.0)
        volatility_penalty = min(volatility, 0.5) * 0.35

        index_disagreement_penalty = 0.05 if evidence and evidence.index_disagreement else 0.0

        composite_pre_penalty = (
            (0.40 * interval_component)
            + (0.25 * projection_component)
            + (0.20 * calibration_component)
            + (0.15 * comp_support_component)
        )
        confidence = cls._clamp(
            composite_pre_penalty - volatility_penalty - index_disagreement_penalty
        )

        components: Dict[str, object] = {
            "uncertainty_pct": round(uncertainty_pct, 6),
            "interval_component": round(interval_component, 4),
            "projection_component": round(projection_component, 4),
            "calibration_component": round(calibration_component, 4),
            "comp_support_component": round(comp_support_component, 4),
            "composite_pre_penalty": round(composite_pre_penalty, 4),
            "volatility": round(volatility, 4),
            "volatility_penalty": round(volatility_penalty, 4),
            "index_disagreement_penalty": round(index_disagreement_penalty, 4),
            "comp_count": comp_count,
            "calibration_status": calibration_status,
        }
        return round(confidence, 4), components

    def get_latest_valuation(self, listing_id: str, max_age_days: Optional[int] = 7) -> Optional[PropertyValuation]:
        """
        Retrieves the latest valuation for a listing if it's recent enough.
        Returns None if no valuation exists or if it's too old.
        """
        query = self.session.query(PropertyValuation).filter(PropertyValuation.listing_id == listing_id)
        if max_age_days is not None:
            cutoff = utcnow() - timedelta(days=max_age_days)
            query = query.filter(PropertyValuation.created_at >= cutoff)

        return query.order_by(PropertyValuation.created_at.desc()).first()

    def save_valuation(self, listing_id: str, analysis: DealAnalysis, model_version: str = "v1.0") -> PropertyValuation:
        """
        Persists a DealAnalysis result into the PropertyValuation table.
        """
        # Serialize evidence/complex types
        evidence_dict = {
            "thesis": analysis.investment_thesis,
            "projections": [p.model_dump() for p in analysis.projections],
            "rent_projections": [p.model_dump() for p in getattr(analysis, "rent_projections", [])],
            "yield_projections": [p.model_dump() for p in getattr(analysis, "yield_projections", [])],
            "signals": analysis.market_signals,
            "evidence": analysis.evidence.model_dump() if analysis.evidence else {}
        }

        confidence, confidence_components = self._derive_confidence(analysis)
        evidence_dict["confidence_components"] = confidence_components
        
        val = PropertyValuation(
            id=str(uuid.uuid4()),
            listing_id=listing_id,
            model_version=model_version,
            created_at=utcnow(),
            fair_value=analysis.fair_value_estimate,
            price_range_low=analysis.fair_value_estimate * 0.9, # precise range is in evidence projections if needed
            price_range_high=analysis.fair_value_estimate * 1.1,
            confidence_score=confidence,
            evidence=evidence_dict
        )
        
        self.session.add(val)
        self.session.commit()
        return val
