from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, Iterable, Optional

import structlog

from src.platform.utils.stealth_requests import create_session, request_get
from src.listings.scraping.pydoll_engine import PydollEngine, PydollEngineConfig

logger = structlog.get_logger(__name__)

_CHALLENGE_HINTS = (
    "captcha",
    "cloudflare",
    "just a moment",
    "enable javascript",
    "verify you are human",
    "access denied",
)

_ENGINE_ALIASES = {
    "http": "http",
    "requests": "http",
    "browser": "pydoll",
    "pydoll": "pydoll",
    "playwright": "playwright",
}

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None

try:
    from playwright_stealth import Stealth
except Exception:  # pragma: no cover - optional dependency
    Stealth = None


class HttpFetcher:
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._local = threading.local()

    def _get_session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = create_session(self.user_agent)
            self._local.session = session
        return session

    def is_available(self) -> bool:
        return True

    def fetch(self, url: str, *, timeout_s: float = 30.0) -> Optional[str]:
        session = self._get_session()
        try:
            response = request_get(session, url, timeout=timeout_s)
        except Exception as exc:
            logger.warning("http_fetch_failed", url=url, error=str(exc))
            return None

        if response and getattr(response, "status_code", None) == 200:
            html = getattr(response, "text", None)
            return html if html else None
        status = getattr(response, "status_code", None)
        logger.warning("http_fetch_status", url=url, status=status)
        return None


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


class PlaywrightFetcher:
    def __init__(
        self,
        user_agent: str,
        *,
        headless: bool = True,
        wait_s: float = 2.0,
        max_concurrency: int = 1,
    ) -> None:
        self.user_agent = user_agent
        self.headless = headless
        self.wait_s = wait_s
        self._available = sync_playwright is not None
        self._semaphore = (
            threading.BoundedSemaphore(max_concurrency)
            if max_concurrency and max_concurrency > 0
            else None
        )

    def is_available(self) -> bool:
        return self._available

    def fetch(self, url: str, *, timeout_s: float = 30.0) -> Optional[str]:
        if not self._available:
            return None
        try:
            if self._semaphore:
                with self._semaphore:
                    return self._fetch_sync(url, timeout_s=timeout_s)
            return self._fetch_sync(url, timeout_s=timeout_s)
        except Exception as exc:
            logger.warning("playwright_fetch_failed", url=url, error=str(exc))
            return None

    def _fetch_sync(self, url: str, *, timeout_s: float) -> Optional[str]:
        if not sync_playwright:
            return None
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context_kwargs: Dict[str, object] = {}
            if self.user_agent:
                context_kwargs["user_agent"] = self.user_agent
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            if Stealth:
                try:
                    Stealth().apply_stealth_sync(page)
                except Exception:
                    pass
            page.goto(url, timeout=int(timeout_s * 1000), wait_until="domcontentloaded")
            if self.wait_s:
                time.sleep(self.wait_s)
            html = page.content()
            browser.close()
            return html


class ScrapeEngine:
    def __init__(
        self,
        fetchers: Dict[str, object],
        order: Iterable[str],
        *,
        allow_fallback: bool = True,
    ) -> None:
        self.fetchers = fetchers
        self.order = list(order)
        self.allow_fallback = allow_fallback

    def fetch(self, url: str, *, timeout_s: float = 30.0) -> Optional[str]:
        for name in self.order:
            fetcher = self.fetchers.get(name)
            if not fetcher:
                continue
            if hasattr(fetcher, "is_available") and not fetcher.is_available():
                continue
            html = fetcher.fetch(url, timeout_s=timeout_s)
            if html and not _is_challenge_page(html):
                return html
            if not self.allow_fallback:
                break
        return None


def resolve_engine_order(
    *,
    engine_order: Optional[Iterable[str]],
    prefer_browser: bool,
    prefer_playwright: bool,
    enable_browser: bool,
    enable_playwright: bool,
) -> list[str]:
    if isinstance(engine_order, str):
        items = [part.strip() for part in engine_order.split(",") if part.strip()]
    else:
        items = list(engine_order or [])

    if items:
        normalized = []
        for item in items:
            name = _normalize_engine_name(item)
            if name:
                normalized.append(name)
        order = normalized
    else:
        order = []
        if prefer_playwright:
            order.append("playwright")
        if prefer_browser:
            order.append("pydoll")
        order.append("http")
        if not prefer_browser:
            order.append("pydoll")
        if not prefer_playwright:
            order.append("playwright")

    final = []
    for name in order:
        if name == "pydoll" and not enable_browser:
            continue
        if name == "playwright" and not enable_playwright:
            continue
        if name not in final:
            final.append(name)
    return final


def _normalize_engine_name(raw: str) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).strip().lower()
    return _ENGINE_ALIASES.get(key)


def _is_challenge_page(html: str) -> bool:
    if not html:
        return True
    text = html.lower()
    return any(token in text for token in _CHALLENGE_HINTS)


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        raise RuntimeError("pydoll_fetch_in_running_loop")
    return loop.run_until_complete(coro)
