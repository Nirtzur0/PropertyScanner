import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

import structlog

from src.listings.crawl_contract import classify_crawl_status, detect_block_reason_from_html, primary_block_reason
from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.listings.source_ids import canonicalize_source_id

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.time import unix_ts, utcnow

logger = structlog.get_logger(__name__)


class IdealistaCrawlerAgent(BaseAgent):
    """
    Crawls Idealista using ScrapeClient (Pydoll browser engine).
    """
    def __init__(self, config: Dict[str, Any], compliance_manager: ComplianceManager):
        super().__init__(name="IdealistaCrawler", config=config)
        self.compliance_manager = compliance_manager
        self.source_id = canonicalize_source_id(config.get("id", "idealista"))
        self.base_url = config.get("base_url", "https://www.idealista.com")
        self.rate_limit_seconds = float((config.get("rate_limit", {}) or {}).get("period_seconds", config.get("period_seconds", 10)))
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(config.get("browser_max_concurrency") or 6)
        self.scrape_client = ScrapeClient(
            source_id=self.source_id,
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
            logger.warning("idealista_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        search_path = input_payload.get("search_path", "/venta-viviendas/madrid/centro/")
        if search_path.startswith("http"):
            start_url = search_path
        elif search_path.startswith("/"):
            start_url = f"{self.base_url}{search_path}"
        else:
            start_url = f"{self.base_url}/{search_path}"

        errors: list[str] = []
        search_pages_attempted = 1
        search_pages_succeeded = 0
        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = input_payload["target_urls"]
        else:
            if hasattr(self.compliance_manager, "assess_url"):
                decision = self.compliance_manager.assess_url(
                    start_url,
                    rate_limit_seconds=self.rate_limit_seconds,
                )
                if not decision.allowed:
                    errors.append(f"policy_blocked:{decision.reason}:{start_url}")
                    return AgentResponse(
                        status=classify_crawl_status(listing_count=0, errors=errors),
                        data=[],
                        errors=errors,
                        metadata={
                            "search_fetch_ok": False,
                            "search_block_reason": primary_block_reason(errors),
                            "search_pages_attempted": search_pages_attempted,
                            "search_pages_succeeded": 0,
                            "listing_urls_discovered": 0,
                            "listing_urls_fetched": 0,
                            "detail_fetch_success_ratio": 0.0,
                        },
                    )
            # Fetch Search Page
            html = self.scrape_client.fetch_html(start_url, retries=3, timeout_s=30, skip_compliance=True)
            if not html:
                errors.append("fetch_failed:search")
            else:
                block_reason = detect_block_reason_from_html(html)
                if block_reason:
                    errors.append(f"blocked:{block_reason}:{start_url}")
                    return AgentResponse(
                        status=classify_crawl_status(listing_count=0, errors=errors),
                        data=[],
                        errors=errors,
                        metadata={
                            "search_fetch_ok": False,
                            "search_block_reason": primary_block_reason(errors),
                            "search_pages_attempted": search_pages_attempted,
                            "search_pages_succeeded": 0,
                            "listing_urls_discovered": 0,
                            "listing_urls_fetched": 0,
                            "detail_fetch_success_ratio": 0.0,
                        },
                    )
                search_pages_succeeded = 1
                # DEBUG: Save search page snapshot
                try:
                    debug_path = self.scrape_client.build_raw_listing(
                        external_id=f"search_{unix_ts()}",
                        url=start_url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("idealista_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                listing_urls = self.scrape_client.extract_links(
                    html,
                    LinkExtractorSpec(
                        selectors=["article.item a.item-link"],
                        include=["/inmueble/"],
                    ),
                )

        results = []
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=30, retries=3):
            if not result.html:
                if result.url:
                    errors.append(result.error or f"fetch_failed:{result.url}")
                continue
            url = result.url
            html = result.html
            
            try:
                lid = url.split("/inmueble/")[1].replace("/", "")
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

        if not listing_urls and "fetch_failed:search" not in errors:
            errors.append("no_listings_found")

        if not results and not errors:
            errors.append("no_listings_found")

        return AgentResponse(
            status=classify_crawl_status(listing_count=len(results), errors=errors),
            data=results,
            errors=errors,
            metadata={
                "search_fetch_ok": search_pages_succeeded > 0,
                "search_block_reason": primary_block_reason(errors),
                "search_pages_attempted": search_pages_attempted,
                "search_pages_succeeded": search_pages_succeeded,
                "listing_urls_discovered": len(listing_urls),
                "listing_urls_fetched": len(results),
                "detail_fetch_success_ratio": round(len(results) / max(len(listing_urls), 1), 6),
            },
        )
