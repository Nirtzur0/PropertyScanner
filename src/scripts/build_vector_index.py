import argparse
import os
from typing import Optional, List

import structlog

from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.core.config import DEFAULT_DB_URL, VECTOR_INDEX_PATH, VECTOR_METADATA_PATH
from src.services.retrieval import CompRetriever
from src.services.storage import StorageService
from src.services.feature_sanitizer import sanitize_listing_features

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
    parser = argparse.ArgumentParser(description="Build FAISS vector index from listings DB.")
    parser.add_argument("--db-url", type=str, default=DEFAULT_DB_URL, help="SQLAlchemy DB URL")
    parser.add_argument("--listing-type", type=str, default="sale", choices=["sale", "rent", "all"], help="Filter listings")
    parser.add_argument("--limit", type=int, default=0, help="Max listings to index (0 = no limit)")
    parser.add_argument("--index-path", type=str, default=str(VECTOR_INDEX_PATH), help="FAISS index output path")
    parser.add_argument("--metadata-path", type=str, default=str(VECTOR_METADATA_PATH), help="Metadata output path")
    parser.add_argument("--clear", action="store_true", help="Delete existing index/metadata before building")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size for indexing")
    parser.add_argument("--model-name", type=str, default="all-MiniLM-L6-v2", help="SentenceTransformer model name")
    parser.add_argument("--vlm-policy", type=str, default="gated", choices=["gated", "off"], help="VLM text policy")
    args = parser.parse_args(argv)

    if args.clear:
        for path in (args.index_path, args.metadata_path):
            if os.path.exists(path):
                os.remove(path)
        logger.info("vector_index_cleared", index_path=args.index_path, metadata_path=args.metadata_path)

    retriever = CompRetriever(
        index_path=args.index_path,
        metadata_path=args.metadata_path,
        model_name=args.model_name,
        strict_model_match=False,
        vlm_policy=args.vlm_policy
    )
    storage = StorageService(db_url=args.db_url)
    session = storage.get_session()

    try:
        query = session.query(DBListing)
        if args.listing_type != "all":
            query = query.filter(DBListing.listing_type == args.listing_type)

        total = 0
        batch: List[CanonicalListing] = []
        for db_item in query.yield_per(200):
            if args.limit and total >= args.limit:
                break
            batch.append(_to_canonical(db_item))
            total += 1
            if len(batch) >= args.batch_size:
                retriever.add_listings(batch)
                batch = []

        if batch:
            retriever.add_listings(batch)

        logger.info("vector_index_built", indexed=total, index_path=args.index_path)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
