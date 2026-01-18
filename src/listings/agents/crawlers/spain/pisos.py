import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


class PisosCrawlerAgent(BaseAgent):
    """
    Crawls Pisos.com using ScrapeClient.
    """
    def __init__(self, config: Dict[str, Any], compliance_manager: ComplianceManager):
        super().__init__(name="PisosCrawler", config=config)
        self.compliance_manager = compliance_manager
        self.base_url = config.get("base_url", "https://www.pisos.com")
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        max_workers = int(config.get("max_workers", 6))
        browser_max_concurrency = int(config.get("browser_max_concurrency", max_workers))
        
        self.scrape_client = ScrapeClient(
            source_id="pisos",
            base_url=self.base_url,
            compliance_manager=self.compliance_manager,
            user_agent=self.user_agent,
            rate_limit_seconds=float(config.get("period_seconds", 3)),
            browser_wait_s=float(config.get("browser_wait_s", 5.0)),
            max_workers=max_workers,
            browser_max_concurrency=browser_max_concurrency,
            pydoll_config=config.get("pydoll_config"),
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=30)
        except Exception as e:
            logger.warning("pisos_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        search_path = input_payload.get("search_path", "/venta/pisos-madrid_capital_centro/")
        
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
                        external_id=f"search_pisos_{int(datetime.now().timestamp())}",
                        url=start_url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("pisos_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                listing_urls = self.scrape_client.extract_links(
                    html,
                    LinkExtractorSpec(
                        selectors=["div.ad-preview a.ad-preview__title"], 
                        include=["/inmueble/", "/comprar/"],
                    ),
                )
        
        results = []
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=30, retries=3):
            if not result.html:
                continue
            url = result.url
            html = result.html
            
            try:
                # Extract ID: /inmueble/piso-madrid_capital_centro-ID/
                if "/inmueble/" in url:
                    # Pisos IDs are usually at the end of the slug or the slug itself is ID-like
                    # example: .../piso-zona-id12345/
                    # Let's just use hash for safety or try split
                    lid = hashlib.md5(url.encode()).hexdigest()[:12]
                else:
                    lid = hashlib.md5(url.encode()).hexdigest()[:12]
            except:
                lid = hashlib.md5(url.encode()).hexdigest()[:12]
            
            raw_path = self.scrape_client.build_raw_listing(
                external_id=lid,
                url=url,
                html=html,
            )
            
            raw_listing = RawListing(
                source_id="pisos",
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
