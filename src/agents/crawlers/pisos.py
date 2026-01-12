import time
from datetime import datetime
from typing import Any, Dict, List
from playwright.sync_api import sync_playwright, Page
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing
from src.utils.compliance import ComplianceManager
from playwright_stealth import Stealth

class PisosCrawlerAgent(BaseAgent):
    """
    Crawls Pisos.com using Playwright.
    Less aggressive than Idealista, but still uses basic stealth.
    """
    def __init__(self, config: Dict, compliance_manager: ComplianceManager = None):
        super().__init__(name="PisosCrawler")
        self.config = config
        self.compliance_manager = compliance_manager or ComplianceManager()

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        start_url = input_payload.get("start_url")
        if not start_url:
            return AgentResponse(status="failure", errors=["No start_url provided"])

        if not self.compliance_manager.check_and_wait(start_url, rate_limit_seconds=2.0):
            return AgentResponse(status="failure", data=None, errors=["Rate Limited or Disallowed"])

        listings = []
        errors = []
        
        self.logger.info("pisos_crawl_start", url=start_url)

        with sync_playwright() as p:
            # 1. Launch Browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            stealth = Stealth()
            stealth.apply_stealth_sync(page)

            listing_urls = []
            
            # --- Input Strategy ---
            if input_payload.get("target_urls"):
                 # Direct Crawl Mode
                 listing_urls = input_payload["target_urls"]
                 self.logger.info("direct_crawl_mode", count=len(listing_urls))
            else:
                # --- Step 1: Get Listing URLs from Search Page ---
                try:
                    response = page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
                    
                    if response.status != 200:
                       self.logger.warning("non_200_response", status=response.status)
                    
                    # Wait for listings
                    try:
                        page.wait_for_selector("div.ad-preview", timeout=10000)
                        
                        # Extract URLs
                        items = page.locator("div.ad-preview").all()
                        self.logger.info("items_found_on_page", count=len(items))
                        
                        for item in items:
                            try:
                                # Try to find the link in the title or the card itself
                                # Usually a.ad-preview__title or similar
                                # Using JS to extract href to be robust
                                url = item.evaluate("el => { const a = el.querySelector('a.ad-preview__title'); return a ? a.href : null; }")
                                if url:
                                    listing_urls.append(url)
                            except Exception as e:
                                pass
                                
                    except Exception as e:
                        self.logger.warning("no_listings_found", error=str(e))
                            
                except Exception as e:
                    errors.append(f"Search page load error: {e}")
            
            # --- Step 2: Visit Each Detail Page ---
            self.logger.info("visiting_details", count=len(listing_urls))
            
            # Limit removed for production
            for url in listing_urls: 
                try:
                    # Random small delay
                    time.sleep(1 + (time.time() % 1)) 
                    
                    page.goto(url, timeout=15000, wait_until="domcontentloaded")
                    
                    # Extract full HTML
                    full_html = page.content()
                    
                    # Extract ID from URL if possible or generate one
                    # url structure: /comprar/piso-city-id_subid/
                    lid = url.split("-")[-1].replace("/", "")
                    
                    raw = RawListing(
                        source_id="pisos",
                        external_id=lid,
                        url=url,
                        raw_data={"html_snippet": full_html, "is_detail_page": True},
                        fetched_at=datetime.now()
                    )
                    listings.append(raw)
                    
                except Exception as e:
                    self.logger.warning("detail_page_failed", url=url, error=str(e))
                    errors.append(f"Detail page {url} failed: {e}")
            
            browser.close()

        return AgentResponse(
            status="success" if listings else "failure",
            data=listings,
            errors=errors
        )
