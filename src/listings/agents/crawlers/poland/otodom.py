
from datetime import datetime
from typing import Optional, Dict, List, Any
import hashlib

import structlog

from src.listings.crawl_contract import build_crawl_response
from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.time import unix_ts, utcnow

logger = structlog.get_logger(__name__)


class OtodomCrawlerAgent(BaseAgent):
    """
    Crawls Otodom.pl (Poland).
    Uses data-cy attributes for reliable crawling.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="OtodomCrawler", config=config)
        self.compliance = compliance
        self.source_id = "otodom_pl"
        self.base_url = config.get("base_url", "https://www.otodom.pl")
        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", config.get("period_seconds", 5)))
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(config.get("browser_max_concurrency") or 4)
        
        self.scrape_client = ScrapeClient(
            source_id="otodom_pl",
            base_url=self.base_url,
            compliance_manager=self.compliance,
            user_agent=self.user_agent,
            rate_limit_seconds=self.rate_limit_seconds,
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

        errors: list[str] = []
        search_pages_attempted = 0
        search_pages_succeeded = 0
        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = input_payload["target_urls"]
        else:
            for start_url in start_urls:
                search_pages_attempted += 1
                if hasattr(self.compliance, "assess_url"):
                    decision = self.compliance.assess_url(
                        start_url,
                        rate_limit_seconds=self.rate_limit_seconds,
                    )
                    if not decision.allowed:
                        errors.append(f"policy_blocked:{decision.reason}:{start_url}")
                        continue
                html = self._fetch_url(start_url)
                if html:
                    search_pages_succeeded += 1
                    try:
                        debug_path = self.scrape_client.build_raw_listing(
                            external_id=f"search_otodom_{unix_ts()}",
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
                else:
                    errors.append(f"fetch_failed:{start_url}")
        
        listing_urls = list(set(listing_urls))
        
        max_listings = input_payload.get("max_listings", 0)
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

        results = []
        logger.info("otodom_crawling_listings", count=len(listing_urls))
        
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                errors.append(result.error or f"fetch_failed:{result.url}")
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
                source_id=self.source_id,
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=utcnow()
            )
            results.append(raw_listing)

        if not listing_urls and not errors:
            errors.append("no_listings_found")

        return build_crawl_response(
            listings=results,
            errors=errors,
            search_pages_attempted=search_pages_attempted,
            search_pages_succeeded=search_pages_succeeded,
            listing_urls_discovered=len(listing_urls),
            search_fetch_ok=search_pages_succeeded > 0 or bool(input_payload.get("target_urls")),
        )
