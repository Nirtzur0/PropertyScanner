"""
Domain constraints — single source of truth for validation boundaries.

Used by quality gate, serving eligibility, valuation candidate filters,
and any other module that needs to know the valid range for a field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class _DomainConstraints:
    """Immutable value object holding all validation boundaries."""

    # Price (EUR equivalent)
    min_price: float = 10_000.0
    max_price: float = 50_000_000.0

    # Surface area (sqm)
    min_surface_area: float = 10.0
    max_surface_area: float = 5_000.0

    # Room counts
    min_room_count: int = 0
    max_room_count: int = 20

    # Allowed enumerations
    allowed_listing_types: FrozenSet[str] = frozenset({"sale", "rent"})
    allowed_currencies: FrozenSet[str] = frozenset({"USD", "EUR", "GBP", "CZK", "PLN"})

    # Coordinate bounds
    min_lat: float = -90.0
    max_lat: float = 90.0
    min_lon: float = -180.0
    max_lon: float = 180.0

    def price_in_range(self, price: float) -> bool:
        return self.min_price <= price <= self.max_price

    def surface_area_in_range(self, area: float) -> bool:
        return self.min_surface_area <= area <= self.max_surface_area

    def room_count_in_range(self, count: int) -> bool:
        return self.min_room_count <= count <= self.max_room_count

    def valid_coordinates(self, lat: float | None, lon: float | None) -> bool:
        if lat is None or lon is None:
            return False
        return self.min_lat <= float(lat) <= self.max_lat and self.min_lon <= float(lon) <= self.max_lon


# Module-level singleton — import this, not the class.
DOMAIN = _DomainConstraints()
