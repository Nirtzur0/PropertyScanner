from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from src.platform.domain.schema import CanonicalListing, GeoLocation, RawListing


def make_raw_listing(
    *,
    source_id: str,
    external_id: str,
    url: str,
    html_snippet: str,
    fetched_at: Any,
    extra_raw: Optional[Dict[str, Any]] = None,
) -> RawListing:
    raw_data = {"html_snippet": html_snippet, "is_detail_page": True}
    if extra_raw:
        raw_data.update(extra_raw)
    return RawListing(
        source_id=source_id,
        external_id=external_id,
        url=url,
        raw_data=raw_data,
        fetched_at=fetched_at,
    )


def make_geo(
    *,
    city: str = "madrid",
    country: str = "ES",
    address_full: str = "Test Address",
    lat: float = 40.4168,
    lon: float = -3.7038,
) -> GeoLocation:
    return GeoLocation(
        city=city,
        country=country,
        address_full=address_full,
        lat=lat,
        lon=lon,
    )


def make_canonical_listing(
    *,
    listing_id: str = "listing-001",
    source_id: str = "test",
    external_id: str = "ext-001",
    url: str = "https://example.com/listing/001",
    title: str = "Test Listing",
    price: float = 300000.0,
    surface_area_sqm: float = 80.0,
    bedrooms: int = 2,
    bathrooms: int = 1,
    location: Optional[GeoLocation] = None,
    listed_at: Optional[datetime] = None,
    **kwargs: Any,
) -> CanonicalListing:
    if location is None:
        location = make_geo()
    return CanonicalListing(
        id=listing_id,
        source_id=source_id,
        external_id=external_id,
        url=url,
        title=title,
        price=price,
        surface_area_sqm=surface_area_sqm,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        location=location,
        listed_at=listed_at,
        **kwargs,
    )
