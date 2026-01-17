import time
from datetime import datetime
from typing import Any, Dict, List
import concurrent.futures
from playwright.sync_api import sync_playwright, Page
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
try:
    from playwright_stealth import Stealth
except Exception:  # pragma: no cover - optional dependency
    Stealth = None

def _run_pisos_crawl(config: Dict, input_payload: Dict) -> List[RawListing]:
    """Process-isolated crawl function."""
    start_url = input_payload.get("start_url")
    listings = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        if Stealth:
            try:
                stealth = Stealth()
                stealth.apply_stealth_sync(page)
            except Exception:
                pass

        listing_urls = []
        
        # --- Input Strategy ---
        if input_payload.get("target_urls"):
                listing_urls = input_payload["target_urls"]
        else:
            # --- Step 1: Get Listing URLs from Search Page ---
            try:
                response = page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
                
                if response.status != 200:
                    pass # Log in main process
                
                try:
                    page.wait_for_selector("div.ad-preview", timeout=10000)
                    items = page.locator("div.ad-preview").all()
                    
                    for item in items:
                        try:
                            # Using JS to extract href to be robust
                            url = item.evaluate("el => { const a = el.querySelector('a.ad-preview__title'); return a ? a.href : null; }")
                            if url:
                                listing_urls.append(url)
                        except Exception:
                            pass
                            
                except Exception:
                    pass
            except Exception:
                pass
        
        print(f"PisosCrawler: processing {len(listing_urls)} listings...")
        
        # --- Step 2: Visit Each Detail Page ---
        for i, url in enumerate(listing_urls): 
            try:
                print(f"PisosCrawler: fetching {i+1}/{len(listing_urls)}: {url}")
                time.sleep(1 + (time.time() % 1)) 
                page.goto(url, timeout=15000, wait_until="domcontentloaded")
                full_html = page.content()
                
                # Extract ID
                lid = url.split("-")[-1].replace("/", "")
                
                raw = RawListing(
                    source_id=config.get("id", "pisos"),
                    external_id=lid,
                    url=url,
                    raw_data={"html_snippet": full_html, "is_detail_page": True},
                    fetched_at=datetime.now()
                )
                listings.append(raw)
                
            except Exception:
                pass
        
        browser.close()
        
    return listings

class PisosCrawlerAgent(BaseAgent):
    """
    Crawls Pisos.com using Playwright (Multiprocess).
    """
    def __init__(self, config: Dict, compliance_manager: ComplianceManager = None):
        super().__init__(name="PisosCrawler")
        self.config = config
        self.compliance_manager = compliance_manager or ComplianceManager(user_agent="PropertyScannerBot/1.0")

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        start_url = input_payload.get("start_url")
        if not start_url:
            return AgentResponse(status="failure", errors=["No start_url provided"])

        if not self.compliance_manager.check_and_wait(start_url, rate_limit_seconds=2.0):
            return AgentResponse(status="failure", data=None, errors=["Rate Limited or Disallowed"])

        listings = []
        errors = []
        
        self.logger.info("pisos_crawl_start", url=start_url)
        
        try:
             with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_pisos_crawl, self.config, input_payload)
                listings = future.result()
                
        except Exception as e:
            self.logger.error("pisos_crawl_failed", error=str(e))
            errors.append(str(e))

        return AgentResponse(
            status="success" if listings else "failure",
            data=listings,
            errors=errors
        )
