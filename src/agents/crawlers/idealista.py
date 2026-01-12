import time
from typing import Any, Dict, List
from playwright.sync_api import sync_playwright, Page
from playwright_stealth import Stealth
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing
from src.utils.compliance import ComplianceManager
from datetime import datetime
import json

from src.services.snapshot_storage import SnapshotService

class IdealistaCrawlerAgent(BaseAgent):
    """
    Specialized agent for crawling Idealista using Playwright.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="IdealistaCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url")
        self.snapshot_service = SnapshotService()

    def _extract_listings_from_page(self, page: Page, source_id: str) -> List[RawListing]:
        """
        Extracts raw listing data from search results page.
        Note: This relies on specific Idealista DOM structure which changes often.
        """
        listings = []
        
        # This selector is a guess/example. In a real scenario, we'd inspect the DOM.
        # Ideally, we look for <article class="item-multimedia-container"> or similar.
        items = page.locator("article.item").all()
        
        for item in items:
            try:
                # Extract basic info to identifier the listing
                external_id = item.get_attribute("data-element-id") or "unknown"
                link_el = item.locator("a.item-link")
                relative_url = link_el.get_attribute("href")
                full_url = f"{self.base_url}{relative_url}"
                
                # We save the OUTER HTML of the list item as the raw data for now
                html_content = item.evaluate("el => el.outerHTML")
                
                # PERSIST RAW SNAPSHOT
                snapshot_path = self.snapshot_service.save_snapshot(
                    content=html_content,
                    source_id=source_id,
                    external_id=external_id
                )
                
                raw_listing = RawListing(
                    source_id=source_id,
                    external_id=external_id,
                    url=full_url,
                    html_snapshot_path=snapshot_path, # STORED
                    raw_data={"html_snippet": html_content}, # Keep for legacy/immediate processing
                    fetched_at=datetime.now()
                )
                listings.append(raw_listing)
                
            except Exception as e:
                self.logger.error("extraction_error", error=str(e))
                continue
                
        return listings

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """
        Expects input_payload to contain 'search_url' or parameters to build one.
        """
        search_path = input_payload.get("search_path", "/venta-viviendas/madrid/centro/")
        start_url = f"{self.base_url}{search_path}"
        
        if not self.compliance.check_and_wait(start_url, rate_limit_seconds=self.config.get("period_seconds", 10)):
             return AgentResponse(status="failure", data=[], errors=["Blocked by robot rules or rate limit"])

        results = []
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True) # Idealista might need headless=False for some stealth checks
                
                # Use stealth headers as recommended
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    extra_http_headers={
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                        "accept-language": "es-ES,es;q=0.9,en;q=0.8",
                        "upgrade-insecure-requests": "1"
                    }
                )
                page = context.new_page()
                
                # Apply Stealth
                stealth = Stealth()
                stealth.apply_stealth_sync(page)
                
                listing_urls = []
                
            try:
                # Direct Crawl Mode
                if input_payload.get("target_urls"):
                    listing_urls = input_payload["target_urls"]
                    self.logger.info("direct_crawl_mode", count=len(listing_urls))
                else:
                    # Search Mode
                    self.logger.info("navigating", url=start_url)
                    page.goto(start_url, timeout=45000, wait_until="domcontentloaded")
                    
                    # Human behavior simulation
                    page.mouse.move(100, 100)
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, 500)")
                    
                    # Wait for content to load
                    page.wait_for_selector("article.item", timeout=15000)
                    
                    # Extract URLs from Search Page
                    items = page.locator("article.item").all()
                    self.logger.info("items_found_on_page", count=len(items))
                    
                    for item in items:
                        try:
                            # Extract link
                            link_el = item.locator("a.item-link").first
                            href = link_el.get_attribute("href")
                            if href:
                                full_url = f"{self.base_url}{href}"
                                listing_urls.append(full_url)
                        except:
                            pass
                            
            except Exception as e:
                self.logger.error("search_page_failed", error=str(e))
                if "403" in str(e) or "challenge" in str(e):
                    raise e # Fast fail if blocked immediately

            # Visit Detail Pages (Common Logic)
                self.logger.info("visiting_details", count=len(listing_urls))
                
                # Limit for testing/safety in this iteration
                for url in listing_urls:
                    try:
                        # Heavy random delay
                        time.sleep(2 + (time.time() % 3))
                        
                        self.logger.info("visiting", url=url)
                        page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        
                        # Simulate reading
                        page.mouse.move(200, 200)
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight/3)")
                        time.sleep(1)
                        
                        # Extract full HTML
                        html_content = page.content()
                        
                        # Extract ID
                        # url params often have id, or from content
                        # idealista structure: .../inmueble/{id}/
                        try:
                            lid = url.split("/inmueble/")[1].replace("/", "")
                        except:
                            lid = "unknown_" + str(int(time.time()))
                        
                        # PERSIST RAW SNAPSHOT
                        snapshot_path = self.snapshot_service.save_snapshot(
                            content=html_content,
                            source_id=self.config.get("id", "idealista"),
                            external_id=lid
                        )
                        
                        raw_listing = RawListing(
                            source_id="idealista",
                            external_id=lid,
                            url=url,
                            html_snapshot_path=snapshot_path,
                            raw_data={"html_snippet": html_content, "is_detail_page": True},
                            fetched_at=datetime.now()
                        )
                        results.append(raw_listing)
                        
                    except Exception as e:
                        self.logger.error("detail_page_failed", url=url, error=str(e))
                        
                browser.close()
                
            return AgentResponse(status="success", data=results)
            
        except Exception as e:
            self.logger.error("crawl_failed", error=str(e))
            return AgentResponse(status="failure", data=[], errors=[str(e)])
