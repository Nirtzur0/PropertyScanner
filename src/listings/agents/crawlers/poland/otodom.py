
from datetime import datetime
from typing import Optional, Dict, List, Any
import hashlib

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


class OtodomCrawlerAgent(BaseAgent):
    """
    Crawls Otodom.pl (Poland).
    Uses data-cy attributes for reliable crawling.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="OtodomCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url", "https://www.otodom.pl")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(
            config.get("browser_max_concurrency", 4)
        )
        
        self.scrape_client = ScrapeClient(
            source_id="otodom_pl",
            base_url=self.base_url,
            compliance_manager=self.compliance,
            user_agent=self.user_agent,
            rate_limit_seconds=float(config.get("period_seconds", 5)),
            browser_wait_s=float(config.get("browser_wait_s", 5.0)),
            browser_max_concurrency=browser_max_concurrency,
            browser_config=config.get("browser_config"),
            seen_mode=config.get("seen_mode"),
        )
        
        # Link extraction
        # Link: a[data-cy="listing-item-link"]
        # Include: /pl/oferta/ (or just match the selector)
        self.link_extractor_spec = LinkExtractorSpec(
            selectors=["a[data-cy='listing-item-link']"], 
            include=["/pl/oferta/"],
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=45)
        except Exception as e:
            logger.warning("otodom_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        start_urls = []
        if input_payload.get("start_url"):
            start_urls.append(input_payload["start_url"])
        else:
             # Default search path
            start_urls.append(f"{self.base_url}/pl/wyniki/sprzedaz/mieszkanie/cala-polska")

        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = input_payload["target_urls"]
        else:
            for start_url in start_urls:
                html = self._fetch_url(start_url)
                if html:
                    try:
                        debug_path = self.scrape_client.build_raw_listing(
                            external_id=f"search_otodom_{int(datetime.now().timestamp())}",
                            url=start_url,
                            html=html,
                            snapshot_ext="html"
                        )
                        logger.info("otodom_search_snapshot_saved", path=debug_path)
                    except Exception:
                        pass

                    extracted = self.scrape_client.extract_links(
                        html,
                        self.link_extractor_spec,
                    )
                    listing_urls.extend(extracted)
        
        listing_urls = list(set(listing_urls))
        
        max_listings = input_payload.get("max_listings", 0)
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

        results = []
        logger.info("otodom_crawling_listings", count=len(listing_urls))
        
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                continue
            url = result.url
            html = result.html
            
            # ID extraction from URL usually ends with ID
            # e.g. ...-ID4mYwE
            lid = hashlib.md5(url.encode()).hexdigest()[:12]
            try:
                if "-ID" in url:
                    lid = url.split("-ID")[-1]
            except:
                pass

            raw_path = self.scrape_client.build_raw_listing(
                external_id=lid,
                url=url,
                html=html,
            )
            
            raw_listing = RawListing(
                source_id="otodom_pl",
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
