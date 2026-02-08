from typing import List, Optional

from src.platform.domain.schema import CanonicalListing
from src.platform.settings import QualityGateConfig


class DataQualityError(RuntimeError):
    pass


class ListingQualityGate:
    def __init__(self, config: Optional[QualityGateConfig] = None) -> None:
        if config is None:
            config = QualityGateConfig()
        self.config = config

    def validate_listing(self, listing: CanonicalListing) -> List[str]:
        reasons: List[str] = []
        if not listing.title:
            reasons.append("missing_title")
        if not listing.price or listing.price <= 0:
            reasons.append("invalid_price")
        # Some portals often omit floor area; if we have bedrooms we can still persist
        # and let downstream models filter or enrich later.
        if not listing.surface_area_sqm or listing.surface_area_sqm <= 0:
            if listing.bedrooms is None:
                reasons.append("invalid_surface_area")
        return reasons

    def should_halt(self, *, invalid_count: int, total_count: int) -> bool:
        if total_count < self.config.min_samples:
            return False
        invalid_ratio = invalid_count / max(total_count, 1)
        return invalid_ratio > self.config.max_invalid_ratio
