from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task
from prefect.tasks import task_input_hash

from src.listings.workflows.unified_crawl import run_backfill
from src.market.services.transactions import TransactionsIngestService
from src.market.workflows.market_data import build_market_data
from src.ml.training.train import train_model
from src.platform.db.base import resolve_db_url
from src.platform.pipeline.state import PipelinePolicy, PipelineStateService
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe
from src.valuation.workflows.indexing import build_vector_index


def _cache_key_or_none(context: Any, parameters: Dict[str, Any]) -> Optional[str]:
    if not parameters.get("enable_cache", True):
        return None
    params = dict(parameters)
    params.pop("enable_cache", None)
    return task_input_hash(context, params)


@task(
    retries=2,
    retry_delay_seconds=60,
    cache_key_fn=_cache_key_or_none,
    cache_expiration=timedelta(hours=6),
    persist_result=True,
)
def crawl_backfill_task(
    *,
    source_ids: Optional[List[str]],
    max_listings: int,
    max_pages: int,
    page_size: int,
    run_vlm: bool,
    enable_cache: bool = True,
) -> List[Dict[str, Any]]:
    return run_backfill(
        source_ids=source_ids,
        max_listings=max_listings,
        max_pages=max_pages,
        page_size=page_size,
        run_vlm=run_vlm,
    )


@task(retries=2, retry_delay_seconds=60)
def transactions_ingest_task(*, db_path: str, transactions_path: str) -> Dict[str, Any]:
    service = TransactionsIngestService(db_path=db_path)
    rows = service.ingest_file(transactions_path)
    return {"rows_ingested": rows}


@task(
    retries=2,
    retry_delay_seconds=60,
    cache_key_fn=_cache_key_or_none,
    cache_expiration=timedelta(hours=12),
    persist_result=True,
)
def market_data_task(*, db_path: str, enable_cache: bool = True) -> Dict[str, Any]:
    build_market_data(db_path=db_path)
    return {"status": "ok"}


@task(
    retries=2,
    retry_delay_seconds=60,
    cache_key_fn=_cache_key_or_none,
    cache_expiration=timedelta(hours=12),
    persist_result=True,
)
def build_vector_index_task(
    *,
    db_url: str,
    index_path: str,
    metadata_path: str,
    enable_cache: bool = True,
) -> Dict[str, Any]:
    build_vector_index(
        db_url=db_url,
        listing_type="all",
        index_path=index_path,
        metadata_path=metadata_path,
    )
    return {"status": "ok"}


@task(retries=1, retry_delay_seconds=60)
def train_model_task(*, db_path: str, epochs: int) -> Dict[str, Any]:
    train_model(db_path=db_path, epochs=epochs)
    return {"status": "ok"}


@flow(name="preflight_flow")
def preflight_flow(
    *,
    db_path: Optional[str] = None,
    crawl_sources: Optional[List[str]] = None,
    max_listings: int = 0,
    max_pages: int = 1,
    page_size: int = 24,
    run_vlm: bool = True,
    max_listing_age_days: int = 7,
    max_market_data_age_days: int = 30,
    min_listings_for_training: int = 200,
    train_epochs: int = 50,
    skip_crawl: bool = False,
    skip_market_data: bool = False,
    skip_index: bool = False,
    skip_training: bool = False,
    transactions_path: Optional[str] = None,
    skip_transactions: bool = False,
    enable_cache: bool = True,
    app_config: Optional[AppConfig] = None,
) -> Dict[str, Any]:
    logger = get_run_logger()
    app_config = app_config or load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)

    db_url = resolve_db_url(db_path=db_path)
    policy = PipelinePolicy(
        max_listing_age_days=max_listing_age_days,
        max_market_data_age_days=max_market_data_age_days,
        min_listings_for_training=min_listings_for_training,
    )
    state_service = PipelineStateService(db_path=db_path, policy=policy, app_config=app_config)

    results: Dict[str, Any] = {
        "initial_state": state_service.snapshot().to_dict(),
        "steps": [],
    }

    if not skip_crawl:
        state = state_service.snapshot()
        if state.needs_crawl:
            logger.info("prefect_preflight_crawl_backfill")
            crawl_backfill_task(
                source_ids=crawl_sources,
                max_listings=max_listings,
                max_pages=max_pages,
                page_size=page_size,
                run_vlm=run_vlm,
                enable_cache=enable_cache,
            )
            results["steps"].append("crawl_backfill")

    if not skip_transactions:
        try:
            tx_path = transactions_path or str(app_config.paths.transactions_path)
            if tx_path and tx_path.strip():
                logger.info("prefect_preflight_transactions", path=tx_path)
                transactions_ingest_task(db_path=db_path, transactions_path=tx_path)
                results["steps"].append("transactions_ingest")
        except FileNotFoundError:
            logger.info("prefect_preflight_transactions_missing", path=transactions_path)
        except Exception as exc:
            logger.warning("prefect_preflight_transactions_failed", error=str(exc))

    if not skip_market_data:
        state = state_service.snapshot()
        if state.needs_market_data:
            logger.info("prefect_preflight_market_data")
            market_data_task(db_path=db_path, enable_cache=enable_cache)
            results["steps"].append("market_data")

    if not skip_index:
        state = state_service.snapshot()
        if state.needs_index:
            logger.info("prefect_preflight_index")
            build_vector_index_task(
                db_url=db_url,
                index_path=str(app_config.pipeline.index_path),
                metadata_path=str(app_config.pipeline.metadata_path),
                enable_cache=enable_cache,
            )
            results["steps"].append("vector_index")

    if not skip_training:
        state = state_service.snapshot()
        if state.needs_training:
            logger.info("prefect_preflight_training", epochs=train_epochs)
            train_model_task(db_path=db_path, epochs=train_epochs)
            results["steps"].append("train_model")

    results["final_state"] = state_service.snapshot().to_dict()
    return results


def add_prefect_preflight_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    defaults = load_app_config_safe()
    parser.add_argument(
        "--db",
        type=str,
        default=str(defaults.pipeline.db_path),
        help="SQLite DB path",
    )
    parser.add_argument("--crawl-source", action="append", help="Source id for crawl backfill (repeatable)")
    parser.add_argument("--max-listings", type=int, default=0, help="Max listings per source (0 = default)")
    parser.add_argument("--max-pages", type=int, default=1, help="Max pages per source (where supported)")
    parser.add_argument("--page-size", type=int, default=24, help="Search page size (where supported)")
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM during crawl backfill")
    parser.add_argument("--max-listing-age-days", type=int, default=7)
    parser.add_argument("--max-market-data-age-days", type=int, default=30)
    parser.add_argument("--min-listings-for-training", type=int, default=200)
    parser.add_argument("--train-epochs", type=int, default=50)
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--skip-market-data", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--skip-training", action="store_true")
    parser.add_argument(
        "--transactions-path",
        type=str,
        default=str(defaults.paths.transactions_path),
        help="CSV/JSONL path for sold data",
    )
    parser.add_argument("--skip-transactions", action="store_true")
    parser.add_argument("--disable-cache", action="store_true", help="Disable Prefect task caching")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prefect orchestration entrypoint.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight", help="Run preflight as a Prefect flow")
    add_prefect_preflight_args(preflight_parser)

    args = parser.parse_args(argv)

    if args.command == "preflight":
        preflight_flow(
            db_path=args.db,
            crawl_sources=args.crawl_source,
            max_listings=args.max_listings,
            max_pages=args.max_pages,
            page_size=args.page_size,
            run_vlm=not args.no_vlm,
            max_listing_age_days=args.max_listing_age_days,
            max_market_data_age_days=args.max_market_data_age_days,
            min_listings_for_training=args.min_listings_for_training,
            train_epochs=args.train_epochs,
            skip_crawl=args.skip_crawl,
            skip_market_data=args.skip_market_data,
            skip_index=args.skip_index,
            skip_training=args.skip_training,
            transactions_path=args.transactions_path,
            skip_transactions=args.skip_transactions,
            enable_cache=not args.disable_cache,
        )
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
