
from datetime import datetime
from typing import Optional, Dict, List, Any
import hashlib
import re

import structlog
import requests

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.time import unix_ts, utcnow

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

        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", 5))
        
        self.scrape_client = ScrapeClient(
            source_id=self.source_id,
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

    def _api_fetch_listing_urls(
        self,
        *,
        max_pages: int,
        page_size: int,
        max_listings: int,
    ) -> List[str]:
        """
        Sreality's /en/search pages can redirect to a consent manager (CMP) without listing links.
        Their public JSON API (api/en/v2/estates) returns listing IDs and locality slugs reliably.
        """
        max_pages = max(1, int(max_pages or 1))
        page_size = max(1, int(page_size or 20))

        # If the caller requested a strict cap, don't over-fetch.
        if max_listings and max_listings > 0:
            page_size = min(page_size, int(max_listings))
            max_pages = min(max_pages, 50)

        headers = {"User-Agent": self.user_agent}
        urls: List[str] = []

        for page in range(1, max_pages + 1):
            api_url = (
                f"{self.base_url}/api/en/v2/estates"
                f"?category_main_cb=1&category_type_cb=1"
                f"&page={page}&per_page={page_size}"
            )
            try:
                resp = requests.get(api_url, headers=headers, timeout=25)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("sreality_api_fetch_failed", url=api_url, error=str(exc))
                break

            estates = (data or {}).get("_embedded", {}).get("estates", []) or []
            if not estates:
                break

            for estate in estates:
                try:
                    hash_id = estate.get("hash_id")
                    seo = estate.get("seo") or {}
                    locality_slug = seo.get("locality")

                    name = estate.get("name") or ""
                    layout = None
                    m = re.search(r"(\d+\+(?:kk|kt|\d+|1))", str(name), flags=re.IGNORECASE)
                    if m:
                        layout = m.group(1).lower().replace("kt", "kk")
                    if not layout:
                        layout = "1+kk"

                    if not hash_id or not locality_slug:
                        continue

                    # Czech detail pages are accessible without triggering the CMP iframe.
                    # Example: https://www.sreality.cz/detail/prodej/byt/2+kk/praha-vinohrady/123456789
                    urls.append(
                        f"{self.base_url}/detail/prodej/byt/{layout}/{locality_slug}/{hash_id}"
                    )
                except Exception:
                    continue

            if max_listings and max_listings > 0 and len(urls) >= max_listings:
                urls = urls[:max_listings]
                break

        return list(dict.fromkeys(urls))

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
        # Try the HTML route first so fixture-based tests can stub fetch_html/fetch_html_batch.
        # If the page served a cookie-consent (CMP) iframe, we fall back to the public API.
        if not listing_urls:
            for url in start_urls:
                html = self._fetch_url(url)
                if not html:
                    errors.append(f"fetch_failed:{url}")
                    continue
                if "Nastavení souhlasu s personalizací" in html:
                    continue

                try:
                    debug_path = self.scrape_client.build_raw_listing(
                        external_id=f"search_sreality_{unix_ts()}",
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

        if not listing_urls:
            max_pages = int(input_payload.get("max_pages", 1))
            page_size = int(input_payload.get("page_size", 24))
            max_listings = int(input_payload.get("max_listings", 0))
            listing_urls = self._api_fetch_listing_urls(
                max_pages=max_pages,
                page_size=page_size,
                max_listings=max_listings,
            )
            try:
                # Store a lightweight search snapshot for debugging.
                debug_path = self.scrape_client.build_raw_listing(
                    external_id=f"search_sreality_{unix_ts()}",
                    url=f"{self.base_url}/api/en/v2/estates?category_main_cb=1&category_type_cb=1",
                    html="\n".join(listing_urls[:200]),
                    snapshot_ext="txt",
                )
                logger.info("sreality_search_snapshot_saved", path=debug_path)
            except Exception:
                pass
        
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

        # Use the browser engine first (helps with dynamic pages). If we get the CMP page, re-fetch via requests.
        batch = self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3)
        batch_by_url = {item.url: item for item in batch}

        headers = {"User-Agent": self.user_agent}
        for url in listing_urls:
            html = (batch_by_url.get(url).html if batch_by_url.get(url) else None) or ""
            if not html or "Nastavení souhlasu s personalizací" in html:
                if not self.compliance.check_and_wait(url, rate_limit_seconds=self.rate_limit_seconds):
                    errors.append(f"blocked:{url}")
                    continue
                try:
                    resp = requests.get(url, headers=headers, timeout=35)
                    html = resp.text if resp.ok else ""
                except Exception as exc:
                    errors.append(f"fetch_failed:{url}:{exc}")
                    continue
                if not html or "Nastavení souhlasu s personalizací" in html:
                    errors.append(f"fetch_failed:{url}:cmp_page")
                    continue
            
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
                fetched_at=utcnow()
            )
            results.append(raw_listing)
            
        status = "success" if results else "failure"
        return AgentResponse(status=status, data=results, errors=errors)
