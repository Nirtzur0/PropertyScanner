import asyncio
import argparse
import hashlib
import json
import time
import os
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from src.core.domain.schema import RawListing, CanonicalListing
from src.agents.processors.pisos import PisosNormalizerAgent
from src.services.enrichment_service import EnrichmentService
from src.services.feature_fusion import FeatureFusionService
from src.services.storage import StorageService
import logging
import structlog
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()

TARGET_COUNT = 1000
BATCH_SIZE = 20
MAX_WORKERS = 4 # Be careful with Ollama load

START_URL_SALE = "https://www.pisos.com/venta/pisos-madrid/"
START_URL_RENT = "https://www.pisos.com/alquiler/pisos-madrid/"
CHECKPOINT_FILE_SALE = "data/harvest_urls_sale.json"
CHECKPOINT_FILE_RENT = "data/harvest_urls_rent.json"

class Harvester:
    def __init__(self, mode="sale"):
        self.mode = mode
        self.storage = StorageService()
        self.normalizer = PisosNormalizerAgent()
        self.enricher = EnrichmentService()
        self.fusion = FeatureFusionService()
        
    def collect_urls(self) -> List[str]:
        """
        Navigates search pages to collect URLs.
        """
        urls = []

        chk_file = CHECKPOINT_FILE_SALE if self.mode == "sale" else CHECKPOINT_FILE_RENT
        start_url = START_URL_SALE if self.mode == "sale" else START_URL_RENT
        
        if os.path.exists(chk_file):
            try:
                with open(chk_file, 'r') as f:
                    urls = json.load(f)
                    logger.info("Loaded URLs from checkpoint", count=len(urls), mode=self.mode)
                    if len(urls) >= TARGET_COUNT:
                        return urls
            except:
                pass

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Set False to verify if needed
            page = browser.new_page()
            stealth = Stealth()
            stealth.apply_stealth_sync(page)
            
            logger.info("Navigating to start url", url=start_url)
            page.goto(start_url, timeout=60000)
            
            # Cookie consent?
            try:
                page.locator("#didomi-notice-agree-button").click(timeout=5000)
            except:
                pass
            
            while len(urls) < TARGET_COUNT:
                # Extract
                cards = page.locator("div.ad-preview, div.row.clearfix").all()
                # Selectors vary
                # Generic link extraction
                links = page.eval_on_selector_all("a.ad-preview__title, a.ad-preview__header", "els => els.map(e => e.href)")
                
                new_count = 0
                for link in links:
                    if link not in urls:
                        urls.append(link)
                        new_count += 1
                
                logger.info("Page processed", total_urls=len(urls), new_on_page=new_count)
                
                # Checkpoint
                with open(chk_file, 'w') as f:
                    json.dump(urls, f)
                    
                if len(urls) >= TARGET_COUNT:
                    break
                    
                # Dismiss overlays (Save Search Modal)
                try:
                    modal = page.locator(".modal__wrapper.js-saveSearchModal")
                    if modal.count() > 0 and modal.first.is_visible():
                        logger.info("Dismissing Save Search Modal")
                        # Try closing with X button
                        close_btn = modal.locator(".modal__close, .close")
                        if close_btn.count() > 0:
                            close_btn.first.click()
                        else:
                            # Try Escape
                            page.keyboard.press("Escape")
                        time.sleep(1)
                except:
                    pass

                # Next Page
                try:
                    next_btn = page.locator(".pagination__next")
                    if next_btn.count() > 0:
                        # Ensure not obscured
                        next_btn.first.scroll_into_view_if_needed()
                        next_btn.first.click(force=True) # Force click to bypass checks
                        page.wait_for_load_state("domcontentloaded")
                        time.sleep(2) 
                    else:
                        logger.warning("No next button found (.pagination__next)!")
                        # Try text fallback
                        try:
                            # Force click fallback too
                            page.get_by_text("Siguiente", exact=True).click(force=True)
                            page.wait_for_load_state("domcontentloaded")
                            time.sleep(2)
                        except:
                            logger.error("Pagination failed completely.")
                            page.screenshot(path="debug_pagination_fail.png")
                            break
                except Exception as e:
                    logger.error("Pagination error", error=str(e))
                    page.screenshot(path="debug_pagination_error.png")
                    break
            
            browser.close()
            
        return urls

    def process_url(self, url: str):
        """
        Fetches detail page, normalizes, labels, saves.
        """
        try:
            # Fetch HTML 
            html = ""
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                html = page.content()
                browser.close()
                
            if not html:
                return
                
            raw = RawListing(
                source_id="pisos",
                external_id=url.split("/")[-1].split("_")[-1] or "mx",
                url=url,
                raw_data={"html_snippet": html},
                fetched_at=datetime.utcnow()
            )
            
            response = self.normalizer.run({"raw_listings": [raw]})
            if response.data:
                canonical = response.data[0]
                
                # Enrich
                if canonical.location and canonical.location.lat:
                     city = self.enricher.get_city(canonical.location.lat, canonical.location.lon)
                     if city != "Unknown": canonical.location.city = city

                # Feature Fusion
                canonical = self.fusion.fuse(canonical)
                     
                self.storage.save_listings([canonical])
                logger.info("Saved listing", id=canonical.id)
                
        except Exception as e:
             logger.error("Failed processing url", url=url, error=str(e))

    def run(self):
        logger.info("Starting Harvest...")
        
        # 1. Collect
        urls = self.collect_urls()
        logger.info("Collection complete", count=len(urls))
        
        # 2. Process
        # 2. Process
        logger.info(f"Processing {len(urls)} URLs with {MAX_WORKERS} workers...")
        
        # We need a browser per thread (not thread-safe to share context easily in sync mode unless careful)
        # Better approach for ThreadPool with Playwright Sync is to launch a browser in each thread OR use one browser and new contexts.
        # But for simplicity and stability, we can keep the single-threaded loop IF it's fast enough.
        # The user specifically asked to ENABLE PARALLELISM.
        
        # Function to process a single URL (self-contained)
        def process_one(url):
            try:
                # Check DB first to avoid re-work
                # Extract probable ID from URL (consistent hashing)
                clean_url = url.rstrip("/")
                slug = clean_url.split("/")[-1]
                parts = slug.split("_")
                if len(parts) > 1 and parts[-1].isdigit():
                    ext_id = parts[-1]
                else:
                    ext_id = slug
                
                if not ext_id: ext_id = "unknown" # Should match below logic roughly

                unique_str = f"pisos_{ext_id}"
                can_id = hashlib.md5(unique_str.encode()).hexdigest()
                
                # Check if we should skip
                existing = self.storage.get_listing(can_id)
                if existing:
                    logger.info("Skipping known listing", id=can_id)
                    return
                # Launch a fresh context for isolation
                with sync_playwright() as p:
                    # Headless chromium invocation is cheap
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    # Stealth
                    stealth = Stealth()
                    stealth.apply_stealth_sync(page)
                    
                    page.goto(url, timeout=45000)
                    html = page.content()
                    browser.close()

                if not html: return

                # ID Extraction Fix:
                # URL: .../piso-...-12345_67890/
                # 1. Strip trailing slash
                clean_url = url.rstrip("/")
                # 2. Get last segment: piso-...-12345_67890
                slug = clean_url.split("/")[-1]
                # 3. Get actual ID part (last chunk after _)
                # some urls might be differnt, fallback to slug hash if needed?
                # Usually: ..._12345
                
                parts = slug.split("_")
                if len(parts) > 1 and parts[-1].isdigit():
                    ext_id = parts[-1]
                else:
                    # Fallback: Just use the whole slug if structure is weird
                    ext_id = slug
                
                if not ext_id:
                     # Very fallback
                     ext_id = hashlib.md5(url.encode()).hexdigest()[:10]

                raw = RawListing(
                    source_id="pisos",
                    external_id=ext_id,
                    url=url,
                    raw_data={"html_snippet": html},
                    fetched_at=datetime.now(timezone.utc)
                )
                
                response = self.normalizer.run({"raw_listings": [raw]})
                if response.data:
                    canonical = response.data[0]
                    # Tag listing type
                    canonical.listing_type = self.mode
                    
                    # Enrich loc
                    if canonical.location and canonical.location.lat:
                            city = self.enricher.get_city(canonical.location.lat, canonical.location.lon)
                            if city != "Unknown": canonical.location.city = city
                    
                    # Feature Fusion (LLM + VLM)
                    canonical = self.fusion.fuse(canonical)
                            
                    self.storage.save_listings([canonical])
                    logger.info("Saved listing", id=canonical.id)
                else:
                    logger.warning("Normalization returned no data", url=url)

            except Exception as e:
                logger.error("Worker failed", url=url, error=str(e))

        # Parallel Execution
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(process_one, urls))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, default="sale", choices=["sale", "rent"], help="Harvest mode: sale or rent")
    parser.add_argument("--clean", action="store_true", help="Clear database and checkpoints before starting")
    args = parser.parse_args()
    
    if args.clean:
        logger.warning("CLEAN START: Deleting database and checkpoints...")
        if os.path.exists("data/listings.db"): os.remove("data/listings.db")
        if os.path.exists(CHECKPOINT_FILE_SALE): os.remove(CHECKPOINT_FILE_SALE)
        if os.path.exists(CHECKPOINT_FILE_RENT): os.remove(CHECKPOINT_FILE_RENT)
        # Re-init DB
        from src.services.storage import StorageService
        StorageService() # This creates the tables if missing
    
    logger.info("Starting Harvester", mode=args.mode)
    harvester = Harvester(mode=args.mode)
    harvester.run()
