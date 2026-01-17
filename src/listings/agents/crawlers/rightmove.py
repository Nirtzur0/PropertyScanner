import hashlib
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import requests
import structlog
from bs4 import BeautifulSoup

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.listings.services.snapshot_storage import SnapshotService
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)


class RightmoveCrawlerAgent(BaseAgent):
    """
    Crawls Rightmove (UK) search pages and extracts listing detail pages.
    """

    def __init__(self, config: Dict[str, Any], compliance_manager: ComplianceManager):
        super().__init__(name="RightmoveCrawler", config=config)
        self.compliance_manager = compliance_manager
        self.snapshot_service = SnapshotService()
        self.base_url = config.get("base_url", "https://www.rightmove.co.uk")
        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", 5))
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": config.get("user_agent", "PropertyScanner/1.0")}
        )

    def _fetch_url(self, url: str, *, retries: int = 3, timeout_s: float = 30.0) -> Optional[str]:
        if not self.compliance_manager.check_and_wait(url, rate_limit_seconds=self.rate_limit_seconds):
            logger.warning("rightmove_blocked_by_robots", url=url)
            return None

        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=timeout_s)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code in {401, 403, 429}:
                    logger.warning("rightmove_blocked", url=url, status=resp.status_code)
                    return None
                logger.warning("rightmove_fetch_failed", url=url, status=resp.status_code)
            except Exception as exc:
                logger.warning("rightmove_fetch_error", url=url, error=str(exc))
            time.sleep(1.5 ** attempt)
        return None

    def _extract_listing_urls(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if "/properties/" not in href:
                continue
            full = urljoin(self.base_url, href)
            urls.add(full.split("#")[0])
        return sorted(urls)

    def _expand_search_urls(self, start_url: str, max_pages: int, page_size: int) -> List[str]:
        if max_pages <= 1:
            return [start_url]
        parsed = urlsplit(start_url)
        query = parse_qs(parsed.query)
        if "index" not in query:
            return [start_url]
        try:
            base_index = int(query.get("index", ["0"])[0] or 0)
        except ValueError:
            base_index = 0
        urls = []
        for page in range(max_pages):
            query["index"] = [str(base_index + page * page_size)]
            new_query = urlencode(query, doseq=True)
            urls.append(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)))
        return urls

    def _extract_external_id(self, url: str) -> str:
        try:
            parts = url.split("/properties/")[1].split("/")
            external_id = parts[0]
            if external_id:
                return external_id
        except Exception:
            pass
        return hashlib.md5(url.encode("utf-8")).hexdigest()[:12]

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        source_id = self.config.get("id", "rightmove_uk")

        target_urls = list(input_payload.get("target_urls") or [])
        listing_url = input_payload.get("listing_url")
        if listing_url:
            target_urls.append(listing_url)

        listing_id = input_payload.get("listing_id")
        if listing_id:
            template = self.config.get("listing_url_template", f"{self.base_url}/properties/{{listing_id}}")
            target_urls.append(template.format(listing_id=listing_id))

        listing_ids = input_payload.get("listing_ids") or []
        if listing_ids:
            template = self.config.get("listing_url_template", f"{self.base_url}/properties/{{listing_id}}")
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
            max_pages = int(input_payload.get("max_pages", 1))
            max_pages = min(max_pages, 42)
            page_size = int(input_payload.get("page_size", 24))

            for search_url in start_urls:
                for page_url in self._expand_search_urls(search_url, max_pages, page_size):
                    html = self._fetch_url(page_url)
                    if not html:
                        continue
                    listing_urls.extend(self._extract_listing_urls(html))

            listing_urls = list(dict.fromkeys(listing_urls))

        max_listings = int(input_payload.get("max_listings", 0))
        if max_listings > 0:
            listing_urls = listing_urls[:max_listings]

        if not listing_urls:
            return AgentResponse(status="failure", data=[], errors=["no_listings_found"])

        for url in listing_urls:
            html_content = self._fetch_url(url)
            if not html_content:
                errors.append(f"fetch_failed:{url}")
                continue

            external_id = self._extract_external_id(url)
            meta = self.snapshot_service.save_snapshot(
                content=html_content,
                source_id=source_id,
                external_id=external_id,
                listing_url=url,
            )
            snapshot_path = meta.file_path if meta else None

            raw_listing = RawListing(
                source_id=source_id,
                external_id=external_id,
                url=url,
                raw_data={"html_snippet": html_content, "is_detail_page": True},
                fetched_at=datetime.utcnow(),
                html_snapshot_path=snapshot_path,
            )
            listings.append(raw_listing)

        status = "success" if listings else "failure"
        return AgentResponse(status=status, data=listings, errors=errors)
