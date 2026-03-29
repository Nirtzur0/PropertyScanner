"""
FusionPool — thread-pool for parallel VLM / text-analysis enrichment.

Extracted from :mod:`unified_crawl` so it can be tested and configured
independently of the crawl orchestration.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import structlog

from src.listings.services.feature_fusion import FeatureFusionService
from src.platform.domain.schema import CanonicalListing
from src.platform.settings import AppConfig

logger = structlog.get_logger(__name__)


class FusionPool:
    """Thread pool that enriches listings via :class:`FeatureFusionService`.

    Each worker thread gets its own ``FeatureFusionService`` instance
    (stored in thread-local storage).  VLM calls are serialised through
    a bounded semaphore to avoid overloading the VLM API.
    """

    def __init__(
        self,
        *,
        app_config: AppConfig,
        max_workers: int = 4,
        run_vlm: bool = True,
        vlm_concurrency: int = 1,
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
        results: list[tuple[int, CanonicalListing]] = []
        futures = {
            self._executor.submit(self._fuse_one, item): idx for idx, item in indexed
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results.append((idx, future.result()))
            except Exception as exc:
                logger.warning(
                    "fusion_failed",
                    id=getattr(listings[idx], "id", None),
                    error=str(exc),
                )
        results.sort(key=lambda item: item[0])
        return [item[1] for item in results]
