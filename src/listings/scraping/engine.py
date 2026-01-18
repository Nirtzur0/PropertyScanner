from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

import structlog

from src.listings.scraping.pydoll_engine import PydollEngine, PydollEngineConfig

logger = structlog.get_logger(__name__)

class PydollFetcher:
    def __init__(
        self,
        user_agent: str,
        *,
        headless: bool = True,
        wait_s: float = 8.0,
        max_concurrency: int = 1,
        pydoll_config: Optional[dict[str, Any]] = None,
    ) -> None:
        self._engine_config = PydollEngineConfig.from_dict(
            pydoll_config,
            user_agent=user_agent,
            headless=headless,
            wait_s=wait_s,
            max_concurrency=max_concurrency,
        )
        self._engine = PydollEngine(self._engine_config)
        self._semaphore = (
            threading.BoundedSemaphore(max_concurrency)
            if max_concurrency and max_concurrency > 0
            else None
        )

    def is_available(self) -> bool:
        return self._engine.is_available()

    @property
    def engine(self) -> PydollEngine:
        return self._engine

    def fetch(self, url: str, *, timeout_s: float = 30.0) -> Optional[str]:
        try:
            if self._semaphore:
                with self._semaphore:
                    return _run_async(self._engine.fetch_html(url, timeout_s=timeout_s))
            return _run_async(self._engine.fetch_html(url, timeout_s=timeout_s))
        except Exception as exc:
            logger.warning("pydoll_fetch_failed", url=url, error=str(exc))
            return None


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        raise RuntimeError("pydoll_fetch_in_running_loop")
    return loop.run_until_complete(coro)
