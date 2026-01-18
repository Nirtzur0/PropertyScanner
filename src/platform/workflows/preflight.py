import argparse
from typing import Any, Dict, List, Optional

import structlog

from src.platform.settings import AppConfig
from src.platform.db.base import resolve_db_url
from src.platform.pipeline.runs import PipelineRunTracker
from src.platform.pipeline.state import PipelinePolicy, PipelineStateService
from src.ml.training.train import train_model
from src.listings.workflows.unified_crawl import run_backfill
from src.valuation.workflows.indexing import build_vector_index
from src.market.workflows.market_data import build_market_data
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


def _run_step(tracker: PipelineRunTracker, step_name: str, func, metadata: Dict[str, Any]) -> Any:
    run_id = tracker.start(step_name=step_name, run_type="preflight", metadata=metadata)
    try:
        result = func()
        tracker.finish(run_id=run_id, status="success", metadata=metadata)
        return result
    except Exception as e:
        metadata = dict(metadata)
        metadata["error"] = str(e)
        tracker.finish(run_id=run_id, status="failed", metadata=metadata)
        raise


def run_preflight(
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
    app_config: Optional[AppConfig] = None,
) -> Dict[str, Any]:
    app_config = app_config or load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)
    db_url = resolve_db_url(db_path=db_path)
    tracker = PipelineRunTracker(db_path=db_path)
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
            logger.info("preflight_crawl_backfill")

            def _crawl_run() -> None:
                run_backfill(
                    source_ids=crawl_sources,
                    max_listings=max_listings,
                    max_pages=max_pages,
                    page_size=page_size,
                    run_vlm=run_vlm,
                    app_config=app_config,
                )

            _run_step(
                tracker,
                step_name="crawl_backfill",
                func=_crawl_run,
                metadata={
                    "sources": crawl_sources,
                    "max_listings": max_listings,
                    "max_pages": max_pages,
                    "page_size": page_size,
                    "run_vlm": run_vlm,
                },
            )
            results["steps"].append("crawl_backfill")

    if not skip_transactions:
        try:
            from src.market.services.transactions import TransactionsIngestService

            tx_path = transactions_path or str(app_config.paths.transactions_path)
            if tx_path and tx_path.strip():
                logger.info("preflight_transactions", path=tx_path)
                service = TransactionsIngestService(db_path=db_path)
                _run_step(
                    tracker,
                    step_name="transactions_ingest",
                    func=lambda: service.ingest_file(tx_path),
                    metadata={"path": tx_path},
                )
                results["steps"].append("transactions_ingest")
        except FileNotFoundError:
            logger.info("preflight_transactions_missing", path=transactions_path)
        except Exception as e:
            logger.warning("preflight_transactions_failed", error=str(e))

    if not skip_market_data:
        state = state_service.snapshot()
        if state.needs_market_data:
            logger.info("preflight_market_data")
            _run_step(
                tracker,
                step_name="market_data",
                func=lambda: build_market_data(db_path=db_path, app_config=app_config),
                metadata={"db_path": db_path},
            )
            results["steps"].append("market_data")

    if not skip_index:
        state = state_service.snapshot()
        if state.needs_index:
            logger.info("preflight_index")
            _run_step(
                tracker,
                step_name="vector_index",
                func=lambda: build_vector_index(
                    db_url=db_url,
                    listing_type="all",
                    index_path=str(app_config.pipeline.index_path),
                    metadata_path=str(app_config.pipeline.metadata_path),
                    app_config=app_config,
                ),
                metadata={
                    "db_url": db_url,
                    "listing_type": "all",
                    "index_path": str(app_config.pipeline.index_path),
                    "metadata_path": str(app_config.pipeline.metadata_path),
                },
            )
            results["steps"].append("vector_index")

    if not skip_training:
        state = state_service.snapshot()
        if state.needs_training:
            logger.info("preflight_training", epochs=train_epochs)
            _run_step(
                tracker,
                step_name="train_model",
                func=lambda: train_model(
                    db_path=db_path,
                    epochs=train_epochs,
                    app_config=app_config,
                ),
                metadata={"db_path": db_path, "epochs": train_epochs},
            )
            results["steps"].append("train_model")

    results["final_state"] = state_service.snapshot().to_dict()
    return results


def add_preflight_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
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
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight pipeline: refresh stale data and artifacts.")
    add_preflight_args(parser)

    args = parser.parse_args(argv)

    run_preflight(
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
