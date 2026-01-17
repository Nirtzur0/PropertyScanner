from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import structlog

from src.listings.agents.factory import AgentFactory
from src.listings.repositories.listings import ListingsRepository
from src.listings.services.feature_fusion import FeatureFusionService
from src.listings.services.listing_augmenter import ListingAugmentor
from src.listings.services.listing_persistence import ListingPersistenceService
from src.listings.services.quality_gate import ListingQualityGate
from src.listings.utils.seen_url_store import SeenUrlStore
from src.platform.db.base import resolve_db_url
from src.platform.domain.schema import RawListing, CanonicalListing
from src.platform.settings import AppConfig
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.config import ConfigLoader, load_app_config_safe

logger = structlog.get_logger(__name__)


@dataclass
class UnifiedSourcePlan:
    source_id: str
    search_urls: List[str] = field(default_factory=list)
    search_path: Optional[str] = None
    start_url: Optional[str] = None
    listing_urls: List[str] = field(default_factory=list)
    listing_ids: List[str] = field(default_factory=list)
    max_listings: int = 0
    max_pages: int = 1
    page_size: int = 24
    crawler_config: Dict[str, Any] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedCrawlSettings:
    source_workers: int = 2
    fusion_workers: int = 4
    vlm_concurrency: int = 1
    run_vlm: bool = True
    enable_fusion: bool = True
    enable_augment: bool = True
    dedupe: bool = True
    persist_batch_size: int = 25
    seen_mode_prefix: str = "unified"


class FusionPool:
    def __init__(
        self,
        *,
        app_config: AppConfig,
        max_workers: int,
        run_vlm: bool,
        vlm_concurrency: int,
    ) -> None:
        self.run_vlm = run_vlm
        self.max_workers = max(1, int(max_workers))
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._local = threading.local()
        self._vlm_semaphore = (
            threading.BoundedSemaphore(vlm_concurrency)
            if run_vlm and vlm_concurrency > 0
            else None
        )
        self._app_config = app_config

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def _fuse_one(self, listing: CanonicalListing) -> CanonicalListing:
        service = getattr(self._local, "service", None)
        if service is None:
            service = FeatureFusionService(app_config=self._app_config)
            self._local.service = service

        if self.run_vlm and self._vlm_semaphore:
            with self._vlm_semaphore:
                return service.fuse(listing, run_vlm=True)
        return service.fuse(listing, run_vlm=False)

    def process(self, listings: List[CanonicalListing]) -> List[CanonicalListing]:
        if not listings:
            return []
        if self.max_workers <= 1 or len(listings) == 1:
            return [self._fuse_one(item) for item in listings]

        indexed = list(enumerate(listings))
        results: List[tuple[int, CanonicalListing]] = []
        futures = {
            self._executor.submit(self._fuse_one, item): idx for idx, item in indexed
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results.append((idx, future.result()))
            except Exception as exc:
                logger.warning("fusion_failed", id=getattr(listings[idx], "id", None), error=str(exc))
        results.sort(key=lambda item: item[0])
        return [item[1] for item in results]


class UnifiedCrawlRunner:
    def __init__(
        self,
        *,
        app_config: Optional[AppConfig] = None,
        db_url: Optional[str] = None,
        seen_urls_db: Optional[str] = None,
        settings: Optional[UnifiedCrawlSettings] = None,
    ) -> None:
        self.app_config = app_config or load_app_config_safe()
        self.settings = settings or UnifiedCrawlSettings()
        self.db_url = resolve_db_url(
            db_url=db_url or self.app_config.pipeline.db_url,
            db_path=self.app_config.pipeline.db_path,
        )
        self.listings_repo = ListingsRepository(db_url=self.db_url)
        self.persistence = ListingPersistenceService(self.listings_repo)
        self.augmenter = ListingAugmentor(self.db_url)
        self.quality_gate = ListingQualityGate(self.app_config.quality_gate)
        self.compliance = ComplianceManager(self.app_config.agents.defaults.uastring)
        seen_path = seen_urls_db or str(Path(self.app_config.paths.data_dir) / "unified_seen_urls.sqlite3")
        self.seen_store = SeenUrlStore(path=seen_path)
        self.fusion_pool = None
        if self.settings.enable_fusion:
            self.fusion_pool = FusionPool(
                app_config=self.app_config,
                max_workers=self.settings.fusion_workers,
                run_vlm=self.settings.run_vlm,
                vlm_concurrency=self.settings.vlm_concurrency,
            )

    def close(self) -> None:
        if self.fusion_pool:
            self.fusion_pool.close()
        if self.seen_store:
            self.seen_store.close()

    def _build_payload(self, plan: UnifiedSourcePlan) -> Dict[str, Any]:
        payload = dict(plan.payload or {})
        if plan.search_urls:
            if len(plan.search_urls) == 1:
                payload.setdefault("start_url", plan.search_urls[0])
            else:
                payload.setdefault("start_urls", plan.search_urls)
        if plan.start_url:
            payload.setdefault("start_url", plan.start_url)
        if plan.search_path:
            payload.setdefault("search_path", plan.search_path)
        if plan.listing_urls:
            payload.setdefault("target_urls", plan.listing_urls)
        if plan.listing_ids:
            payload.setdefault("listing_ids", plan.listing_ids)
        if plan.max_listings:
            payload.setdefault("max_listings", plan.max_listings)
        if plan.max_pages:
            payload.setdefault("max_pages", plan.max_pages)
        if plan.page_size:
            payload.setdefault("page_size", plan.page_size)
        return payload

    def _normalize_raw(self, raw_listings: Iterable[Any]) -> List[RawListing]:
        normalized: List[RawListing] = []
        for item in raw_listings:
            if isinstance(item, RawListing):
                normalized.append(item)
            elif isinstance(item, dict):
                normalized.append(RawListing(**item))
        return normalized

    def _apply_quality_gate(
        self, listings: List[CanonicalListing]
    ) -> tuple[List[CanonicalListing], List[Dict[str, Any]]]:
        valid: List[CanonicalListing] = []
        invalid: List[Dict[str, Any]] = []
        for listing in listings:
            reasons = self.quality_gate.validate_listing(listing)
            if reasons:
                invalid.append({"id": listing.id, "reasons": reasons})
            else:
                valid.append(listing)
        return valid, invalid

    def _persist_listings(self, listings: List[CanonicalListing]) -> int:
        if not listings:
            return 0
        batch_size = max(1, int(self.settings.persist_batch_size))
        saved = 0
        for idx in range(0, len(listings), batch_size):
            batch = listings[idx : idx + batch_size]
            saved += self.persistence.save_listings(batch)
        return saved

    def _dedupe_raw(self, source_id: str, raw_listings: List[RawListing]) -> List[RawListing]:
        if not self.settings.dedupe or not raw_listings:
            return raw_listings
        urls = [getattr(item, "url", None) for item in raw_listings if getattr(item, "url", None)]
        if not urls:
            return raw_listings
        mode = f"{self.settings.seen_mode_prefix}:{source_id}"
        new_urls = set(self.seen_store.insert_new(mode, urls))
        if not new_urls:
            return []
        return [item for item in raw_listings if getattr(item, "url", None) in new_urls]

    def run_source(self, plan: UnifiedSourcePlan) -> Dict[str, Any]:
        crawler_config = {"id": plan.source_id}
        crawler_config.update(plan.crawler_config or {})
        payload = self._build_payload(plan)
        logger.info("unified_crawl_start", source=plan.source_id, payload=payload)

        crawler = AgentFactory.create_crawler(plan.source_id, crawler_config, self.compliance)
        crawl_response = crawler.run(payload)
        raw_listings = self._normalize_raw(crawl_response.data or [])

        raw_listings = self._dedupe_raw(plan.source_id, raw_listings)
        if not raw_listings:
            return {
                "source_id": plan.source_id,
                "crawled": 0,
                "normalized": 0,
                "saved": 0,
                "invalid": 0,
                "errors": crawl_response.errors or [],
            }

        normalizer = AgentFactory.create_normalizer(plan.source_id)
        norm_response = normalizer.run({"raw_listings": raw_listings})
        canonical_listings = list(norm_response.data or [])

        valid, invalid = self._apply_quality_gate(canonical_listings)
        if self.settings.enable_fusion and valid and self.fusion_pool:
            valid = self.fusion_pool.process(valid)
        if self.settings.enable_augment and valid:
            valid = self.augmenter.augment_listings(valid)

        saved = self._persist_listings(valid)
        errors = []
        if crawl_response.errors:
            errors.extend(crawl_response.errors)
        if norm_response.errors:
            errors.extend(norm_response.errors)

        return {
            "source_id": plan.source_id,
            "crawled": len(raw_listings),
            "normalized": len(canonical_listings),
            "saved": saved,
            "invalid": len(invalid),
            "errors": errors,
        }

    def run(self, plans: List[UnifiedSourcePlan]) -> List[Dict[str, Any]]:
        if not plans:
            return []
        max_workers = max(1, int(self.settings.source_workers))
        max_workers = min(max_workers, len(plans))
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self.run_source, plan): plan for plan in plans}
            for future in as_completed(future_map):
                plan = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.error("unified_crawl_failed", source=plan.source_id, error=str(exc))
                    results.append(
                        {
                            "source_id": plan.source_id,
                            "crawled": 0,
                            "normalized": 0,
                            "saved": 0,
                            "invalid": 0,
                            "errors": [str(exc)],
                        }
                    )
        return results


def _parse_json_arg(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _shard_key(value: str, shard_count: int) -> int:
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()
    return int(digest, 16) % shard_count


def _apply_sharding(
    plans: List[UnifiedSourcePlan],
    *,
    shard_index: Optional[int],
    shard_count: Optional[int],
) -> List[UnifiedSourcePlan]:
    if shard_index is None or shard_count is None:
        return plans
    shard_count = int(shard_count)
    if shard_count <= 1:
        return plans
    shard_index = int(shard_index) % shard_count

    sharded: List[UnifiedSourcePlan] = []
    for plan in plans:
        search_urls = [u for u in plan.search_urls if _shard_key(u, shard_count) == shard_index]
        listing_urls = [u for u in plan.listing_urls if _shard_key(u, shard_count) == shard_index]
        listing_ids = [lid for lid in plan.listing_ids if _shard_key(lid, shard_count) == shard_index]

        plan.search_urls = search_urls
        plan.listing_urls = listing_urls
        plan.listing_ids = listing_ids

        has_work = bool(search_urls or listing_urls or listing_ids or plan.start_url or plan.search_path)
        if not has_work:
            if _shard_key(plan.source_id, shard_count) != shard_index:
                continue
        sharded.append(plan)

    return sharded


def _plans_from_config(
    config_loader: ConfigLoader,
    *,
    source_ids: Optional[List[str]],
    search_urls: Optional[List[str]],
    search_path: Optional[str],
    listing_urls: Optional[List[str]],
    listing_ids: Optional[List[str]],
    max_listings: int,
    max_pages: int,
    page_size: int,
    crawler_config: Dict[str, Any],
) -> List[UnifiedSourcePlan]:
    if source_ids:
        selected = source_ids
    else:
        selected = [s.id for s in config_loader.sources.sources if s.enabled]

    plans = []
    for source_id in selected:
        plans.append(
            UnifiedSourcePlan(
                source_id=source_id,
                search_urls=search_urls or [],
                search_path=search_path,
                listing_urls=listing_urls or [],
                listing_ids=listing_ids or [],
                max_listings=max_listings,
                max_pages=max_pages,
                page_size=page_size,
                crawler_config=dict(crawler_config),
            )
        )
    return plans


def _load_plan_file(path: str) -> tuple[List[UnifiedSourcePlan], UnifiedCrawlSettings]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Plan file must be a JSON object")

    settings_raw = data.get("settings", {})
    settings = UnifiedCrawlSettings(
        source_workers=int(settings_raw.get("source_workers", 2)),
        fusion_workers=int(settings_raw.get("fusion_workers", 4)),
        vlm_concurrency=int(settings_raw.get("vlm_concurrency", 1)),
        run_vlm=bool(settings_raw.get("run_vlm", True)),
        enable_fusion=bool(settings_raw.get("enable_fusion", True)),
        enable_augment=bool(settings_raw.get("enable_augment", True)),
        dedupe=bool(settings_raw.get("dedupe", True)),
        persist_batch_size=int(settings_raw.get("persist_batch_size", 25)),
        seen_mode_prefix=str(settings_raw.get("seen_mode_prefix", "unified")),
    )

    plans: List[UnifiedSourcePlan] = []
    for item in data.get("sources", []):
        if not isinstance(item, dict):
            continue
        source_id = item.get("source_id") or item.get("id")
        if not source_id:
            continue
        plans.append(
            UnifiedSourcePlan(
                source_id=source_id,
                search_urls=item.get("search_urls", []) or [],
                search_path=item.get("search_path"),
                start_url=item.get("start_url"),
                listing_urls=item.get("listing_urls", []) or [],
                listing_ids=item.get("listing_ids", []) or [],
                max_listings=int(item.get("max_listings", 0)),
                max_pages=int(item.get("max_pages", 1)),
                page_size=int(item.get("page_size", 24)),
                crawler_config=item.get("crawler_config", {}) or {},
                payload=item.get("payload", {}) or {},
            )
        )

    return plans, settings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Unified crawl runner for multi-source harvesting.")
    parser.add_argument("--plan", help="Path to JSON crawl plan file")
    parser.add_argument("--source", action="append", help="Source id (repeatable)")
    parser.add_argument("--search-url", action="append", help="Search URL (repeatable)")
    parser.add_argument("--search-path", help="Search path (e.g. /for-sale/property/london/)")
    parser.add_argument("--listing-url", action="append", help="Listing URL (repeatable)")
    parser.add_argument("--listing-id", action="append", help="Listing id (repeatable)")
    parser.add_argument("--max-listings", type=int, default=0, help="Limit listings per source")
    parser.add_argument("--max-pages", type=int, default=1, help="Max search pages (where supported)")
    parser.add_argument("--page-size", type=int, default=24, help="Search page size (where supported)")
    parser.add_argument("--source-workers", type=int, default=2, help="Parallel sources to crawl")
    parser.add_argument("--fusion-workers", type=int, default=4, help="Parallel fusion workers")
    parser.add_argument("--vlm-concurrency", type=int, default=1, help="Concurrent VLM requests")
    parser.add_argument("--no-fusion", action="store_true", help="Disable LLM/VLM fusion")
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM within fusion")
    parser.add_argument("--no-augment", action="store_true", help="Disable enrichment/rent estimation")
    parser.add_argument("--no-dedupe", action="store_true", help="Disable seen-url de-duplication")
    parser.add_argument("--seen-db", help="Override path for seen-url SQLite DB")
    parser.add_argument("--shard-index", type=int, help="Shard index for distributed runs")
    parser.add_argument("--shard-count", type=int, help="Total number of shards")
    parser.add_argument("--crawler-config", help="JSON object applied to each crawler")
    parser.add_argument("--output", help="Path to write JSON summary")
    args = parser.parse_args(argv)

    config_loader = ConfigLoader()

    if args.plan:
        plans, settings = _load_plan_file(args.plan)
        if args.no_fusion:
            settings.enable_fusion = False
        if args.no_vlm:
            settings.run_vlm = False
        if args.no_augment:
            settings.enable_augment = False
        if args.no_dedupe:
            settings.dedupe = False
        if args.source_workers:
            settings.source_workers = args.source_workers
        if args.fusion_workers:
            settings.fusion_workers = args.fusion_workers
        if args.vlm_concurrency is not None:
            settings.vlm_concurrency = args.vlm_concurrency
    else:
        crawler_config = _parse_json_arg(args.crawler_config)
        plans = _plans_from_config(
            config_loader,
            source_ids=args.source,
            search_urls=args.search_url,
            search_path=args.search_path,
            listing_urls=args.listing_url,
            listing_ids=args.listing_id,
            max_listings=args.max_listings,
            max_pages=args.max_pages,
            page_size=args.page_size,
            crawler_config=crawler_config,
        )
        settings = UnifiedCrawlSettings(
            source_workers=args.source_workers,
            fusion_workers=args.fusion_workers,
            vlm_concurrency=args.vlm_concurrency,
            run_vlm=not args.no_vlm,
            enable_fusion=not args.no_fusion,
            enable_augment=not args.no_augment,
            dedupe=not args.no_dedupe,
        )

    if not plans:
        print("No crawl plans found.")
        return 1

    plans = _apply_sharding(plans, shard_index=args.shard_index, shard_count=args.shard_count)
    if not plans:
        print("No crawl plans assigned to this shard.")
        return 1

    runner = UnifiedCrawlRunner(
        app_config=config_loader.app,
        settings=settings,
        seen_urls_db=args.seen_db,
    )
    try:
        results = runner.run(plans)
    finally:
        runner.close()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=True, indent=2)
    else:
        print(json.dumps(results, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
