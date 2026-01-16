import argparse
from typing import Optional

import structlog

from src.core.domain.models import DBListing
from src.core.config import DEFAULT_DB_URL
from src.services.storage import StorageService
from src.services.valuation import ValuationService
from src.services.valuation_persister import ValuationPersister
from src.services.listing_adapter import db_listing_to_canonical

logger = structlog.get_logger(__name__)


def backfill_valuations(
    *,
    db_url: str = DEFAULT_DB_URL,
    city: Optional[str] = None,
    listing_type: str = "sale",
    limit: int = 0,
    max_age_days: int = 7,
) -> int:
    storage = StorageService(db_url=db_url)
    valuation = ValuationService(storage)

    session = storage.get_session()
    try:
        query = session.query(DBListing.id)
        if city:
            query = query.filter(DBListing.city.ilike(city))
        if listing_type != "all":
            query = query.filter(DBListing.listing_type == listing_type)
        if limit:
            query = query.limit(limit)
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

            cached_val = persister.get_latest_valuation(db_item.id, max_age_days=max_age_days)
            if cached_val:
                skipped += 1
                continue

            listing = db_listing_to_canonical(db_item)
            analysis = valuation.evaluate_deal(listing, comps=None)
            persister.save_valuation(db_item.id, analysis)

            processed += 1
            if processed % 50 == 0:
                logger.info("backfill_progress", processed=processed, skipped=skipped)
        finally:
            session.close()

    logger.info("backfill_done", processed=processed, skipped=skipped)
    return processed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill cached valuations + projections for listings in the DB."
    )
    parser.add_argument("--db-url", type=str, default=DEFAULT_DB_URL, help="SQLAlchemy DB URL")
    parser.add_argument("--city", type=str, default=None, help="Only backfill a specific city (case-insensitive)")
    parser.add_argument(
        "--listing-type",
        type=str,
        default="sale",
        choices=["sale", "rent", "all"],
        help="Filter listings",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max listings to process (0 = no limit)")
    parser.add_argument(
        "--max-age-days", type=int, default=7, help="Skip if cached valuation is newer than this"
    )
    args = parser.parse_args(argv)

    backfill_valuations(
        db_url=args.db_url,
        city=args.city,
        listing_type=args.listing_type,
        limit=args.limit,
        max_age_days=args.max_age_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
