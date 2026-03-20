import argparse
import json
import subprocess
import sys
from typing import List

def _run_command(cmd: List[str]) -> int:
    try:
        return subprocess.run(cmd, check=False).returncode
    except KeyboardInterrupt:
        return 130


def _run_module(module: str, args: List[str]) -> int:
    cmd = [sys.executable, "-m", module] + args
    return _run_command(cmd)


def _run_streamlit(args: List[str]) -> int:
    cmd = [sys.executable, "-m", "streamlit", "run", "src/interfaces/dashboard/app.py"] + args
    return _run_command(cmd)


def _run_uvicorn(args: List[str]) -> int:
    cmd = [sys.executable, "-m", "uvicorn", "src.adapters.http.app:app"] + args
    return _run_command(cmd)


def _add_passthrough_parser(subparsers, name: str, help_text: str) -> None:
    parser = subparsers.add_parser(name, help=help_text)
    parser.add_argument("args", nargs=argparse.REMAINDER)


def _add_preflight_args(parser: argparse.ArgumentParser) -> None:
    # Keep these flags in sync with add_prefect_preflight_args in
    # src/platform/workflows/prefect_orchestration.py without importing Prefect.
    parser.add_argument("--db", type=str, default=None, help="SQLite DB path")
    parser.add_argument("--crawl-source", action="append", default=None, help="Source id for crawl backfill (repeatable)")
    parser.add_argument("--max-listings", type=int, default=None, help="Max listings per source (0 = default)")
    parser.add_argument("--max-pages", type=int, default=None, help="Max pages per source (where supported)")
    parser.add_argument("--page-size", type=int, default=None, help="Search page size (where supported)")
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM during crawl backfill")
    parser.add_argument("--max-listing-age-days", type=int, default=None, help="Skip crawl if listings are newer than this")
    parser.add_argument("--max-market-data-age-days", type=int, default=None, help="Skip market-data refresh if newer than this")
    parser.add_argument("--min-listings-for-training", type=int, default=None, help="Minimum listings required before training")
    parser.add_argument("--train-epochs", type=int, default=None, help="Training epochs when preflight triggers training")
    parser.add_argument("--skip-crawl", action="store_true", help="Skip crawl backfill step")
    parser.add_argument("--skip-market-data", action="store_true", help="Skip market-data step")
    parser.add_argument("--skip-index", action="store_true", help="Skip vector-index build step")
    parser.add_argument("--skip-training", action="store_true", help="Skip model training step")
    parser.add_argument("--transactions-path", type=str, default=None, help="CSV/JSONL path for sold transactions")
    parser.add_argument("--skip-transactions", action="store_true", help="Skip transactions ingest step")
    parser.add_argument("--disable-cache", action="store_true", help="Disable Prefect task caching")


def _get_container():
    from src.application.container import get_container

    return get_container()


def _build_preflight_args(parsed: argparse.Namespace, extras: List[str]) -> List[str]:
    args = ["preflight"]

    for source_id in parsed.crawl_source or []:
        args.extend(["--crawl-source", source_id])

    scalar_flags = (
        ("db", "--db"),
        ("max_listings", "--max-listings"),
        ("max_pages", "--max-pages"),
        ("page_size", "--page-size"),
        ("max_listing_age_days", "--max-listing-age-days"),
        ("max_market_data_age_days", "--max-market-data-age-days"),
        ("min_listings_for_training", "--min-listings-for-training"),
        ("train_epochs", "--train-epochs"),
        ("transactions_path", "--transactions-path"),
    )
    for attr, flag in scalar_flags:
        value = getattr(parsed, attr, None)
        if value is not None:
            args.extend([flag, str(value)])

    bool_flags = (
        ("no_vlm", "--no-vlm"),
        ("skip_crawl", "--skip-crawl"),
        ("skip_market_data", "--skip-market-data"),
        ("skip_index", "--skip-index"),
        ("skip_training", "--skip-training"),
        ("skip_transactions", "--skip-transactions"),
        ("disable_cache", "--disable-cache"),
    )
    for attr, flag in bool_flags:
        if getattr(parsed, attr, False):
            args.append(flag)

    if extras:
        args.extend(extras)
    return args


def main(argv: List[str] = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(description="Property Scanner CLI (preflight is the canonical entry point)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_passthrough_parser(subparsers, "market-data", "Build market/hedonic indices & ingest registries (runs Prefect flow)")
    _add_passthrough_parser(subparsers, "build-index", "Build vector index (LanceDB) (runs Prefect flow)")
    _add_passthrough_parser(subparsers, "train", "Train the fusion model (wraps src.ml.training.train)")
    _add_passthrough_parser(
        subparsers,
        "benchmark",
        "Benchmark fusion against RF/XGBoost baselines (wraps src.ml.training.benchmark)",
    )
    _add_passthrough_parser(
        subparsers,
        "retriever-ablation",
        "Run geo/structure/semantic retriever ablations (wraps src.ml.training.retriever_ablation)",
    )
    _add_passthrough_parser(subparsers, "backfill", "Backfill cached valuations (runs Prefect flow)")
    _add_passthrough_parser(subparsers, "transactions", "Ingest sold/transaction data (runs Prefect flow)")
    _add_passthrough_parser(subparsers, "dashboard", "Launch legacy Streamlit dashboard (deprecated)")
    _add_passthrough_parser(subparsers, "legacy-dashboard", "Launch legacy Streamlit dashboard (deprecated)")
    _add_passthrough_parser(subparsers, "api", "Launch the local FastAPI backend")
    _add_passthrough_parser(subparsers, "agent", "Run the cognitive agent (wraps src.interfaces.agent)")
    _add_passthrough_parser(subparsers, "calibrators", "Update conformal calibrators (wraps src.valuation.workflows.calibration)")
    _add_passthrough_parser(subparsers, "clean-data", "Fix metadata/geocoding issues (runs Prefect maintenance flow)")
    _add_passthrough_parser(subparsers, "prefect", "Run Prefect flows (wraps src.platform.workflows.prefect_orchestration)")
    _add_passthrough_parser(subparsers, "unified-crawl", "Run unified multi-source crawl (wraps src.listings.workflows.unified_crawl)")
    _add_passthrough_parser(subparsers, "sidecar-crawl", "Run the Node/TypeScript scraper sidecar contract")
    _add_passthrough_parser(subparsers, "migrate", "Run database schema migrations (wraps src.platform.migrations)")
    _add_passthrough_parser(subparsers, "train-pipeline", "Run full training sequence: VLM prep + Fusion Train (runs Prefect flow)")
    _add_passthrough_parser(subparsers, "caption-images", "Run image captioning batch job (runs Prefect maintenance flow)")
    _add_passthrough_parser(subparsers, "audit-serving-data", "Audit serving eligibility issues into data_quality_events")
    seed_parser = subparsers.add_parser(
        "seed-sample-data",
        help="Seed a small local sample dataset for smoke tests and first-run demos",
    )
    seed_parser.add_argument("--db", type=str, default=None, help="SQLite DB path")

    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Refresh stale data and artifacts (runs Prefect preflight flow)",
        description="Run preflight with common freshness/caching flags. Extra args are forwarded to the Prefect module.",
    )
    _add_preflight_args(preflight_parser)

    args, remaining = parser.parse_known_args(raw_args)
    if args.command == "preflight":
        cmd_args = _build_preflight_args(args, remaining)
    else:
        cmd_args = raw_args[1:]

    module_map = {
        "market-data": "src.platform.workflows.prefect_orchestration",
        "build-index": "src.platform.workflows.prefect_orchestration",
        "train": "src.ml.training.train",
        "benchmark": "src.ml.training.benchmark",
        "retriever-ablation": "src.ml.training.retriever_ablation",
        "backfill": "src.platform.workflows.prefect_orchestration",
        "transactions": "src.platform.workflows.prefect_orchestration",
        "agent": "src.interfaces.agent",
        "calibrators": "src.valuation.workflows.calibration",
        "clean-data": "src.platform.workflows.prefect_orchestration",
        "preflight": "src.platform.workflows.prefect_orchestration",
        "prefect": "src.platform.workflows.prefect_orchestration",
        "unified-crawl": "src.listings.workflows.unified_crawl",
        "sidecar-crawl": "src.listings.scraping.sidecar",
        "migrate": "src.platform.migrations",
        "train-pipeline": "src.platform.workflows.prefect_orchestration",
        "caption-images": "src.platform.workflows.prefect_orchestration",
    }

    if args.command in {"dashboard", "legacy-dashboard"}:
        print(
            "warning: Streamlit dashboard is deprecated; use the React app through `python -m src.interfaces.cli api`.",
            file=sys.stderr,
        )
        if "--skip-preflight" in cmd_args:
            cmd_args = [arg for arg in cmd_args if arg != "--skip-preflight"]
        return _run_streamlit(cmd_args)
    if args.command == "api":
        return _run_uvicorn(cmd_args)

    if args.command == "seed-sample-data":
        from src.application.sample_data import seed_sample_data
        from src.platform.db.base import resolve_db_url
        from src.platform.storage import StorageService

        db_url = resolve_db_url(db_path=args.db) if args.db else None
        storage = StorageService(db_url=db_url) if db_url else _get_container().storage
        print(json.dumps(seed_sample_data(storage=storage), indent=2, default=str))
        return 0

    container = _get_container()
    if args.command == "preflight":
        payload = {
            "source_ids": args.crawl_source,
            "max_listings": args.max_listings or 0,
            "max_pages": args.max_pages or 1,
            "page_size": args.page_size or 24,
            "skip_crawl": bool(args.skip_crawl),
            "skip_market_data": bool(args.skip_market_data),
            "skip_index": bool(args.skip_index),
            "skip_training": bool(args.skip_training),
        }
        print(json.dumps(container.pipeline.run_preflight(**payload), indent=2, default=str))
        return 0
    if args.command == "market-data":
        print(json.dumps(container.pipeline.run_market_data(), indent=2, default=str))
        return 0
    if args.command == "audit-serving-data":
        source_summary = container.sources.audit_sources(persist=False).model_dump(mode="json")
        source_status_by_source = {
            str(item.get("source_id")): str(item.get("status") or "experimental")
            for item in source_summary.get("sources", [])
            if item.get("source_id")
        }
        print(
            json.dumps(
                container.pipeline.export_source_quality_snapshot(source_status_by_source=source_status_by_source),
                indent=2,
                default=str,
            )
        )
        return 0
    if args.command == "build-index":
        limit = 0
        listing_type = "all"
        if "--limit" in cmd_args:
            idx = cmd_args.index("--limit")
            if idx + 1 < len(cmd_args):
                limit = int(cmd_args[idx + 1])
        if "--listing-type" in cmd_args:
            idx = cmd_args.index("--listing-type")
            if idx + 1 < len(cmd_args):
                listing_type = cmd_args[idx + 1]
        print(json.dumps(container.pipeline.run_index(listing_type=listing_type, limit=limit), indent=2, default=str))
        return 0
    module = module_map.get(args.command)
    if not module:
        parser.error(f"Unknown command: {args.command}")
        return 2

    if args.command == "clean-data":
        cmd_args = ["maintenance", "--clean"] + cmd_args
    elif args.command == "caption-images":
        mapped = ["maintenance", "--vlm"]
        idx = 0
        while idx < len(cmd_args):
            arg = cmd_args[idx]
            if arg == "--override":
                mapped.append("--vlm-override")
            elif arg.startswith("--workers="):
                mapped.append("--vlm-workers=" + arg.split("=", 1)[1])
            elif arg == "--workers":
                mapped.append("--vlm-workers")
                if idx + 1 < len(cmd_args):
                    mapped.append(cmd_args[idx + 1])
                    idx += 1
            else:
                mapped.append(arg)
            idx += 1
        cmd_args = mapped
    elif args.command == "market-data":
        cmd_args = ["market-data"] + cmd_args
    elif args.command == "build-index":
        cmd_args = ["build-index"] + cmd_args
    elif args.command == "transactions":
        cmd_args = ["transactions"] + cmd_args
    elif args.command == "train-pipeline":
        cmd_args = ["train-pipeline"] + cmd_args
    elif args.command == "backfill":
        cmd_args = ["backfill"] + cmd_args

    return _run_module(module, cmd_args)


if __name__ == "__main__":
    raise SystemExit(main())
