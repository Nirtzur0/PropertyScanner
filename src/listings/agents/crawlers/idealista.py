import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


class IdealistaCrawlerAgent(BaseAgent):
    """
    Crawls Idealista using curl_cffi to bypass TLS fingerprinting protections.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="IdealistaCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url", "https://www.idealista.com")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        max_workers = int(config.get("max_workers", 6))
        browser_max_concurrency = int(config.get("browser_max_concurrency", 1))
        playwright_max_concurrency = int(config.get("playwright_max_concurrency", 1))
        prefer_playwright = bool(config.get("prefer_playwright", config.get("use_playwright", False)))
        self.scrape_client = ScrapeClient(
            source_id=config.get("id", "idealista"),
            base_url=self.base_url,
            compliance_manager=self.compliance,
            user_agent=self.user_agent,
            rate_limit_seconds=float(config.get("period_seconds", 10)),
            prefer_browser=bool(config.get("prefer_browser", False)),
            prefer_playwright=prefer_playwright,
            enable_playwright=bool(config.get("enable_playwright", True)),
            browser_wait_s=float(config.get("browser_wait_s", 8.0)),
            playwright_wait_s=float(config.get("playwright_wait_s", 2.0)),
            playwright_headless=bool(config.get("playwright_headless", True)),
            engine_order=config.get("engine_order"),
            max_workers=max_workers,
            browser_max_concurrency=browser_max_concurrency,
            playwright_max_concurrency=playwright_max_concurrency,
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=30)
        except Exception as e:
            logger.warning("idealista_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        search_path = input_payload.get("search_path", "/venta-viviendas/madrid/centro/")
        if search_path.startswith("http"):
            start_url = search_path
        elif search_path.startswith("/"):
            start_url = f"{self.base_url}{search_path}"
        else:
            start_url = f"{self.base_url}/{search_path}"

        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = input_payload["target_urls"]
        else:
            # Fetch Search Page
            html = self._fetch_url(start_url)
            if html:
                listing_urls = self.scrape_client.extract_links(
                    html,
                    LinkExtractorSpec(
                        selectors=["article.item a.item-link"],
                        include=["/inmueble/"],
                    ),
                )
        
        results = []
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=30, retries=3):
            if not result.html:
                continue
            url = result.url
            html = result.html
            
            try:
                lid = url.split("/inmueble/")[1].replace("/", "")
            except:
                lid = hashlib.md5(url.encode()).hexdigest()[:12]
            
            raw_path = self.scrape_client.build_raw_listing(
                external_id=lid,
                url=url,
                html=html,
            )
            
            raw_listing = RawListing(
                source_id=self.config.get("id", "idealista"),
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
