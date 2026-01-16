import time
from typing import Any, Dict, List
from playwright.sync_api import sync_playwright, Page
from playwright_stealth import Stealth
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing
from src.utils.compliance import ComplianceManager
from datetime import datetime
import json
import concurrent.futures

from src.services.snapshot_storage import SnapshotService

# Standalone function for multiprocess execution
def _run_crawl_process(config: Dict[str, Any], input_payload: Dict[str, Any]) -> List[RawListing]:
    """
    Executes the crawl in a separate process to ensure a clean Event Loop for Playwright.
    """
    base_url = config.get("base_url")
    # Re-instantiate services in the new process
    # Note: Rate limits won't share state with main process, acceptable for single-run debug.
    compliance = ComplianceManager(user_agent="PropertyScannerBot/1.0") 
    snapshot_service = SnapshotService()

    search_path = input_payload.get("search_path", "/venta-viviendas/madrid/centro/")
    start_url = f"{base_url}{search_path}"
    
    # Pre-check (though we do it in main process too, safe to double check or skip)
    # period_seconds defaults to 10 if not set
    if not compliance.check_and_wait(start_url, rate_limit_seconds=config.get("period_seconds", 10)):
        # In a real scenario we might want to return an error signal, 
        # but here we'll just return empty or raise.
        pass # proceed, check checks robots.txt mostly.

    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
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
        stealth = Stealth()
        stealth.apply_stealth_sync(page)
        
        listing_urls = []
        
        try:
            if input_payload.get("target_urls"):
                listing_urls = input_payload["target_urls"]
            else:
                page.goto(start_url, timeout=45000, wait_until="domcontentloaded")
                
                # Human behavior
                page.mouse.move(100, 100)
                time.sleep(1)
                page.evaluate("window.scrollTo(0, 500)")
                
                page.wait_for_selector("article.item", timeout=15000)
                items = page.locator("article.item").all()
                
                for item in items:
                    try:
                        link_el = item.locator("a.item-link").first
                        href = link_el.get_attribute("href")
                        if href:
                            full_url = f"{base_url}{href}"
                            listing_urls.append(full_url)
                    except:
                        pass
                        
        except Exception as e:
            if "403" in str(e) or "challenge" in str(e):
                browser.close()
                raise e
            # Log but continue (will result in empty listing_urls if critical)

        # Visit Details
        for url in listing_urls:
            try:
                time.sleep(2 + (time.time() % 3))
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                
                page.mouse.move(200, 200)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight/3)")
                time.sleep(1)
                
                html_content = page.content()
                
                try:
                    lid = url.split("/inmueble/")[1].replace("/", "")
                except:
                    lid = "unknown_" + str(int(time.time()))
                
                # Snapshot
                meta = snapshot_service.save_snapshot(
                    content=html_content,
                    source_id=config.get("id", "idealista"),
                    external_id=lid
                )
                
                raw_path = meta.file_path if meta else None
                
                raw_listing = RawListing(
                    source_id=config.get("id", "idealista"),
                    external_id=lid,
                    url=url,
                    html_snapshot_path=raw_path,
                    raw_data={"html_snippet": html_content, "is_detail_page": True},
                    fetched_at=datetime.now()
                )
                results.append(raw_listing)
                
            except Exception as e:
                 # In a worker, we might print or ignore. 
                 # structlog in main process won't see this unless we configure it in worker.
                 print(f"Worker Error visiting {url}: {e}")
                 
        browser.close()
        
    return results

class IdealistaCrawlerAgent(BaseAgent):
    """
    Specialized agent for crawling Idealista using Playwright.
    Runs logic in a separate process to avoid async event loop collisions.
    """
    def __init__(self, config: Dict[str, Any], compliance: ComplianceManager):
        super().__init__(name="IdealistaCrawler", config=config)
        self.compliance = compliance
        self.base_url = config.get("base_url")
        self.snapshot_service = SnapshotService()

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """
        Expects input_payload to contain 'search_url' or parameters to build one.
        """
        search_path = input_payload.get("search_path", "/venta-viviendas/madrid/centro/")
        start_url = f"{self.base_url}{search_path}"
        
        # Initial compliance check in main process (shared state)
        if not self.compliance.check_and_wait(start_url, rate_limit_seconds=self.config.get("period_seconds", 10)):
             return AgentResponse(status="failure", data=[], errors=["Blocked by robot rules or rate limit"])

        try:
            # Run the heavy lifting in a separate process
            with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
                # We pass 'config' and 'input_payload'. 'self' cannot be passed effectively if it has locks.
                # We reconstruct necessary context in the worker.
                future = executor.submit(_run_crawl_process, self.config, input_payload)
                results = future.result()
                
            self.logger.info("crawl_process_completed", count=len(results))
            return AgentResponse(status="success", data=results)
            
        except Exception as e:
            self.logger.error("crawl_failed", error=str(e))
            return AgentResponse(status="failure", data=[], errors=[str(e)])
