from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

import structlog

from src.listings.scraping.browser_engine import BrowserEngine, BrowserEngineConfig

logger = structlog.get_logger(__name__)

class BrowserFetcher:
    def __init__(
        self,
        user_agent: str,
        *,
        headless: bool = True,
        wait_s: float = 8.0,
        max_concurrency: int = 1,
        browser_config: Optional[dict[str, Any]] = None,
    ) -> None:
        self._engine_config = BrowserEngineConfig.from_dict(
            browser_config,
            user_agent=user_agent,
            headless=headless,
            wait_s=wait_s,
            max_concurrency=max_concurrency,
        )
        self._engine = BrowserEngine(self._engine_config)
        self._semaphore = (
            threading.BoundedSemaphore(max_concurrency)
            if max_concurrency and max_concurrency > 0
            else None
        )

    def is_available(self) -> bool:
        return self._engine.is_available()

    @property
    def engine(self) -> BrowserEngine:
        return self._engine

    def fetch(self, url: str, *, timeout_s: float = 30.0) -> Optional[str]:
        try:
            if self._semaphore:
                with self._semaphore:
                    return _run_async(self._engine.fetch_html(url, timeout_s=timeout_s))
            return _run_async(self._engine.fetch_html(url, timeout_s=timeout_s))
        except RuntimeError as exc:
            if str(exc) == "pydoll_fetch_in_running_loop":
                raise
            logger.warning("browser_fetch_failed", url=url, error=str(exc))
            return None
        except Exception as exc:
            logger.warning("browser_fetch_failed", url=url, error=str(exc))
            return None

    async def fetch_async(self, url: str, *, timeout_s: float = 30.0) -> Optional[str]:
        return await self._engine.fetch_html(url, timeout_s=timeout_s)

    async def fetch_many_async(
        self,
        urls: list[str],
        *,
        timeout_s: float = 30.0,
        max_concurrency: Optional[int] = None,
        preflight=None,
    ):
        return await self._engine.fetch_many(
            urls,
            timeout_s=timeout_s,
            max_concurrency=max_concurrency,
            preflight=preflight,
        )

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        raise RuntimeError("pydoll_fetch_in_running_loop")
    return loop.run_until_complete(coro)
