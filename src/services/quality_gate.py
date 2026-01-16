from dataclasses import dataclass
from typing import List

from src.core.domain.schema import CanonicalListing


class DataQualityError(RuntimeError):
    pass


@dataclass
class QualityGateConfig:
    max_invalid_ratio: float = 0.1
    min_samples: int = 20


class ListingQualityGate:
    def __init__(self, config: QualityGateConfig) -> None:
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
