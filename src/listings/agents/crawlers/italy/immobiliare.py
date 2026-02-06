import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.time import utcnow

logger = structlog.get_logger(__name__)


class ImmobiliareCrawlerAgent(BaseAgent):
    """
    Crawls Immobiliare.it (Italy) using ScrapeClient (Pydoll browser engine).
    """
    def __init__(self, config: Dict[str, Any], compliance_manager: ComplianceManager):
        super().__init__(name="ImmobiliareCrawler", config=config)
        self.compliance_manager = compliance_manager
        self.base_url = config.get("base_url", "https://www.immobiliare.it")
        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", 3))
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(
            config.get("browser_max_concurrency", 6)
        )
        self.scrape_client = ScrapeClient(
            source_id=config.get("id", "immobiliare_it"),
            base_url=self.base_url,
            compliance_manager=self.compliance_manager,
            user_agent=self.user_agent,
            rate_limit_seconds=self.rate_limit_seconds,
            browser_wait_s=float(config.get("browser_wait_s", 8.0)),
            browser_max_concurrency=browser_max_concurrency,
            browser_config=config.get("browser_config"),
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=30)
        except Exception as e:
            logger.warning("immobiliare_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        source_id = self.config.get("id", "immobiliare_it")
        start_url = input_payload.get("start_url")
        if not start_url:
            search_path = input_payload.get("search_path")
            if search_path:
                if str(search_path).startswith("http"):
                    start_url = str(search_path)
                else:
                    start_url = urljoin(self.base_url, str(search_path))
            else:
                city = input_payload.get("city", "milano")
                start_url = f"{self.base_url}/vendita-case/{city}/"

        target_urls = list(input_payload.get("target_urls") or [])
        listing_url = input_payload.get("listing_url")
        if listing_url:
            target_urls.append(listing_url)
        listing_id = input_payload.get("listing_id")
        if listing_id:
            target_urls.append(f"{self.base_url}/annunci/{listing_id}/")
        listing_ids = input_payload.get("listing_ids") or []
        for lid in listing_ids:
            target_urls.append(f"{self.base_url}/annunci/{lid}/")

        normalized_targets = []
        for url in target_urls:
            if str(url).startswith("http"):
                normalized_targets.append(url)
            else:
                normalized_targets.append(urljoin(self.base_url, str(url)))
        target_urls = normalized_targets

        listing_urls = []
        errors: List[str] = []
        if target_urls:
            listing_urls = target_urls
        else:
            # Search Page
            html = self._fetch_url(start_url)
            if not html:
                errors.append("fetch_failed:search")
            else:
                listing_urls = self.scrape_client.extract_links(
                    html,
                    LinkExtractorSpec(
                        selectors=[
                            "li.nd-list__item a.in-card__title",
                            "li.in-realEstateResults__item a.in-card__title",
                            "a.in-reListCard__title",
                        ],
                        include=["/annunci/"],
                    ),
                )
                        
        listings = []
        
        listing_urls = list(set(listing_urls))
        
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=30, retries=2):
            full_url = result.url if result.url.startswith("http") else urljoin(self.base_url, result.url)
            html = result.html
            if not html:
                errors.append(f"fetch_failed:{full_url}")
                continue
            
            try:
                lid = full_url.split("/annunci/")[1].split("/")[0]
            except:
                lid = hashlib.md5(full_url.encode()).hexdigest()[:12]
            
            snapshot_path = self.scrape_client.build_raw_listing(
                external_id=lid,
                url=full_url,
                html=html,
            )
            
            raw = RawListing(
                source_id=source_id,
                external_id=lid,
                url=full_url,
                html_snapshot_path=snapshot_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=utcnow()
            )
            listings.append(raw)

        if not listing_urls and "fetch_failed:search" not in errors:
            errors.append("no_listings_found")
        if not listings and not errors:
            errors.append("no_listings_found")
             
        status = "success" if listings else "failure"
        return AgentResponse(status=status, data=listings, errors=errors)
