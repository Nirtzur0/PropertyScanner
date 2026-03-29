from typing import List, Optional

from src.platform.domain.constraints import DOMAIN
from src.platform.domain.schema import CanonicalListing
from src.platform.settings import QualityGateConfig


class DataQualityError(RuntimeError):
    pass


class ListingQualityGate:
    # Backward-compatible class-level aliases (tests may reference these).
    MIN_PRICE = DOMAIN.min_price
    MAX_PRICE = DOMAIN.max_price
    MIN_SURFACE_AREA = DOMAIN.min_surface_area
    MAX_SURFACE_AREA = DOMAIN.max_surface_area
    MIN_ROOM_COUNT = DOMAIN.min_room_count
    MAX_ROOM_COUNT = DOMAIN.max_room_count
    ALLOWED_LISTING_TYPES = set(DOMAIN.allowed_listing_types)
    ALLOWED_CURRENCIES = set(DOMAIN.allowed_currencies)

    def __init__(self, config: Optional[QualityGateConfig] = None) -> None:
        if config is None:
            config = QualityGateConfig()
        self.config = config

    def validate_listing(self, listing: CanonicalListing) -> List[str]:
        reasons: List[str] = []
        if not listing.source_id:
            reasons.append("missing_source_id")
        if not listing.external_id:
            reasons.append("missing_external_id")
        if not listing.url:
            reasons.append("missing_url")
        if not listing.title:
            reasons.append("missing_title")
        if not listing.price:
            reasons.append("invalid_price")
        elif not DOMAIN.price_in_range(float(listing.price)):
            reasons.append("price_out_of_range")
        if listing.surface_area_sqm is None:
            reasons.append("missing_surface_area")
        elif not DOMAIN.surface_area_in_range(float(listing.surface_area_sqm)):
            reasons.append("surface_area_out_of_range")
        if listing.bedrooms is not None and not DOMAIN.room_count_in_range(round(float(listing.bedrooms))):
            reasons.append("bedrooms_out_of_range")
        if listing.bathrooms is not None and not DOMAIN.room_count_in_range(round(float(listing.bathrooms))):
            reasons.append("bathrooms_out_of_range")
        listing_type = str(getattr(listing, "listing_type", "") or "").strip().lower()
        if listing_type not in DOMAIN.allowed_listing_types:
            reasons.append("invalid_listing_type")
        currency_value = getattr(listing, "currency", "")
        if hasattr(currency_value, "value"):
            currency_value = currency_value.value
        currency = str(currency_value or "").strip().upper()
        if currency not in DOMAIN.allowed_currencies:
            reasons.append("invalid_currency")
        if listing.location is None:
            reasons.append("missing_location")
        else:
            if not listing.location.city:
                reasons.append("missing_city")
            if not listing.location.country:
                reasons.append("missing_country")
            lat = listing.location.lat
            lon = listing.location.lon
            if lat is None or lon is None:
                reasons.append("missing_coordinates")
            elif not DOMAIN.valid_coordinates(lat, lon):
                reasons.append("invalid_coordinates")
        return reasons

    def should_halt(self, *, invalid_count: int, total_count: int) -> bool:
        if total_count < self.config.min_samples:
            return False
        invalid_ratio = invalid_count / max(total_count, 1)
        return invalid_ratio > self.config.max_invalid_ratio
