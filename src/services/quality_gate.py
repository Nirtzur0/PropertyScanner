from typing import List, Optional

from src.core.domain.schema import CanonicalListing
from src.core.settings import QualityGateConfig
from src.utils.config import load_app_config


class DataQualityError(RuntimeError):
    pass


class ListingQualityGate:
    def __init__(self, config: Optional[QualityGateConfig] = None) -> None:
        if config is None:
            try:
                config = load_app_config().quality_gate
            except Exception:
                config = QualityGateConfig()
        self.config = config

    def validate_listing(self, listing: CanonicalListing) -> List[str]:
        reasons: List[str] = []
        if not listing.title:
            reasons.append("missing_title")
        if not listing.price or listing.price <= 0:
            reasons.append("invalid_price")
        if not listing.surface_area_sqm or listing.surface_area_sqm <= 0:
            reasons.append("invalid_surface_area")
        return reasons

    def should_halt(self, *, invalid_count: int, total_count: int) -> bool:
        if total_count < self.config.min_samples:
            return False
        invalid_ratio = invalid_count / max(total_count, 1)
        return invalid_ratio > self.config.max_invalid_ratio
