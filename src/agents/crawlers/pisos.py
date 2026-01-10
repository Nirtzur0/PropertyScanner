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
            return AgentResponse(status="failure", errors=["Rate Limited or Disallowed"])

        listings = []
        errors = []
        
        self.logger.info("pisos_crawl_start", url=start_url)

        with sync_playwright() as p:
            # 1. Launch Browser (Headless is usually fine for Pisos)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            
            # Simple stealth
            stealth = Stealth()
            stealth.apply_stealth_sync(page)

            try:
                response = page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
                
                if response.status != 200:
                   self.logger.warning("non_200_response", status=response.status)
                   # For Pisos, sometimes they redirect or 403 on aggressive searching, but usually ok.
                
                # Wait for listings
                # Selector: div.ad-preview
                page.wait_for_selector("div.ad-preview", timeout=10000)
                
                # Extract
                items = page.locator("div.ad-preview").all()
                self.logger.info("items_found", count=len(items))
                
                for item in items:
                    try:
                        # Get External ID
                        lid = item.get_attribute("data-id") or item.get_attribute("id")
                        if not lid:
                            continue
                            
                        # Get HTML Snippet
                        html_snippet = item.inner_html()
                        # Also wrap it in the container for correct parsing structure if needed,
                        # but BeautifulSoup usually handles fragments. 
                        # To be safe, wrapping in a div with the class.
                        full_html = f'<div class="ad-preview" data-id="{lid}">{html_snippet}</div>'
                        
                        raw = RawListing(
                            source_id="pisos",
                            external_id=lid,
                            url=start_url, # Parent URL, individual URL extracted in Normalizer
                            raw_data={"html_snippet": full_html},
                            fetched_at=datetime.now()
                        )
                        listings.append(raw)
                        
                    except Exception as e:
                        errors.append(f"Error extracting item: {e}")
                        
            except Exception as e:
                errors.append(f"Page load error: {e}")
            finally:
                browser.close()

        return AgentResponse(
            status="success" if listings else "failure",
            data=listings,
            errors=errors
        )
