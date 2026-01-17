import argparse
import os
from typing import List, Optional

import structlog

from src.platform.domain.models import DBListing
from src.platform.settings import AppConfig
from src.platform.db.base import resolve_db_url
from src.valuation.services.retrieval import CompRetriever
from src.platform.storage import StorageService
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


def build_vector_index(
    *,
    db_url: Optional[str] = None,
    listing_type: str = "all",
    limit: int = 0,
    index_path: Optional[str] = None,
    metadata_path: Optional[str] = None,
    clear: bool = False,
    batch_size: int = 200,
    model_name: Optional[str] = None,
    vlm_policy: Optional[str] = None,
    app_config: Optional[AppConfig] = None,
) -> int:
    app_config = app_config or load_app_config_safe()
    if db_url is None:
        db_url = resolve_db_url(
            db_url=app_config.pipeline.db_url,
            db_path=app_config.pipeline.db_path,
        )
    if index_path is None:
        index_path = str(app_config.pipeline.index_path)
    if metadata_path is None:
        metadata_path = str(app_config.pipeline.metadata_path)
    if model_name is None:
        model_name = app_config.valuation.retriever_model_name
    if vlm_policy is None:
        vlm_policy = app_config.valuation.retriever_vlm_policy

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
    defaults = load_app_config_safe()
    parser.add_argument(
        "--db-url",
        type=str,
        default=str(resolve_db_url(db_url=defaults.pipeline.db_url, db_path=defaults.pipeline.db_path)),
        help="SQLAlchemy DB URL",
    )
    parser.add_argument(
        "--listing-type",
        type=str,
        default="all",
        choices=["sale", "rent", "all"],
        help="Filter listings",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max listings to index (0 = no limit)")
    parser.add_argument(
        "--index-path",
        type=str,
        default=str(defaults.pipeline.index_path),
        help="FAISS index output path",
    )
    parser.add_argument(
        "--metadata-path", type=str, default=str(defaults.pipeline.metadata_path), help="Metadata output path"
    )
    parser.add_argument("--clear", action="store_true", help="Delete existing index/metadata before building")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size for indexing")
    parser.add_argument(
        "--model-name",
        type=str,
        default=defaults.valuation.retriever_model_name,
        help="SentenceTransformer model name",
    )
    parser.add_argument(
        "--vlm-policy",
        type=str,
        default=defaults.valuation.retriever_vlm_policy,
        choices=["gated", "off"],
        help="VLM text policy",
    )
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
        app_config=defaults,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
