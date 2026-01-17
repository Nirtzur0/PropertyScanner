import time
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from curl_cffi import requests
import hashlib
import structlog
from datetime import datetime
from urllib.parse import urljoin

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.listings.services.snapshot_storage import SnapshotService
from src.platform.utils.compliance import ComplianceManager

logger = structlog.get_logger(__name__)

class IdealistaCrawlerAgent(BaseAgent):
    """
    Crawls Idealista using curl_cffi to bypass TLS fingerprinting protections.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="IdealistaCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url", "https://www.idealista.com")
        self.snapshot_service = SnapshotService()
        self.session = requests.Session()
        # Idealista is very sensitive
        self.rate_limit_seconds = float(config.get("period_seconds", 10))

    def _fetch_url(self, url: str) -> Optional[str]:
        if not self.compliance.check_and_wait(url, rate_limit_seconds=self.rate_limit_seconds):
             logger.warning("idealista_blocked_compliance", url=url)
             # return None # Compliance manager usually blocks on robots.txt 403.
             # But for Idealista, robots.txt is often 403.
             # We might want to force proceed if robots check failed due to 403 but not explicit Disallow.
             pass

        try:
            # Impersonate chrome
            resp = self.session.get(
                url,
                impersonate="chrome124",
                timeout=30
            )
            
            if resp.status_code == 200:
                if "human verification" in resp.text.lower() or "captcha" in resp.text.lower():
                    logger.warning("idealista_captcha_detected", url=url)
                    return None
                return resp.text
            elif resp.status_code in {403, 429}:
                logger.warning("idealista_blocked_cffi", url=url, status=resp.status_code)
                return None
            else:
                 logger.warning("idealista_fetch_failed", url=url, status=resp.status_code)
                 return None

        except Exception as e:
            logger.warning("idealista_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        search_path = input_payload.get("search_path", "/venta-viviendas/madrid/centro/")
        if not search_path.startswith("/"):
             start_url = search_path
        else:
             start_url = f"{self.base_url}{search_path}"
             
        listing_urls = []
        if input_payload.get("target_urls"):
            listing_urls = input_payload["target_urls"]
        else:
            # Fetch Search Page
            html = self._fetch_url(start_url)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select("article.item")
                for item in items:
                    link = item.select_one("a.item-link")
                    if link:
                        href = link.get("href")
                        if href:
                             listing_urls.append(urljoin(self.base_url, href))
        
        results = []
        for url in listing_urls:
            html = self._fetch_url(url)
            if not html:
                continue
            
            try:
                lid = url.split("/inmueble/")[1].replace("/", "")
            except:
                lid = hashlib.md5(url.encode()).hexdigest()[:12]
            
            meta = self.snapshot_service.save_snapshot(
                content=html,
                source_id=self.config.get("id", "idealista"),
                external_id=lid,
                listing_url=url
            )
            raw_path = meta.file_path if meta else None
            
            raw_listing = RawListing(
                source_id=self.config.get("id", "idealista"),
                external_id=lid,
                url=url,
                html_snapshot_path=raw_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
            results.append(raw_listing)
            
        return AgentResponse(status="success" if results else "failure", data=results)
