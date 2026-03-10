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
import numpy as np

from src.platform.storage import StorageService
from sqlalchemy import text, func
import geolib.geohash
from src.platform.domain.schema import (
    CanonicalListing,
    DealAnalysis,
    CompEvidence,
    EvidencePack,
    ValuationProjection,
    GeoLocation,
    CompListing,
)
from src.platform.domain.models import DBListing
from src.valuation.services.forecasting import ForecastingService
from src.market.services.market_analytics import MarketAnalyticsService
from src.market.services.hedonic_index import HedonicIndexService
from src.valuation.services.conformal_calibrator import StratifiedCalibratorRegistry
from src.listings.services.feature_sanitizer import sanitize_listing_features
from src.ml.services.fusion_model import FusionModelService, FusionOutput
from src.ml.services.encoders import MultimodalEncoder
from src.valuation.services.retrieval import build_retriever
from src.market.services.eri_signals import ERISignalsService
from src.market.services.area_intelligence import AreaIntelligenceService
from src.platform.settings import AppConfig, ValuationConfig
from src.platform.config import DEFAULT_DB_PATH
from src.platform.utils.time import utcnow

logger = structlog.get_logger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

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
        config: ValuationConfig = None,
        *,
        app_config: Optional[AppConfig] = None,
        db_path: Optional[str] = None,
    ):
        self.storage = storage
        if config is None:
            if app_config is not None:
                config = app_config.valuation
            else:
                config = DEFAULT_CONFIG
        self.config = config

        if db_path is None and app_config is not None:
            db_path = str(app_config.pipeline.db_path)
        if db_path is None:
            db_path = str(DEFAULT_DB_PATH)

        # Services
        self.forecasting = ForecastingService(
            db_path=db_path,
            index_source=self.config.forecast_index_source,
            forecast_mode=self.config.forecast_mode,
            tft_model_path=self.config.tft_model_path,
        )
        self.analytics = MarketAnalyticsService(db_path=db_path)
        self.hedonic = HedonicIndexService(db_path=db_path)
        self.eri = ERISignalsService(
            db_path=db_path,
            lag_days=self.config.eri_lag_days,
            app_config=app_config,
        )
        self.area_intel = AreaIntelligenceService(db_path=db_path, app_config=app_config)
        if app_config is not None:
            self.fusion = FusionModelService(
                model_path=str(app_config.paths.fusion_model_path),
                config_path=str(app_config.paths.fusion_config_path),
            )
        else:
            self.fusion = FusionModelService()
        retriever_cfg = {}
        if getattr(self.fusion, "config", None):
            retriever_cfg = self.fusion.config.get("retriever", {}) or {}
        if retriever_cfg:
            self.config.retriever_index_path = retriever_cfg.get("index_path", self.config.retriever_index_path)
            self.config.retriever_metadata_path = retriever_cfg.get("metadata_path", self.config.retriever_metadata_path)
            self.config.retriever_model_name = retriever_cfg.get("model_name", self.config.retriever_model_name)
            self.config.retriever_vlm_policy = retriever_cfg.get("vlm_policy", self.config.retriever_vlm_policy)
            self.config.retriever_backend = retriever_cfg.get("backend", self.config.retriever_backend)
            self.config.retriever_lancedb_path = retriever_cfg.get("lancedb_path", self.config.retriever_lancedb_path)

        self.retriever = build_retriever(
            backend=self.config.retriever_backend,
            index_path=self.config.retriever_index_path,
            metadata_path=self.config.retriever_metadata_path,
            lancedb_path=self.config.retriever_lancedb_path,
            model_name=self.config.retriever_model_name,
            strict_model_match=True,
            vlm_policy=self.config.retriever_vlm_policy,
            app_config=app_config,
        )
        if retriever_cfg:
            expected_fingerprint = retriever_cfg.get("index_fingerprint")
            if expected_fingerprint:
                try:
                    actual_fingerprint = self.retriever.get_metadata().get("index_fingerprint")
                except Exception:
                    actual_fingerprint = None
                if actual_fingerprint and actual_fingerprint != expected_fingerprint:
                    logger.warning(
                        "retriever_index_fingerprint_mismatch",
                        expected=expected_fingerprint,
                        actual=actual_fingerprint,
                    )
        
        # Encoder for embeddings (Vision disabled to avoid heavy dependencies)
        self.encoder = MultimodalEncoder(
            enable_vision=False,
            text_model=self.config.retriever_model_name,
        )

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

    def _apply_interval_policy(
        self,
        *,
        bucket_key: str,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float,
        horizon_months: int,
    ) -> Tuple[float, float, float, Dict[str, Any], Dict[str, float]]:
        decision = self.calibrators.interval_policy(bucket_key, horizon_months=horizon_months)
        if decision["mode"] == "calibrated":
            cal_q10, cal_q50, cal_q90 = self.calibrators.calibrate_interval(
                bucket_key,
                pred_q10,
                pred_q50,
                pred_q90,
                horizon_months=horizon_months,
            )
        else:
            cal_q10, cal_q50, cal_q90 = self.calibrators.bootstrap_interval(
                bucket_key,
                pred_q10,
                pred_q50,
                pred_q90,
                horizon_months=horizon_months,
                min_uncertainty_pct=self.config.bootstrap_min_uncertainty_pct,
            )

        diagnostics = {
            "coverage_rate": float(decision["coverage_rate"]),
            "coverage_floor": float(decision["coverage_floor"]),
            "n_samples": float(decision["n_samples"]),
            "min_samples": float(decision["min_samples"]),
            "horizon_months": float(decision["horizon_months"]),
        }
        return cal_q10, cal_q50, cal_q90, decision, diagnostics

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
        comps: List[CompListing]
        try:
            comps = self.retriever.retrieve_comps(
                target=listing,
                k=self.config.K_model,
                max_radius_km=self.config.max_distance_km,
                listing_type=listing.listing_type or "sale",
                max_listed_at=as_of_date,
                exclude_duplicate_external=True
            )
        except Exception as exc:
            logger.warning("retriever_failed", error=str(exc), listing_id=listing.id)
            comps = []
        if len(comps) < self.config.min_comps_for_fusion:
            fallback, fallback_weights = self._fallback_comps_from_db(listing, as_of_date=as_of_date)
            if len(fallback) >= self.config.min_comps_for_fusion:
                return fallback, fallback_weights
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

    def _fallback_comps_from_db(
        self,
        listing: CanonicalListing,
        as_of_date: Optional[datetime] = None
    ) -> Tuple[List[CanonicalListing], Dict[str, float]]:
        if not listing.location or not listing.location.city:
            return [], {}

        session = self.storage.get_session()
        try:
            query = session.query(DBListing).filter(
                DBListing.price.isnot(None),
                DBListing.surface_area_sqm.isnot(None),
                DBListing.price > 0,
                DBListing.surface_area_sqm > 0,
            )
            city = listing.location.city.strip().lower()
            query = query.filter(func.lower(DBListing.city) == city)
            if listing.listing_type:
                query = query.filter(DBListing.listing_type == listing.listing_type)
            if listing.id:
                query = query.filter(DBListing.id != listing.id)
            if as_of_date:
                query = query.filter(
                    func.coalesce(DBListing.listed_at, DBListing.updated_at) <= as_of_date
                )

            order_ts = func.coalesce(DBListing.updated_at, DBListing.listed_at)
            rows = query.order_by(order_ts.desc()).limit(self.config.K_candidates).all()
        finally:
            session.close()

        hydrated = [self._db_to_canonical(row) for row in rows]
        similarity_by_id = {item.id: 1.0 for item in hydrated if item.id}
        return hydrated, similarity_by_id

    def _normalize_comps_input(
        self,
        comps: List[Any],
    ) -> Tuple[List[CanonicalListing], Dict[str, float]]:
        if not comps:
            return [], {}

        if isinstance(comps[0], CanonicalListing):
            similarity_by_id = {}
            for comp in comps:
                comp_id = getattr(comp, "id", None)
                if comp_id:
                    similarity_by_id[comp_id] = getattr(comp, "similarity_score", 1.0)
            return comps, similarity_by_id

        if isinstance(comps[0], DBListing):
            return [self._db_to_canonical(c) for c in comps], {}

        ids: List[str] = []
        similarity_by_id: Dict[str, float] = {}
        for comp in comps:
            comp_id = None
            similarity = None
            if isinstance(comp, CompListing):
                comp_id = comp.id
                similarity = comp.similarity_score
            elif isinstance(comp, dict):
                comp_id = comp.get("id")
                similarity = comp.get("similarity_score")
            else:
                comp_id = getattr(comp, "id", None)
                similarity = getattr(comp, "similarity_score", None)

            if comp_id:
                ids.append(comp_id)
                if similarity is not None:
                    similarity_by_id[comp_id] = float(similarity)

        ids = [cid for cid in ids if cid]
        if not ids:
            return [], similarity_by_id

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
        valuation_date = valuation_date or utcnow()
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
                comps, similarity_by_id = self._normalize_comps_input(comps)
                if len(comps) < self.config.min_comps_for_fusion:
                    if tracer:
                        tracer.log("comps_insufficient_provided", {"count": len(comps)})
                    comps, similarity_by_id = self._retrieve_comps(listing, as_of_date=valuation_date)

            country_code = listing.location.country if listing.location else None
            eri_disagree, eri_details, eri_signals = self._eri_disagreement(
                region_id,
                valuation_date,
                country_code,
            )
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
            if evidence.model_used == "fusion":
                base_q10 = fair_value * (1 - uncertainty)
                base_q90 = fair_value * (1 + uncertainty)
                if tracer:
                    tracer.log("calibration_spot_before", {
                        "q10": base_q10,
                        "q50": fair_value,
                        "q90": base_q90
                    })

                cal_q10, cal_q50, cal_q90, calibration_decision, calibration_diagnostics = (
                    self._apply_interval_policy(
                        bucket_key=bucket_key,
                        pred_q10=base_q10,
                        pred_q50=fair_value,
                        pred_q90=base_q90,
                        horizon_months=0,
                    )
                )

                if tracer:
                    tracer.log("calibration_spot_after", {
                        "q10": cal_q10,
                        "q50": cal_q50,
                        "q90": cal_q90,
                        "mode": calibration_decision["mode"],
                        "reason": calibration_decision["reason"],
                    })

                if cal_q50 > 0:
                    uncertainty = (cal_q90 - cal_q10) / (2 * cal_q50)
                evidence.calibration_status = str(calibration_decision["mode"])
                evidence.calibration_fallback_reason = (
                    None
                    if calibration_decision["mode"] == "calibrated"
                    else str(calibration_decision["reason"])
                )
                evidence.calibration_diagnostics = calibration_diagnostics

            if eri_disagree:
                uncertainty *= self.config.eri_uncertainty_multiplier

            extra_flags: List[str] = []
            
            # =====================================================================
            # STAGE 1.5: RENT ESTIMATION & YIELD
            # =====================================================================

            try:
                rent_est, rent_uncertainty, rent_comps, rent_meta = self._compute_rental_value(
                    listing, region_id, valuation_date, tracer
                )
            except ValueError as exc:
                rent_est, rent_uncertainty, rent_comps, rent_meta = self._fallback_rent_estimate(
                    listing=listing,
                    fair_value=fair_value,
                    reason=str(exc),
                    region_id=region_id,
                    valuation_date=valuation_date,
                    tracer=tracer,
                )
            rent_source = rent_meta.get("rent_source") if rent_meta else None
            if rent_source and rent_source != "rent_comps":
                extra_flags.append("rent_fallback")
                if rent_meta.get("rent_source_circular"):
                    extra_flags.append("rent_fallback_circular")
            if fair_value <= 0:
                raise ValueError("invalid_fair_value")
            rental_yield = (rent_est * 12 / fair_value * 100)

            # =====================================================================
            # STAGE 2: MARKET SIGNALS + INCOME/AREA ADJUSTMENTS
            # =====================================================================
            
            try:
                market_signals = self._get_market_signals(listing, region_id, valuation_date)
            except ValueError as exc:
                market_signals = self._fallback_market_signals(
                    rental_yield=rental_yield,
                    reason=str(exc),
                    region_id=region_id,
                    valuation_date=valuation_date,
                )
                extra_flags.append("market_signals_fallback")
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

            score_listing = listing
            if not listing.price or listing.price <= 0:
                if hasattr(listing, "model_copy"):
                    score_listing = listing.model_copy(update={"price": fair_value})
                else:
                    score_listing = listing.copy(update={"price": fair_value})
                extra_flags.append("missing_listing_price")
            score, flags = self._compute_deal_score(
                score_listing, fair_value, uncertainty, evidence, market_signals, rental_yield
            )
            if eri_disagree:
                flags.append("index_disagreement")
            if extra_flags:
                flags.extend(extra_flags)

            # =====================================================================
            # STAGE 4: FUTURE PROJECTIONS (Market Drift Only)
            # =====================================================================
            
            try:
                projections = self._compute_projections(
                    fair_value,
                    region_id,
                    valuation_date,
                    bucket_key,
                    country_code=country_code,
                )
            except ValueError as exc:
                logger.warning("projection_failed", error=str(exc), listing_id=listing.id)
                projections = []
                flags.append("missing_projections")

            # =====================================================================
            # STAGE 4b: RENT & YIELD PROJECTIONS
            # =====================================================================

            try:
                rent_projections = self.forecasting.forecast_rent(
                    region_id=region_id,
                    current_monthly_rent=rent_est,
                    country_code=country_code,
                    horizons_months=self.config.horizons_months,
                )
            except ValueError as exc:
                logger.warning("rent_projection_failed", error=str(exc), listing_id=listing.id)
                rent_projections = []
                flags.append("missing_rent_projections")

            if projections and rent_projections:
                try:
                    yield_projections = self._compute_yield_projections(
                        price_projections=projections,
                        rent_projections=rent_projections,
                    )
                except ValueError as exc:
                    logger.warning("yield_projection_failed", error=str(exc), listing_id=listing.id)
                    yield_projections = []
                    flags.append("missing_yield_projections")
            else:
                yield_projections = []

            pricing_signals = self._build_pricing_signals(
                listing=listing,
                fair_value=fair_value,
                rent_est=rent_est,
                rental_yield=rental_yield,
                market_signals=market_signals,
                projections=projections,
                rent_projections=rent_projections,
                yield_projections=yield_projections,
            )
            if pricing_signals:
                market_signals = {**market_signals, **pricing_signals}
            
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

    def _build_text_for_embedding(self, listing: CanonicalListing, include_vlm: bool) -> str:
        text_parts = [listing.title]
        if listing.description:
            text_parts.append(listing.description)
        if include_vlm and listing.vlm_description and self.config.retriever_vlm_policy != "off":
            if self._is_vlm_safe(listing.vlm_description):
                text_parts.append(listing.vlm_description)
        return " ".join(part for part in text_parts if part)

    def _build_tabular_features(self, listing: CanonicalListing) -> Dict[str, float]:
        price_sqm = 0.0
        return {
            'bedrooms': listing.bedrooms or 0,
            'bathrooms': listing.bathrooms or 0,
            'surface_area_sqm': listing.surface_area_sqm or 0,
            'year_built': 0,
            'floor': listing.floor or 0,
            'lat': listing.location.lat if listing.location else 0,
            'lon': listing.location.lon if listing.location else 0,
            'price_per_sqm': price_sqm,
            'text_sentiment': listing.text_sentiment or 0.5,
            'image_sentiment': listing.image_sentiment or 0.5,
            'has_elevator': 1.0 if listing.has_elevator else 0.0
        }

    def _get_image_embedding(self, listing: CanonicalListing) -> Optional[np.ndarray]:
        if listing.image_embeddings and len(listing.image_embeddings) > 0:
            try:
                return np.array(listing.image_embeddings[0], dtype='float32')
            except Exception:
                return None
        return None
    
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
        hedonic_fallback = False
        fallback_reasons = set()

        for comp in comps[:self.config.K_model]:
            comp_timestamp = comp.listed_at or comp.updated_at
            if not comp_timestamp:
                continue

            raw_price = self._resolve_comp_price(comp)
            if raw_price is None or raw_price <= 0:
                continue

            try:
                adj_price, adj_factor, meta = self.hedonic.adjust_comp_price(
                    raw_price=raw_price,
                    region_id=region_id,
                    comp_timestamp=comp_timestamp,
                    target_timestamp=valuation_date
                )
            except ValueError as exc:
                adj_price = raw_price
                adj_factor = 1.0
                meta = {
                    "comp_index_fallback": True,
                    "target_index_fallback": True,
                    "fallback_reason": str(exc),
                    "clamped": False,
                }

            comp_fallback = bool(meta.get("comp_index_fallback"))
            target_fallback = bool(meta.get("target_index_fallback"))
            if comp_fallback:
                fallback_reasons.add(
                    meta.get("comp_fallback_reason") or meta.get("fallback_reason") or "unknown"
                )
            if target_fallback:
                fallback_reasons.add(
                    meta.get("target_fallback_reason") or meta.get("fallback_reason") or "unknown"
                )

            if comp_fallback or target_fallback:
                allowed_reasons = {
                    "all_region",
                    "global_region",
                    "global_recent",
                    "recent_month",
                    "hedonic_index_not_found",
                    "ine_ipv_anchor",
                    "unknown",
                }
                disallowed = [r for r in fallback_reasons if r not in allowed_reasons]
                if disallowed:
                    raise ValueError("hedonic_index_fallback_detected")
                hedonic_fallback = True

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
        target_text = self._build_text_for_embedding(listing, include_vlm=use_vlm)
        target_text_emb = self.encoder.text_encoder.encode([target_text])[0]
        target_tab = self.encoder.tabular_encoder.encode(self._build_tabular_features(listing))
        target_img = self._get_image_embedding(listing)

        comp_list = [item["comp"] for item in adjusted_comps]
        comp_texts = [
            self._build_text_for_embedding(comp, include_vlm=use_vlm) for comp in comp_list
        ]
        comp_text_embeddings = (
            self.encoder.text_encoder.encode(comp_texts) if comp_texts else np.array([])
        )
        comp_tab_features = [self._build_tabular_features(comp) for comp in comp_list]
        comp_tab_embeddings = (
            self.encoder.tabular_encoder.encode_batch(comp_tab_features) if comp_tab_features else np.array([])
        )
        comp_img_list = [self._get_image_embedding(comp) for comp in comp_list]
        comp_prices_list = [item["adj_price"] for item in adjusted_comps]

        comp_text_list = [comp_text_embeddings[i] for i in range(len(comp_list))]
        comp_tab_list = [comp_tab_embeddings[i] for i in range(len(comp_list))]

        use_residual = self.fusion.config.get("target_mode") == "log_residual"
        fusion_out = None
        model_used = "fusion"
        try:
            if use_residual:
                baseline_weights = [similarity_by_id.get(item["comp"].id, 1.0) for item in adjusted_comps]
                baseline = self._robust_comp_baseline(comp_prices_list, baseline_weights)
                baseline_log = float(np.log(baseline))

                fusion_out = self.fusion.predict(
                    target_text_embedding=target_text_emb,
                    target_tabular_features=target_tab,
                    target_image_embedding=target_img,
                    comp_text_embeddings=comp_text_list,
                    comp_tabular_features=comp_tab_list,
                    comp_image_embeddings=comp_img_list,
                    comp_prices=comp_prices_list,
                    output_mode="residual"
                )

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
                    target_text_embedding=target_text_emb,
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
        except Exception as exc:
            logger.warning("fusion_predict_failed", error=str(exc), listing_id=listing.id)
            baseline_weights = [similarity_by_id.get(item["comp"].id, 1.0) for item in adjusted_comps]
            baseline = self._robust_comp_baseline(comp_prices_list, baseline_weights)
            std = float(np.std(comp_prices_list)) if comp_prices_list else 0.0
            if std <= 0:
                std = max(baseline * 0.05, 1.0)
            q50 = float(baseline)
            q10 = max(q50 - 1.2816 * std, q50 * 0.5)
            q90 = q50 + 1.2816 * std
            anchor_price = q50
            anchor_std = std
            model_used = "comp_baseline"
        if q50 <= 0 or q10 <= 0 or q90 <= 0 or not (q10 <= q50 <= q90):
            baseline_weights = [similarity_by_id.get(item["comp"].id, 1.0) for item in adjusted_comps]
            baseline = self._robust_comp_baseline(comp_prices_list, baseline_weights)
            std = float(np.std(comp_prices_list)) if comp_prices_list else 0.0
            if std <= 0:
                std = max(baseline * 0.05, 1.0)
            q50 = float(baseline)
            q10 = max(q50 - 1.2816 * std, q50 * 0.5)
            q90 = q50 + 1.2816 * std
            anchor_price = q50
            anchor_std = std
            model_used = "comp_baseline"

        attn_weights = (
            fusion_out.attention_weights.flatten()
            if fusion_out is not None and fusion_out.attention_weights is not None
            else None
        )
        if attn_weights is not None and len(attn_weights) >= len(comp_evidence):
            for i, ce in enumerate(comp_evidence):
                ce.attention_weight = float(attn_weights[i])
        else:
            weights = []
            for ce in comp_evidence:
                weight = similarity_by_id.get(ce.id, 1.0)
                weights.append(float(weight) if weight is not None else 1.0)
            total = sum(weights)
            if total <= 0:
                weights = [1.0 for _ in weights]
                total = float(len(weights)) if weights else 1.0
            for ce, weight in zip(comp_evidence, weights):
                ce.attention_weight = float(weight) / total

        comp_evidence.sort(key=lambda ce: ce.attention_weight, reverse=True)

        uncertainty = (q90 - q10) / (2 * q50)

        # Comp date range
        comp_months = [ce.observed_month for ce in comp_evidence]
        comp_date_range = f"{min(comp_months)} to {max(comp_months)}" if comp_months else None

        evidence = EvidencePack(
            model_used=model_used,
            anchor_price=anchor_price,
            anchor_std=anchor_std,
            top_comps=comp_evidence,
            hedonic_fallback=hedonic_fallback,
            hedonic_fallback_reason=", ".join(sorted(fallback_reasons)) if hedonic_fallback else None,
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
        text = self._build_text_for_embedding(listing, include_vlm=include_vlm)
        text_emb = self.encoder.text_encoder.encode_single(text)
        tab_vec = self.encoder.tabular_encoder.encode(self._build_tabular_features(listing))
        img_emb = self._get_image_embedding(listing)
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
        bucket_key: str,
        country_code: Optional[str] = None,
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
            country_code=country_code,
            horizons_months=self.config.horizons_months,
        )

        # Apply conformal calibration per horizon
        for proj in raw_projections:
            horizon = proj.months_future

            cal_q10, cal_q50, cal_q90, calibration_decision, _ = self._apply_interval_policy(
                bucket_key=bucket_key,
                pred_q10=proj.confidence_interval_low,
                pred_q50=proj.predicted_value,
                pred_q90=proj.confidence_interval_high,
                horizon_months=horizon,
            )

            proj.confidence_interval_low = cal_q10
            proj.predicted_value = cal_q50
            proj.confidence_interval_high = cal_q90
            if cal_q50 > 0:
                spread = (cal_q90 - cal_q10) / cal_q50
                proj.confidence_score = max(0.1, 1.0 - spread)
            proj.scenario_name = f"{proj.scenario_name}_{calibration_decision['mode']}"

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

    @staticmethod
    def _select_projection(
        projections: List[ValuationProjection],
        target_months: int,
    ) -> Optional[ValuationProjection]:
        if not projections:
            return None
        exact = [p for p in projections if getattr(p, "months_future", None) == target_months]
        if exact:
            return exact[0]
        return min(
            projections,
            key=lambda p: abs(getattr(p, "months_future", target_months) - target_months),
        )

    def _build_pricing_signals(
        self,
        *,
        listing: CanonicalListing,
        fair_value: float,
        rent_est: float,
        rental_yield: Optional[float],
        market_signals: Dict[str, float],
        projections: List[ValuationProjection],
        rent_projections: List[ValuationProjection],
        yield_projections: List[ValuationProjection],
    ) -> Dict[str, float]:
        signals: Dict[str, float] = {}

        price_basis = listing.price if listing.price and listing.price > 0 else fair_value
        annual_rent = rent_est * 12 if rent_est and rent_est > 0 else None
        if annual_rent:
            signals["price_to_rent_years"] = float(price_basis / annual_rent)
            if fair_value > 0:
                signals["value_to_rent_years"] = float(fair_value / annual_rent)

        market_yield = market_signals.get("market_yield")
        if market_yield and market_yield > 0:
            signals["market_price_to_rent_years"] = float(100.0 / market_yield)
            if rental_yield is not None:
                signals["yield_spread_pp"] = float(rental_yield - market_yield)
            if signals.get("price_to_rent_years"):
                signals["price_to_rent_gap_years"] = float(
                    signals["price_to_rent_years"] - signals["market_price_to_rent_years"]
                )

        proj_12m = self._select_projection(projections, 12)
        rent_proj_12m = self._select_projection(rent_projections, 12)
        yield_proj_12m = self._select_projection(yield_projections, 12)

        if proj_12m and proj_12m.predicted_value > 0:
            projected_value = float(proj_12m.predicted_value)
            signals["projected_value_12m"] = projected_value
            if price_basis > 0:
                signals["price_return_12m_pct"] = float(
                    (projected_value - price_basis) / price_basis * 100
                )
            if fair_value > 0:
                signals["fair_value_return_12m_pct"] = float(
                    (projected_value - fair_value) / fair_value * 100
                )

        if rent_proj_12m and rent_proj_12m.predicted_value > 0:
            signals["projected_rent_12m"] = float(rent_proj_12m.predicted_value)

        if yield_proj_12m and yield_proj_12m.predicted_value > 0:
            signals["projected_yield_12m_pct"] = float(yield_proj_12m.predicted_value)

        base_yield = signals.get("projected_yield_12m_pct")
        if base_yield is None and rental_yield is not None:
            base_yield = float(rental_yield)
        if "price_return_12m_pct" in signals and base_yield is not None:
            signals["total_return_12m_pct"] = float(signals["price_return_12m_pct"] + base_yield)

        return signals

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

                comp_coverage = min(
                    1.0,
                    len(rent_comps) / max(1, self.config.min_rent_comps),
                )
                rent_unc = max(0.0, float(rent_uncertainty))
                rent_variance = rent_unc * rent_unc
                variance_factor = 1.0 / (1.0 + rent_variance * 4.0)
                income_weight = self.config.income_value_weight_max * comp_coverage * variance_factor
                if income_weight < self.config.income_value_weight_min:
                    income_weight = 0.0

                if income_weight > 0:
                    adjusted_value = adjusted_value * (1 - income_weight) + income_value * income_weight
                    adjusted_uncertainty = adjusted_uncertainty * (
                        1 + income_weight * min(rent_unc, 0.5)
                    )

                adjustments.update({
                    "income_value": float(income_value),
                    "income_weight": float(income_weight),
                    "rent_uncertainty": float(rent_unc),
                    "rent_comp_coverage": float(comp_coverage),
                    "rent_comp_variance": float(rent_variance),
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

        if not listing.price or listing.price <= 0:
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

    def _fallback_rent_estimate(
        self,
        listing: CanonicalListing,
        fair_value: float,
        reason: str,
        region_id: str,
        valuation_date: datetime,
        tracer: Any = None,
    ) -> Tuple[float, float, List[CanonicalListing], Dict[str, Any]]:
        fallback_rent = None
        fallback_source = None
        fallback_circular = False
        fallback_uncertainty = float(self.config.rent_fallback_uncertainty)
        if listing.surface_area_sqm and listing.surface_area_sqm > 0:
            try:
                rent_index = self._get_market_index_value(
                    region_id,
                    valuation_date.strftime("%Y-%m"),
                    "rent_index_sqm",
                )
            except ValueError:
                rent_index = None
            if rent_index and rent_index > 0:
                fallback_rent = rent_index * listing.surface_area_sqm
                fallback_source = "rent_index"

        if not fallback_rent or fallback_rent <= 0:
            fallback_rent = getattr(listing, "estimated_rent", None)
            if fallback_rent and fallback_rent > 0:
                fallback_source = "estimated_rent"

        if not fallback_rent or fallback_rent <= 0:
            gross_yield = getattr(listing, "gross_yield", None)
            price_basis = listing.price if listing.price and listing.price > 0 else fair_value
            if gross_yield and gross_yield > 0 and price_basis > 0:
                fallback_rent = price_basis * (gross_yield / 100.0) / 12.0
                fallback_source = "gross_yield"
                fallback_circular = True

        if not fallback_rent or fallback_rent <= 0:
            price_basis = listing.price if listing.price and listing.price > 0 else fair_value
            yield_stats = self._get_yield_distribution(region_id, valuation_date)
            local_yield = yield_stats.get("yield_p50")
            if local_yield and local_yield > 0 and price_basis > 0:
                fallback_rent = price_basis * (local_yield / 100.0) / 12.0
                fallback_source = "local_yield_distribution"
                fallback_circular = True
                yield_std = yield_stats.get("yield_std")
                if yield_std and local_yield > 0:
                    fallback_uncertainty = max(fallback_uncertainty, float(yield_std) / float(local_yield))
            else:
                fallback_rent = price_basis * (self.config.fallback_yield_pct / 100.0) / 12.0
                fallback_source = "default_yield"
                fallback_circular = True

        if tracer:
            tracer.log("rental_fallback", {
                "rent_est": float(fallback_rent),
                "reason": reason,
                "source": fallback_source,
                "source_circular": fallback_circular,
            })

        meta = {
            "rent_source": fallback_source or "unknown",
            "rent_source_circular": fallback_circular,
        }
        return float(fallback_rent), fallback_uncertainty, [], meta

    def _fallback_market_signals(
        self,
        rental_yield: float,
        reason: str,
        region_id: Optional[str] = None,
        valuation_date: Optional[datetime] = None,
    ) -> Dict[str, float]:
        yield_stats: Dict[str, float] = {}
        if region_id and valuation_date:
            yield_stats = self._get_yield_distribution(region_id, valuation_date)
        market_yield = yield_stats.get("yield_p50")
        if not market_yield or market_yield <= 0:
            market_yield = float(rental_yield) if rental_yield and rental_yield > 0 else float(self.config.fallback_yield_pct)
        logger.warning("market_signals_fallback", reason=reason)
        signals = {
            "momentum": 0.0,
            "liquidity": 0.5,
            "catchup": 0.0,
            "market_yield": market_yield,
            "area_sentiment": 0.5,
            "area_development": 0.5,
            "area_confidence": 0.0,
        }
        if yield_stats:
            if yield_stats.get("yield_p10") is not None:
                signals["market_yield_p10"] = float(yield_stats["yield_p10"])
            if yield_stats.get("yield_p90") is not None:
                signals["market_yield_p90"] = float(yield_stats["yield_p90"])
            if yield_stats.get("yield_std") is not None:
                signals["market_yield_std"] = float(yield_stats["yield_std"])
            if yield_stats.get("yield_samples") is not None:
                signals["market_yield_samples"] = float(yield_stats["yield_samples"])
        return signals
    
    def _get_region_id(self, listing: CanonicalListing) -> str:
        """Extract region identifier for index lookups with resilient fallbacks."""
        city = None
        if listing.location and listing.location.city:
            city = self._normalize_region_text(listing.location.city)
        if city:
            return city

        resolved = self._resolve_region_from_storage(listing)
        if resolved:
            return resolved

        logger.warning("region_id_fallback_all", listing_id=getattr(listing, "id", None))
        return "all"

    @staticmethod
    def _normalize_region_text(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().lower()
        if not text:
            return None
        text = re.sub(r"\s+", " ", text)
        if text in {"unknown", "n/a", "none", "null", "nan"}:
            return None
        return text

    def _resolve_region_from_storage(self, listing: CanonicalListing) -> Optional[str]:
        listing_id = getattr(listing, "id", None)
        stored = self._fetch_listing_location(listing_id) if listing_id else {}

        city = self._normalize_region_text(stored.get("city"))
        if city:
            return city

        zip_code = stored.get("zip_code")
        if not zip_code and listing.location:
            zip_code = getattr(listing.location, "zip_code", None)
        if zip_code:
            city = self._lookup_city_by_zip(zip_code)
            if city:
                return city

        geohash = stored.get("geohash")
        lat = stored.get("lat")
        lon = stored.get("lon")
        if (lat is None or lon is None) and listing.location:
            lat = getattr(listing.location, "lat", None)
            lon = getattr(listing.location, "lon", None)
        if not geohash and lat is not None and lon is not None:
            try:
                geohash = geolib.geohash.encode(lat, lon, 6)
            except Exception:
                geohash = None
        if geohash:
            city = self._lookup_city_by_geohash(geohash)
            if city:
                return city

        if lat is not None and lon is not None:
            city = self._lookup_city_by_latlon(lat, lon)
            if city:
                return city

        return None

    def _resolve_geohash_prefix(self, listing: CanonicalListing, precision: int = 6) -> Optional[str]:
        geohash = None
        listing_id = getattr(listing, "id", None)
        stored = self._fetch_listing_location(listing_id) if listing_id else {}
        if stored.get("geohash"):
            geohash = stored.get("geohash")
        if not geohash and stored.get("lat") is not None and stored.get("lon") is not None:
            try:
                geohash = geolib.geohash.encode(stored["lat"], stored["lon"], precision)
            except Exception:
                geohash = None
        if not geohash and listing.location:
            lat = getattr(listing.location, "lat", None)
            lon = getattr(listing.location, "lon", None)
            if lat is not None and lon is not None:
                try:
                    geohash = geolib.geohash.encode(lat, lon, precision)
                except Exception:
                    geohash = None
        if not geohash:
            return None
        text = str(geohash).strip().lower()
        if not text:
            return None
        return text[:precision]

    def _get_geohash_area_data(self, listing: CanonicalListing) -> Optional[Dict[str, Any]]:
        geohash = self._resolve_geohash_prefix(listing)
        if not geohash:
            return None
        area_id = f"geo:{geohash}"
        area_data = self.area_intel.get_area_indicators(
            area_id,
            country_code=listing.location.country if listing.location else None,
        )
        sources = area_data.get("source_urls") or []
        if "internal:listings" not in sources:
            return None
        return area_data

    def _fetch_listing_location(self, listing_id: str) -> Dict[str, Optional[object]]:
        query = text(
            """
            SELECT city, zip_code, geohash, lat, lon
            FROM listings
            WHERE id = :listing_id
            LIMIT 1
            """
        )
        try:
            with self.storage.engine.connect() as conn:
                row = conn.execute(query, {"listing_id": listing_id}).fetchone()
            if not row:
                return {}
            return {
                "city": row[0],
                "zip_code": row[1],
                "geohash": row[2],
                "lat": row[3],
                "lon": row[4],
            }
        except Exception:
            return {}

    def _lookup_city_by_zip(self, zip_code: str) -> Optional[str]:
        zip_norm = str(zip_code).strip().lower()
        if not zip_norm:
            return None
        query = text(
            """
            SELECT city
            FROM listings
            WHERE LOWER(zip_code) = :zip
              AND city IS NOT NULL
              AND city != ''
            LIMIT 1
            """
        )
        try:
            with self.storage.engine.connect() as conn:
                row = conn.execute(query, {"zip": zip_norm}).fetchone()
            return self._normalize_region_text(row[0]) if row else None
        except Exception:
            return None

    def _lookup_city_by_geohash(self, geohash: str) -> Optional[str]:
        geohash = str(geohash).strip().lower()
        if not geohash:
            return None
        prefixes = [geohash[:6], geohash[:5], geohash[:4]]
        query = text(
            """
            SELECT city
            FROM listings
            WHERE geohash LIKE :prefix
              AND city IS NOT NULL
              AND city != ''
            LIMIT 1
            """
        )
        for prefix in prefixes:
            if len(prefix) < 4:
                continue
            try:
                with self.storage.engine.connect() as conn:
                    row = conn.execute(query, {"prefix": f"{prefix}%"}).fetchone()
                if row and row[0]:
                    city = self._normalize_region_text(row[0])
                    if city:
                        return city
            except Exception:
                return None
        return None

    def _lookup_city_by_latlon(self, lat: float, lon: float) -> Optional[str]:
        deltas = [0.01, 0.03, 0.08]
        query = text(
            """
            SELECT city
            FROM listings
            WHERE lat BETWEEN :min_lat AND :max_lat
              AND lon BETWEEN :min_lon AND :max_lon
              AND city IS NOT NULL
              AND city != ''
            LIMIT 1
            """
        )
        for delta in deltas:
            try:
                with self.storage.engine.connect() as conn:
                    row = conn.execute(
                        query,
                        {
                            "min_lat": lat - delta,
                            "max_lat": lat + delta,
                            "min_lon": lon - delta,
                            "max_lon": lon + delta,
                        },
                    ).fetchone()
                if row and row[0]:
                    city = self._normalize_region_text(row[0])
                    if city:
                        return city
            except Exception:
                return None
        return None

    def _resolve_comp_price(self, comp: CanonicalListing) -> Optional[float]:
        if comp.listing_type == "sale":
            sold_price = getattr(comp, "sold_price", None)
            if sold_price is not None and sold_price > 0:
                return float(sold_price)
        if comp.price is None:
            return None
        try:
            return float(comp.price)
        except (TypeError, ValueError):
            return None

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
            if region_id != "all":
                with self.storage.engine.connect() as conn:
                    fallback = conn.execute(
                        query,
                        {"region_id": "all", "month_key": f"{month_key}%"}
                    ).fetchone()
                if fallback and fallback[0] is not None:
                    return float(fallback[0])
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
        valuation_date: datetime,
        country_code: Optional[str],
    ) -> Tuple[bool, Dict[str, float], Dict[str, Any]]:
        eri_signals = self.eri.get_signals(
            region_id,
            valuation_date,
            country_code=country_code,
        )
        if not eri_signals:
            return False, {}, {}

        if eri_signals.get("proxy_used"):
            return False, {"eri_proxy_used": True}, eri_signals

        effective_date = valuation_date
        effective_str = eri_signals.get("effective_date")
        if effective_str:
            try:
                effective_date = datetime.fromisoformat(str(effective_str))
            except ValueError:
                effective_date = valuation_date

        eri_yoy = eri_signals.get("registral_price_sqm_change")
        hedonic_yoy = self._get_index_yoy("hedonic_indices", "hedonic_index_sqm", region_id, effective_date)
        market_yoy = self._get_index_yoy("market_indices", "price_index_sqm", region_id, effective_date)

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

    def _get_yield_distribution(
        self,
        region_id: str,
        valuation_date: datetime,
        *,
        window_months: int = 24,
        min_samples: int = 6,
    ) -> Dict[str, float]:
        if not region_id:
            return {}

        end_key = valuation_date.strftime("%Y-%m")
        start_date = valuation_date - timedelta(days=window_months * 31)
        start_key = start_date.strftime("%Y-%m")

        def _fetch(region: str) -> List[float]:
            query = text(
                """
                SELECT price_index_sqm, rent_index_sqm
                FROM market_indices
                WHERE region_id = :region_id
                  AND substr(month_date, 1, 7) >= :start_key
                  AND substr(month_date, 1, 7) <= :end_key
                ORDER BY month_date DESC
                """
            )
            with self.storage.engine.connect() as conn:
                rows = conn.execute(
                    query,
                    {"region_id": region, "start_key": start_key, "end_key": end_key},
                ).fetchall()

            values: List[float] = []
            for row in rows:
                price_index = row[0]
                rent_index = row[1]
                if price_index is None or rent_index is None:
                    continue
                price_val = float(price_index)
                rent_val = float(rent_index)
                if price_val <= 0 or rent_val <= 0:
                    continue
                values.append((rent_val * 12 / price_val) * 100)
            return values

        values = _fetch(region_id)
        if len(values) < min_samples and region_id != "all":
            values = _fetch("all")
        if len(values) < min_samples:
            return {}

        series = np.array(values, dtype=float)
        return {
            "yield_p10": float(np.percentile(series, 10)),
            "yield_p50": float(np.percentile(series, 50)),
            "yield_p90": float(np.percentile(series, 90)),
            "yield_std": float(np.std(series)),
            "yield_samples": float(len(series)),
        }

    def _get_market_signals(
        self,
        listing: CanonicalListing,
        region_id: str,
        valuation_date: datetime
    ) -> Dict[str, float]:
        """Get current market signals (strict)."""
        if not listing.location or not listing.location.city:
            raise ValueError("missing_location")

        profile = self.analytics.analyze_listing(listing, include_eri=False)
        if not profile:
            raise ValueError("missing_market_profile")
        if getattr(profile, "zone_id", None) == "unknown":
            raise ValueError("missing_market_profile")

        yield_stats = self._get_yield_distribution(region_id, valuation_date)
        market_yield = yield_stats.get("yield_p50")
        if not market_yield:
            market_yield = self._get_market_yield(region_id, valuation_date)
        area_data = self.area_intel.get_area_indicators(
            region_id,
            country_code=listing.location.country if listing.location else None,
        )
        area_sentiment = float(area_data.get("sentiment_score", 0.5))
        area_development = float(area_data.get("future_development_score", 0.5))
        area_confidence = area_data.get("area_confidence")

        geo_data = self._get_geohash_area_data(listing)
        geo_confidence = None
        if geo_data:
            geo_sentiment = float(geo_data.get("sentiment_score", area_sentiment))
            geo_confidence = geo_data.get("area_confidence")
            geo_weight = 0.0
            if geo_confidence is not None:
                geo_weight = min(0.35, 0.35 * float(geo_confidence))
            if geo_weight > 0:
                area_sentiment = (area_sentiment * (1 - geo_weight)) + (geo_sentiment * geo_weight)
            if geo_confidence is not None:
                if area_confidence is None:
                    area_confidence = float(geo_confidence)
                else:
                    area_confidence = max(float(area_confidence), float(geo_confidence))

        signals = {
            "momentum": profile.momentum_score,
            "liquidity": profile.liquidity_score,
            "catchup": profile.catchup_potential,
            "market_yield": market_yield,
            "area_sentiment": float(area_sentiment),
            "area_development": float(area_development),
        }
        if yield_stats:
            if yield_stats.get("yield_p10") is not None:
                signals["market_yield_p10"] = float(yield_stats["yield_p10"])
            if yield_stats.get("yield_p90") is not None:
                signals["market_yield_p90"] = float(yield_stats["yield_p90"])
            if yield_stats.get("yield_std") is not None:
                signals["market_yield_std"] = float(yield_stats["yield_std"])
            if yield_stats.get("yield_samples") is not None:
                signals["market_yield_samples"] = float(yield_stats["yield_samples"])
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
        if geo_data:
            signals["geo_area_sentiment"] = float(geo_data.get("sentiment_score", area_sentiment))
            if geo_confidence is not None:
                signals["geo_area_confidence"] = float(geo_confidence)
            geo_sent_cred = geo_data.get("sentiment_credibility")
            if geo_sent_cred is not None:
                signals["geo_area_sentiment_credibility"] = float(geo_sent_cred)
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
        price_basis = listing.price
        missing_price = False
        if not price_basis or price_basis <= 0:
            price_basis = fair_value
            missing_price = True
        value_gap_pct = (fair_value - price_basis) / price_basis * 100 if price_basis > 0 else 0.0
        market_yield = market_signals.get("market_yield")
        momentum = market_signals.get("momentum")
        liquidity = market_signals.get("liquidity")

        if missing_price:
            thesis = (
                f"Fair value €{fair_value:,.0f} (±{uncertainty:.0%}) from comp-fusion; "
                "ask unavailable. "
            )
        else:
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

        price_to_rent = market_signals.get("price_to_rent_years")
        market_pr = market_signals.get("market_price_to_rent_years")
        if price_to_rent is not None and market_pr is not None:
            thesis += f"Price-to-rent {price_to_rent:.1f}y vs market {market_pr:.1f}y. "
        elif price_to_rent is not None:
            thesis += f"Price-to-rent {price_to_rent:.1f}y. "

        total_return_12m = market_signals.get("total_return_12m_pct")
        if total_return_12m is not None:
            thesis += f"12m total return {total_return_12m:+.1f}%. "

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
    ) -> Tuple[float, float, List[CanonicalListing], Dict[str, Any]]:
        """
        Estimate rent using robust comparable rental listings.

        Returns:
            (estimated_monthly_rent, uncertainty_pct, rental_comps_used, rent_meta)
        """
        if not listing.surface_area_sqm or listing.surface_area_sqm <= 0:
            raise ValueError("missing_surface_area_for_rent")

        try:
            rental_comps, similarity_by_id = self._retrieve_rent_comps(listing, as_of_date=valuation_date)
        except ValueError as exc:
            fallback_rent = None
            fallback_source = None
            fallback_circular = False
            try:
                rent_index = self._get_market_index_value(
                    region_id,
                    valuation_date.strftime("%Y-%m"),
                    "rent_index_sqm"
                )
            except ValueError:
                rent_index = None
            if rent_index and rent_index > 0:
                fallback_rent = rent_index * listing.surface_area_sqm
                fallback_source = "rent_index"
            if not fallback_rent or fallback_rent <= 0:
                fallback_rent = getattr(listing, "estimated_rent", None)
                if fallback_rent and fallback_rent > 0:
                    fallback_source = "estimated_rent"
            if not fallback_rent or fallback_rent <= 0:
                raise
            if tracer:
                tracer.log(
                    "rental_fallback",
                    {
                        "rent_est": fallback_rent,
                        "reason": str(exc),
                        "source": fallback_source,
                        "source_circular": fallback_circular,
                    },
                )
            meta = {
                "rent_source": fallback_source or "unknown",
                "rent_source_circular": fallback_circular,
            }
            return float(fallback_rent), float(self.config.rent_fallback_uncertainty), [], meta

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

        meta = {
            "rent_source": "rent_comps",
            "rent_source_circular": False,
        }
        return est_rent, uncertainty, comps_used, meta
