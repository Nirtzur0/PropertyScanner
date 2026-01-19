import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


class ImovirtualCrawlerAgent(BaseAgent):
    """
    Crawls Imovirtual (Portugal).
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="ImovirtualCrawler", config=config)
        self.compliance = compliance
        self.source_id = config.get("id", "imovirtual_pt")
        self.base_url = config.get("base_url", "https://www.imovirtual.com")
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
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=45)
        except Exception as e:
            logger.warning("imovirtual_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        start_url = input_payload.get("start_url") or input_payload.get("search_url")
        search_path = input_payload.get("search_path")
        if not start_url:
            search_path = search_path or "/comprar/apartamento/lisboa/"
            if str(search_path).startswith("http"):
                start_url = str(search_path)
            elif str(search_path).startswith("/"):
                start_url = f"{self.base_url}{search_path}"
            else:
                start_url = f"{self.base_url}/{search_path}"

        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = list(input_payload["target_urls"] or [])
        else:
            # Fetch Search Page
            html = self._fetch_url(start_url)
            if html:
                try:
                    debug_path = self.scrape_client.build_raw_listing(
                        external_id=f"search_imovirtual_{int(datetime.now().timestamp())}",
                        url=start_url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("imovirtual_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                listing_urls = self.scrape_client.extract_links(
                    html,
                    LinkExtractorSpec(
                        selectors=["article a[data-cy='listing-item-link']", "a.css-13l592k"], 
                        include=["/anuncio/"],
                    ),
                )

        listing_urls = list(dict.fromkeys(listing_urls))
        max_listings = int(input_payload.get("max_listings", 0))
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

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
                source_id=self.source_id,
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
