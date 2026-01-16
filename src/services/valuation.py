"""
Valuation Service (SOTA V3)

Orchestrates property valuation with defensible methodology:
1. Fusion Model with time-adjusted comps
2. Market-drift projections via index regime
3. Rent comps + yield projections (no implicit fallbacks)

Key Features:
- Comps are TIME-ADJUSTED using hedonic index before fusion
- "Today" value: comps-anchor + residual
- "Future" value: V_t × market drift (no double-counting)
- Rental yield computed from explicit rent comps + rent index drift
- All intervals calibrated per-horizon via conformal prediction
- Structured evidence pack for auditability

References:
- RICS Red Book Valuation Standards
- Eurostat HPI methodology
"""

import structlog
import re
import os
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np

from src.services.storage import StorageService
from sqlalchemy import text
from src.core.domain.schema import (
    CanonicalListing, DealAnalysis, CompEvidence, EvidencePack, ValuationProjection, GeoLocation
)
from src.core.domain.models import DBListing
from src.services.forecasting import ForecastingService
from src.services.market_analytics import MarketAnalyticsService
from src.services.hedonic_index import HedonicIndexService
from src.services.conformal_calibrator import StratifiedCalibratorRegistry
from src.services.feature_sanitizer import sanitize_listing_features
from src.services.fusion_model import FusionModelService, FusionOutput
from src.services.encoders import MultimodalEncoder
from src.services.retrieval import CompRetriever
from src.services.eri_signals import ERISignalsService
from src.services.area_intelligence import AreaIntelligenceService
from src.core.config import (
    DEFAULT_DB_PATH,
    VECTOR_INDEX_PATH,
    VECTOR_METADATA_PATH,
    TFT_MODEL_PATH,
    CALIBRATION_PATH,
)

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
    min_comps_for_baseline: int = 5
    min_rent_comps: int = 5
    rent_radius_km: float = 2.0
    retriever_model_name: str = "all-MiniLM-L6-v2"
    retriever_index_path: str = str(VECTOR_INDEX_PATH)
    retriever_metadata_path: str = str(VECTOR_METADATA_PATH)
    retriever_vlm_policy: str = "gated"

    # ERI checks
    eri_lag_days: int = 45
    eri_disagreement_threshold: float = 0.08
    eri_uncertainty_multiplier: float = 1.25
    
    # Horizons
    horizons_months: List[int] = None

    # Forecasting
    forecast_mode: str = "analytic"  # analytic or tft
    forecast_index_source: str = "market"
    tft_model_path: str = str(TFT_MODEL_PATH)
    
    # Conformal
    conformal_alpha: float = 0.1
    conformal_window: int = 50
    calibration_path: str = str(CALIBRATION_PATH)

    # Income + area adjustments
    income_value_weight_max: float = 0.35
    income_value_weight_min: float = 0.0
    income_value_max_adjustment_pct: float = 0.35
    area_sentiment_weight: float = 0.06
    area_development_weight: float = 0.04
    area_adjustment_cap: float = 0.08
    
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
    Fusion-only valuation with time-adjusted comps.

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
        self.forecasting = ForecastingService(
            db_path=str(DEFAULT_DB_PATH),
            index_source=self.config.forecast_index_source,
            forecast_mode=self.config.forecast_mode,
            tft_model_path=self.config.tft_model_path
        )
        self.analytics = MarketAnalyticsService(db_path=str(DEFAULT_DB_PATH))
        self.hedonic = HedonicIndexService(db_path=str(DEFAULT_DB_PATH))
        self.eri = ERISignalsService(db_path=str(DEFAULT_DB_PATH), lag_days=self.config.eri_lag_days)
        self.area_intel = AreaIntelligenceService(db_path=str(DEFAULT_DB_PATH))
        self.fusion = FusionModelService()
        retriever_cfg = {}
        if getattr(self.fusion, "config", None):
            retriever_cfg = self.fusion.config.get("retriever", {}) or {}
        if retriever_cfg:
            self.config.retriever_index_path = retriever_cfg.get("index_path", self.config.retriever_index_path)
            self.config.retriever_metadata_path = retriever_cfg.get("metadata_path", self.config.retriever_metadata_path)
            self.config.retriever_model_name = retriever_cfg.get("model_name", self.config.retriever_model_name)
            self.config.retriever_vlm_policy = retriever_cfg.get("vlm_policy", self.config.retriever_vlm_policy)

        self.retriever = CompRetriever(
            index_path=self.config.retriever_index_path,
            metadata_path=self.config.retriever_metadata_path,
            model_name=self.config.retriever_model_name,
            strict_model_match=True,
            vlm_policy=self.config.retriever_vlm_policy
        )
        
        # Encoder for embeddings (Vision disabled to avoid heavy dependencies)
        self.encoder = MultimodalEncoder(enable_vision=False)

        # Conformal calibrators (per-horizon, stratified)
        if os.path.exists(self.config.calibration_path):
            try:
                self.calibrators = StratifiedCalibratorRegistry.load(self.config.calibration_path)
                logger.info("calibration_loaded", path=self.config.calibration_path)
            except Exception as e:
                logger.warning("calibration_load_failed", error=str(e))
                self.calibrators = StratifiedCalibratorRegistry(
                    horizons=[0] + self.config.horizons_months,
                    alpha=self.config.conformal_alpha,
                    window_size=self.config.conformal_window
                )
        else:
            self.calibrators = StratifiedCalibratorRegistry(
                horizons=[0] + self.config.horizons_months,
                alpha=self.config.conformal_alpha,
                window_size=self.config.conformal_window
            )

    def _normalize_property_type(self, value: Optional[str]) -> str:
        if value is None:
            return "apartment"
        text = str(value).strip()
        if "." in text:
            text = text.split(".")[-1]
        return text.lower() or "apartment"

    def _to_int(self, value: Optional[object]) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("", "null", "none"):
                return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _to_float(self, value: Optional[object]) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("", "null", "none"):
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _db_to_canonical(self, db_item: DBListing) -> CanonicalListing:
        loc = None
        if db_item.city or db_item.lat or db_item.lon:
            loc = GeoLocation(
                lat=db_item.lat,
                lon=db_item.lon,
                address_full=db_item.address_full or db_item.title,
                city=db_item.city or "Unknown",
                zip_code=getattr(db_item, "zip_code", None),
                country=db_item.country or "ES",
            )

        listing = CanonicalListing(
            id=db_item.id,
            source_id=db_item.source_id,
            external_id=db_item.external_id,
            url=str(db_item.url),
            title=db_item.title,
            description=db_item.description,
            price=db_item.price,
            currency=db_item.currency,
            listing_type=getattr(db_item, "listing_type", "sale") or "sale",
            property_type=self._normalize_property_type(db_item.property_type),
            bedrooms=self._to_int(db_item.bedrooms),
            bathrooms=self._to_int(db_item.bathrooms),
            surface_area_sqm=self._to_float(db_item.surface_area_sqm),
            plot_area_sqm=self._to_float(getattr(db_item, "plot_area_sqm", None)),
            floor=self._to_int(db_item.floor),
            has_elevator=db_item.has_elevator,
            location=loc,
            image_urls=db_item.image_urls or [],
            vlm_description=db_item.vlm_description,
            text_sentiment=db_item.text_sentiment,
            image_sentiment=db_item.image_sentiment,
            analysis_meta=db_item.analysis_meta,
            image_embeddings=getattr(db_item, "image_embeddings", None),
            listed_at=db_item.listed_at,
            updated_at=db_item.updated_at,
            status=db_item.status,
            sold_price=getattr(db_item, "sold_price", None),
            sold_at=getattr(db_item, "sold_at", None),
            tags=db_item.tags or [],
        )
        return sanitize_listing_features(listing)

    def _retrieve_comps(
        self,
        listing: CanonicalListing,
        as_of_date: Optional[datetime] = None
    ) -> Tuple[List[CanonicalListing], Dict[str, float]]:
        comps = self.retriever.retrieve_comps(
            target=listing,
            k=self.config.K_model,
            max_radius_km=self.config.max_distance_km,
            listing_type=listing.listing_type or "sale",
            max_listed_at=as_of_date,
            exclude_duplicate_external=True
        )
        if len(comps) < self.config.min_comps_for_fusion:
            raise ValueError("insufficient_comps")

        similarity_by_id = {c.id: c.similarity_score for c in comps}
        ids = [c.id for c in comps]

        session = self.storage.get_session()
        try:
            rows = session.query(DBListing).filter(DBListing.id.in_(ids)).all()
        finally:
            session.close()

        by_id = {r.id: r for r in rows}
        hydrated = []
        for comp_id in ids:
            row = by_id.get(comp_id)
            if row:
                hydrated.append(self._db_to_canonical(row))

        if len(hydrated) < self.config.min_comps_for_fusion:
            raise ValueError("insufficient_hydrated_comps")

        return hydrated, similarity_by_id

    def _retrieve_rent_comps(
        self,
        listing: CanonicalListing,
        as_of_date: Optional[datetime] = None
    ) -> Tuple[List[CanonicalListing], Dict[str, float]]:
        comps = self.retriever.retrieve_comps(
            target=listing,
            k=self.config.K_model,
            max_radius_km=self.config.rent_radius_km,
            listing_type="rent",
            max_listed_at=as_of_date,
            exclude_duplicate_external=True
        )
        if len(comps) < self.config.min_rent_comps:
            raise ValueError("insufficient_rent_comps")

        similarity_by_id = {c.id: c.similarity_score for c in comps}
        ids = [c.id for c in comps]

        session = self.storage.get_session()
        try:
            rows = (
                session.query(DBListing)
                .filter(DBListing.id.in_(ids))
                .filter(DBListing.listing_type == "rent")
                .all()
            )
        finally:
            session.close()

        by_id = {r.id: r for r in rows}
        hydrated = []
        for comp_id in ids:
            row = by_id.get(comp_id)
            if row:
                hydrated.append(self._db_to_canonical(row))

        if len(hydrated) < self.config.min_rent_comps:
            raise ValueError("insufficient_hydrated_rent_comps")

        return hydrated, similarity_by_id
    
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
        sanitize_listing_features(listing)
        
        if tracer:
            tracer.start_trace(listing.id)
            tracer.log("input_listing", listing)
            tracer.log("input_comps_count", len(comps) if comps else 0)
        
        try:
            # Get region for index lookups
            region_id = self._get_region_id(listing)
            if region_id == "unknown":
                raise ValueError("missing_region_id")
            
            # =====================================================================
            # STAGE 1: SPOT VALUATION ("Today's Fair Value")
            # =====================================================================

            if comps is None:
                comps, similarity_by_id = self._retrieve_comps(listing, as_of_date=valuation_date)
            else:
                similarity_by_id = {}

            eri_disagree, eri_details, eri_signals = self._eri_disagreement(region_id, valuation_date)
            use_vlm = not eri_disagree

            fair_value, uncertainty, evidence = self._compute_spot_value(
                listing,
                comps,
                similarity_by_id,
                region_id,
                valuation_date,
                tracer,
                use_vlm=use_vlm,
                external_signals=eri_signals,
                index_disagreement=eri_disagree,
                index_disagreement_details=eri_details
            )
            
            if tracer:
                tracer.log("spot_valuation_raw", {
                    "fair_value": fair_value,
                    "uncertainty": uncertainty,
                    "model_used": evidence.model_used
                })
            
            ptype = getattr(listing, "property_type", None)
            if hasattr(ptype, "value"):
                ptype = ptype.value
            ptype = str(ptype) if ptype else None
            bucket_key = self.calibrators.bucket_key(
                region_id=region_id,
                property_type=ptype,
                price=fair_value
            )

            # Apply conformal calibration to spot estimate
            if evidence.model_used == "fusion" and self.calibrators.is_calibrated(bucket_key, 0):
                if tracer:
                    tracer.log("calibration_spot_before", {
                        "q10": fair_value * (1 - uncertainty),
                        "q50": fair_value,
                        "q90": fair_value * (1 + uncertainty)
                    })
    
                cal_q10, cal_q50, cal_q90 = self.calibrators.calibrate_interval(
                    bucket_key,
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

            if eri_disagree:
                uncertainty *= self.config.eri_uncertainty_multiplier
            
            # =====================================================================
            # STAGE 1.5: RENT ESTIMATION & YIELD
            # =====================================================================

            rent_est, rent_uncertainty, rent_comps = self._compute_rental_value(
                listing, region_id, valuation_date, tracer
            )
            if fair_value <= 0:
                raise ValueError("invalid_fair_value")
            rental_yield = (rent_est * 12 / fair_value * 100)

            # =====================================================================
            # STAGE 2: MARKET SIGNALS + INCOME/AREA ADJUSTMENTS
            # =====================================================================
            
            market_signals = self._get_market_signals(listing, region_id, valuation_date)
            fair_value, uncertainty, adjustment_info = self._apply_income_and_area_adjustments(
                listing=listing,
                fair_value=fair_value,
                uncertainty=uncertainty,
                rent_est=rent_est,
                rent_uncertainty=rent_uncertainty,
                rent_comps=rent_comps,
                market_signals=market_signals,
            )
            if adjustment_info:
                evidence.external_signals = {
                    **(evidence.external_signals or {}),
                    **adjustment_info
                }
                rental_yield = (rent_est * 12 / fair_value * 100)

            # =====================================================================
            # STAGE 3: DEAL SCORING
            # =====================================================================

            score, flags = self._compute_deal_score(
                listing, fair_value, uncertainty, evidence, market_signals, rental_yield
            )
            if eri_disagree:
                flags.append("index_disagreement")

            # =====================================================================
            # STAGE 4: FUTURE PROJECTIONS (Market Drift Only)
            # =====================================================================
            
            projections = self._compute_projections(fair_value, region_id, valuation_date, bucket_key)

            # =====================================================================
            # STAGE 4b: RENT & YIELD PROJECTIONS
            # =====================================================================

            rent_projections = self.forecasting.forecast_rent(
                region_id=region_id,
                current_monthly_rent=rent_est,
                horizons_months=self.config.horizons_months,
            )

            yield_projections = self._compute_yield_projections(
                price_projections=projections,
                rent_projections=rent_projections,
            )
            
            # =====================================================================
            # STAGE 5: MARKET SIGNALS
            # =====================================================================
            
            # =====================================================================
            # BUILD RESULT
            # =====================================================================
            
            thesis = self._generate_thesis(
                listing, fair_value, uncertainty, evidence, score, rental_yield, market_signals
            )
            
            return DealAnalysis(
                listing_id=listing.id,
                fair_value_estimate=fair_value,
                fair_value_uncertainty_pct=uncertainty,
                deal_score=score,
                flags=flags,
                investment_thesis=thesis,
                projections=projections,
                rent_projections=rent_projections,
                yield_projections=yield_projections,
                market_signals=market_signals,
                evidence=evidence,
                rental_yield_estimate=rental_yield
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
        similarity_by_id: Dict[str, float],
        region_id: str,
        valuation_date: datetime,
        tracer: Any = None,
        use_vlm: bool = True,
        external_signals: Optional[Dict[str, float]] = None,
        index_disagreement: Optional[bool] = None,
        index_disagreement_details: Optional[Dict[str, float]] = None
    ) -> Tuple[float, float, EvidencePack]:
        """
        Compute today's fair value using fusion-only approach.
        Requires a minimum number of comps and a trained fusion model.
        """
        if not comps or len(comps) < self.config.min_comps_for_fusion:
            raise ValueError("insufficient_comps_for_fusion")

        return self._try_fusion_valuation(
            listing,
            comps,
            similarity_by_id,
            region_id,
            valuation_date,
            tracer,
            use_vlm=use_vlm,
            external_signals=external_signals,
            index_disagreement=index_disagreement,
            index_disagreement_details=index_disagreement_details
        )

    def _is_vlm_safe(self, text: Optional[str]) -> bool:
        if not text:
            return False
        cleaned = str(text).strip()
        if len(cleaned) < 30 or len(cleaned) > 600:
            return False
        lower = cleaned.lower()
        for bad in ("no image", "image not available", "unknown", "n/a", "not provided", "no description"):
            if bad in lower:
                return False
        tokens = [t for t in re.split(r"[^a-z0-9]+", lower) if t]
        if len(tokens) < 5:
            return False
        uniq_ratio = len(set(tokens)) / max(len(tokens), 1)
        return uniq_ratio >= 0.4
    
    def _try_fusion_valuation(
        self,
        listing: CanonicalListing,
        comps: List[CanonicalListing],
        similarity_by_id: Dict[str, float],
        region_id: str,
        valuation_date: datetime,
        tracer: Any = None,
        use_vlm: bool = True,
        external_signals: Optional[Dict[str, float]] = None,
        index_disagreement: Optional[bool] = None,
        index_disagreement_details: Optional[Dict[str, float]] = None
    ) -> Tuple[float, float, EvidencePack]:
        """
        Attempt Fusion Model valuation with time-adjusted comps.
        """
        # Time-adjust comp prices
        adjusted_comps = []
        comp_evidence = []

        for comp in comps[:self.config.K_model]:
            comp_timestamp = comp.listed_at or comp.updated_at
            if not comp_timestamp:
                continue

            raw_price = self._resolve_comp_price(comp)

            adj_price, adj_factor, meta = self.hedonic.adjust_comp_price(
                raw_price=raw_price,
                region_id=region_id,
                comp_timestamp=comp_timestamp,
                target_timestamp=valuation_date
            )

            if meta.get("comp_index_fallback") or meta.get("target_index_fallback"):
                raise ValueError("hedonic_index_fallback_detected")

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
                raw_price=raw_price,
                adj_factor=adj_factor,
                adj_price=adj_price,
                attention_weight=0.0,  # Updated after fusion
                is_sold=bool(getattr(comp, "sold_price", None)) or (comp.status.value == "sold" if comp.status else False),
                similarity_score=similarity_by_id.get(comp.id)
            ))

        if len(adjusted_comps) < self.config.min_comps_for_fusion:
            raise ValueError("insufficient_time_adjusted_comps")

        if tracer:
            tracer.log("fusion_time_adjustment", {
                "comps_count": len(adjusted_comps),
                "sample_adj_factors": [c['adj_factor'] for c in adjusted_comps[:5]],
                "sample_meta": [c['meta'] for c in adjusted_comps[:5]]
            })

        # Get embeddings and features for target
        target_text, target_tab, target_img = self._get_embeddings(listing, include_vlm=use_vlm)

        # Get embeddings and features for comps
        comp_text_list = []
        comp_tab_list = []
        comp_img_list = []
        comp_prices_list = []

        for item in adjusted_comps:
            comp = item['comp']
            c_text, c_tab, c_img = self._get_embeddings(comp, include_vlm=use_vlm)

            comp_text_list.append(c_text)
            comp_tab_list.append(c_tab)
            comp_img_list.append(c_img)
            comp_prices_list.append(item['adj_price'])

        use_residual = self.fusion.config.get("target_mode") == "log_residual"
        if use_residual:
            baseline_weights = [similarity_by_id.get(item["comp"].id, 1.0) for item in adjusted_comps]
            baseline = self._robust_comp_baseline(comp_prices_list, baseline_weights)
            baseline_log = float(np.log(baseline))

            # Run fusion model (predict residuals in log space)
            fusion_out = self.fusion.predict(
                target_text_embedding=target_text,
                target_tabular_features=target_tab,
                target_image_embedding=target_img,
                comp_text_embeddings=comp_text_list,
                comp_tabular_features=comp_tab_list,
                comp_image_embeddings=comp_img_list,
                comp_prices=comp_prices_list,
                output_mode="residual"
            )

            # Extract residual quantiles
            try:
                r10 = float(fusion_out.price_quantiles["0.1"])
                r50 = float(fusion_out.price_quantiles["0.5"])
                r90 = float(fusion_out.price_quantiles["0.9"])
            except Exception as exc:
                raise ValueError("missing_fusion_quantiles") from exc

            q10 = float(np.exp(baseline_log + r10))
            q50 = float(np.exp(baseline_log + r50))
            q90 = float(np.exp(baseline_log + r90))

            if tracer:
                tracer.log("fusion_quantiles_raw", {"q10": q10, "q50": q50, "q90": q90, "baseline": baseline})

            anchor_price = baseline
            anchor_std = float(np.std(comp_prices_list)) if comp_prices_list else 0.0
        else:
            fusion_out = self.fusion.predict(
                target_text_embedding=target_text,
                target_tabular_features=target_tab,
                target_image_embedding=target_img,
                comp_text_embeddings=comp_text_list,
                comp_tabular_features=comp_tab_list,
                comp_image_embeddings=comp_img_list,
                comp_prices=comp_prices_list
            )

            try:
                q10 = float(fusion_out.price_quantiles["0.1"])
                q50 = float(fusion_out.price_quantiles["0.5"])
                q90 = float(fusion_out.price_quantiles["0.9"])
            except Exception as exc:
                raise ValueError("missing_fusion_quantiles") from exc

            if tracer:
                tracer.log("fusion_quantiles_raw", {"q10": q10, "q50": q50, "q90": q90})

            anchor_price = q50
            anchor_std = (q90 - q10) / 2

        if q50 <= 0 or q10 <= 0 or q90 <= 0 or not (q10 <= q50 <= q90):
            raise ValueError("invalid_fusion_quantiles")

        if fusion_out.attention_weights is None:
            raise ValueError("missing_attention_weights")

        attn_weights = fusion_out.attention_weights.flatten()
        for i, ce in enumerate(comp_evidence):
            if i < len(attn_weights):
                ce.attention_weight = float(attn_weights[i])

        comp_evidence.sort(key=lambda ce: ce.attention_weight, reverse=True)

        uncertainty = (q90 - q10) / (2 * q50)

        # Comp date range
        comp_months = [ce.observed_month for ce in comp_evidence]
        comp_date_range = f"{min(comp_months)} to {max(comp_months)}" if comp_months else None

        evidence = EvidencePack(
            model_used="fusion",
            anchor_price=anchor_price,
            anchor_std=anchor_std,
            top_comps=comp_evidence,
            hedonic_fallback=False,
            hedonic_fallback_reason=None,
            calibration_status="uncalibrated",
            valuation_date=valuation_date.strftime("%Y-%m-%d"),
            comp_date_range=comp_date_range,
            external_signals=external_signals,
            index_disagreement=index_disagreement,
            index_disagreement_details=index_disagreement_details
        )

        return (q50, uncertainty, evidence)

    def _get_embeddings(
        self,
        listing: CanonicalListing,
        include_vlm: bool = True
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """
        Helper to extract embeddings and features for a listing.
        Returns: (text_embedding, tabular_features, image_embedding)
        """
        sanitize_listing_features(listing)
        # 1. Text Embedding
        text_parts = [listing.title]
        if listing.description:
            text_parts.append(listing.description)
        if include_vlm and listing.vlm_description and self.config.retriever_vlm_policy != "off":
            if self._is_vlm_safe(listing.vlm_description):
                text_parts.append(listing.vlm_description)
        full_text = " ".join(text_parts)

        text_emb = self.encoder.text_encoder.encode_single(full_text)

        # 2. Tabular Features
        # Features expected by TabularEncoder default:
        # bedrooms, bathrooms, surface_area_sqm, year_built, floor, lat, lon, price_per_sqm, sentiment_score, has_elevator

        # Avoid train/infer leakage: do not use price_per_sqm as an input feature.
        price_sqm = 0.0

        features = {
            'bedrooms': listing.bedrooms or 0,
            'bathrooms': listing.bathrooms or 0,
            'surface_area_sqm': listing.surface_area_sqm or 0,
            'year_built': 0, # Not in CanonicalListing
            'floor': listing.floor or 0,
            'lat': listing.location.lat if listing.location else 0,
            'lon': listing.location.lon if listing.location else 0,
            'price_per_sqm': price_sqm,
            'text_sentiment': listing.text_sentiment or 0.5,
            'image_sentiment': listing.image_sentiment or 0.5,
            'has_elevator': 1.0 if listing.has_elevator else 0.0
        }

        tab_vec = self.encoder.tabular_encoder.encode(features)

        # 3. Image Embedding
        # Use cached if available
        img_emb = None
        if listing.image_embeddings and len(listing.image_embeddings) > 0:
            # Assume first embedding or mean
            # image_embeddings is List[List[float]]
            try:
                img_emb = np.array(listing.image_embeddings[0], dtype='float32')
            except:
                pass

        return text_emb, tab_vec, img_emb

    def _robust_comp_baseline(
        self,
        prices: List[float],
        weights: Optional[List[float]] = None
    ) -> float:
        if not prices:
            raise ValueError("missing_comp_prices")
        values = np.array(prices, dtype=float)
        if np.any(values <= 0):
            values = values[values > 0]
        if len(values) == 0:
            raise ValueError("invalid_comp_prices")

        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        if mad <= 0:
            mad = max(median * 0.05, 1.0)

        mask = np.abs(values - median) <= (3.0 * mad)
        values = values[mask]
        if len(values) < self.config.min_comps_for_baseline:
            raise ValueError("insufficient_baseline_comps")

        if weights is None:
            weights_arr = np.ones_like(values) / len(values)
        else:
            weights_arr = np.array(weights, dtype=float)
            weights_arr = weights_arr[mask] if len(weights_arr) >= len(mask) else weights_arr
            if weights_arr.sum() <= 0:
                weights_arr = np.ones_like(values) / len(values)
            else:
                weights_arr = weights_arr / weights_arr.sum()

        order = np.argsort(values)
        cum = np.cumsum(weights_arr[order])
        idx = int(np.searchsorted(cum, 0.5))
        return float(values[order][min(idx, len(values) - 1)])

    # =========================================================================
    # PROJECTIONS (Market Drift Only - No Double Counting)
    # =========================================================================
    
    def _compute_projections(
        self,
        spot_value: float,
        region_id: str,
        valuation_date: datetime,
        bucket_key: str
    ) -> List[ValuationProjection]:
        """
        Compute future value projections.
        
        CRITICAL: Apply only market drift to spot value.
        Do NOT re-compute comps at future dates.
        
        Formula: V_{t+h} = V_t × growth_ratio_{r,h}
        """
        projections = []

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
            if self.calibrators.is_calibrated(bucket_key, horizon):
                cal_q10, cal_q50, cal_q90 = self.calibrators.calibrate_interval(
                    bucket_key,
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

        return projections

    def _compute_yield_projections(
        self,
        price_projections: List[ValuationProjection],
        rent_projections: List[ValuationProjection],
    ) -> List[ValuationProjection]:
        """
        Compute forward gross yield projections by combining price + rent projections.
        """
        if not price_projections or not rent_projections:
            raise ValueError("missing_yield_projection_inputs")

        price_by_horizon = {p.months_future: p for p in price_projections}
        rent_by_horizon = {p.months_future: p for p in rent_projections}
        missing = [
            h for h in self.config.horizons_months
            if h not in price_by_horizon or h not in rent_by_horizon
        ]
        if missing:
            raise ValueError("missing_projection_horizon")

        out: List[ValuationProjection] = []

        for h in self.config.horizons_months:
            price = price_by_horizon.get(h)
            rent = rent_by_horizon.get(h)
            if not price or not rent:
                raise ValueError("missing_projection_horizon")
            if price.predicted_value <= 0 or rent.predicted_value <= 0:
                raise ValueError("invalid_projection_values")

            rent_q10 = rent.confidence_interval_low
            rent_q50 = rent.predicted_value
            rent_q90 = rent.confidence_interval_high
            rent_conf = rent.confidence_score

            # Conservative bounds: low yield = low rent / high price; high yield = high rent / low price.
            denom_low = price.confidence_interval_high if price.confidence_interval_high > 0 else price.predicted_value
            denom_high = price.confidence_interval_low if price.confidence_interval_low and price.confidence_interval_low > 0 else price.predicted_value

            y50 = (rent_q50 * 12 / price.predicted_value) * 100 if price.predicted_value > 0 else 0.0
            y10 = (rent_q10 * 12 / denom_low) * 100 if denom_low > 0 else 0.0
            y90 = (rent_q90 * 12 / denom_high) * 100 if denom_high > 0 else y50

            # Ensure monotonicity
            low = min(y10, y50, y90)
            high = max(y10, y50, y90)

            out.append(
                ValuationProjection(
                    metric="yield_pct",
                    months_future=h,
                    years_future=h / 12.0,
                    predicted_value=float(y50),
                    confidence_interval_low=float(low),
                    confidence_interval_high=float(high),
                    confidence_score=float(min(price.confidence_score, rent_conf)),
                    scenario_name="yield_baseline",
                )
            )

        return out

    def update_calibration(
        self,
        listing: CanonicalListing,
        actual_value: float,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float,
        horizon_months: int = 0
    ):
        if actual_value <= 0:
            raise ValueError("invalid_actual_value")
        region_id = self._get_region_id(listing)
        ptype = getattr(listing, "property_type", None)
        if hasattr(ptype, "value"):
            ptype = ptype.value
        ptype = str(ptype) if ptype else None
        bucket_key = self.calibrators.bucket_key(
            region_id=region_id,
            property_type=ptype,
            price=actual_value
        )
        self.calibrators.update(bucket_key, horizon_months, actual_value, pred_q10, pred_q50, pred_q90)
        try:
            self.calibrators.save(self.config.calibration_path)
        except Exception as e:
            logger.warning("calibration_save_failed", error=str(e))

    def _apply_income_and_area_adjustments(
        self,
        *,
        listing: CanonicalListing,
        fair_value: float,
        uncertainty: float,
        rent_est: float,
        rent_uncertainty: float,
        rent_comps: List[CanonicalListing],
        market_signals: Dict[str, float],
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Blend comp-based value with income-based value and apply area adjustments.
        """
        adjusted_value = fair_value
        adjusted_uncertainty = uncertainty
        adjustments: Dict[str, float] = {}

        if listing.listing_type == "sale" and rent_est > 0:
            market_yield = market_signals.get("market_yield")
            if market_yield and market_yield > 0:
                income_value = (rent_est * 12) / (market_yield / 100.0)
                max_delta = max(0.0, self.config.income_value_max_adjustment_pct)
                min_val = fair_value * (1 - max_delta)
                max_val = fair_value * (1 + max_delta)
                income_value = float(min(max(income_value, min_val), max_val))

                comp_factor = min(
                    1.0,
                    len(rent_comps) / max(1, self.config.min_rent_comps * 2),
                )
                unc_factor = max(0.0, 1.0 - min(float(rent_uncertainty), 0.9))
                income_weight = self.config.income_value_weight_max * comp_factor * unc_factor
                if income_weight < self.config.income_value_weight_min:
                    income_weight = 0.0

                if income_weight > 0:
                    adjusted_value = adjusted_value * (1 - income_weight) + income_value * income_weight
                    adjusted_uncertainty = adjusted_uncertainty * (
                        1 + income_weight * min(float(rent_uncertainty), 0.5)
                    )

                adjustments.update({
                    "income_value": float(income_value),
                    "income_weight": float(income_weight),
                    "rent_uncertainty": float(rent_uncertainty),
                    "rent_comps_count": float(len(rent_comps)),
                })

        area_sentiment = float(market_signals.get("area_sentiment", 0.5))
        area_development = float(market_signals.get("area_development", 0.5))
        area_confidence = market_signals.get("area_confidence")
        if area_confidence is None:
            area_confidence = 1.0
        area_confidence = float(max(0.0, min(1.0, area_confidence)))
        area_adjustment = (
            (area_sentiment - 0.5) * self.config.area_sentiment_weight
            + (area_development - 0.5) * self.config.area_development_weight
        )
        cap = self.config.area_adjustment_cap
        area_adjustment = float(max(-cap, min(cap, area_adjustment)))
        area_adjustment = float(area_adjustment * area_confidence)
        if area_adjustment != 0:
            adjusted_value = adjusted_value * (1 + area_adjustment)
            adjusted_uncertainty = adjusted_uncertainty * (1 + abs(area_adjustment))

        adjustments.update({
            "area_sentiment": area_sentiment,
            "area_development": area_development,
            "area_confidence": area_confidence,
            "area_adjustment": area_adjustment,
        })
        for key in (
            "area_sentiment_credibility",
            "area_development_credibility",
            "area_sentiment_freshness_days",
            "area_development_freshness_days",
        ):
            value = market_signals.get(key)
            if value is not None:
                adjustments[key] = float(value)

        return adjusted_value, adjusted_uncertainty, adjustments
    
    # =========================================================================
    # DEAL SCORING
    # =========================================================================
    
    def _compute_deal_score(
        self,
        listing: CanonicalListing,
        fair_value: float,
        uncertainty: float,
        evidence: EvidencePack,
        market_signals: Dict[str, float],
        rental_yield: float
    ) -> Tuple[float, List[str]]:
        """
        Compute deal score from value, yield, and market regime signals.
        """
        flags = []

        if listing.price <= 0:
            raise ValueError("invalid_listing_price")
        if rental_yield is None or rental_yield <= 0:
            raise ValueError("missing_rental_yield")

        market_yield = market_signals.get("market_yield")
        momentum = market_signals.get("momentum")
        liquidity = market_signals.get("liquidity")
        catchup = market_signals.get("catchup")
        area_sentiment = market_signals.get("area_sentiment")
        area_development = market_signals.get("area_development")
        area_confidence = market_signals.get("area_confidence")
        if market_yield is None or market_yield <= 0:
            raise ValueError("missing_market_yield")
        if momentum is None or liquidity is None or catchup is None:
            raise ValueError("missing_market_signals")

        diff_pct = (fair_value - listing.price) / listing.price
        yield_spread = (rental_yield - market_yield) / market_yield

        value_component = float(np.tanh(diff_pct / 0.15))
        yield_component = float(np.tanh(yield_spread / 0.03))
        momentum_component = float(np.tanh(momentum / 0.05))
        liquidity_component = float((liquidity - 0.5) / 0.5)
        catchup_component = float((catchup - 0.5) / 0.5)
        if area_sentiment is not None and area_development is not None:
            sent_component = (float(area_sentiment) - 0.5) / 0.5
            dev_component = (float(area_development) - 0.5) / 0.5
            area_component = float(0.5 * (sent_component + dev_component))
            if area_confidence is not None:
                area_component = float(area_component * max(0.0, min(1.0, float(area_confidence))))
        else:
            area_component = 0.0

        raw_score = (
            0.32 * value_component +
            0.23 * yield_component +
            0.18 * momentum_component +
            0.09 * liquidity_component +
            0.08 * catchup_component +
            0.10 * area_component
        )

        conviction = max(0.0, 1.0 - (uncertainty / 0.35))
        score = (0.5 + 0.5 * raw_score) * conviction
        score = max(0.0, min(1.0, score))

        if uncertainty > 0.25:
            flags.append("high_uncertainty")

        if diff_pct > 0.15:
            flags.append("undervalued")
        if diff_pct > 0.25:
            flags.append("deep_value")
        if diff_pct < -0.15:
            flags.append("overpriced")

        if yield_spread > 0.01:
            flags.append("yield_advantage")
        if yield_spread < -0.01:
            flags.append("yield_disadvantage")

        if momentum > 0.03:
            flags.append("strong_momentum")
        if momentum < -0.03:
            flags.append("negative_momentum")

        if liquidity < 0.3:
            flags.append("low_liquidity")

        if area_sentiment is not None:
            if area_sentiment > 0.65:
                flags.append("positive_area_sentiment")
            if area_sentiment < 0.35:
                flags.append("negative_area_sentiment")

        if area_development is not None and area_development > 0.65:
            flags.append("strong_development")

        if evidence.calibration_status != "calibrated":
            flags.append("uncalibrated")

        return score, flags
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _get_region_id(self, listing: CanonicalListing) -> str:
        """Extract region identifier from listing"""
        if listing.location and listing.location.city:
            return listing.location.city.lower()
        return "unknown"

    def _resolve_comp_price(self, comp: CanonicalListing) -> float:
        if comp.listing_type == "sale":
            sold_price = getattr(comp, "sold_price", None)
            if sold_price is not None and sold_price > 0:
                return float(sold_price)
        return float(comp.price)

    def _get_market_index_value(self, region_id: str, month_key: str, column: str) -> float:
        allowed = {"price_index_sqm", "rent_index_sqm"}
        if column not in allowed:
            raise ValueError("unsupported_market_index_column")

        query = text(
            f"""
            SELECT {column}
            FROM market_indices
            WHERE region_id = :region_id AND month_date LIKE :month_key
            ORDER BY month_date DESC
            LIMIT 1
            """
        )

        with self.storage.engine.connect() as conn:
            row = conn.execute(
                query,
                {"region_id": region_id, "month_key": f"{month_key}%"}
            ).fetchone()

        if not row or row[0] is None:
            raise ValueError("missing_market_index")

        value = float(row[0])
        if value <= 0:
            raise ValueError("invalid_market_index")

        return value

    def _get_index_yoy(
        self,
        table: str,
        column: str,
        region_id: str,
        valuation_date: datetime
    ) -> Optional[float]:
        if not region_id:
            return None

        month_key = valuation_date.strftime("%Y-%m")
        prev_date = (valuation_date.replace(day=1) - timedelta(days=365)).strftime("%Y-%m")

        query = text(
            f"""
            SELECT month_date, {column}
            FROM {table}
            WHERE region_id = :region_id AND month_date LIKE :month_key
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        prev_query = text(
            f"""
            SELECT month_date, {column}
            FROM {table}
            WHERE region_id = :region_id AND month_date LIKE :month_key
            ORDER BY month_date DESC
            LIMIT 1
            """
        )

        with self.storage.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id, "month_key": f"{month_key}%"}).fetchone()
            prev = conn.execute(prev_query, {"region_id": region_id, "month_key": f"{prev_date}%"}).fetchone()
            if (not row or not prev) and region_id != "all":
                row = conn.execute(query, {"region_id": "all", "month_key": f"{month_key}%"}).fetchone()
                prev = conn.execute(prev_query, {"region_id": "all", "month_key": f"{prev_date}%"}).fetchone()

        if not row or not prev:
            return None

        curr_val = float(row[1]) if row[1] is not None else None
        prev_val = float(prev[1]) if prev[1] is not None else None
        if not curr_val or not prev_val or prev_val <= 0:
            return None

        return curr_val / prev_val - 1.0

    def _eri_disagreement(
        self,
        region_id: str,
        valuation_date: datetime
    ) -> Tuple[bool, Dict[str, float], Dict[str, float]]:
        eri_signals = self.eri.get_signals(region_id, valuation_date)
        if not eri_signals:
            return False, {}, {}

        eri_yoy = eri_signals.get("registral_price_sqm_change")
        hedonic_yoy = self._get_index_yoy("hedonic_indices", "hedonic_index_sqm", region_id, valuation_date)
        market_yoy = self._get_index_yoy("market_indices", "price_index_sqm", region_id, valuation_date)

        details: Dict[str, float] = {}
        disagree = False

        if eri_yoy is not None and hedonic_yoy is not None:
            diff = abs(eri_yoy - hedonic_yoy)
            details["eri_vs_hedonic_yoy_diff"] = diff
            if diff >= self.config.eri_disagreement_threshold:
                disagree = True

        if eri_yoy is not None and market_yoy is not None:
            diff = abs(eri_yoy - market_yoy)
            details["eri_vs_market_yoy_diff"] = diff
            if diff >= self.config.eri_disagreement_threshold:
                disagree = True

        return disagree, details, eri_signals

    def _get_market_yield(self, region_id: str, valuation_date: datetime) -> float:
        month_key = valuation_date.strftime("%Y-%m")
        price_index = self._get_market_index_value(region_id, month_key, "price_index_sqm")
        rent_index = self._get_market_index_value(region_id, month_key, "rent_index_sqm")
        return (rent_index * 12 / price_index) * 100

    def _get_market_signals(
        self,
        listing: CanonicalListing,
        region_id: str,
        valuation_date: datetime
    ) -> Dict[str, float]:
        """Get current market signals (strict)."""
        if not listing.location or not listing.location.city:
            raise ValueError("missing_location")

        profile = self.analytics.analyze_listing(listing)
        if not profile:
            raise ValueError("missing_market_profile")
        if getattr(profile, "zone_id", None) == "unknown":
            raise ValueError("missing_market_profile")

        market_yield = self._get_market_yield(region_id, valuation_date)
        area_data = self.area_intel.get_area_indicators(region_id)

        signals = {
            "momentum": profile.momentum_score,
            "liquidity": profile.liquidity_score,
            "catchup": profile.catchup_potential,
            "market_yield": market_yield,
            "area_sentiment": float(area_data.get("sentiment_score", 0.5)),
            "area_development": float(area_data.get("future_development_score", 0.5)),
        }
        area_confidence = area_data.get("area_confidence")
        if area_confidence is not None:
            signals["area_confidence"] = float(area_confidence)
        for key, out_key in (
            ("sentiment_credibility", "area_sentiment_credibility"),
            ("development_credibility", "area_development_credibility"),
            ("sentiment_freshness_days", "area_sentiment_freshness_days"),
            ("development_freshness_days", "area_development_freshness_days"),
        ):
            value = area_data.get(key)
            if value is not None:
                signals[out_key] = float(value)
        return signals

    def _adjust_rent_price(
        self,
        raw_price: float,
        region_id: str,
        comp_timestamp: datetime,
        target_timestamp: datetime,
    ) -> Tuple[float, float]:
        comp_month = comp_timestamp.strftime("%Y-%m")
        target_month = target_timestamp.strftime("%Y-%m")

        comp_index = self._get_market_index_value(region_id, comp_month, "rent_index_sqm")
        target_index = self._get_market_index_value(region_id, target_month, "rent_index_sqm")

        factor = target_index / comp_index
        if factor <= 0:
            raise ValueError("invalid_rent_adjustment_factor")
        if factor < 0.5 or factor > 2.0:
            raise ValueError("rent_adjustment_out_of_bounds")

        return raw_price * factor, factor
    
    def _generate_thesis(
        self,
        listing: CanonicalListing,
        fair_value: float,
        uncertainty: float,
        evidence: EvidencePack,
        score: float,
        rental_yield: float,
        market_signals: Dict[str, float]
    ) -> str:
        """Generate investment thesis text"""
        if listing.price <= 0:
            raise ValueError("invalid_listing_price")

        value_gap_pct = (fair_value - listing.price) / listing.price * 100
        market_yield = market_signals.get("market_yield")
        momentum = market_signals.get("momentum")
        liquidity = market_signals.get("liquidity")

        thesis = (
            f"Fair value €{fair_value:,.0f} (±{uncertainty:.0%}) from comp-fusion; "
            f"value gap {value_gap_pct:+.1f}% vs ask. "
        )

        if evidence.top_comps:
            thesis += f"Based on {len(evidence.top_comps)} time-adjusted comps. "

        if evidence.external_signals:
            income_weight = evidence.external_signals.get("income_weight")
            area_adjustment = evidence.external_signals.get("area_adjustment")
            if income_weight:
                thesis += f"Income blend {income_weight * 100:.0f}% from rent comps. "
            if area_adjustment:
                thesis += f"Area adjustment {area_adjustment * 100:+.1f}%. "

        if market_yield is not None:
            spread_pp = rental_yield - market_yield
            thesis += f"Yield {rental_yield:.1f}% vs market {market_yield:.1f}% ({spread_pp:+.1f}pp). "
        else:
            thesis += f"Yield {rental_yield:.1f}%. "

        if momentum is not None and liquidity is not None:
            thesis += f"Momentum {momentum * 100:.1f}%/yr, liquidity {liquidity:.2f}. "

        area_sentiment = market_signals.get("area_sentiment")
        area_development = market_signals.get("area_development")
        if area_sentiment is not None and area_development is not None:
            thesis += (
                f"Area sentiment {area_sentiment:.2f}, development {area_development:.2f}. "
            )

        if evidence.calibration_status == "calibrated":
            thesis += "Intervals calibrated. "

        if score > 0.7:
            thesis += "Strong buy signal."
        elif score > 0.55:
            thesis += "Potential opportunity."
        elif score < 0.4:
            thesis += "Likely overpriced."

        return thesis

    def _compute_rental_value(
        self,
        listing: CanonicalListing,
        region_id: str,
        valuation_date: datetime,
        tracer: Any = None
    ) -> Tuple[float, float, List[CanonicalListing]]:
        """
        Estimate rent using robust comparable rental listings.

        Returns:
            (estimated_monthly_rent, uncertainty_pct, rental_comps_used)
        """
        if not listing.surface_area_sqm or listing.surface_area_sqm <= 0:
            raise ValueError("missing_surface_area_for_rent")

        rental_comps, similarity_by_id = self._retrieve_rent_comps(listing, as_of_date=valuation_date)

        adjusted_rents = []
        adjusted_weights = []
        comps_used = []

        for comp in rental_comps:
            if not comp.surface_area_sqm or comp.surface_area_sqm <= 0:
                continue
            comp_timestamp = comp.listed_at or comp.updated_at
            if not comp_timestamp:
                continue

            adj_price, adj_factor = self._adjust_rent_price(
                raw_price=comp.price,
                region_id=region_id,
                comp_timestamp=comp_timestamp,
                target_timestamp=valuation_date,
            )
            rent_sqm = adj_price / comp.surface_area_sqm
            weight = similarity_by_id.get(comp.id, 0.0)
            if weight <= 0:
                continue

            adjusted_rents.append(rent_sqm)
            adjusted_weights.append(weight)
            comps_used.append(comp)

        if len(adjusted_rents) < self.config.min_rent_comps:
            raise ValueError("insufficient_adjusted_rent_comps")

        values = np.array(adjusted_rents, dtype=float)
        weights = np.array(adjusted_weights, dtype=float)
        weight_sum = float(weights.sum())
        if weight_sum <= 0:
            raise ValueError("invalid_rent_comp_weights")

        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        if mad <= 0:
            mad = max(median * 0.05, 0.1)

        mask = np.abs(values - median) <= (3.0 * mad)
        values = values[mask]
        weights = weights[mask]
        comps_used = [c for c, keep in zip(comps_used, mask) if keep]

        if len(values) < self.config.min_rent_comps:
            raise ValueError("rent_comp_filter_excessive")

        weights = weights / weights.sum()
        est_rent_sqm = float(np.sum(weights * values))
        variance = float(np.sum(weights * (values - est_rent_sqm) ** 2))
        std_rent_sqm = float(np.sqrt(variance))

        if est_rent_sqm <= 0:
            raise ValueError("invalid_rent_estimate")

        est_rent = est_rent_sqm * listing.surface_area_sqm
        uncertainty = std_rent_sqm / est_rent_sqm

        if tracer:
            tracer.log("rental_valuation", {
                "est_rent": est_rent,
                "comps_count": len(comps_used),
                "avg_sqm": est_rent_sqm
            })

        return est_rent, uncertainty, comps_used
