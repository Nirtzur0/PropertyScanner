import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional, List

import structlog
from bs4 import BeautifulSoup

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


class FundaCrawlerAgent(BaseAgent):
    """
    Crawls Funda.nl (Netherlands).
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="FundaCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url", "https://www.funda.nl")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(
            config.get("browser_max_concurrency", 4)
        )
        
        self.scrape_client = ScrapeClient(
            source_id="funda",
            base_url=self.base_url,
            compliance_manager=self.compliance,
            user_agent=self.user_agent,
            rate_limit_seconds=float(config.get("period_seconds", 5)),
            browser_wait_s=float(config.get("browser_wait_s", 5.0)),
            browser_max_concurrency=browser_max_concurrency,
            browser_config=config.get("browser_config"),
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=45)
        except Exception as e:
            logger.warning("funda_fetch_error", url=url, error=str(e))
            return None

    def _extract_json_ld_links(self, html: str) -> List[str]:
        """Extracts listing URLs from JSON-LD schema in the HTML."""
        urls = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            script_tags = soup.find_all("script", {"type": "application/ld+json"})
            
            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    # Handle both list and single object
                    if isinstance(data, dict):
                        # check for ItemList
                        if data.get("@type") == "ItemList" or "ItemList" in data.get("@type", []):
                            items = data.get("itemListElement", [])
                            for item in items:
                                if isinstance(item, dict) and "url" in item:
                                    urls.append(item["url"])
                    elif isinstance(data, list):
                        # Sometimes it's a list of objects
                        for entry in data:
                             if isinstance(entry, dict) and "url" in entry:
                                 # We are looking for property details
                                 if "/detail/koop/" in entry["url"] or "/detail/huur/" in entry["url"]:
                                     urls.append(entry["url"])

                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning("funda_json_ld_extraction_error", error=str(e))
            
        return urls

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        search_path = input_payload.get("search_path", "/koop/amsterdam/")
        
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
                        external_id=f"search_funda_{int(datetime.now().timestamp())}",
                        url=start_url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("funda_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                # Attempt JSON-LD extraction first (more reliable)
                json_links = self._extract_json_ld_links(html)
                if json_links:
                    listing_urls = json_links
                    logger.info("funda_extracted_links_json_ld", count=len(listing_urls))
                
                # Fallback or combine with selector extraction if needed
                if not listing_urls:
                    listing_urls = self.scrape_client.extract_links(
                        html,
                        LinkExtractorSpec(
                            selectors=["div.search-result__header-title-col a", "a[data-test-id='object-image-link']"], 
                            include=["/koop/", "/huur/"],
                        ),
                    )
        
        results = []
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                continue
            url = result.url
            html = result.html
            
            try:
                lid = hashlib.md5(url.encode()).hexdigest()[:12]
            except:
                lid = hashlib.md5(url.encode()).hexdigest()[:12]
            
            raw_path = self.scrape_client.build_raw_listing(
                external_id=lid,
                url=url,
                html=html,
            )
            
            raw_listing = RawListing(
                source_id="funda",
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
