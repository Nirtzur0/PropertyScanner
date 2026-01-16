import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from curl_cffi import requests
import hashlib
import structlog

from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing
from src.utils.compliance import ComplianceManager
from src.services.snapshot_storage import SnapshotService

logger = structlog.get_logger(__name__)

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None

try:
    from playwright_stealth import Stealth
except Exception:  # pragma: no cover - optional dependency
    Stealth = None

class ImmobiliareCrawlerAgent(BaseAgent):
    """
    Crawls Immobiliare.it (Italy) using curl_cffi to bypass protection.
    """
    def __init__(self, config: Dict[str, Any], compliance_manager: ComplianceManager):
        super().__init__(name="ImmobiliareCrawler", config=config)
        self.compliance_manager = compliance_manager
        self.snapshot_service = SnapshotService()
        self.base_url = config.get("base_url", "https://www.immobiliare.it")
        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", 3))
        self.session = requests.Session()

    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        if not sync_playwright:
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                if Stealth:
                    try:
                        Stealth().apply_stealth_sync(page)
                    except Exception:
                        pass
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            logger.warning("immobiliare_playwright_failed", url=url, error=str(e))
            return None

    def _fetch_url(self, url: str, *, use_playwright: bool = False) -> Optional[str]:
        if not self.compliance_manager.check_and_wait(url, rate_limit_seconds=self.rate_limit_seconds):
            # Pass compliance errors if strict
            pass

        if use_playwright:
            html = self._fetch_with_playwright(url)
            if html:
                return html

        try:
            resp = self.session.get(
                url,
                impersonate="chrome124",
                timeout=30
            )
            
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code in {403, 429}:
                logger.warning("immobiliare_blocked_cffi", url=url, status=resp.status_code)
                return None
            else:
                 logger.warning("immobiliare_fetch_failed", url=url, status=resp.status_code)
                 return None

        except Exception as e:
            logger.warning("immobiliare_fetch_error", url=url, error=str(e))
            return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        source_id = self.config.get("id", "immobiliare_it")
        start_url = input_payload.get("start_url")
        if not start_url:
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

        prefer_playwright = self.config.get("use_playwright")
        if prefer_playwright is None:
            prefer_playwright = bool(sync_playwright and listing_url)
        
        listing_urls = []
        if target_urls:
            listing_urls = target_urls
        else:
            # Search Page
            html = self._fetch_url(start_url, use_playwright=False)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                # Immobiliare uses various selectors
                anchors = soup.select("li.nd-list__item a.in-card__title, li.in-realEstateResults__item a.in-card__title, a.in-reListCard__title")
                for a in anchors:
                    href = a.get("href")
                    if href:
                        listing_urls.append(href)
                        
        listings = []
        errors = []
        
        listing_urls = list(set(listing_urls))
        
        for url in listing_urls:
             # Check limits
             full_url = url if url.startswith("http") else urljoin(self.base_url, url)
             html = self._fetch_url(full_url, use_playwright=bool(prefer_playwright))
             if not html:
                 continue
             
             try:
                 lid = full_url.split("/annunci/")[1].split("/")[0]
             except:
                 lid = hashlib.md5(full_url.encode()).hexdigest()[:12]
             
             meta = self.snapshot_service.save_snapshot(
                content=html,
                source_id=source_id,
                external_id=lid,
                listing_url=full_url,
            )
             snapshot_path = meta.file_path if meta else None
             
             raw = RawListing(
                source_id=source_id,
                external_id=lid,
                url=full_url,
                html_snapshot_path=snapshot_path,
                raw_data={"html_snippet": html, "is_detail_page": True},
                fetched_at=datetime.now()
            )
             listings.append(raw)
             
        status = "success" if listings else "failure"
        return AgentResponse(status=status, data=listings, errors=errors)
