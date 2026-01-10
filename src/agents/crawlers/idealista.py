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
                browser = p.chromium.launch(headless=True)
                
                # Use stealth headers as recommended
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
                    extra_http_headers={
                        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                        "accept-language": "en-US;en;q=0.9",
                        "accept-encoding": "gzip, deflate, br",
                        "cache-control": "max-age=0",
                        "upgrade-insecure-requests": "1",
                        "sec-fetch-dest": "document",
                        "sec-fetch-mode": "navigate",
                        "sec-fetch-site": "none",
                        "sec-fetch-user": "?1"
                    }
                )
                page = context.new_page()
                
                # Apply Stealth
                stealth = Stealth()
                stealth.apply_stealth_sync(page)
                
                try:
                    self.logger.info("navigating", url=start_url)
                    # Increased timeout for stealth/blocking checks
                    page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
                    
                    # Wait for content to load
                    page.wait_for_selector("article.item", timeout=10000)
                    
                    # Extract
                    listings = self._extract_listings_from_page(page, source_id=self.config.get("id"))
                    results.extend(listings)
                    
                    self.logger.info("extracted_count", count=len(listings))
                    
                except Exception as e:
                    self.logger.error("crawl_failed_in_context", error=str(e))
                    timestamp = int(time.time())
                    try:
                        page.screenshot(path=f"data/debug_screenshot_{timestamp}.png")
                        with open(f"data/debug_page_{timestamp}.html", "w") as f:
                            f.write(page.content())
                        self.logger.info("debug_artifacts_saved", timestamp=timestamp)
                    except Exception as save_err:
                        self.logger.error("failed_to_save_debug", error=str(save_err))
                    raise e
                finally:
                    browser.close()
                
            return AgentResponse(status="success", data=results)
            
        except Exception as e:
            self.logger.error("crawl_failed", error=str(e))
            return AgentResponse(status="failure", data=[], errors=[str(e)])
