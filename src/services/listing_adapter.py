from typing import Optional

from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.services.feature_sanitizer import sanitize_listing_features


def normalize_property_type(value: Optional[str]) -> str:
    if value is None:
        return "apartment"
    text = str(value).strip()
    if "." in text:
        text = text.split(".")[-1]
    return text.lower() or "apartment"


def to_int(value: Optional[object]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("", "null", "none"):
            return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("", "null", "none"):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def db_listing_to_canonical(db_item: DBListing) -> CanonicalListing:
    loc = None
    if db_item.city or db_item.lat or db_item.lon:
        loc = GeoLocation(
            lat=db_item.lat,
            lon=db_item.lon,
            address_full=db_item.address_full or db_item.title,
            city=db_item.city or "Unknown",
            zip_code=getattr(db_item, "zip_code", None),
            country=db_item.country or "ES",
        )

    listing = CanonicalListing(
        id=db_item.id,
        source_id=db_item.source_id,
        external_id=db_item.external_id,
        url=str(db_item.url),
        title=db_item.title,
        description=db_item.description,
        price=db_item.price,
        currency=db_item.currency,
        listing_type=getattr(db_item, "listing_type", "sale") or "sale",
        estimated_rent=getattr(db_item, "estimated_rent", None),
        gross_yield=getattr(db_item, "gross_yield", None),
        property_type=normalize_property_type(db_item.property_type),
        bedrooms=to_int(db_item.bedrooms),
        bathrooms=to_int(db_item.bathrooms),
        surface_area_sqm=to_float(db_item.surface_area_sqm),
        plot_area_sqm=to_float(getattr(db_item, "plot_area_sqm", None)),
        floor=to_int(db_item.floor),
        has_elevator=db_item.has_elevator,
        location=loc,
        image_urls=db_item.image_urls or [],
        vlm_description=db_item.vlm_description,
        text_sentiment=db_item.text_sentiment,
        image_sentiment=db_item.image_sentiment,
        analysis_meta=db_item.analysis_meta,
        image_embeddings=getattr(db_item, "image_embeddings", None),
        listed_at=db_item.listed_at,
        updated_at=db_item.updated_at,
        status=db_item.status,
        tags=db_item.tags or [],
    )
    return sanitize_listing_features(listing)
