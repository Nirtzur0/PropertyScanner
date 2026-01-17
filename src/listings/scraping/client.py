from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup

from src.listings.scraping.engine import (
    HttpFetcher,
    PlaywrightFetcher,
    PydollFetcher,
    ScrapeEngine,
    resolve_engine_order,
)
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
        prefer_browser: bool = False,
        prefer_playwright: bool = False,
        enable_browser: bool = True,
        enable_playwright: bool = True,
        browser_wait_s: float = 8.0,
        playwright_wait_s: float = 2.0,
        playwright_headless: bool = True,
        engine_order: Optional[Iterable[str]] = None,
        max_workers: int = 4,
        browser_max_concurrency: int = 1,
        playwright_max_concurrency: int = 1,
        allow_fallback: bool = True,
    ) -> None:
        self.source_id = source_id
        self.base_url = base_url
        self.compliance_manager = compliance_manager
        self.rate_limit_seconds = rate_limit_seconds
        self.snapshot_service = SnapshotService()
        self.max_workers = max(1, int(max_workers))

        http_fetcher = HttpFetcher(user_agent)
        pydoll_fetcher = (
            PydollFetcher(
                user_agent,
                wait_s=browser_wait_s,
                max_concurrency=browser_max_concurrency,
            )
            if enable_browser
            else None
        )
        playwright_fetcher = (
            PlaywrightFetcher(
                user_agent,
                headless=playwright_headless,
                wait_s=playwright_wait_s,
                max_concurrency=playwright_max_concurrency,
            )
            if enable_playwright
            else None
        )

        order = resolve_engine_order(
            engine_order=engine_order,
            prefer_browser=prefer_browser,
            prefer_playwright=prefer_playwright,
            enable_browser=enable_browser,
            enable_playwright=enable_playwright,
        )
        self.engine = ScrapeEngine(
            fetchers={
                "http": http_fetcher,
                "pydoll": pydoll_fetcher,
                "playwright": playwright_fetcher,
            },
            order=order,
            allow_fallback=allow_fallback,
        )

    def fetch_html(
        self,
        url: str,
        *,
        retries: int = 3,
        timeout_s: float = 30.0,
        backoff_base: float = 1.4,
    ) -> Optional[str]:
        if not self.compliance_manager.check_and_wait(
            url, rate_limit_seconds=self.rate_limit_seconds
        ):
            logger.warning("crawler_blocked_by_robots", url=url)
            return None

        for attempt in range(retries):
            html = self.engine.fetch(url, timeout_s=timeout_s)
            if html:
                return html
            time.sleep(backoff_base ** attempt)

        return None

    def fetch_html_batch(
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
        worker_count = max_workers if max_workers is not None else self.max_workers
        worker_count = max(1, int(worker_count))
        worker_count = min(worker_count, len(deduped))

        if worker_count <= 1:
            results = []
            for url in deduped:
                html = self.fetch_html(url, retries=retries, timeout_s=timeout_s)
                results.append(FetchResult(url=url, html=html))
            return results

        results: list[FetchResult] = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self.fetch_html, url, retries=retries, timeout_s=timeout_s): url
                for url in deduped
            }
            for future in as_completed(future_map):
                url = future_map[future]
                try:
                    html = future.result()
                    results.append(FetchResult(url=url, html=html))
                except Exception as exc:
                    results.append(FetchResult(url=url, html=None, error=str(exc)))

        index = {url: i for i, url in enumerate(deduped)}
        results.sort(key=lambda item: index.get(item.url, 0))
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
