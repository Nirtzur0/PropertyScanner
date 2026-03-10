from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.platform.domain.models import DBListing


MIN_PRICE = 10_000.0
MAX_PRICE = 50_000_000.0
MIN_SURFACE_AREA = 10.0
MAX_SURFACE_AREA = 1_000.0
MIN_ROOM_COUNT = 0
MAX_ROOM_COUNT = 20


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


def _is_valid_coordinate_pair(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    return -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0


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
    if not (MIN_PRICE <= float(row.price) <= MAX_PRICE):
        return ServingEligibility(
            eligible=False,
            reason="Listing price falls outside the serving range.",
            field_name="price",
            code="price_out_of_range",
        )
    if row.surface_area_sqm is not None and not (MIN_SURFACE_AREA <= float(row.surface_area_sqm) <= MAX_SURFACE_AREA):
        return ServingEligibility(
            eligible=False,
            reason="Surface area falls outside the serving range.",
            field_name="surface_area_sqm",
            code="surface_area_out_of_range",
        )
    if row.bedrooms is not None and not (MIN_ROOM_COUNT <= int(row.bedrooms) <= MAX_ROOM_COUNT):
        return ServingEligibility(
            eligible=False,
            reason="Bedroom count falls outside the serving range.",
            field_name="bedrooms",
            code="bedrooms_out_of_range",
        )
    if row.bathrooms is not None and not (MIN_ROOM_COUNT <= int(row.bathrooms) <= MAX_ROOM_COUNT):
        return ServingEligibility(
            eligible=False,
            reason="Bathroom count falls outside the serving range.",
            field_name="bathrooms",
            code="bathrooms_out_of_range",
        )
    if not _is_valid_coordinate_pair(row.lat, row.lon):
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
    if not _is_valid_coordinate_pair(row.lat, row.lon):
        return ValuationReadiness(ready=False, reason="target_coordinates_required")
    return ValuationReadiness(ready=True)
