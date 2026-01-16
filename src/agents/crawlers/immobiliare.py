import time
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, Page, TimeoutError
from playwright_stealth import Stealth
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing
from src.utils.compliance import ComplianceManager
from src.services.snapshot_storage import SnapshotService

class ImmobiliareCrawlerAgent(BaseAgent):
    """
    Crawls Immobiliare.it (Italy).
    Visits search results and then detail pages.
    """
    def __init__(self, config: Dict[str, Any], compliance_manager: ComplianceManager):
        super().__init__(name="ImmobiliareCrawler", config=config)
        self.compliance_manager = compliance_manager
        self.snapshot_service = SnapshotService()
        self.base_url = config.get("base_url", "https://www.immobiliare.it")
        rate_conf = config.get("rate_limit", {}) or {}
        self.rate_limit_seconds = float(rate_conf.get("period_seconds", 3))

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        source_id = self.config.get("id", "immobiliare_it")
        start_url = input_payload.get("start_url")
        if not start_url:
            # Check for city/search params if full URL not provided
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

        compliance_url = target_urls[0] if target_urls else start_url
        if not self.compliance_manager.check_and_wait(compliance_url, rate_limit_seconds=self.rate_limit_seconds):
            return AgentResponse(status="failure", errors=["Rate Limited or Disallowed"])

        listings = []
        errors = []
        
        self.logger.info("crawl_start", target=start_url)

        with sync_playwright() as p:
            # Launch
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                locale="it-IT"
            )
            
            page = context.new_page()
            stealth = Stealth()
            stealth.apply_stealth_sync(page)

            listing_urls = []
            
            # --- Input Strategy ---
            if target_urls:
                listing_urls = target_urls
                self.logger.info("direct_crawl_mode", count=len(listing_urls))
            else:
                # --- Step 1: Search Page ---
                try:
                    self.logger.info("navigating_search", url=start_url)
                    page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
                    
                    # Handling Cookie Consent (common in EU)
                    try:
                        # Generic guess for cookie buttons
                        page.get_by_text("Accetta", exact=True).click(timeout=3000)
                    except:
                        pass
    
                    # Wait for listings
                    try:
                        # Wait for generally any likely container
                        page.wait_for_selector("li.nd-list__item, div.in-card, li.in-realEstateResults__item", timeout=10000)
                    except TimeoutError:
                        self.logger.warning("timeout_waiting_listings")
    
                    # Extract URLs
                    anchors = page.locator("li.nd-list__item a.in-card__title, li.in-realEstateResults__item a.in-card__title").all()
                    
                    if not anchors:
                        # Fallback for updated UI
                        anchors = page.locator("a.in-reListCard__title").all()
                    
                    self.logger.info("items_found", count=len(anchors))
                    
                    for a in anchors:
                        href = a.get_attribute("href")
                        if href:
                             listing_urls.append(href)
                             
                    # Deduplicate
                    listing_urls = list(set(listing_urls))
    
                except Exception as e:
                    errors.append(f"Search page error: {e}")
                    self.logger.error("search_failed", error=str(e))

            # --- Step 2: Detail Pages ---
            self.logger.info("visiting_details", count=len(listing_urls))
            
            for url in listing_urls:
                try:
                    # Politeness delay
                    time.sleep(2 + (time.time() % 2))
                    
                    self.logger.info("visiting", url=url)
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    
                    full_html = page.content()
                    
                    # Extract ID
                    # URL usually: https://www.immobiliare.it/annunci/123456789/
                    try:
                        lid = url.split("/annunci/")[1].split("/")[0]
                    except:
                        lid = "unknown_" + str(int(time.time()))
                    
                    # Save HTML snapshot
                    meta = self.snapshot_service.save_snapshot(
                        content=full_html,
                        source_id=source_id,
                        external_id=lid,
                        listing_url=url,
                    )
                    snapshot_path = meta.file_path if meta else None

                    raw = RawListing(
                        source_id=source_id,
                        external_id=lid,
                        url=url,
                        html_snapshot_path=snapshot_path,
                        raw_data={"html_snippet": full_html, "is_detail_page": True},
                        fetched_at=datetime.now()
                    )
                    listings.append(raw)

                except Exception as e:
                    self.logger.warning("detail_failed", url=url, error=str(e))
                    errors.append(f"Detail failed {url}: {e}")

            browser.close()

        return AgentResponse(
            status="success" if listings else "failure",
            data=listings,
            errors=errors
        )
