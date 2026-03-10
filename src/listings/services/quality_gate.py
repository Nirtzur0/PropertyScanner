from typing import List, Optional

from src.platform.domain.schema import CanonicalListing
from src.platform.settings import QualityGateConfig


class DataQualityError(RuntimeError):
    pass


class ListingQualityGate:
    MIN_PRICE = 10_000.0
    MAX_PRICE = 50_000_000.0
    MIN_SURFACE_AREA = 10.0
    MAX_SURFACE_AREA = 1_000.0
    MIN_ROOM_COUNT = 0
    MAX_ROOM_COUNT = 20
    ALLOWED_LISTING_TYPES = {"sale", "rent"}
    ALLOWED_CURRENCIES = {"USD", "EUR", "GBP", "CZK", "PLN"}

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
        elif not (self.MIN_PRICE <= float(listing.price) <= self.MAX_PRICE):
            reasons.append("price_out_of_range")
        if listing.surface_area_sqm is None:
            reasons.append("missing_surface_area")
        elif not (self.MIN_SURFACE_AREA <= float(listing.surface_area_sqm) <= self.MAX_SURFACE_AREA):
            reasons.append("surface_area_out_of_range")
        if listing.bedrooms is not None and not (self.MIN_ROOM_COUNT <= int(listing.bedrooms) <= self.MAX_ROOM_COUNT):
            reasons.append("bedrooms_out_of_range")
        if listing.bathrooms is not None and not (self.MIN_ROOM_COUNT <= int(listing.bathrooms) <= self.MAX_ROOM_COUNT):
            reasons.append("bathrooms_out_of_range")
        listing_type = str(getattr(listing, "listing_type", "") or "").strip().lower()
        if listing_type not in self.ALLOWED_LISTING_TYPES:
            reasons.append("invalid_listing_type")
        currency_value = getattr(listing, "currency", "")
        if hasattr(currency_value, "value"):
            currency_value = currency_value.value
        currency = str(currency_value or "").strip().upper()
        if currency not in self.ALLOWED_CURRENCIES:
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
            elif not (-90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0):
                reasons.append("invalid_coordinates")
        return reasons

    def should_halt(self, *, invalid_count: int, total_count: int) -> bool:
        if total_count < self.config.min_samples:
            return False
        invalid_ratio = invalid_count / max(total_count, 1)
        return invalid_ratio > self.config.max_invalid_ratio
