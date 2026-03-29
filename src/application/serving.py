from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.platform.domain.constraints import DOMAIN
from src.platform.domain.models import DBListing

# Backward-compatible aliases so existing imports (tests, valuation module) keep working.
MIN_PRICE = DOMAIN.min_price
MAX_PRICE = DOMAIN.max_price
MIN_SURFACE_AREA = DOMAIN.min_surface_area
MAX_SURFACE_AREA = DOMAIN.max_surface_area
MIN_ROOM_COUNT = DOMAIN.min_room_count
MAX_ROOM_COUNT = DOMAIN.max_room_count


@dataclass(frozen=True)
class ServingEligibility:
    eligible: bool
    reason: Optional[str] = None
    field_name: Optional[str] = None
    code: Optional[str] = None


@dataclass(frozen=True)
class ValuationReadiness:
    ready: bool
    reason: Optional[str] = None


def evaluate_serving_eligibility(row: DBListing, *, source_status: str) -> ServingEligibility:
    if source_status == "blocked":
        return ServingEligibility(
            eligible=False,
            reason="Blocked source listings are hidden from serving surfaces.",
            field_name="source_status",
            code="blocked_source",
        )
    if row.price is None:
        return ServingEligibility(
            eligible=False,
            reason="Listing price is missing.",
            field_name="price",
            code="price_missing",
        )
    if not DOMAIN.price_in_range(float(row.price)):
        return ServingEligibility(
            eligible=False,
            reason="Listing price falls outside the serving range.",
            field_name="price",
            code="price_out_of_range",
        )
    if row.surface_area_sqm is not None and not DOMAIN.surface_area_in_range(float(row.surface_area_sqm)):
        return ServingEligibility(
            eligible=False,
            reason="Surface area falls outside the serving range.",
            field_name="surface_area_sqm",
            code="surface_area_out_of_range",
        )
    if row.bedrooms is not None and not DOMAIN.room_count_in_range(round(float(row.bedrooms))):
        return ServingEligibility(
            eligible=False,
            reason="Bedroom count falls outside the serving range.",
            field_name="bedrooms",
            code="bedrooms_out_of_range",
        )
    if row.bathrooms is not None and not DOMAIN.room_count_in_range(round(float(row.bathrooms))):
        return ServingEligibility(
            eligible=False,
            reason="Bathroom count falls outside the serving range.",
            field_name="bathrooms",
            code="bathrooms_out_of_range",
        )
    if not DOMAIN.valid_coordinates(row.lat, row.lon):
        return ServingEligibility(
            eligible=False,
            reason="Listing coordinates are missing or invalid.",
            field_name="coordinates",
            code="invalid_coordinates",
        )
    return ServingEligibility(eligible=True)


def evaluate_valuation_readiness(row: DBListing) -> ValuationReadiness:
    if row.price is None or float(row.price) <= 0:
        return ValuationReadiness(ready=False, reason="target_price_required")
    if row.surface_area_sqm is None or float(row.surface_area_sqm) <= 0:
        return ValuationReadiness(ready=False, reason="target_surface_area_required")
    if not row.city or not str(row.city).strip():
        return ValuationReadiness(ready=False, reason="target_city_required")
    if not DOMAIN.valid_coordinates(row.lat, row.lon):
        return ValuationReadiness(ready=False, reason="target_coordinates_required")
    return ValuationReadiness(ready=True)
