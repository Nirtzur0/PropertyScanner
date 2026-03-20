from __future__ import annotations

from datetime import timedelta
from math import atan2, cos, radians, sin, sqrt
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.application.serving import MAX_PRICE, MAX_SURFACE_AREA, MIN_PRICE, MIN_SURFACE_AREA
from src.listings.source_ids import canonicalize_source_id
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.platform.domain.models import DBListing
from src.platform.domain.schema import CanonicalListing, CompEvidence, DealAnalysis, EvidencePack, ValuationProjection
from src.platform.settings import ValuationConfig
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow
from src.valuation.services.valuation_persister import ValuationPersister


def _weighted_quantile(values: Sequence[float], weights: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("weighted_quantile_empty")
    values_arr = np.asarray(values, dtype=float)
    weights_arr = np.asarray(weights, dtype=float)
    if float(weights_arr.sum()) <= 0:
        return float(np.quantile(values_arr, quantile))
    order = np.argsort(values_arr)
    values_sorted = values_arr[order]
    weights_sorted = weights_arr[order]
    cumulative = np.cumsum(weights_sorted) / np.sum(weights_sorted)
    idx = int(np.searchsorted(cumulative, quantile, side="left"))
    idx = min(max(idx, 0), len(values_sorted) - 1)
    return float(values_sorted[idx])


class ComparableBaselineValuationService:
    def __init__(self, *, storage: StorageService, config: Optional[ValuationConfig] = None) -> None:
        self.storage = storage
        self.config = config or ValuationConfig()

    @staticmethod
    def _distance_km(
        lat1: Optional[float],
        lon1: Optional[float],
        lat2: Optional[float],
        lon2: Optional[float],
    ) -> float:
        if None in (lat1, lon1, lat2, lon2):
            return 0.0
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return 6371.0 * 2 * atan2(sqrt(a), sqrt(1 - a))

    @staticmethod
    def _candidate_observed_at(row: DBListing):
        return row.listed_at or row.updated_at or row.fetched_at

    @staticmethod
    def _candidate_source_status(
        row: DBListing,
        source_status_by_source: Optional[Dict[str, str]],
    ) -> Optional[str]:
        if not source_status_by_source:
            return None
        canonical_source_id = canonicalize_source_id(str(row.source_id))
        return (
            source_status_by_source.get(canonical_source_id)
            or source_status_by_source.get(str(row.source_id))
        )

    @staticmethod
    def _candidate_source_metrics(
        row: DBListing,
        source_metrics_by_source: Optional[Dict[str, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if not source_metrics_by_source:
            return {}
        canonical_source_id = canonicalize_source_id(str(row.source_id))
        return dict(
            source_metrics_by_source.get(canonical_source_id)
            or source_metrics_by_source.get(str(row.source_id))
            or {}
        )

    @staticmethod
    def _source_metric_penalty(source_metrics: Optional[Dict[str, Any]]) -> float:
        if not source_metrics:
            return 0.0
        invalid_price_ratio = max(float(source_metrics.get("invalid_price_ratio") or 0.0), 0.0)
        invalid_surface_area_ratio = max(float(source_metrics.get("invalid_surface_area_ratio") or 0.0), 0.0)
        freshness_window_days = max(float(source_metrics.get("freshness_window_days") or 14.0), 1.0)
        coverage_floor = min(
            1.0,
            float(source_metrics.get("title_coverage_ratio") or 1.0),
            float(source_metrics.get("price_coverage_ratio") or 1.0),
            float(source_metrics.get("surface_area_coverage_ratio") or 1.0),
            float(source_metrics.get("location_coverage_ratio") or 1.0),
        )
        last_seen_age_days_raw = source_metrics.get("last_seen_age_days")
        latest_run_age_days_raw = source_metrics.get("latest_run_age_days")
        last_seen_age_days = (
            max(float(last_seen_age_days_raw), 0.0) if last_seen_age_days_raw not in (None, "") else None
        )
        latest_run_age_days = (
            max(float(latest_run_age_days_raw), 0.0) if latest_run_age_days_raw not in (None, "") else None
        )
        invalid_penalty = min((invalid_price_ratio * 0.18) + (invalid_surface_area_ratio * 0.18), 0.22)
        coverage_penalty = max(0.0, 1.0 - coverage_floor) * 0.15
        freshness_penalty = (
            min(last_seen_age_days / freshness_window_days, 1.0) * 0.03 if last_seen_age_days is not None else 0.0
        )
        contract_run_penalty = (
            min(latest_run_age_days / freshness_window_days, 1.0) * 0.02
            if latest_run_age_days is not None
            else 0.0
        )
        return min(invalid_penalty + coverage_penalty + freshness_penalty + contract_run_penalty, 0.34)

    @classmethod
    def _source_health_multiplier(
        cls,
        source_status: Optional[str],
        source_metrics: Optional[Dict[str, Any]] = None,
    ) -> float:
        if source_status == "degraded":
            base = 0.9
        elif source_status == "experimental":
            base = 0.97
        else:
            base = 1.0
        return max(0.55, min(1.0, base - cls._source_metric_penalty(source_metrics)))

    def _candidate_rows(
        self,
        target: CanonicalListing,
        k: int = 10,
        *,
        source_status_by_source: Optional[Dict[str, str]] = None,
        source_metrics_by_source: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Tuple[DBListing, float, float]]:
        if target.location is None or not target.location.city:
            raise ValueError("target_city_required")
        if not target.surface_area_sqm or target.surface_area_sqm <= 0:
            raise ValueError("target_surface_area_required")

        session = self.storage.get_session()
        try:
            query = (
                session.query(DBListing)
                .filter(DBListing.id != target.id)
                .filter(DBListing.city == target.location.city)
                .filter(DBListing.listing_type == (target.listing_type or "sale"))
                .filter(DBListing.price.isnot(None))
                .filter(DBListing.price >= MIN_PRICE)
                .filter(DBListing.price <= MAX_PRICE)
                .filter(DBListing.surface_area_sqm.isnot(None))
                .filter(DBListing.surface_area_sqm >= MIN_SURFACE_AREA)
                .filter(DBListing.surface_area_sqm <= MAX_SURFACE_AREA)
            )
            if target.property_type:
                query = query.filter(DBListing.property_type == str(getattr(target.property_type, "value", target.property_type)))
            rows = query.order_by(DBListing.updated_at.desc()).limit(250).all()
        finally:
            session.close()

        scored: List[Tuple[DBListing, float, float]] = []
        age_cutoff = utcnow() - timedelta(days=max(int(self.config.max_age_months), 0) * 30)
        for row in rows:
            source_status = self._candidate_source_status(row, source_status_by_source)
            source_metrics = self._candidate_source_metrics(row, source_metrics_by_source)
            if source_status == "blocked":
                continue
            observed_at = self._candidate_observed_at(row)
            if observed_at is not None and observed_at < age_cutoff:
                continue
            row_sqm = float(row.surface_area_sqm or 0.0)
            if row_sqm <= 0:
                continue
            ratio = row_sqm / float(target.surface_area_sqm)
            if ratio < 0.7 or ratio > 1.3:
                continue
            if target.bedrooms is not None and row.bedrooms is not None and abs(int(row.bedrooms) - int(target.bedrooms)) > 1:
                continue
            distance = self._distance_km(
                target.location.lat if target.location else None,
                target.location.lon if target.location else None,
                row.lat,
                row.lon,
            )
            similarity = 1.0 / (1.0 + abs(1.0 - ratio) + (distance / 10.0))
            similarity *= self._source_health_multiplier(source_status, source_metrics)
            implied_value = (float(row.price) / row_sqm) * float(target.surface_area_sqm)
            scored.append((row, similarity, implied_value))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def evaluate_listing(
        self,
        target: CanonicalListing,
        *,
        persist: bool = False,
        model_version: str = "baseline-comp-v1",
        source_status_by_source: Optional[Dict[str, str]] = None,
        source_metrics_by_source: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> DealAnalysis:
        candidates = self._candidate_rows(
            target,
            k=10,
            source_status_by_source=source_status_by_source,
            source_metrics_by_source=source_metrics_by_source,
        )
        if len(candidates) < 3:
            raise ValueError("insufficient_comps")

        comp_values = [value for _, _, value in candidates]
        weights = [max(similarity, 0.01) for _, similarity, _ in candidates]
        fair_value = _weighted_quantile(comp_values, weights, 0.5)
        q10 = _weighted_quantile(comp_values, weights, 0.1)
        q90 = _weighted_quantile(comp_values, weights, 0.9)
        uncertainty_pct = max((q90 - q10) / max(fair_value * 2.0, 1.0), 0.05)
        current_price = float(target.price or 0.0)
        undervaluation_pct = ((fair_value - current_price) / current_price) if current_price > 0 else 0.0
        deal_score = max(0.0, min(1.0, 0.5 + (undervaluation_pct / 0.2)))

        evidence = EvidencePack(
            model_used="heuristic",
            anchor_price=fair_value,
            anchor_std=float(np.std(comp_values)) if len(comp_values) > 1 else 0.0,
            calibration_status="uncalibrated",
            top_comps=[
                CompEvidence(
                    id=row.id,
                    url=str(row.url),
                    observed_month=(row.listed_at or row.updated_at).strftime("%Y-%m") if (row.listed_at or row.updated_at) else "unknown",
                    raw_price=float(row.price),
                    adj_factor=1.0,
                    adj_price=float(implied_value),
                    attention_weight=float(similarity),
                    is_sold=bool(row.sold_price),
                    similarity_score=float(similarity),
                )
                for row, similarity, implied_value in candidates
            ],
            valuation_date=target.updated_at.isoformat() if target.updated_at else None,
            comp_date_range=None,
            external_signals={"baseline_method": "city_geo_structure"},
        )

        projections = [
            ValuationProjection(
                metric="price",
                months_future=0,
                years_future=0.0,
                predicted_value=fair_value,
                confidence_interval_low=q10,
                confidence_interval_high=q90,
                confidence_score=max(0.05, min(0.95, 1.0 - uncertainty_pct)),
                scenario_name="baseline",
            )
        ]
        analysis = DealAnalysis(
            listing_id=target.id,
            fair_value_estimate=fair_value,
            fair_value_uncertainty_pct=uncertainty_pct,
            deal_score=deal_score,
            flags=["baseline_valuation"],
            investment_thesis=(
                f"Comparable baseline from {len(candidates)} local comps with mean implied value "
                f"{mean(comp_values):,.0f}."
            ),
            projections=projections,
            market_signals={"comp_count": float(len(candidates))},
            evidence=evidence,
        )
        if persist:
            session = self.storage.get_session()
            try:
                ValuationPersister(session).save_valuation(target.id, analysis, model_version=model_version)
            finally:
                session.close()
        return analysis

    def evaluate_listing_id(
        self,
        listing_id: str,
        *,
        persist: bool = False,
        source_status_by_source: Optional[Dict[str, str]] = None,
        source_metrics_by_source: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> DealAnalysis:
        session = self.storage.get_session()
        try:
            row = session.query(DBListing).filter(DBListing.id == listing_id).first()
            if row is None:
                raise ValueError("listing_not_found")
            target = db_listing_to_canonical(row)
        finally:
            session.close()
        return self.evaluate_listing(
            target,
            persist=persist,
            source_status_by_source=source_status_by_source,
            source_metrics_by_source=source_metrics_by_source,
        )
