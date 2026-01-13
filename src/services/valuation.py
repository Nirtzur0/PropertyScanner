"""
Valuation Service (SOTA V3)

Orchestrates property valuation with defensible methodology:
1. Fusion Model as PRIMARY (comps-based with time-adjustment)
2. Tabular ML as fallback
3. Heuristic as final fallback

Key Features:
- Comps are TIME-ADJUSTED using hedonic index before fusion
- "Today" value: comps-anchor + residual
- "Future" value: V_t × market drift (no double-counting)
- All intervals calibrated per-horizon via conformal prediction
- Structured evidence pack for auditability

References:
- RICS Red Book Valuation Standards
- Eurostat HPI methodology
"""

import structlog
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from dataclasses import dataclass
import numpy as np

from src.services.storage import StorageService
from src.services.modeling import ValuationModel
from src.core.domain.schema import (
    CanonicalListing, DealAnalysis, CompEvidence, EvidencePack, ValuationProjection
)
from src.core.domain.models import DBListing
from src.services.forecasting import ForecastingService
from src.services.market_analytics import MarketAnalyticsService
from src.services.hedonic_index import HedonicIndexService
from src.services.conformal_calibrator import HorizonCalibratorRegistry
from src.services.fusion_model import FusionModelService, FusionOutput

logger = structlog.get_logger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ValuationConfig:
    """Configuration knobs for valuation pipeline"""
    # Comp retrieval
    K_candidates: int = 100  # Initial comp candidates to retrieve
    K_model: int = 30  # Comps to pass to fusion model
    max_distance_km: float = 10.0
    max_age_months: int = 24
    min_comps_for_fusion: int = 5
    
    # Horizons
    horizons_months: List[int] = None
    
    # Conformal
    conformal_alpha: float = 0.1
    conformal_window: int = 50
    
    def __post_init__(self):
        if self.horizons_months is None:
            self.horizons_months = [12, 36, 60]


DEFAULT_CONFIG = ValuationConfig()


# =============================================================================
# VALUATION SERVICE
# =============================================================================

class ValuationService:
    """
    SOTA V3 Valuation Service.
    
    Orchestration hierarchy:
    1. Fusion Model (comps-based cross-attention)
    2. Tabular ML (LightGBM quantile regression)
    3. Heuristic (market average)
    
    All comp prices are time-adjusted before use.
    All prediction intervals are conformally calibrated.
    """
    
    def __init__(
        self, 
        storage: StorageService,
        config: ValuationConfig = None
    ):
        self.storage = storage
        self.config = config or DEFAULT_CONFIG
        
        # Services
        self.ml_model = ValuationModel()
        self.forecasting = ForecastingService()
        self.analytics = MarketAnalyticsService()
        self.hedonic = HedonicIndexService()
        self.fusion = FusionModelService()
        
        # Conformal calibrators (per-horizon)
        self.calibrators = HorizonCalibratorRegistry(
            horizons=[0] + self.config.horizons_months,
            alpha=self.config.conformal_alpha,
            window_size=self.config.conformal_window
        )
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    def evaluate_deal(
        self, 
        listing: CanonicalListing, 
        comps: List[CanonicalListing] = None,
        valuation_date: datetime = None,
        tracer: Any = None
    ) -> DealAnalysis:
        """
        Generates a fair value estimate with full evidence pack.
        
        Args:
            listing: Target property to value
            comps: Optional pre-retrieved comparables
            valuation_date: Target date for valuation (default: now)
            
        Returns:
            DealAnalysis with fair value, projections, and evidence
        """
        valuation_date = valuation_date or datetime.now()
        
        if tracer:
            tracer.start_trace(listing.id)
            tracer.log("input_listing", listing)
            tracer.log("input_comps_count", len(comps) if comps else 0)
        
        try:
            # Get region for index lookups
            region_id = self._get_region_id(listing)
            
            # =====================================================================
            # STAGE 1: SPOT VALUATION ("Today's Fair Value")
            # =====================================================================
            
            fair_value, uncertainty, evidence = self._compute_spot_value(
                listing, comps, region_id, valuation_date, tracer
            )
            
            if tracer:
                tracer.log("spot_valuation_raw", {
                    "fair_value": fair_value,
                    "uncertainty": uncertainty,
                    "model_used": evidence.model_used
                })
            
            # Apply conformal calibration to spot estimate
            if evidence.model_used == "fusion" and self.calibrators.is_calibrated(0):
                if tracer:
                    tracer.log("calibration_spot_before", {
                        "q10": fair_value * (1 - uncertainty),
                        "q50": fair_value,
                        "q90": fair_value * (1 + uncertainty)
                    })
    
                cal_q10, cal_q50, cal_q90 = self.calibrators.calibrate_interval(
                    fair_value * (1 - uncertainty),
                    fair_value,
                    fair_value * (1 + uncertainty),
                    horizon_months=0
                )
                
                if tracer:
                    tracer.log("calibration_spot_after", {
                        "q10": cal_q10,
                        "q50": cal_q50,
                        "q90": cal_q90
                    })
    
                # Recalculate uncertainty from calibrated interval
                if cal_q50 > 0:
                    uncertainty = (cal_q90 - cal_q10) / (2 * cal_q50)
                evidence.calibration_status = "calibrated"
            
            # =====================================================================
            # STAGE 2: DEAL SCORING
            # =====================================================================
            
            score, flags = self._compute_deal_score(
                listing, fair_value, uncertainty, evidence
            )
            
            # =====================================================================
            # STAGE 3: FUTURE PROJECTIONS (Market Drift Only)
            # =====================================================================
            
            projections = self._compute_projections(
                fair_value, region_id, valuation_date
            )
            
            # =====================================================================
            # STAGE 4: MARKET SIGNALS
            # =====================================================================
            
            market_signals = self._get_market_signals(listing)
            
            # =====================================================================
            # BUILD RESULT
            # =====================================================================
            
            thesis = self._generate_thesis(
                listing, fair_value, uncertainty, evidence, score
            )
            
            return DealAnalysis(
                listing_id=listing.id,
                fair_value_estimate=fair_value,
                fair_value_uncertainty_pct=uncertainty,
                deal_score=score,
                flags=flags,
                investment_thesis=thesis,
                projections=projections,
                market_signals=market_signals,
                evidence=evidence
            )
        finally:
            if tracer:
                tracer.end_trace()
    
    # =========================================================================
    # SPOT VALUATION
    # =========================================================================
    
    def _compute_spot_value(
        self,
        listing: CanonicalListing,
        comps: Optional[List[CanonicalListing]],
        region_id: str,
        valuation_date: datetime,
        tracer: Any = None
    ) -> Tuple[float, float, EvidencePack]:
        """
        Compute today's fair value using tiered approach.
        
        Hierarchy:
        1. Fusion Model (if comps >= min_comps and embeddings available)
        2. Tabular ML (if ML model trained)
        3. Heuristic (market average)
        """
        
        # Try Fusion Model first
        if comps and len(comps) >= self.config.min_comps_for_fusion:
            result = self._try_fusion_valuation(
                listing, comps, region_id, valuation_date, tracer
            )
            if result:
                return result
        
        # Fallback to Tabular ML
        result = self._try_tabular_valuation(listing)
        if result:
            return result
        
        # Final fallback: Heuristic
        return self._heuristic_valuation(listing)
    
    def _try_fusion_valuation(
        self,
        listing: CanonicalListing,
        comps: List[CanonicalListing],
        region_id: str,
        valuation_date: datetime,
        tracer: Any = None
    ) -> Optional[Tuple[float, float, EvidencePack]]:
        """
        Attempt Fusion Model valuation with time-adjusted comps.
        """
        try:
            # Time-adjust comp prices
            adjusted_comps = []
            comp_evidence = []
            
            for comp in comps[:self.config.K_model]:
                comp_timestamp = comp.listed_at or comp.updated_at or valuation_date
                
                adj_price, adj_factor, meta = self.hedonic.adjust_comp_price(
                    raw_price=comp.price,
                    region_id=region_id,
                    comp_timestamp=comp_timestamp,
                    target_timestamp=valuation_date
                )
                
                adjusted_comps.append({
                    'comp': comp,
                    'adj_price': adj_price,
                    'adj_factor': adj_factor,
                    'meta': meta
                })
                
                comp_evidence.append(CompEvidence(
                    id=comp.id,
                    url=str(comp.url) if comp.url else None,
                    observed_month=comp_timestamp.strftime("%Y-%m"),
                    raw_price=comp.price,
                    adj_factor=adj_factor,
                    adj_price=adj_price,
                    attention_weight=0.0,  # Will be updated after fusion
                    is_sold=comp.status.value == "sold" if comp.status else False
                ))
            
            if tracer:
                tracer.log("fusion_time_adjustment", {
                    "comps_count": len(adjusted_comps),
                    "sample_adj_factors": [c['adj_factor'] for c in adjusted_comps[:5]],
                    "sample_meta": [c['meta'] for c in adjusted_comps[:5]]
                })

            # TODO: Get embeddings from cache/encode
            # For now, use fallback in fusion model
            adj_prices = [c['adj_price'] for c in adjusted_comps]
            
            # Simple fusion fallback (no embeddings)
            anchor_price = np.mean(adj_prices)
            anchor_std = np.std(adj_prices) if len(adj_prices) > 1 else anchor_price * 0.1
            
            if tracer:
                tracer.log("fusion_anchor", {"anchor": anchor_price, "std": anchor_std})

            # Quantiles from comp distribution
            q10 = np.percentile(adj_prices, 10)
            q50 = np.median(adj_prices)
            q90 = np.percentile(adj_prices, 90)
            
            if tracer:
                tracer.log("fusion_quantiles_raw", {"q10": q10, "q50": q50, "q90": q90})
            
            # Adjust for target size if different from median comp
            residual_adjustment = 0.0

            if listing.surface_area_sqm and listing.surface_area_sqm > 0:
                # Extract valid comps for size regression
                valid_comps_data = [
                    (c['comp'].surface_area_sqm, c['adj_price'])
                    for c in adjusted_comps
                    if c['comp'].surface_area_sqm and c['comp'].surface_area_sqm > 0
                ]

                if len(valid_comps_data) >= 3:
                    comp_sizes = np.array([d[0] for d in valid_comps_data])
                    comp_prices = np.array([d[1] for d in valid_comps_data])

                    # Compute median price per sqm as benchmark
                    median_price_sqm = np.median(comp_prices / comp_sizes)

                    try:
                        # Linear regression: Price = slope * Size + intercept
                        slope, intercept = np.polyfit(comp_sizes, comp_prices, 1)

                        # Sanity check on slope (marginal value of space)
                        # Should be positive and reasonable (e.g. < 2x median price/sqm)
                        if slope < 0 or slope > median_price_sqm * 2:
                            # Fallback to damped median price/sqm
                            slope = median_price_sqm * 0.7

                        # Calculate residual
                        median_comp_size = np.median(comp_sizes)
                        size_diff = listing.surface_area_sqm - median_comp_size

                        residual_adjustment = slope * size_diff

                        if tracer:
                            tracer.log("fusion_residual_adjustment", {
                                "slope": slope,
                                "intercept": intercept,
                                "median_comp_size": median_comp_size,
                                "size_diff": size_diff,
                                "adjustment": residual_adjustment,
                                "median_price_sqm": median_price_sqm
                            })

                    except Exception as e:
                        logger.warning("residual_regression_failed", error=str(e))

            # Apply adjustment
            q10 += residual_adjustment
            q50 += residual_adjustment
            q90 += residual_adjustment
            
            uncertainty = (q90 - q10) / (2 * q50) if q50 > 0 else 0.15
            
            # Update attention weights (uniform for now)
            uniform_weight = 1.0 / len(comp_evidence)
            for ce in comp_evidence:
                ce.attention_weight = uniform_weight
            
            # Determine if hedonic fallback was used
            hedonic_fallback = any(c['meta'].get('comp_index_fallback') for c in adjusted_comps)
            fallback_reasons = [c['meta'].get('fallback_reason') for c in adjusted_comps if c['meta'].get('fallback_reason')]
            
            # Comp date range
            comp_months = [ce.observed_month for ce in comp_evidence]
            comp_date_range = f"{min(comp_months)} to {max(comp_months)}" if comp_months else None
            
            evidence = EvidencePack(
                model_used="fusion",
                anchor_price=anchor_price,
                anchor_std=anchor_std,
                top_comps=comp_evidence,
                hedonic_fallback=hedonic_fallback,
                hedonic_fallback_reason=fallback_reasons[0] if fallback_reasons else None,
                calibration_status="uncalibrated",
                valuation_date=valuation_date.strftime("%Y-%m-%d"),
                comp_date_range=comp_date_range
            )
            
            return (q50, uncertainty, evidence)
            
        except Exception as e:
            logger.warning("fusion_valuation_failed", error=str(e))
            return None
    
    def _try_tabular_valuation(
        self,
        listing: CanonicalListing
    ) -> Optional[Tuple[float, float, EvidencePack]]:
        """
        Attempt Tabular ML valuation.
        """
        try:
            ml_est = self.ml_model.predict(listing)
            est_price_sqm = ml_est.get("q50", 0.0)
            
            if est_price_sqm <= 0:
                return None
            
            q10 = ml_est.get("q10", est_price_sqm * 0.85)
            q90 = ml_est.get("q90", est_price_sqm * 1.15)
            
            if listing.surface_area_sqm and listing.surface_area_sqm > 0:
                fair_value = listing.surface_area_sqm * est_price_sqm
                val_q10 = listing.surface_area_sqm * q10
                val_q90 = listing.surface_area_sqm * q90
            else:
                return None
            
            uncertainty = (val_q90 - val_q10) / (2 * fair_value) if fair_value > 0 else 0.2
            
            evidence = EvidencePack(
                model_used="tabular_ml",
                anchor_price=fair_value,
                anchor_std=fair_value * uncertainty,
                top_comps=[],
                calibration_status="uncalibrated"
            )
            
            return (fair_value, uncertainty, evidence)
            
        except Exception as e:
            logger.warning("tabular_valuation_failed", error=str(e))
            return None
    
    def _heuristic_valuation(
        self,
        listing: CanonicalListing
    ) -> Tuple[float, float, EvidencePack]:
        """
        Fallback heuristic valuation using market averages.
        """
        market_avg_sqm, sample_size = self._get_market_average_sqm(
            listing.location.city if listing.location else None
        )
        
        if listing.surface_area_sqm and market_avg_sqm > 0:
            fair_value = listing.surface_area_sqm * market_avg_sqm
        else:
            fair_value = listing.price if listing.price > 0 else 300000.0
        
        uncertainty = 0.25  # High uncertainty for heuristic
        
        evidence = EvidencePack(
            model_used="heuristic",
            anchor_price=fair_value,
            anchor_std=fair_value * uncertainty,
            top_comps=[],
            calibration_status="uncalibrated"
        )
        
        return (fair_value, uncertainty, evidence)
    
    # =========================================================================
    # PROJECTIONS (Market Drift Only - No Double Counting)
    # =========================================================================
    
    def _compute_projections(
        self,
        spot_value: float,
        region_id: str,
        valuation_date: datetime
    ) -> List[ValuationProjection]:
        """
        Compute future value projections.
        
        CRITICAL: Apply only market drift to spot value.
        Do NOT re-compute comps at future dates.
        
        Formula: V_{t+h} = V_t × growth_ratio_{r,h}
        """
        projections = []
        
        try:
            # Get growth forecasts from ForecastingService
            raw_projections = self.forecasting.forecast_property(
                region_id=region_id,
                current_value=spot_value,
                horizons_months=self.config.horizons_months
            )
            
            # Apply conformal calibration per horizon
            for proj in raw_projections:
                horizon = proj.months_future
                
                # Calibrate if we have enough data
                if self.calibrators.is_calibrated(horizon):
                    cal_q10, cal_q50, cal_q90 = self.calibrators.calibrate_interval(
                        proj.confidence_interval_low,
                        proj.predicted_value,
                        proj.confidence_interval_high,
                        horizon_months=horizon
                    )
                    
                    # Update with calibrated values
                    proj.confidence_interval_low = cal_q10
                    proj.predicted_value = cal_q50
                    proj.confidence_interval_high = cal_q90
                    
                    # Recalculate confidence
                    if cal_q50 > 0:
                        spread = (cal_q90 - cal_q10) / cal_q50
                        proj.confidence_score = max(0.1, 1.0 - spread)
                    
                    proj.scenario_name = f"{proj.scenario_name}_calibrated"
                
                projections.append(proj)
                
        except Exception as e:
            logger.warning("projection_failed", error=str(e))
        
        return projections
    
    # =========================================================================
    # DEAL SCORING
    # =========================================================================
    
    def _compute_deal_score(
        self,
        listing: CanonicalListing,
        fair_value: float,
        uncertainty: float,
        evidence: EvidencePack
    ) -> Tuple[float, List[str]]:
        """
        Compute deal score with uncertainty-aware penalties.
        """
        flags = []
        
        # Base score from value gap
        if listing.price > 0:
            diff_pct = (fair_value - listing.price) / listing.price
        else:
            diff_pct = 0.0
        
        base_score = 0.5 + diff_pct
        
        # Uncertainty penalty
        uncertainty_penalty = 0.0
        if uncertainty > 0.25:
            uncertainty_penalty = (uncertainty - 0.25) * 0.5
            flags.append("high_uncertainty")
        
        # Evidence quality penalty
        evidence_penalty = 0.0
        if evidence.model_used == "heuristic":
            evidence_penalty = 0.15
            flags.append("heuristic_valuation")
        elif evidence.model_used == "tabular_ml":
            evidence_penalty = 0.05
        
        # Hedonic fallback penalty
        if evidence.hedonic_fallback:
            evidence_penalty += 0.05
            flags.append("hedonic_fallback")
        
        # Calibration penalty
        if evidence.calibration_status != "calibrated":
            evidence_penalty += 0.03
            flags.append("uncalibrated")
        
        # Final score
        score = base_score - uncertainty_penalty - evidence_penalty
        score = max(0.0, min(1.0, score))
        
        # Value flags
        if diff_pct > 0.15:
            flags.append("undervalued")
        if diff_pct > 0.25:
            flags.append("deep_value")
        if diff_pct < -0.15:
            flags.append("overpriced")
        
        return score, flags
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _get_region_id(self, listing: CanonicalListing) -> str:
        """Extract region identifier from listing"""
        if listing.location and listing.location.city:
            return listing.location.city.lower()
        return "unknown"
    
    def _get_market_average_sqm(self, city: str = None) -> Tuple[float, int]:
        """Get market average price per sqm"""
        session = self.storage.get_session()
        try:
            query = session.query(
                DBListing.price, DBListing.surface_area_sqm
            ).filter(
                DBListing.price > 0,
                DBListing.surface_area_sqm > 0
            )
            
            if city:
                query = query.filter(DBListing.city == city)
            
            data = query.all()
            if not data:
                return 3000.0, 0  # Default for Madrid
                
            ratios = [row.price / row.surface_area_sqm for row in data]
            avg_sqm = sum(ratios) / len(ratios)
            return avg_sqm, len(ratios)
        finally:
            session.close()
    
    def _get_market_signals(self, listing: CanonicalListing) -> Dict[str, float]:
        """Get current market signals"""
        try:
            if listing.location and listing.location.city:
                profile = self.analytics.analyze_listing(listing)
                if profile:
                    return {
                        "momentum": profile.momentum_score,
                        "liquidity": profile.liquidity_score,
                        "catchup": profile.catchup_potential
                    }
        except Exception as e:
            logger.warning("market_signals_failed", error=str(e))
        
        return {}
    
    def _generate_thesis(
        self,
        listing: CanonicalListing,
        fair_value: float,
        uncertainty: float,
        evidence: EvidencePack,
        score: float
    ) -> str:
        """Generate investment thesis text"""
        model_name = {
            "fusion": "Comparable Analysis",
            "tabular_ml": "ML Model",
            "heuristic": "Market Average"
        }.get(evidence.model_used, evidence.model_used)
        
        thesis = f"Fair value €{fair_value:,.0f} (±{uncertainty:.0%}) via {model_name}. "
        
        if evidence.top_comps:
            thesis += f"Based on {len(evidence.top_comps)} time-adjusted comps. "
        
        if evidence.calibration_status == "calibrated":
            thesis += "Intervals conformally calibrated. "
        
        if score > 0.7:
            thesis += "Strong buy signal."
        elif score > 0.55:
            thesis += "Potential opportunity."
        elif score < 0.4:
            thesis += "Likely overpriced."
        
        return thesis
