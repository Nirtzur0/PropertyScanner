import argparse
from typing import Optional

import structlog

from src.core.config import DEFAULT_DB_PATH, TRANSACTIONS_PATH
from src.services.pipeline_runs import PipelineRunTracker
from src.services.transactions import TransactionsIngestService

logger = structlog.get_logger(__name__)


def ingest_transactions(
    *,
    path: str,
    db_path: str = str(DEFAULT_DB_PATH),
    listing_type: str = "sale",
    source_id: Optional[str] = None,
) -> dict:
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
    parser.add_argument("--path", type=str, default=str(TRANSACTIONS_PATH), help="CSV/JSONL path")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="SQLite DB path")
    parser.add_argument("--listing-type", type=str, default="sale", choices=["sale", "rent"])
    parser.add_argument("--source-id", type=str, default=None, help="Default source_id for matching")
    args = parser.parse_args(argv)

    ingest_transactions(
        path=args.path,
        db_path=args.db,
        listing_type=args.listing_type,
        source_id=args.source_id,
    )
    logger.info("transactions_ingest_complete", path=args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
