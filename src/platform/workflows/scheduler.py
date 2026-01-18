import argparse
from typing import Any, Dict, List, Optional

import structlog
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.interfaces.api.pipeline import PipelineAPI
from src.platform.workflows.preflight import add_preflight_args

logger = structlog.get_logger(__name__)


def _build_preflight_kwargs(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "db_path": args.db,
        "crawl_sources": args.crawl_source,
        "max_listings": args.max_listings,
        "max_pages": args.max_pages,
        "page_size": args.page_size,
        "run_vlm": not args.no_vlm,
        "max_listing_age_days": args.max_listing_age_days,
        "max_market_data_age_days": args.max_market_data_age_days,
        "min_listings_for_training": args.min_listings_for_training,
        "train_epochs": args.train_epochs,
        "skip_crawl": args.skip_crawl,
        "skip_market_data": args.skip_market_data,
        "skip_index": args.skip_index,
        "skip_training": args.skip_training,
    }


def schedule_preflight(
    *,
    interval_minutes: int,
    cron: Optional[str],
    run_on_start: bool,
    preflight_kwargs: Dict[str, Any],
) -> None:
    api = PipelineAPI()
    scheduler = BlockingScheduler()

    def _job() -> None:
        logger.info("preflight_scheduled_run_started")
        try:
            api.preflight(**preflight_kwargs)
            logger.info("preflight_scheduled_run_completed")
        except Exception as exc:
            logger.error("preflight_scheduled_run_failed", error=str(exc))

    if cron:
        trigger = CronTrigger.from_crontab(cron)
        scheduler.add_job(
            _job,
            trigger=trigger,
            id="preflight",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=900,
        )
        logger.info("preflight_scheduler_started", mode="cron", cron=cron)
    else:
        scheduler.add_job(
            _job,
            trigger="interval",
            minutes=interval_minutes,
            id="preflight",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=900,
        )
        logger.info("preflight_scheduler_started", mode="interval", minutes=interval_minutes)

    if run_on_start:
        _job()

    scheduler.start()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run scheduled preflight refreshes (canonical automation entry point)."
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=360,
        help="Interval between preflight runs in minutes (ignored if --cron is set).",
    )
    parser.add_argument(
        "--cron",
        type=str,
        default=None,
        help="Cron expression (5 fields). Example: '0 3 * * *' for daily at 03:00.",
    )
    parser.add_argument(
        "--skip-initial",
        action="store_true",
        help="Skip the immediate preflight run on startup.",
    )
    add_preflight_args(parser)
    args = parser.parse_args(argv)

    if args.cron and args.interval_minutes:
        # interval is ignored when cron is set; keep behavior explicit
        logger.info("scheduler_cron_overrides_interval", interval_minutes=args.interval_minutes)

    schedule_preflight(
        interval_minutes=args.interval_minutes,
        cron=args.cron,
        run_on_start=not args.skip_initial,
        preflight_kwargs=_build_preflight_kwargs(args),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
