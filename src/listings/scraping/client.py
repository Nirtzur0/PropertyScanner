from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup

from src.listings.crawl_contract import detect_block_reason_from_html
from src.listings.scraping.engine import BrowserFetcher, _run_async
from src.listings.utils.seen_url_store import SeenUrlStore
from src.listings.services.snapshot_storage import SnapshotService
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


@dataclass
class LinkExtractorSpec:
    selectors: Iterable[str]
    include: Iterable[str] = ()
    exclude: Iterable[str] = ()
    attr: str = "href"
    limit: Optional[int] = None


@dataclass
class FetchResult:
    url: str
    html: Optional[str]
    error: Optional[str] = None


class ScrapeClient:
    def __init__(
        self,
        *,
        source_id: str,
        base_url: str,
        compliance_manager: ComplianceManager,
        user_agent: str,
        rate_limit_seconds: float,
        browser_wait_s: float = 8.0,
        browser_max_concurrency: Optional[int] = None,
        browser_config: Optional[dict[str, Any]] = None,
        seen_store: Optional[SeenUrlStore] = None,
        seen_mode: Optional[str] = None,
    ) -> None:
        self.source_id = source_id
        self.base_url = base_url
        self.compliance_manager = compliance_manager
        self.rate_limit_seconds = rate_limit_seconds
        self.snapshot_service = SnapshotService()
        self.seen_store = seen_store or SeenUrlStore()
        self.seen_mode = seen_mode or f"fetch:{self.source_id}"
        resolved_concurrency = max(1, int(browser_max_concurrency or 4))

        self.browser_fetcher = BrowserFetcher(
            user_agent,
            wait_s=browser_wait_s,
            max_concurrency=resolved_concurrency,
            browser_config=browser_config,
        )
        self.browser_engine = self.browser_fetcher.engine

    def _filter_seen_urls(self, urls: list[str]) -> list[str]:
        if not urls or not self.seen_store:
            return urls
        new_urls = self.seen_store.insert_new(self.seen_mode, urls)
        skipped = len(urls) - len(new_urls)
        if skipped:
            logger.info(
                "seen_urls_skipped",
                source_id=self.source_id,
                skipped=skipped,
                kept=len(new_urls),
            )
        return new_urls

    @staticmethod
    def _running_loop() -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return loop.is_running()

    def fetch_html(
        self,
        url: str,
        *,
        retries: int = 3,
        timeout_s: float = 30.0,
        backoff_base: float = 1.4,
        skip_compliance: bool = False,
    ) -> Optional[str]:
        if self._running_loop():
            raise RuntimeError("scrape_client_async_required")
        if not skip_compliance:
            decision = (
                self.compliance_manager.assess_url(url, rate_limit_seconds=self.rate_limit_seconds)
                if hasattr(self.compliance_manager, "assess_url")
                else None
            )
            allowed = bool(decision.allowed) if decision is not None else self.compliance_manager.check_and_wait(
                url, rate_limit_seconds=self.rate_limit_seconds
            )
            if not allowed:
                logger.warning(
                    "crawler_blocked_by_robots",
                    url=url,
                    reason=getattr(decision, "reason", None),
                )
                return None

        for attempt in range(retries):
            html = self.browser_fetcher.fetch(url, timeout_s=timeout_s)
            if html:
                return html
            time.sleep(backoff_base ** attempt)

        return None

    async def fetch_html_async(
        self,
        url: str,
        *,
        retries: int = 3,
        timeout_s: float = 30.0,
        backoff_base: float = 1.4,
        skip_compliance: bool = False,
    ) -> Optional[str]:
        if not skip_compliance:
            if hasattr(self.compliance_manager, "assess_url"):
                decision = await asyncio.to_thread(
                    self.compliance_manager.assess_url, url, self.rate_limit_seconds
                )
                allowed = bool(getattr(decision, "allowed", False))
                reason = getattr(decision, "reason", None)
            else:
                decision = None
                allowed = await asyncio.to_thread(
                    self.compliance_manager.check_and_wait, url, self.rate_limit_seconds
                )
                reason = None
            if not allowed:
                logger.warning("crawler_blocked_by_robots", url=url, reason=reason)
                return None

        for attempt in range(retries):
            html = await self.browser_fetcher.fetch_async(url, timeout_s=timeout_s)
            if html:
                return html
            await asyncio.sleep(backoff_base ** attempt)

        return None

    def fetch_html_batch(
        self,
        urls: Iterable[str],
        *,
        max_workers: Optional[int] = None,
        timeout_s: float = 30.0,
        retries: int = 3,
    ) -> list[FetchResult]:
        if self._running_loop():
            raise RuntimeError("scrape_client_async_required")
        url_list = [u for u in urls if u]
        if not url_list:
            return []

        deduped = list(dict.fromkeys(url_list))
        deduped = self._filter_seen_urls(deduped)
        if not deduped:
            return []
        max_concurrency = max_workers if max_workers is not None else None
        preflight_errors: dict[str, str] = {}

        async def preflight(url: str) -> bool:
            if hasattr(self.compliance_manager, "assess_url"):
                decision = await asyncio.to_thread(
                    self.compliance_manager.assess_url, url, self.rate_limit_seconds
                )
                if not bool(getattr(decision, "allowed", False)):
                    reason = str(getattr(decision, "reason", "") or "preflight")
                    prefix = "policy_blocked" if reason.startswith("robots_") else "blocked"
                    preflight_errors[url] = f"{prefix}:{reason}:{url}"
                    return False
                return True
            return await asyncio.to_thread(
                self.compliance_manager.check_and_wait, url, self.rate_limit_seconds
            )

        try:
            browser_results = _run_async(
                self.browser_engine.fetch_many(
                    deduped,
                    timeout_s=timeout_s,
                    max_concurrency=max_concurrency,
                    preflight=preflight,
                )
            )
        except Exception as exc:
            logger.warning("browser_batch_failed", error=str(exc))
            results = []
            for url in deduped:
                html = self.fetch_html(url, retries=retries, timeout_s=timeout_s)
                results.append(FetchResult(url=url, html=html, error=str(exc)))
            return results

        results: list[FetchResult] = []
        for item in browser_results:
            html = item.html
            error = preflight_errors.get(item.url) or item.error
            block_reason = detect_block_reason_from_html(html)
            if block_reason:
                html = None
                error = f"blocked:{block_reason}:{item.url}"
            if not html:
                if error and (error.startswith("policy_blocked:") or error.startswith("blocked:")):
                    html = None
                else:
                    html = self.fetch_html(url=item.url, retries=max(1, retries), timeout_s=timeout_s)
                    if html:
                        error = None
                    elif not error:
                        error = f"fetch_failed:{item.url}"
            results.append(FetchResult(url=item.url, html=html, error=error))
        return results

    async def fetch_html_batch_async(
        self,
        urls: Iterable[str],
        *,
        max_workers: Optional[int] = None,
        timeout_s: float = 30.0,
        retries: int = 3,
    ) -> list[FetchResult]:
        url_list = [u for u in urls if u]
        if not url_list:
            return []

        deduped = list(dict.fromkeys(url_list))
        deduped = self._filter_seen_urls(deduped)
        if not deduped:
            return []
        max_concurrency = max_workers if max_workers is not None else None
        preflight_errors: dict[str, str] = {}

        async def preflight(url: str) -> bool:
            if hasattr(self.compliance_manager, "assess_url"):
                decision = await asyncio.to_thread(
                    self.compliance_manager.assess_url, url, self.rate_limit_seconds
                )
                if not bool(getattr(decision, "allowed", False)):
                    reason = str(getattr(decision, "reason", "") or "preflight")
                    prefix = "policy_blocked" if reason.startswith("robots_") else "blocked"
                    preflight_errors[url] = f"{prefix}:{reason}:{url}"
                    return False
                return True
            return await asyncio.to_thread(
                self.compliance_manager.check_and_wait, url, self.rate_limit_seconds
            )

        try:
            browser_results = await self.browser_engine.fetch_many(
                deduped,
                timeout_s=timeout_s,
                max_concurrency=max_concurrency,
                preflight=preflight,
            )
        except Exception as exc:
            logger.warning("browser_batch_failed", error=str(exc))
            raise

        results = [
            FetchResult(
                url=item.url,
                html=item.html,
                error=preflight_errors.get(item.url) or item.error,
            )
            for item in browser_results
        ]
        return results

    def extract_links(self, html: str, spec: LinkExtractorSpec) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        selectors = list(spec.selectors) if spec.selectors else []

        if selectors:
            nodes = []
            for selector in selectors:
                nodes.extend(soup.select(selector))
        else:
            nodes = soup.find_all("a")

        for node in nodes:
            if not node.has_attr(spec.attr):
                continue
            href = str(node.get(spec.attr)).strip()
            if not href:
                continue
            full = urljoin(self.base_url, href)
            if spec.include and not any(token in full for token in spec.include):
                continue
            if spec.exclude and any(token in full for token in spec.exclude):
                continue
            if full not in urls:
                urls.append(full)
            if spec.limit and len(urls) >= spec.limit:
                break
        return urls

    def build_raw_listing(
        self, *, external_id: str, url: str, html: str, snapshot_ext: str = "html"
    ):
        meta = self.snapshot_service.save_snapshot(
            content=html,
            source_id=self.source_id,
            external_id=external_id,
            listing_url=url,
            extension=snapshot_ext,
        )
        snapshot_path = meta.file_path if meta else None
        return snapshot_path
