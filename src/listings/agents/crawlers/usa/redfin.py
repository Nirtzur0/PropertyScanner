import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from src.listings.crawl_contract import build_crawl_response
from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.listings.scraping.proxy_config import proxy_requirement_error, resolve_browser_runtime_config
from src.listings.source_ids import canonicalize_source_id
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.time import unix_ts, utcnow

logger = structlog.get_logger(__name__)


class RedfinCrawlerAgent(BaseAgent):
    """
    Crawls Redfin (USA).
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="RedfinCrawler", config=config)
        self.compliance = compliance
        self.source_id = canonicalize_source_id(config.get("id", "redfin_us"))
        self.base_url = config.get("base_url", "https://www.redfin.com")
        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", config.get("period_seconds", 5)))
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(config.get("browser_max_concurrency") or 4)
        self.browser_config = resolve_browser_runtime_config(self.source_id, config.get("browser_config"))

        self.scrape_client = ScrapeClient(
            source_id=self.source_id,
            base_url=self.base_url,
            compliance_manager=self.compliance,
            user_agent=self.user_agent,
            rate_limit_seconds=self.rate_limit_seconds,
            browser_wait_s=float(config.get("browser_wait_s", 5.0)),
            browser_max_concurrency=browser_max_concurrency,
            browser_config=self.browser_config,
        )

    def _fetch_url(self, url: str) -> Optional[str]:
        try:
            return self.scrape_client.fetch_html(url, retries=3, timeout_s=45)
        except Exception as e:
            logger.warning("redfin_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        proxy_error = proxy_requirement_error(self.source_id, self.browser_config)
        if proxy_error:
            return build_crawl_response(
                listings=[],
                errors=[proxy_error],
                extra_metadata={"proxy_required": True},
            )

        search_path = input_payload.get("search_path", "/city/17151/CA/San-Francisco")
        
        if search_path.startswith("http"):
            start_url = search_path
        elif search_path.startswith("/"):
            start_url = f"{self.base_url}{search_path}"
        else:
            start_url = f"{self.base_url}/{search_path}"

        errors: list[str] = []
        search_pages_attempted = 0
        search_pages_succeeded = 0
        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = input_payload["target_urls"]
        else:
            search_pages_attempted = 1
            if hasattr(self.compliance, "assess_url"):
                decision = self.compliance.assess_url(
                    start_url,
                    rate_limit_seconds=self.rate_limit_seconds,
                )
                if not decision.allowed:
                    errors.append(f"policy_blocked:{decision.reason}:{start_url}")
                    return build_crawl_response(
                        listings=[],
                        errors=errors,
                        search_pages_attempted=search_pages_attempted,
                        search_pages_succeeded=0,
                        listing_urls_discovered=0,
                    )
            # Fetch Search Page
            html = self._fetch_url(start_url)
            if html:
                search_pages_succeeded = 1
                try:
                    debug_path = self.scrape_client.build_raw_listing(
                        external_id=f"search_redfin_{unix_ts()}",
                        url=start_url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("redfin_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                listing_urls = self.scrape_client.extract_links(
                    html,
                    LinkExtractorSpec(
                        selectors=["a.slider-item", "a.homecard-link"], 
                        include=["/home/"],
                    ),
                )
            else:
                errors.append(f"fetch_failed:{start_url}")
        
        results = []
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                errors.append(result.error or f"fetch_failed:{result.url}")
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
