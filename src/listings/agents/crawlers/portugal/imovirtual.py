import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import structlog

from src.listings.scraping.client import ScrapeClient, LinkExtractorSpec
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.time import unix_ts, utcnow

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

    def _extract_listing_urls(self, html: str) -> list[str]:
        urls = self.scrape_client.extract_links(
            html,
            LinkExtractorSpec(
                selectors=[
                    "a[data-cy='listing-item-link']",
                    "a[href*='/pt/anuncio/']",
                    "a[href*='/pt/comprar/']",
                ],
                include=["/pt/anuncio/", "/pt/comprar/"],
            ),
        )

        patterns = [
            r"https?://www\.imovirtual\.com/pt/(?:anuncio|comprar)/[^\"'\s]+-ID[0-9A-Za-z]+",
            r"/pt/(?:anuncio|comprar)/[^\"'\s]+-ID[0-9A-Za-z]+",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, html):
                if match.startswith("http"):
                    urls.append(match)
                else:
                    urls.append(urljoin(self.base_url, match))

        deduped = []
        seen = set()
        for url in urls:
            normalized = url.split("#")[0]
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

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
            search_path = input_payload.get("search_path") or "/comprar/apartamento/lisboa/"
            if str(search_path).startswith("http"):
                start_urls.append(str(search_path))
            elif str(search_path).startswith("/"):
                start_urls.append(f"{self.base_url}{search_path}")
            else:
                start_urls.append(f"{self.base_url}/{search_path}")

        errors = []
        if not listing_urls:
            for url in start_urls:
                html = self._fetch_url(url)
                if not html:
                    errors.append(f"fetch_failed:{url}")
                    continue
                try:
                    debug_path = self.scrape_client.build_raw_listing(
                        external_id=f"search_imovirtual_{unix_ts()}",
                        url=url,
                        html=html,
                        snapshot_ext="html"
                    )
                    logger.info("imovirtual_search_snapshot_saved", path=debug_path)
                except Exception:
                    pass

                listing_urls.extend(self._extract_listing_urls(html))

        listing_urls = list(dict.fromkeys(listing_urls))
        max_listings = int(input_payload.get("max_listings", 0))
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

        if not listing_urls:
            if not errors:
                errors.append("no_listings_found")
            return AgentResponse(status="failure", data=[], errors=errors)

        results = []
        for result in self.scrape_client.fetch_html_batch(listing_urls, timeout_s=45, retries=3):
            if not result.html:
                errors.append(f"fetch_failed:{result.url}")
                continue
            url = result.url
            html = result.html
            
            try:
                match = re.search(r"ID[0-9A-Za-z]+", url)
                lid = match.group(0) if match else hashlib.md5(url.encode()).hexdigest()[:12]
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
            
        status = "success" if results else "failure"
        return AgentResponse(status=status, data=results, errors=errors)
