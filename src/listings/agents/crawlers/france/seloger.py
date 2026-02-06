import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.time import unix_ts, utcnow

logger = structlog.get_logger(__name__)


class SeLogerCrawlerAgent(BaseAgent):
    """
    Crawls SeLoger (France).
    Note: SeLoger has heavy anti-bot protections (Datadome). 
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="SeLogerCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url", "https://www.seloger.com")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(
            config.get("browser_max_concurrency", 4)
        )
        
        self.scrape_client = ScrapeClient(
            source_id="seloger",
            base_url=self.base_url,
            compliance_manager=self.compliance,
            user_agent=self.user_agent,
            rate_limit_seconds=float(config.get("period_seconds", 30)), # Slower pace
            browser_wait_s=float(config.get("browser_wait_s", 10.0)),
            browser_max_concurrency=browser_max_concurrency,
            browser_config=config.get("browser_config"),
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=45)
        except Exception as e:
            logger.warning("seloger_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        # Example search path
        search_path = input_payload.get("search_path", "/immobilier/achat/paris/75") 
        
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
                try:
                    debug_path = self.scrape_client.build_raw_listing(
                        external_id=f"search_seloger_{unix_ts()}",
                        url=start_url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("seloger_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                listing_urls = self.scrape_client.extract_links(
                    html,
                    LinkExtractorSpec(
                        selectors=["a[data-testid='c-link']", "a.CoveringLink-sc-191893i-0"], # Guessing selectors based on common React apps
                        include=["/annonces/"],
                    ),
                )
        
        results = []
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                continue
            url = result.url
            html = result.html
            
            try:
                # Extract ID if possible from URL, else hash
                lid = hashlib.md5(url.encode()).hexdigest()[:12]
            except:
                lid = hashlib.md5(url.encode()).hexdigest()[:12]
            
            raw_path = self.scrape_client.build_raw_listing(
                external_id=lid,
                url=url,
                html=html,
            )
            
            raw_listing = RawListing(
                source_id="seloger",
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=utcnow()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
