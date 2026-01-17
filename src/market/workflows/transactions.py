import argparse
from typing import Optional

import structlog

from src.platform.settings import AppConfig
from src.platform.pipeline.runs import PipelineRunTracker
from src.market.services.transactions import TransactionsIngestService
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


def ingest_transactions(
    *,
    path: str,
    db_path: Optional[str] = None,
    listing_type: str = "sale",
    source_id: Optional[str] = None,
    app_config: Optional[AppConfig] = None,
) -> dict:
    app_config = app_config or load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)
    tracker = PipelineRunTracker(db_path=db_path)
    run_id = tracker.start(step_name="transactions_ingest", run_type="workflow", metadata={"path": path})
    try:
        service = TransactionsIngestService(db_path=db_path)
        result = service.ingest_file(path, default_listing_type=listing_type, default_source_id=source_id)
        tracker.finish(run_id=run_id, status="success", metadata=result)
        return result
    except Exception as exc:
        tracker.finish(run_id=run_id, status="failed", metadata={"error": str(exc)})
        raise


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest sold/transaction data into listings.")
    defaults = load_app_config_safe()
    parser.add_argument(
        "--path",
        type=str,
        default=str(defaults.paths.transactions_path),
        help="CSV/JSONL path",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(defaults.pipeline.db_path),
        help="SQLite DB path",
    )
    parser.add_argument("--listing-type", type=str, default="sale", choices=["sale", "rent"])
    parser.add_argument("--source-id", type=str, default=None, help="Default source_id for matching")
    args = parser.parse_args(argv)

    ingest_transactions(
        path=args.path,
        db_path=args.db,
        listing_type=args.listing_type,
        source_id=args.source_id,
        app_config=defaults,
    )
    logger.info("transactions_ingest_complete", path=args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
