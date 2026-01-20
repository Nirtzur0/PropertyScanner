
from datetime import datetime
from typing import Optional, Dict, List, Any

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from .rightmove_normalizer import RightmoveNormalizer

logger = structlog.get_logger(__name__)


class DaftCrawlerAgent(BaseAgent):
    """
    Crawls Daft.ie (Ireland).
    Uses data-testid selectors for robustness.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="DaftCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url", "https://www.daft.ie")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(
            config.get("browser_max_concurrency", 4)
        )
        
        self.scrape_client = ScrapeClient(
            source_id="daft_ie",
            base_url=self.base_url,
            compliance_manager=self.compliance,
            user_agent=self.user_agent,
            rate_limit_seconds=float(config.get("period_seconds", 5)),
            browser_wait_s=float(config.get("browser_wait_s", 5.0)),
            browser_max_concurrency=browser_max_concurrency,
            browser_config=config.get("browser_config"),
            seen_mode=config.get("seen_mode"),
        )
        
        # Link extraction config based on research
        self.link_extractor_spec = LinkExtractorSpec(
             # [data-testid^='result-'] a[href*='/for-sale/'] found in research
            selectors=["[data-testid^='result-'] a[href*='/for-sale/']"], 
            include=["/for-sale/"],
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=45)
        except Exception as e:
            logger.warning("daft_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        start_urls = []
        if input_payload.get("start_url"):
            start_urls.append(input_payload["start_url"])
        else:
             # Default search path if none provided
            start_urls.append(f"{self.base_url}/property-for-sale/ireland")

        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = input_payload["target_urls"]
        else:
            # Crawl start URLs to find listings
            for start_url in start_urls:
                html = self._fetch_url(start_url)
                if html:
                    try:
                        debug_path = self.scrape_client.build_raw_listing(
                            external_id=f"search_daft_{int(datetime.now().timestamp())}",
                            url=start_url,
                            html=html,
                            snapshot_ext="html"
                        )
                        logger.info("daft_search_snapshot_saved", path=debug_path)
                    except Exception:
                        pass

                    extracted = self.scrape_client.extract_links(
                        html,
                        self.link_extractor_spec,
                    )
                    listing_urls.extend(extracted)
        
        # De-duplicate
        listing_urls = list(set(listing_urls))
        
        # Limit to max_listings if specified
        max_listings = input_payload.get("max_listings", 0)
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

        results = []
        logger.info("daft_crawling_listings", count=len(listing_urls))
        
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                continue
            url = result.url
            html = result.html
            
            # Simple hash external ID for now, Daft has IDs in URL but safe to hash
            import hashlib
            lid = hashlib.md5(url.encode()).hexdigest()[:12]
            
            # Try parse ID from URL: .../123456
            try:
                parts = url.strip("/").split("/")
                if parts and parts[-1].isdigit():
                    lid = parts[-1]
            except:
                pass

            raw_path = self.scrape_client.build_raw_listing(
                external_id=lid,
                url=url,
                html=html,
            )
            
            raw_listing = RawListing(
                source_id="daft_ie",
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
