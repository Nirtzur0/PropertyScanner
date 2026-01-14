import argparse
import hashlib
import json
import time
import os
import gc
import re
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import requests

from src.core.domain.schema import RawListing, CanonicalListing
from src.agents.processors.pisos import PisosNormalizerAgent
from src.services.enrichment_service import EnrichmentService
from src.services.feature_fusion import FeatureFusionService
from src.services.storage import StorageService
from src.utils.seen_url_store import SeenUrlStore
from src.utils.harvest_state import (
    HarvestState,
    HarvestAreaState,
    load_harvest_state,
    save_harvest_state,
)
import logging
import structlog
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()

DEFAULT_TARGET_COUNT = 20000
DEFAULT_MAX_NO_NEW_PAGES = 500
DEFAULT_MAX_PAGES_PER_AREA = 10000
BATCH_SIZE = 40
MAX_WORKERS = 2 # Be careful with Ollama load
SEEN_URLS_DB = "data/harvest_seen_urls.sqlite3"

LEGACY_DEFAULT_START_URLS_SALE = [
    "https://www.pisos.com/venta/pisos-espana/",
    "https://www.pisos.com/venta/casas-espana/",
]
LEGACY_DEFAULT_START_URLS_RENT = [
    "https://www.pisos.com/alquiler/pisos-espana/",
    "https://www.pisos.com/alquiler/casas-espana/",
]
CHECKPOINT_FILE_SALE = "data/harvest_urls_sale.json"
CHECKPOINT_FILE_RENT = "data/harvest_urls_rent.json"
STATE_FILE_SALE = "data/harvest_state_sale.json"
STATE_FILE_RENT = "data/harvest_state_rent.json"

PISOS_MAPAWEB_BASE = "https://www.pisos.com/mapaweb"


def _extract_mapaweb_slugs(html: str, prefix: str) -> List[str]:
    slugs: List[str] = []
    for href in re.findall(r'href="([^"]+)"', html):
        if not href.startswith(prefix):
            continue
        if not href.endswith("/"):
            continue
        slug = href[len(prefix) : -1]
        if slug:
            slugs.append(slug)
    # preserve order while de-duping
    seen = set()
    out: List[str] = []
    for s in slugs:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _fetch_mapaweb_slugs(path: str, *, timeout_s: float = 30.0) -> List[str]:
    url = f"{PISOS_MAPAWEB_BASE}/{path.strip('/')}/"
    resp = requests.get(
        url,
        timeout=timeout_s,
        headers={"User-Agent": "Mozilla/5.0 (PropertyScanner/1.0; +https://example.invalid)"},
    )
    resp.raise_for_status()
    prefix = f"/mapaweb/{path.strip('/')}-"
    return _extract_mapaweb_slugs(resp.text, prefix)


def _default_start_urls(mode: str) -> List[str]:
    """
    Build a stable Spain-wide (province-level) start URL list from Pisos.com's sitemap pages.
    Falls back to the legacy /espana/ URLs if the sitemap fetch fails.
    """
    try:
        if mode == "sale":
            piso_slugs = _fetch_mapaweb_slugs("venta-piso")
            casa_slugs = _fetch_mapaweb_slugs("venta-casas")
            start_urls = [f"https://www.pisos.com/venta/pisos-{s}/" for s in piso_slugs] + [
                f"https://www.pisos.com/venta/casas-{s}/" for s in casa_slugs
            ]
        else:
            piso_slugs = _fetch_mapaweb_slugs("alquiler-piso")
            casa_slugs = _fetch_mapaweb_slugs("alquiler-casas")
            start_urls = [f"https://www.pisos.com/alquiler/pisos-{s}/" for s in piso_slugs] + [
                f"https://www.pisos.com/alquiler/casas-{s}/" for s in casa_slugs
            ]
        start_urls = [u for u in start_urls if u]
        if start_urls:
            return start_urls
    except Exception as e:
        logger.warning("Failed building default areas from mapaweb; falling back", mode=mode, error=str(e))

    return LEGACY_DEFAULT_START_URLS_SALE if mode == "sale" else LEGACY_DEFAULT_START_URLS_RENT


class Harvester:
    def __init__(
        self,
        mode: str = "sale",
        target_count: int = DEFAULT_TARGET_COUNT,
        start_urls: Optional[List[str]] = None,
        max_no_new_pages: int = DEFAULT_MAX_NO_NEW_PAGES,
        max_pages_per_area: int = DEFAULT_MAX_PAGES_PER_AREA,
        process_batch_size: int = BATCH_SIZE,
        max_workers: int = MAX_WORKERS,
        run_vlm: bool = True,
    ):
        self.mode = mode
        self.target_count = target_count
        self.start_urls = start_urls or _default_start_urls(mode)
        self.max_no_new_pages = max_no_new_pages
        self.max_pages_per_area = max_pages_per_area
        self.process_batch_size = max(1, int(process_batch_size))
        self.max_workers = max(1, int(max_workers))
        self.run_vlm = bool(run_vlm)
        self.storage = StorageService()
        self.normalizer = PisosNormalizerAgent()
        self.enricher = EnrichmentService()
        self.fusion = FeatureFusionService()

    def _canonicalize_url(self, url: str) -> str:
        return url.strip().rstrip("/")

    def _extract_external_id(self, url: str) -> str:
        clean_url = url.rstrip("/")
        slug = clean_url.split("/")[-1]
        ext_id = slug.split("-")[-1].split("_")[0]
        if ext_id:
            return ext_id
        return hashlib.md5(url.encode()).hexdigest()[:10]

    def _canonical_listing_id(self, external_id: str) -> str:
        unique_str = f"pisos_{external_id}"
        return hashlib.md5(unique_str.encode()).hexdigest()

    def _dismiss_cookie_consent(self, page) -> None:
        try:
            page.locator("#didomi-notice-agree-button").click(timeout=5000)
        except Exception:
            pass

    def _dismiss_overlays(self, page) -> None:
        try:
            modal = page.locator(".modal__wrapper.js-saveSearchModal")
            if modal.count() > 0 and modal.first.is_visible():
                logger.info("Dismissing Save Search Modal")
                close_btn = modal.locator(".modal__close, .close")
                if close_btn.count() > 0:
                    close_btn.first.click()
                else:
                    page.keyboard.press("Escape")
                time.sleep(1)
        except Exception:
            pass

    def _page_listing_links(self, page) -> List[str]:
        links = page.eval_on_selector_all(
            "a.ad-preview__title, a.ad-preview__header",
            "els => els.map(e => e.href)",
        )
        return [self._canonicalize_url(u) for u in links if u]

    def _click_next_page(self, page) -> Optional[str]:
        """
        Attempts to navigate to the next search page.
        Returns the new page URL, or None if pagination appears to be exhausted.
        """
        next_btn = page.locator(".pagination__next")
        if next_btn.count() == 0:
            try:
                before_url = page.url
                page.get_by_text("Siguiente", exact=True).click(force=True)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
                return page.url if page.url != before_url else page.url
            except Exception:
                return None

        btn = next_btn.first
        try:
            aria_disabled = btn.get_attribute("aria-disabled")
            cls = btn.get_attribute("class") or ""
            if aria_disabled == "true" or "disabled" in cls.lower():
                return None
        except Exception:
            pass

        before_url = page.url
        btn.scroll_into_view_if_needed()
        btn.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)
        return page.url if page.url != before_url else page.url

    def collect_urls(self) -> List[str]:
        """
        Navigates search pages to collect URLs across one or more start URLs ("areas").
        Includes safeguards to avoid getting stuck when an area runs out of results or pagination fails.
        """
        urls: List[str] = []

        chk_file = CHECKPOINT_FILE_SALE if self.mode == "sale" else CHECKPOINT_FILE_RENT
        state_file = STATE_FILE_SALE if self.mode == "sale" else STATE_FILE_RENT
        
        if os.path.exists(chk_file):
            try:
                with open(chk_file, 'r') as f:
                    urls = json.load(f)
                    logger.info("Loaded URLs from checkpoint", count=len(urls), mode=self.mode)
                    if len(urls) >= self.target_count:
                        return urls
            except:
                pass

        url_set = set(self._canonicalize_url(u) for u in urls)

        state: HarvestState = load_harvest_state(
            path=state_file,
            mode=self.mode,
            target_count=self.target_count,
            start_urls=self.start_urls,
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Set False to verify if needed
            page = browser.new_page()
            stealth = Stealth()
            stealth.apply_stealth_sync(page)
            

            self._dismiss_cookie_consent(page)

            for area_index in range(state.current_area_index, len(state.areas)):
                area: HarvestAreaState = state.areas[area_index]
                if area.done:
                    continue

                start_or_resume_url = area.current_url or area.start_url
                logger.info("Navigating to area", area_index=area_index, url=start_or_resume_url)
                page.goto(start_or_resume_url, timeout=60000)
                self._dismiss_cookie_consent(page)

                while len(urls) < self.target_count:
                    links = self._page_listing_links(page)
                    page_signature = area.compute_signature(links)

                    new_count = 0
                    for link in links:
                        if link not in url_set:
                            url_set.add(link)
                            urls.append(link)
                            new_count += 1

                    area.pages_visited += 1
                    area.current_url = self._canonicalize_url(page.url)

                    if new_count == 0:
                        area.consecutive_no_new_pages += 1
                    else:
                        area.consecutive_no_new_pages = 0

                    if area.last_signature == page_signature:
                        area.consecutive_same_signature += 1
                    else:
                        area.consecutive_same_signature = 0
                    area.last_signature = page_signature

                    logger.info(
                        "Page processed",
                        area_index=area_index,
                        total_urls=len(urls),
                        new_on_page=new_count,
                        consecutive_no_new_pages=area.consecutive_no_new_pages,
                    )

                    # Checkpoints
                    with open(chk_file, "w") as f:
                        json.dump(urls, f)
                    save_harvest_state(state_file, state)

                    if len(urls) >= self.target_count:
                        break

                    self._dismiss_overlays(page)

                    # Stop conditions for this area
                    if area.pages_visited >= self.max_pages_per_area:
                        logger.warning("Max pages reached for area; moving on", area_index=area_index)
                        break
                    if area.consecutive_no_new_pages >= self.max_no_new_pages:
                        logger.warning("No-new-pages limit reached; moving on", area_index=area_index)
                        break
                    if area.consecutive_same_signature >= 3:
                        logger.warning("Pagination appears stuck; moving on", area_index=area_index)
                        break

                    next_url = self._click_next_page(page)
                    if not next_url:
                        logger.info("No next page; area complete", area_index=area_index)
                        break

                area.done = True
                state.current_area_index = area_index + 1
                save_harvest_state(state_file, state)

                if len(urls) >= self.target_count:
                    break
            
            browser.close()
            
        return urls

    def _process_batch(self, urls: List[str]) -> None:
        logger.info("Processing batch", size=len(urls), max_workers=self.max_workers)

        def process_one(url: str) -> None:
            try:
                ext_id = self._extract_external_id(url)
                can_id = self._canonical_listing_id(ext_id)

                existing = self.storage.get_listing(can_id)
                if existing:
                    return

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    stealth = Stealth()
                    stealth.apply_stealth_sync(page)

                    page.goto(url, timeout=45000)
                    html = page.content()
                    browser.close()

                if not html:
                    return

                raw = RawListing(
                    source_id="pisos",
                    external_id=ext_id,
                    url=url,
                    raw_data={"html_snippet": html},
                    fetched_at=datetime.now(timezone.utc),
                )

                response = self.normalizer.run({"raw_listings": [raw]})
                if not response.data:
                    logger.warning("Normalization returned no data", url=url)
                    return

                canonical = response.data[0]
                canonical.listing_type = self.mode

                if canonical.location and canonical.location.lat:
                    city = self.enricher.get_city(canonical.location.lat, canonical.location.lon)
                    if city != "Unknown":
                        canonical.location.city = city

                canonical = self.fusion.fuse(canonical, run_vlm=self.run_vlm)
                self.storage.save_listings([canonical])
                logger.info("Saved listing", id=canonical.id)

            except Exception as e:
                logger.error("Worker failed", url=url, error=str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for _ in executor.map(process_one, urls):
                pass

    def run(self):
        logger.info("Starting Harvest (batched)...")

        chk_file = CHECKPOINT_FILE_SALE if self.mode == "sale" else CHECKPOINT_FILE_RENT
        state_file = STATE_FILE_SALE if self.mode == "sale" else STATE_FILE_RENT

        seen_store = SeenUrlStore(path=SEEN_URLS_DB)
        try:
            logger.info("Configured areas", mode=self.mode, areas=len(self.start_urls))
            if os.path.exists(chk_file) and seen_store.count(self.mode) == 0:
                try:
                    with open(chk_file, "r") as f:
                        seeded_urls = json.load(f)
                    if isinstance(seeded_urls, list):
                        inserted = seen_store.seed(self.mode, (self._canonicalize_url(u) for u in seeded_urls if u))
                        logger.info("Seeded seen-url DB from checkpoint", inserted=inserted, checkpoint=chk_file)
                except Exception as e:
                    logger.warning("Failed seeding seen-url DB from checkpoint", checkpoint=chk_file, error=str(e))

            seen_count = seen_store.count(self.mode)
            logger.info("Seen-url DB ready", db=SEEN_URLS_DB, mode=self.mode, seen=seen_count)

            state: HarvestState = load_harvest_state(
                path=state_file,
                mode=self.mode,
                target_count=self.target_count,
                start_urls=self.start_urls,
            )

            areas_total = len(state.areas)
            areas_done = sum(1 for a in state.areas if a.done)
            if areas_total == 0:
                logger.warning("No areas configured; nothing to do", mode=self.mode)
                return
            if areas_done >= areas_total or state.current_area_index >= areas_total:
                logger.warning(
                    "No remaining areas to crawl (state complete)",
                    mode=self.mode,
                    seen=seen_count,
                    target=self.target_count,
                    areas_total=areas_total,
                    areas_done=areas_done,
                    state_file=state_file,
                )
                return

            pending: List[str] = []

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)  # Set False to verify if needed
                page = browser.new_page()
                stealth = Stealth()
                stealth.apply_stealth_sync(page)

                for area_index in range(state.current_area_index, len(state.areas)):
                    area: HarvestAreaState = state.areas[area_index]
                    if area.done:
                        continue

                    start_or_resume_url = area.current_url or area.start_url
                    logger.info("Navigating to area", area_index=area_index, url=start_or_resume_url)
                    page.goto(start_or_resume_url, timeout=60000)
                    page.wait_for_load_state("domcontentloaded")
                    self._dismiss_cookie_consent(page)

                    while seen_count < self.target_count:
                        links = self._page_listing_links(page)
                        page_signature = area.compute_signature(links)

                        new_urls = seen_store.insert_new(self.mode, links)
                        new_count = len(new_urls)
                        seen_count += new_count

                        if new_count:
                            pending.extend(new_urls)
                            while len(pending) >= self.process_batch_size:
                                batch = pending[: self.process_batch_size]
                                del pending[: self.process_batch_size]
                                self._process_batch(batch)
                                gc.collect()

                        area.pages_visited += 1
                        area.current_url = self._canonicalize_url(page.url)

                        if new_count == 0:
                            area.consecutive_no_new_pages += 1
                        else:
                            area.consecutive_no_new_pages = 0

                        if area.last_signature == page_signature:
                            area.consecutive_same_signature += 1
                        else:
                            area.consecutive_same_signature = 0
                        area.last_signature = page_signature

                        logger.info(
                            "Page processed",
                            area_index=area_index,
                            total_unique_urls=seen_count,
                            new_on_page=new_count,
                            consecutive_no_new_pages=area.consecutive_no_new_pages,
                        )

                        save_harvest_state(state_file, state)

                        if seen_count >= self.target_count:
                            break

                        self._dismiss_overlays(page)

                        if area.pages_visited >= self.max_pages_per_area:
                            logger.warning("Max pages reached for area; moving on", area_index=area_index)
                            break
                        if area.consecutive_no_new_pages >= self.max_no_new_pages:
                            logger.warning("No-new-pages limit reached; moving on", area_index=area_index)
                            break
                        if area.consecutive_same_signature >= 3:
                            logger.warning("Pagination appears stuck; moving on", area_index=area_index)
                            break

                        next_url = self._click_next_page(page)
                        if not next_url:
                            logger.info("No next page; area complete", area_index=area_index)
                            break

                    if seen_count >= self.target_count:
                        state.current_area_index = area_index
                        save_harvest_state(state_file, state)
                        break

                    area.done = True
                    state.current_area_index = area_index + 1
                    save_harvest_state(state_file, state)

                browser.close()

            if pending:
                logger.info("Processing final partial batch", size=len(pending))
                while pending:
                    batch = pending[: self.process_batch_size]
                    del pending[: self.process_batch_size]
                    self._process_batch(batch)
                    gc.collect()
            logger.info("Harvest run complete", mode=self.mode, seen=seen_count, target=self.target_count)

        finally:
            seen_store.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, default="sale", choices=["sale", "rent"], help="Harvest mode: sale or rent")
    parser.add_argument("--clean", action="store_true", help="Clear database and checkpoints before starting")
    parser.add_argument("--target-count", type=int, default=DEFAULT_TARGET_COUNT, help="Stop after collecting this many unique URLs")
    parser.add_argument("--start-url", type=str, default=None, help="Single start URL (overrides default areas)")
    parser.add_argument("--areas-file", type=str, default=None, help="JSON file containing a list of start URLs to crawl in order")
    parser.add_argument("--max-no-new-pages", type=int, default=DEFAULT_MAX_NO_NEW_PAGES, help="Per-area limit of consecutive pages with no new URLs before moving on")
    parser.add_argument("--max-pages-per-area", type=int, default=DEFAULT_MAX_PAGES_PER_AREA, help="Safety cap of pages visited per start URL")
    parser.add_argument("--process-batch-size", type=int, default=BATCH_SIZE, help="Process URLs in batches to reduce peak memory")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS, help="Parallel workers for processing (reduce if memory is tight)")
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM image analysis (reduces memory/CPU and Ollama load)")
    args = parser.parse_args()
    
    if args.clean:
        logger.warning("CLEAN START: Deleting database and checkpoints...")
        if os.path.exists("data/listings.db"): os.remove("data/listings.db")
        if os.path.exists(CHECKPOINT_FILE_SALE): os.remove(CHECKPOINT_FILE_SALE)
        if os.path.exists(CHECKPOINT_FILE_RENT): os.remove(CHECKPOINT_FILE_RENT)
        if os.path.exists(STATE_FILE_SALE): os.remove(STATE_FILE_SALE)
        if os.path.exists(STATE_FILE_RENT): os.remove(STATE_FILE_RENT)
        if os.path.exists(SEEN_URLS_DB): os.remove(SEEN_URLS_DB)
        # Re-init DB
        from src.services.storage import StorageService
        StorageService() # This creates the tables if missing
    
    logger.info("Starting Harvester", mode=args.mode)
    start_urls = None
    if args.areas_file:
        with open(args.areas_file, "r") as f:
            start_urls = json.load(f)
    elif args.start_url:
        start_urls = [args.start_url]

    harvester = Harvester(
        mode=args.mode,
        target_count=args.target_count,
        start_urls=start_urls,
        max_no_new_pages=args.max_no_new_pages,
        max_pages_per_area=args.max_pages_per_area,
        process_batch_size=args.process_batch_size,
        max_workers=args.max_workers,
        run_vlm=not args.no_vlm,
    )
    harvester.run()
