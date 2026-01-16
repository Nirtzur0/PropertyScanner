import argparse
import os
from typing import Optional

import structlog

from src.core.domain.models import DBListing
from src.core.config import DEFAULT_DB_URL, VECTOR_INDEX_PATH, VECTOR_METADATA_PATH
from src.services.retrieval import CompRetriever
from src.services.storage import StorageService
from src.services.listing_adapter import db_listing_to_canonical

logger = structlog.get_logger(__name__)


def build_vector_index(
    *,
    db_url: str = DEFAULT_DB_URL,
    listing_type: str = "sale",
    limit: int = 0,
    index_path: str = str(VECTOR_INDEX_PATH),
    metadata_path: str = str(VECTOR_METADATA_PATH),
    clear: bool = False,
    batch_size: int = 200,
    model_name: str = "all-MiniLM-L6-v2",
    vlm_policy: str = "gated",
) -> int:
    if clear:
        for path in (index_path, metadata_path):
            if os.path.exists(path):
                os.remove(path)
        logger.info("vector_index_cleared", index_path=index_path, metadata_path=metadata_path)

    retriever = CompRetriever(
        index_path=index_path,
        metadata_path=metadata_path,
        model_name=model_name,
        strict_model_match=False,
        vlm_policy=vlm_policy,
    )
    storage = StorageService(db_url=db_url)
    session = storage.get_session()

    try:
        query = session.query(DBListing)
        if listing_type != "all":
            query = query.filter(DBListing.listing_type == listing_type)

        total = 0
        batch = []
        for db_item in query.yield_per(200):
            if limit and total >= limit:
                break
            batch.append(db_listing_to_canonical(db_item))
            total += 1
            if len(batch) >= batch_size:
                retriever.add_listings(batch)
                batch = []

        if batch:
            retriever.add_listings(batch)

        logger.info("vector_index_built", indexed=total, index_path=index_path)
        return total
    finally:
        session.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build FAISS vector index from listings DB.")
    parser.add_argument("--db-url", type=str, default=DEFAULT_DB_URL, help="SQLAlchemy DB URL")
    parser.add_argument(
        "--listing-type",
        type=str,
        default="sale",
        choices=["sale", "rent", "all"],
        help="Filter listings",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max listings to index (0 = no limit)")
    parser.add_argument("--index-path", type=str, default=str(VECTOR_INDEX_PATH), help="FAISS index output path")
    parser.add_argument(
        "--metadata-path", type=str, default=str(VECTOR_METADATA_PATH), help="Metadata output path"
    )
    parser.add_argument("--clear", action="store_true", help="Delete existing index/metadata before building")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size for indexing")
    parser.add_argument("--model-name", type=str, default="all-MiniLM-L6-v2", help="SentenceTransformer model name")
    parser.add_argument("--vlm-policy", type=str, default="gated", choices=["gated", "off"], help="VLM text policy")
    args = parser.parse_args(argv)

    build_vector_index(
        db_url=args.db_url,
        listing_type=args.listing_type,
        limit=args.limit,
        index_path=args.index_path,
        metadata_path=args.metadata_path,
        clear=args.clear,
        batch_size=args.batch_size,
        model_name=args.model_name,
        vlm_policy=args.vlm_policy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
