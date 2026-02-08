import hashlib
import re
import time
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


class ZooplaCrawlerAgent(BaseAgent):
    """
    Crawls Zoopla (UK) using ScrapeClient (Pydoll browser engine).
    """

    def __init__(self, config: Dict[str, Any], compliance_manager: ComplianceManager):
        super().__init__(name="ZooplaCrawler", config=config)
        self.compliance_manager = compliance_manager
        self.base_url = config.get("base_url", "https://www.zoopla.co.uk")
        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", 5))
        self.user_agent = config.get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        browser_max_concurrency = int(
            config.get("browser_max_concurrency", 6)
        )
        self.scrape_client = ScrapeClient(
            source_id=config.get("id", "zoopla_uk"),
            base_url=self.base_url,
            compliance_manager=self.compliance_manager,
            user_agent=self.user_agent,
            rate_limit_seconds=self.rate_limit_seconds,
            browser_wait_s=float(config.get("browser_wait_s", 8.0)),
            browser_max_concurrency=browser_max_concurrency,
            browser_config=config.get("browser_config"),
        )

    def _fetch_url(self, url: str, *, retries: int = 3, timeout_s: float = 30.0) -> Optional[str]:
        for attempt in range(retries):
            html = self.scrape_client.fetch_html(url, retries=1, timeout_s=timeout_s)
            if html:
                return html
            time.sleep(1.5 ** attempt)
        return None

    def _extract_listing_urls(self, html: str) -> List[str]:
        urls = self.scrape_client.extract_links(
            html,
            LinkExtractorSpec(
                selectors=["a[href*='/details/']"],
                include=["/details/"],
            ),
        )
        cleaned = [u.split("#")[0] for u in urls]

        # Next.js pages can embed listing routes in scripts/JSON without explicit <a> tags.
        for match in re.findall(r"/for-sale/details/\d+/?", html):
            cleaned.append(urljoin(self.base_url, match))
        # Zoopla also serves "contact" routes under `/for-sale/details/contact/<id>/`.
        # Keep only true listing detail URLs: `/for-sale/details/<digits>/`.
        filtered = []
        for url in cleaned:
            if "/details/contact/" in url:
                continue
            if "/new-homes/" in url:
                continue
            if re.search(r"/for-sale/details/\d+/?$", url):
                filtered.append(url)
                continue
            # Some pages link to `/details/<id>/` directly.
            if re.search(r"/details/\d+/?$", url):
                filtered.append(url)
        return filtered

    def _extract_external_id(self, url: str) -> str:
        try:
            parts = url.split("/details/")[1].split("/")
            external_id = parts[0]
            if external_id:
                return external_id
        except Exception:
            pass
        return hashlib.md5(url.encode("utf-8")).hexdigest()[:12]

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        source_id = self.config.get("id", "zoopla_uk")
        
        target_urls = list(input_payload.get("target_urls") or [])
        listing_url = input_payload.get("listing_url")
        if listing_url:
            target_urls.append(listing_url)

        listing_id = input_payload.get("listing_id")
        if listing_id:
            template = self.config.get(
                "listing_url_template", f"{self.base_url}/for-sale/details/{{listing_id}}/"
            )
            target_urls.append(template.format(listing_id=listing_id))

        listing_ids = input_payload.get("listing_ids") or []
        if listing_ids:
            template = self.config.get(
                "listing_url_template", f"{self.base_url}/for-sale/details/{{listing_id}}/"
            )
            for lid in listing_ids:
                target_urls.append(template.format(listing_id=lid))

        raw_start_urls = input_payload.get("start_urls") or []
        start_urls = []
        for url in raw_start_urls:
            if str(url).startswith("http"):
                start_urls.append(url)
            else:
                start_urls.append(urljoin(self.base_url, str(url)))
        start_url = input_payload.get("start_url") or input_payload.get("search_url")
        if start_url:
            if str(start_url).startswith("http"):
                start_urls.append(start_url)
            else:
                start_urls.append(urljoin(self.base_url, start_url))

        if not start_urls and not target_urls:
            search_path = input_payload.get("search_path")
            if search_path:
                if search_path.startswith("http"):
                    start_urls.append(search_path)
                else:
                    start_urls.append(urljoin(self.base_url, search_path))

        listings: List[RawListing] = []
        errors: List[str] = []
        
        listing_urls: List[str] = []
        if target_urls:
            listing_urls = list(dict.fromkeys(target_urls))
        else:
            for search_url in start_urls:
                html = self._fetch_url(search_url)
                if not html:
                    errors.append(f"fetch_failed:{search_url}")
                    continue
                listing_urls.extend(self._extract_listing_urls(html))
            listing_urls = list(dict.fromkeys(listing_urls))

        max_listings = int(input_payload.get("max_listings", 0))
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

        if not listing_urls:
            if not errors:
                errors.append("no_listings_found")
            return AgentResponse(status="failure", data=[], errors=errors)

        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=30, retries=2):
            if not result.html:
                errors.append(f"fetch_failed:{result.url}")
                continue
            html_content = result.html
            url = result.url

            external_id = self._extract_external_id(url)
            snapshot_path = self.scrape_client.build_raw_listing(
                external_id=external_id,
                url=url,
                html=html_content,
            )

            raw_listing = RawListing(
                source_id=source_id,
                external_id=external_id,
                url=url,
                raw_data={
                    "html_snippet": html_content,
                    "is_detail_page": True,
                },
                fetched_at=utcnow(),
                html_snapshot_path=snapshot_path,
            )
            listings.append(raw_listing)
        
        status = "success" if listings else "failure"
        return AgentResponse(status=status, data=listings, errors=errors)
