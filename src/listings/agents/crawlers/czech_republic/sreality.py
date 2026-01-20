
from datetime import datetime
from typing import Optional, Dict, List, Any
import hashlib

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


class SrealityCrawlerAgent(BaseAgent):
    """
    Crawls Sreality.cz.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="SrealityCrawler", config=config)
        self.compliance = compliance
        self.source_id = config.get("id", "sreality_cz")
        self.base_url = config.get("base_url", "https://www.sreality.cz")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(
            config.get("browser_max_concurrency", 4)
        )
        
        self.scrape_client = ScrapeClient(
            source_id=self.source_id,
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
        # Link: a[href*="/en/detail/"]
        # Include: /en/detail/
        self.link_extractor_spec = LinkExtractorSpec(
            selectors=["a[href*='/en/detail/']"], 
            include=["/en/detail/"],
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=45)
        except Exception as e:
            logger.warning("sreality_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        listing_urls = list(input_payload.get("target_urls") or [])
        start_urls = []
        raw_start_urls = input_payload.get("start_urls") or []
        for url in raw_start_urls:
            url = str(url)
            if not url.startswith("http"):
                url = f"{self.base_url}{url}" if url.startswith("/") else f"{self.base_url}/{url}"
            start_urls.append(url)
        start_url = input_payload.get("start_url") or input_payload.get("search_url")
        if start_url:
            start_url = str(start_url)
            if not start_url.startswith("http"):
                start_url = (
                    f"{self.base_url}{start_url}"
                    if start_url.startswith("/")
                    else f"{self.base_url}/{start_url}"
                )
            start_urls.append(start_url)
        if not start_urls and not listing_urls:
            start_urls.append(f"{self.base_url}/en/search/for-sale/apartments")

        errors = []
        if not listing_urls:
            for url in start_urls:
                html = self._fetch_url(url)
                if not html:
                    errors.append(f"fetch_failed:{url}")
                    continue
                try:
                    debug_path = self.scrape_client.build_raw_listing(
                        external_id=f"search_sreality_{int(datetime.utcnow().timestamp())}",
                        url=url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("sreality_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                extracted = self.scrape_client.extract_links(
                    html,
                    self.link_extractor_spec,
                )
                listing_urls.extend(extracted)
        
        # De-duplicate
        listing_urls = list(dict.fromkeys(listing_urls))
        
        # Limit to max_listings if specified
        max_listings = input_payload.get("max_listings", 0)
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

        if not listing_urls:
            if not errors:
                errors.append("no_listings_found")
            return AgentResponse(status="failure", data=[], errors=errors)

        results = []
        logger.info("sreality_crawling_listings", count=len(listing_urls))
        
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                errors.append(f"fetch_failed:{result.url}")
                continue
            url = result.url
            html = result.html
            
            # ID extraction from URL: /en/detail/sale/apartment/3+1/prague-liben-u-skolske-zahrady/3233633884
            lid = hashlib.md5(url.encode()).hexdigest()[:12]
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
                source_id=self.source_id,
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.utcnow()
            )
            results.append(raw_listing)
            
        status = "success" if results else "failure"
        return AgentResponse(status=status, data=results, errors=errors)
