import argparse
from typing import Optional, List

import structlog

from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.core.config import DEFAULT_DB_URL
from src.services.storage import StorageService
from src.services.feature_sanitizer import sanitize_listing_features
from src.services.valuation import ValuationService
from src.services.valuation_persister import ValuationPersister

logger = structlog.get_logger(__name__)


def _normalize_property_type(value: Optional[str]) -> str:
    if value is None:
        return "apartment"
    text = str(value).strip()
    if "." in text:
        text = text.split(".")[-1]
    return text.lower() or "apartment"

def _to_int(value: Optional[object]) -> Optional[int]:
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


def _to_float(value: Optional[object]) -> Optional[float]:
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


def _to_canonical(db_item: DBListing) -> CanonicalListing:
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
        property_type=_normalize_property_type(db_item.property_type),
        bedrooms=_to_int(db_item.bedrooms),
        bathrooms=_to_int(db_item.bathrooms),
        surface_area_sqm=_to_float(db_item.surface_area_sqm),
        plot_area_sqm=_to_float(getattr(db_item, "plot_area_sqm", None)),
        floor=_to_int(db_item.floor),
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill cached valuations + projections for listings in the DB.")
    parser.add_argument("--db-url", type=str, default=DEFAULT_DB_URL, help="SQLAlchemy DB URL")
    parser.add_argument("--city", type=str, default=None, help="Only backfill a specific city (case-insensitive)")
    parser.add_argument("--listing-type", type=str, default="sale", choices=["sale", "rent", "all"], help="Filter listings")
    parser.add_argument("--limit", type=int, default=0, help="Max listings to process (0 = no limit)")
    parser.add_argument("--max-age-days", type=int, default=7, help="Skip if cached valuation is newer than this")
    args = parser.parse_args(argv)

    storage = StorageService(db_url=args.db_url)
    valuation = ValuationService(storage)

    # First collect IDs to avoid read/write contention on SQLite.
    session = storage.get_session()
    try:
        query = session.query(DBListing.id)
        if args.city:
            query = query.filter(DBListing.city.ilike(args.city))
        if args.listing_type != "all":
            query = query.filter(DBListing.listing_type == args.listing_type)
        if args.limit:
            query = query.limit(args.limit)
        listing_ids = [row[0] for row in query.all()]
    finally:
        session.close()

    processed = 0
    skipped = 0

    for listing_id in listing_ids:
        session = storage.get_session()
        try:
            persister = ValuationPersister(session)
            db_item = session.query(DBListing).filter(DBListing.id == listing_id).first()
            if not db_item:
                continue

            cached_val = persister.get_latest_valuation(db_item.id, max_age_days=args.max_age_days)
            if cached_val:
                skipped += 1
                continue

            listing = _to_canonical(db_item)
            analysis = valuation.evaluate_deal(listing, comps=None)
            persister.save_valuation(db_item.id, analysis)

            processed += 1
            if processed % 50 == 0:
                logger.info("backfill_progress", processed=processed, skipped=skipped)
        finally:
            session.close()

    logger.info("backfill_done", processed=processed, skipped=skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
