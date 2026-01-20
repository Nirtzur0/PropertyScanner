from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger, task
from prefect.tasks import task_input_hash

from src.listings.workflows.unified_crawl import run_backfill
from src.listings.workflows.maintenance import clean_data
from src.market.services.transactions import TransactionsIngestService
from src.market.workflows.market_data import build_market_data
from src.ml.training.train import train_model
from src.ml.training.image_captioning import batch_process_vlm
from src.platform.db.base import resolve_db_url
from src.platform.pipeline.runs import PipelineRunTracker
from src.platform.pipeline.state import PipelinePolicy, PipelineStateService
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe
from src.valuation.workflows.backfill import backfill_valuations
from src.valuation.workflows.indexing import build_vector_index


def _cache_key_or_none(context: Any, parameters: Dict[str, Any]) -> Optional[str]:
    if not parameters.get("enable_cache", True):
        return None
    params = dict(parameters)
    params.pop("enable_cache", None)
    return task_input_hash(context, params)


def _resolve_task_result(result: Any) -> Any:
    if hasattr(result, "result"):
        return result.result()
    return result


def _run_tracked(
    tracker: PipelineRunTracker,
    *,
    step_name: str,
    func,
    metadata: Dict[str, Any],
) -> Any:
    run_id = tracker.start(step_name=step_name, run_type="prefect", metadata=metadata)
    try:
        result = func()
        resolved = _resolve_task_result(result)
        tracker.finish(run_id=run_id, status="success", metadata=metadata)
        return resolved
    except Exception as exc:
        metadata = dict(metadata)
        metadata["error"] = str(exc)
        tracker.finish(run_id=run_id, status="failed", metadata=metadata)
        raise


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
def transactions_ingest_task(
    *,
    db_path: str,
    transactions_path: str,
    listing_type: str = "sale",
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    service = TransactionsIngestService(db_path=db_path)
    return service.ingest_file(
        transactions_path,
        default_listing_type=listing_type,
        default_source_id=source_id,
    )


@task(
    retries=2,
    retry_delay_seconds=60,
    cache_key_fn=_cache_key_or_none,
    cache_expiration=timedelta(hours=12),
    persist_result=True,
)
def market_data_task(
    *,
    db_path: str,
    skip_migrations: bool = False,
    skip_macro: bool = False,
    skip_market_indices: bool = False,
    skip_hedonic: bool = False,
    city: Optional[str] = None,
    train_tft: bool = False,
    enable_cache: bool = True,
) -> Dict[str, Any]:
    build_market_data(
        db_path=db_path,
        skip_migrations=skip_migrations,
        skip_macro=skip_macro,
        skip_market_indices=skip_market_indices,
        skip_hedonic=skip_hedonic,
        city=city,
        train_tft=train_tft,
    )
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
    listing_type: str = "all",
    limit: int = 0,
    lancedb_path: Optional[str] = None,
    clear: bool = False,
    batch_size: int = 200,
    model_name: Optional[str] = None,
    vlm_policy: Optional[str] = None,
    enable_cache: bool = True,
) -> Dict[str, Any]:
    indexed = build_vector_index(
        db_url=db_url,
        listing_type=listing_type,
        limit=limit,
        index_path=index_path,
        metadata_path=metadata_path,
        lancedb_path=lancedb_path,
        clear=clear,
        batch_size=batch_size,
        model_name=model_name,
        vlm_policy=vlm_policy,
    )
    return {"status": "ok", "indexed": indexed}


@task(retries=1, retry_delay_seconds=60)
def train_model_task(
    *,
    db_path: str,
    epochs: int,
    batch_size: int = 32,
    lr: float = 1e-4,
    patience: int = 10,
    device: str = "cpu",
) -> Dict[str, Any]:
    train_model(
        db_path=db_path,
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        patience=patience,
        device=device,
    )
    return {"status": "ok"}


@task(retries=3, retry_delay_seconds=60)
def vlm_backfill_task(*, db_path: str, override: bool = False, workers: int = 4) -> Dict[str, Any]:
    batch_process_vlm(db_path=db_path, override=override, max_workers=workers)
    return {"status": "ok"}


@task(retries=1, retry_delay_seconds=30)
def maintenance_clean_task(*, db_path: str) -> Dict[str, Any]:
    clean_data(db_path=db_path)
    return {"status": "ok"}


@task(retries=1, retry_delay_seconds=30)
def valuation_backfill_task(
    *,
    db_path: Optional[str] = None,
    db_url: Optional[str] = None,
    listing_type: str = "sale",
    limit: int = 0,
    max_age_days: int = 7,
    city: Optional[str] = None,
) -> int:
    resolved = resolve_db_url(db_url=db_url, db_path=db_path)
    return backfill_valuations(
        db_url=resolved,
        city=city,
        listing_type=listing_type,
        limit=limit,
        max_age_days=max_age_days,
    )


@flow(name="maintenance_flow")
def maintenance_flow(
    *,
    db_path: Optional[str] = None,
    run_vlm: bool = False,
    run_clean: bool = True,
    run_valuation: bool = False,
    vlm_override: bool = False,
    vlm_workers: int = 4,
    valuation_limit: int = 0,
    valuation_listing_type: str = "sale",
    valuation_city: Optional[str] = None,
    valuation_max_age_days: int = 7,
) -> Dict[str, Any]:
    logger = get_run_logger()
    app_config = load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)

    tracker = PipelineRunTracker(db_path=db_path)
    
    results = {}

    if run_clean:
        logger.info("maintenance_clean_start")
        _run_tracked(
            tracker,
            step_name="maintenance_clean",
            func=lambda: maintenance_clean_task(db_path=db_path),
            metadata={"db_path": db_path},
        )
        results["clean"] = "ok"

    if run_vlm:
        logger.info("maintenance_vlm_start")
        _run_tracked(
            tracker,
            step_name="vlm_backfill",
            func=lambda: vlm_backfill_task(
                db_path=db_path,
                override=vlm_override,
                workers=vlm_workers,
            ),
            metadata={
                "db_path": db_path,
                "override": vlm_override,
                "workers": vlm_workers,
            },
        )
        results["vlm"] = "ok"

    if run_valuation:
        logger.info("maintenance_valuation_start")
        count = _run_tracked(
            tracker,
            step_name="valuation_backfill",
            func=lambda: valuation_backfill_task(
                db_path=db_path,
                listing_type=valuation_listing_type,
                limit=valuation_limit,
                max_age_days=valuation_max_age_days,
                city=valuation_city,
            ),
            metadata={
                "db_path": db_path,
                "limit": valuation_limit,
                "listing_type": valuation_listing_type,
                "max_age_days": valuation_max_age_days,
                "city": valuation_city,
            },
        )
        results["valuation"] = count

    return results


@flow(name="transactions_flow")
def transactions_flow(
    *,
    db_path: Optional[str] = None,
    transactions_path: Optional[str] = None,
    listing_type: str = "sale",
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    logger = get_run_logger()
    app_config = load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)
    if transactions_path is None:
        transactions_path = str(app_config.paths.transactions_path)
    if not transactions_path or not transactions_path.strip():
        raise ValueError("transactions_path_missing")

    tracker = PipelineRunTracker(db_path=db_path)
    logger.info("prefect_transactions_ingest path=%s", transactions_path)
    result = _run_tracked(
        tracker,
        step_name="transactions_ingest",
        func=lambda: transactions_ingest_task(
            db_path=db_path,
            transactions_path=transactions_path,
            listing_type=listing_type,
            source_id=source_id,
        ),
        metadata={
            "db_path": db_path,
            "path": transactions_path,
            "listing_type": listing_type,
            "source_id": source_id,
        },
    )
    return {"status": "ok", "result": result}


@flow(name="market_data_flow")
def market_data_flow(
    *,
    db_path: Optional[str] = None,
    skip_migrations: bool = False,
    skip_macro: bool = False,
    skip_market_indices: bool = False,
    skip_hedonic: bool = False,
    city: Optional[str] = None,
    train_tft: bool = False,
    registries_only: bool = False,
    transactions: bool = False,
    transactions_path: Optional[str] = None,
    transactions_listing_type: str = "sale",
    transactions_source_id: Optional[str] = None,
    enable_cache: bool = True,
) -> Dict[str, Any]:
    logger = get_run_logger()
    app_config = load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)

    if registries_only:
        skip_migrations = True
        skip_macro = True
        skip_market_indices = True
        skip_hedonic = True

    tracker = PipelineRunTracker(db_path=db_path)
    _run_tracked(
        tracker,
        step_name="market_data",
        func=lambda: market_data_task(
            db_path=db_path,
            skip_migrations=skip_migrations,
            skip_macro=skip_macro,
            skip_market_indices=skip_market_indices,
            skip_hedonic=skip_hedonic,
            city=city,
            train_tft=train_tft,
            enable_cache=enable_cache,
        ),
        metadata={
            "db_path": db_path,
            "skip_migrations": skip_migrations,
            "skip_macro": skip_macro,
            "skip_market_indices": skip_market_indices,
            "skip_hedonic": skip_hedonic,
            "city": city,
            "train_tft": train_tft,
        },
    )

    results: Dict[str, Any] = {"market_data": "ok"}
    if transactions:
        tx_path = transactions_path or str(app_config.paths.transactions_path)
        logger.info("prefect_market_data_transactions path=%s", tx_path)
        _run_tracked(
            tracker,
            step_name="transactions_ingest",
            func=lambda: transactions_ingest_task(
                db_path=db_path,
                transactions_path=tx_path,
                listing_type=transactions_listing_type,
                source_id=transactions_source_id,
            ),
            metadata={
                "db_path": db_path,
                "path": tx_path,
                "listing_type": transactions_listing_type,
                "source_id": transactions_source_id,
            },
        )
        results["transactions"] = "ok"

    return results


@flow(name="build_index_flow")
def build_index_flow(
    *,
    db_url: Optional[str] = None,
    db_path: Optional[str] = None,
    listing_type: str = "all",
    limit: int = 0,
    index_path: Optional[str] = None,
    lancedb_path: Optional[str] = None,
    metadata_path: Optional[str] = None,
    clear: bool = False,
    batch_size: int = 200,
    model_name: Optional[str] = None,
    vlm_policy: Optional[str] = None,
    enable_cache: bool = True,
) -> Dict[str, Any]:
    logger = get_run_logger()
    app_config = load_app_config_safe()
    if db_path is None and db_url is None:
        db_path = str(app_config.pipeline.db_path)

    resolved = resolve_db_url(db_url=db_url, db_path=db_path)
    if index_path is None:
        index_path = str(app_config.pipeline.index_path)
    if metadata_path is None:
        metadata_path = str(app_config.pipeline.metadata_path)
    if lancedb_path is None:
        lancedb_path = str(app_config.valuation.retriever_lancedb_path)

    tracker = PipelineRunTracker(db_url=resolved)
    logger.info("prefect_build_index_start")
    result = _run_tracked(
        tracker,
        step_name="vector_index",
        func=lambda: build_vector_index_task(
            db_url=resolved,
            listing_type=listing_type,
            limit=limit,
            index_path=index_path,
            lancedb_path=lancedb_path,
            metadata_path=metadata_path,
            clear=clear,
            batch_size=batch_size,
            model_name=model_name,
            vlm_policy=vlm_policy,
            enable_cache=enable_cache,
        ),
        metadata={
            "db_url": resolved,
            "listing_type": listing_type,
            "limit": limit,
            "index_path": index_path,
            "lancedb_path": lancedb_path,
            "metadata_path": metadata_path,
            "clear": clear,
            "batch_size": batch_size,
            "model_name": model_name,
            "vlm_policy": vlm_policy,
        },
    )
    return {"status": "ok", "result": result}


@flow(name="training_flow")
def training_flow(
    *,
    db_path: Optional[str] = None,
    epochs: int = 100,
    batch_size: int = 16,
    lr: float = 1e-4,
    patience: int = 15,
    device: str = "cpu",
    run_vlm: bool = True,
    vlm_override: bool = False,
    vlm_workers: int = 4,
) -> Dict[str, Any]:
    logger = get_run_logger()
    app_config = load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)

    tracker = PipelineRunTracker(db_path=db_path)
    results: Dict[str, Any] = {}

    if run_vlm:
        logger.info("training_vlm_start")
        _run_tracked(
            tracker,
            step_name="vlm_backfill",
            func=lambda: vlm_backfill_task(
                db_path=db_path,
                override=vlm_override,
                workers=vlm_workers,
            ),
            metadata={
                "db_path": db_path,
                "override": vlm_override,
                "workers": vlm_workers,
            },
        )
        results["vlm"] = "ok"

    logger.info("training_model_start epochs=%s", epochs)
    _run_tracked(
        tracker,
        step_name="train_model",
        func=lambda: train_model_task(
            db_path=db_path,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            patience=patience,
            device=device,
        ),
        metadata={
            "db_path": db_path,
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": lr,
            "patience": patience,
            "device": device,
        },
    )
    results["train"] = "ok"
    return results


@flow(name="valuation_backfill_flow")
def valuation_backfill_flow(
    *,
    db_url: Optional[str] = None,
    db_path: Optional[str] = None,
    listing_type: str = "sale",
    limit: int = 0,
    max_age_days: int = 7,
    city: Optional[str] = None,
) -> Dict[str, Any]:
    app_config = load_app_config_safe()
    if db_path is None and db_url is None:
        db_url = resolve_db_url(
            db_url=app_config.pipeline.db_url,
            db_path=app_config.pipeline.db_path,
        )
    resolved = resolve_db_url(db_url=db_url, db_path=db_path)
    tracker = PipelineRunTracker(db_url=resolved)
    count = _run_tracked(
        tracker,
        step_name="valuation_backfill",
        func=lambda: valuation_backfill_task(
            db_url=resolved,
            listing_type=listing_type,
            limit=limit,
            max_age_days=max_age_days,
            city=city,
        ),
        metadata={
            "db_url": resolved,
            "listing_type": listing_type,
            "limit": limit,
            "max_age_days": max_age_days,
            "city": city,
        },
    )
    return {"processed": count}


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
            logger.info("prefect_preflight_crawl_backfill")
            _run_tracked(
                tracker,
                step_name="crawl_backfill",
                func=lambda: crawl_backfill_task(
                    source_ids=crawl_sources,
                    max_listings=max_listings,
                    max_pages=max_pages,
                    page_size=page_size,
                    run_vlm=run_vlm,
                    enable_cache=enable_cache,
                ),
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
        tx_path = transactions_path or str(app_config.paths.transactions_path)
        if not tx_path or not tx_path.strip():
            raise ValueError("transactions_path_missing")
        logger.info("prefect_preflight_transactions path=%s", tx_path)
        _run_tracked(
            tracker,
            step_name="transactions_ingest",
            func=lambda: transactions_ingest_task(
                db_path=db_path,
                transactions_path=tx_path,
            ),
            metadata={"path": tx_path},
        )
        results["steps"].append("transactions_ingest")

    if not skip_market_data:
        state = state_service.snapshot()
        if state.needs_market_data:
            logger.info("prefect_preflight_market_data")
            _run_tracked(
                tracker,
                step_name="market_data",
                func=lambda: market_data_task(
                    db_path=db_path,
                    enable_cache=enable_cache,
                ),
                metadata={"db_path": db_path},
            )
            results["steps"].append("market_data")

    if not skip_index:
        state = state_service.snapshot()
        if state.needs_index:
            logger.info("prefect_preflight_index")
            _run_tracked(
                tracker,
                step_name="vector_index",
                func=lambda: build_vector_index_task(
                    db_url=db_url,
                    index_path=str(app_config.pipeline.index_path),
                    metadata_path=str(app_config.pipeline.metadata_path),
                    enable_cache=enable_cache,
                ),
                metadata={
                    "db_url": db_url,
                    "index_path": str(app_config.pipeline.index_path),
                    "metadata_path": str(app_config.pipeline.metadata_path),
                },
            )
            results["steps"].append("vector_index")

    if not skip_training:
        state = state_service.snapshot()
        if state.needs_training:
            logger.info("prefect_preflight_training epochs=%s", train_epochs)
            _run_tracked(
                tracker,
                step_name="train_model",
                func=lambda: train_model_task(db_path=db_path, epochs=train_epochs),
                metadata={"db_path": db_path, "epochs": train_epochs},
            )
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


def add_maintenance_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    defaults = load_app_config_safe()
    parser.add_argument("--db", type=str, default=str(defaults.pipeline.db_path), help="SQLite DB path")
    parser.add_argument("--clean", action="store_true", default=False, help="Run clean-data")
    parser.add_argument("--vlm", action="store_true", default=False, help="Run VLM backfill")
    parser.add_argument("--valuation", action="store_true", default=False, help="Run Valuation backfill")
    parser.add_argument("--vlm-override", action="store_true", help="Override existing VLM descriptions")
    parser.add_argument("--vlm-workers", type=int, default=4)
    parser.add_argument("--valuation-limit", type=int, default=0)
    parser.add_argument(
        "--valuation-listing-type",
        type=str,
        default="sale",
        choices=["sale", "rent", "all"],
        help="Listing type filter for valuation backfill",
    )
    parser.add_argument("--valuation-city", type=str, default=None, help="City filter for valuation backfill")
    parser.add_argument("--valuation-max-age-days", type=int, default=7)
    return parser


def add_transactions_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
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
    return parser


def add_market_data_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    defaults = load_app_config_safe()
    parser.add_argument(
        "--db",
        type=str,
        default=str(defaults.pipeline.db_path),
        help="Path to SQLite DB",
    )
    parser.add_argument("--skip-migrations", action="store_true", help="Skip schema migrations")
    parser.add_argument("--skip-macro", action="store_true", help="Skip macro_indicators refresh")
    parser.add_argument("--skip-market-indices", action="store_true", help="Skip market_indices recompute")
    parser.add_argument("--skip-hedonic", action="store_true", help="Skip hedonic_indices recompute")
    parser.add_argument("--city", type=str, default=None, help="Only compute hedonic index for this city (lowercased)")
    parser.add_argument("--train-tft", action="store_true", help="Train TFT forecaster (requires hedonic indices)")
    parser.add_argument(
        "--registries-only",
        action="store_true",
        help="Run ONLY official registry ingestion (skips indices/macro)",
    )
    parser.add_argument("--transactions", action="store_true", help="Also ingest sold/transaction data from defaults")
    parser.add_argument("--transactions-path", type=str, default=None)
    parser.add_argument("--transactions-listing-type", type=str, default="sale", choices=["sale", "rent"])
    parser.add_argument("--transactions-source-id", type=str, default=None)
    parser.add_argument("--disable-cache", action="store_true", help="Disable Prefect task caching")
    return parser


def add_build_index_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    defaults = load_app_config_safe()
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="SQLAlchemy DB URL",
    )
    parser.add_argument("--db", type=str, default=None, help="SQLite DB path (optional)")
    parser.add_argument(
        "--listing-type",
        type=str,
        default="all",
        choices=["sale", "rent", "all"],
        help="Filter listings",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max listings to index (0 = no limit)")
    parser.add_argument(
        "--lancedb-path",
        type=str,
        default=str(defaults.valuation.retriever_lancedb_path),
        help="LanceDB index directory",
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
    parser.add_argument("--disable-cache", action="store_true", help="Disable Prefect task caching")
    return parser


def add_training_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    defaults = load_app_config_safe()
    parser.add_argument("--db", default=str(defaults.pipeline.db_path), help="SQLite DB path")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--skip-vlm", action="store_true", help="Skip VLM preprocessing before training")
    parser.add_argument("--vlm-override", action="store_true", help="Override existing VLM descriptions")
    parser.add_argument("--vlm-workers", type=int, default=4)
    return parser


def add_backfill_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    defaults = load_app_config_safe()
    parser.add_argument(
        "--db-url",
        type=str,
        default=str(resolve_db_url(db_url=defaults.pipeline.db_url, db_path=defaults.pipeline.db_path)),
        help="SQLAlchemy DB URL",
    )
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
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prefect orchestration entrypoint.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight", help="Run preflight as a Prefect flow")
    add_prefect_preflight_args(preflight_parser)
    
    deploy_parser = subparsers.add_parser("deploy", help="Register deployment with Prefect")
    add_prefect_preflight_args(deploy_parser)

    maintenance_parser = subparsers.add_parser("maintenance", help="Run maintenance as a Prefect flow")
    add_maintenance_args(maintenance_parser)

    transactions_parser = subparsers.add_parser("transactions", help="Ingest transactions as a Prefect flow")
    add_transactions_args(transactions_parser)

    market_data_parser = subparsers.add_parser("market-data", help="Run market data as a Prefect flow")
    add_market_data_args(market_data_parser)

    build_index_parser = subparsers.add_parser("build-index", help="Run vector index build as a Prefect flow")
    add_build_index_args(build_index_parser)

    training_parser = subparsers.add_parser("train-pipeline", help="Run VLM + training as a Prefect flow")
    add_training_args(training_parser)

    backfill_parser = subparsers.add_parser("backfill", help="Run valuation backfill as a Prefect flow")
    add_backfill_args(backfill_parser)

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

    elif args.command == "maintenance":
        if not (args.clean or args.vlm or args.valuation):
            parser.error("maintenance requires at least one of --clean, --vlm, or --valuation")

        maintenance_flow(
            db_path=args.db,
            run_clean=args.clean,
            run_vlm=args.vlm,
            run_valuation=args.valuation,
            vlm_override=args.vlm_override,
            vlm_workers=args.vlm_workers,
            valuation_limit=args.valuation_limit,
            valuation_listing_type=args.valuation_listing_type,
            valuation_city=args.valuation_city,
            valuation_max_age_days=args.valuation_max_age_days,
        )
        return 0

    elif args.command == "transactions":
        transactions_flow(
            db_path=args.db,
            transactions_path=args.path,
            listing_type=args.listing_type,
            source_id=args.source_id,
        )
        return 0

    elif args.command == "market-data":
        market_data_flow(
            db_path=args.db,
            skip_migrations=args.skip_migrations,
            skip_macro=args.skip_macro,
            skip_market_indices=args.skip_market_indices,
            skip_hedonic=args.skip_hedonic,
            city=args.city,
            train_tft=args.train_tft,
            registries_only=args.registries_only,
            transactions=args.transactions,
            transactions_path=args.transactions_path,
            transactions_listing_type=args.transactions_listing_type,
            transactions_source_id=args.transactions_source_id,
            enable_cache=not args.disable_cache,
        )
        return 0

    elif args.command == "build-index":
        build_index_flow(
            db_url=args.db_url,
            db_path=args.db,
            listing_type=args.listing_type,
            limit=args.limit,
            lancedb_path=args.lancedb_path,
            metadata_path=args.metadata_path,
            clear=args.clear,
            batch_size=args.batch_size,
            model_name=args.model_name,
            vlm_policy=args.vlm_policy,
            enable_cache=not args.disable_cache,
        )
        return 0

    elif args.command == "train-pipeline":
        training_flow(
            db_path=args.db,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            patience=args.patience,
            device=args.device,
            run_vlm=not args.skip_vlm,
            vlm_override=args.vlm_override,
            vlm_workers=args.vlm_workers,
        )
        return 0

    elif args.command == "backfill":
        valuation_backfill_flow(
            db_url=args.db_url,
            listing_type=args.listing_type,
            limit=args.limit,
            max_age_days=args.max_age_days,
            city=args.city,
        )
        return 0

    elif args.command == "deploy":
        from prefect.deployments import Deployment

        deployment = Deployment.build_from_flow(
            flow=preflight_flow,
            name="daily-preflight",
            work_queue_name="default",
            parameters={
                "db_path": args.db,
                "skip_training": False,
                # Add reasonable defaults for a daily background run
                "max_listings": 100, 
            },
            entrypoint="src/platform/workflows/prefect_orchestration.py:preflight_flow",
        )
        deployment.apply()
        print("Deployment 'daily-preflight' applied! Run 'prefect agent start -q default' to execute schedules.")
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
