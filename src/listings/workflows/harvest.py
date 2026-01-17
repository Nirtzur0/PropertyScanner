import argparse
import hashlib
import json
import time
import os
import gc
import re
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import requests

from src.platform.domain.schema import RawListing, CanonicalListing
from src.listings.agents.processors.pisos import PisosNormalizerAgent
from src.listings.services.feature_fusion import FeatureFusionService
from src.listings.services.listing_persistence import ListingPersistenceService
from src.listings.services.listing_augmenter import ListingAugmentor
from src.platform.pipeline.runs import PipelineRunTracker
from src.platform.settings import AppConfig, PathsConfig, QualityGateConfig
from src.listings.services.quality_gate import ListingQualityGate, DataQualityError
from src.listings.utils.seen_url_store import SeenUrlStore
from src.platform.db.base import resolve_db_url
from src.listings.repositories.listings import ListingsRepository
from src.platform.utils.config import load_app_config_safe
from src.listings.utils.harvest_state import (
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

LEGACY_DEFAULT_START_URLS_SALE = [
    "https://www.pisos.com/venta/pisos-espana/",
    "https://www.pisos.com/venta/casas-espana/",
]
LEGACY_DEFAULT_START_URLS_RENT = [
    "https://www.pisos.com/alquiler/pisos-espana/",
    "https://www.pisos.com/alquiler/casas-espana/",
]

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
        quality_gate_config: Optional[QualityGateConfig] = None,
        headless: Optional[bool] = None,
        *,
        app_config: Optional[AppConfig] = None,
        paths: Optional[PathsConfig] = None,
        db_url: Optional[str] = None,
        db_path: Optional[str] = None,
        listings_repo: Optional[ListingsRepository] = None,
        listing_persistence: Optional[ListingPersistenceService] = None,
    ):
        self.mode = mode
        self.target_count = target_count
        self.start_urls = start_urls or _default_start_urls(mode)
        self.max_no_new_pages = max_no_new_pages
        self.max_pages_per_area = max_pages_per_area
        self.process_batch_size = max(1, int(process_batch_size))
        self.max_workers = max(1, int(max_workers))
        self.run_vlm = bool(run_vlm)
        config_headless = True
        if app_config is not None:
            config_headless = bool(app_config.agents.crawler.headless)
        self.headless = config_headless if headless is None else bool(headless)
        self.paths = paths or (app_config.paths if app_config is not None else PathsConfig())
        if db_path is None:
            if app_config is not None:
                db_path = str(app_config.pipeline.db_path)
            else:
                db_path = str(self.paths.default_db_path)
        self.db_path = db_path
        if db_url is None:
            db_url = resolve_db_url(
                db_url=app_config.pipeline.db_url if app_config is not None else None,
                db_path=db_path,
            )
        self.listings_repo = listings_repo or ListingsRepository(db_url=db_url)
        self.listing_persistence = listing_persistence or ListingPersistenceService(self.listings_repo)
        self.normalizer = PisosNormalizerAgent()
        self.fusion = FeatureFusionService(app_config=app_config)
        self.augmenter = ListingAugmentor()
        if quality_gate_config is None and app_config is not None:
            quality_gate_config = app_config.quality_gate
        self.quality_gate = ListingQualityGate(quality_gate_config)
        self.quality_stats = {"processed": 0, "invalid": 0, "saved": 0, "errors": 0}
        self.quality_samples: List[dict] = []
        self.seen_urls_db = str(self.paths.harvest_seen_urls_db)
        self.checkpoint_file_sale = str(self.paths.harvest_urls_sale)
        self.checkpoint_file_rent = str(self.paths.harvest_urls_rent)
        self.state_file_sale = str(self.paths.harvest_state_sale)
        self.state_file_rent = str(self.paths.harvest_state_rent)

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

    def _quality_payload(self) -> dict:
        processed = self.quality_stats.get("processed", 0)
        invalid = self.quality_stats.get("invalid", 0)
        invalid_ratio = invalid / max(processed, 1)
        return {
            "processed": processed,
            "saved": self.quality_stats.get("saved", 0),
            "invalid": invalid,
            "errors": self.quality_stats.get("errors", 0),
            "invalid_ratio": round(invalid_ratio, 4),
            "samples": list(self.quality_samples),
        }

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

        chk_file = self.checkpoint_file_sale if self.mode == "sale" else self.checkpoint_file_rent
        state_file = self.state_file_sale if self.mode == "sale" else self.state_file_rent
        
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
            browser = p.chromium.launch(headless=self.headless)
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

        def process_one(url: str) -> dict:
            try:
                ext_id = self._extract_external_id(url)
                can_id = self._canonical_listing_id(ext_id)

                existing = self.listings_repo.get_listing_by_id(can_id)
                if existing:
                    return {"status": "skipped", "url": url}

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.headless)
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
                    return {"status": "invalid", "url": url, "reasons": ["normalize_empty"]}

                canonical = response.data[0]
                canonical.listing_type = self.mode

                reasons = self.quality_gate.validate_listing(canonical)
                if reasons:
                    logger.warning("Listing failed quality gate", url=url, reasons=reasons)
                    return {"status": "invalid", "url": url, "reasons": reasons}

                canonical = self.fusion.fuse(canonical, run_vlm=self.run_vlm)
                canonical = self.augmenter.augment_listing(canonical)
                self.listing_persistence.save_listings([canonical])
                logger.info("Saved listing", id=canonical.id)
                return {"status": "saved", "url": url, "id": canonical.id}

            except Exception as e:
                logger.error("Worker failed", url=url, error=str(e))
                return {"status": "error", "url": url, "error": str(e)}

        batch_processed = 0
        batch_invalid = 0
        batch_saved = 0
        batch_errors = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(process_one, url): url for url in urls}
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as e:
                    result = {"status": "error", "url": futures[future], "error": str(e)}

                status = result.get("status")
                if status == "saved":
                    batch_processed += 1
                    batch_saved += 1
                elif status == "invalid":
                    batch_processed += 1
                    batch_invalid += 1
                elif status == "error":
                    batch_processed += 1
                    batch_invalid += 1
                    batch_errors += 1
                else:
                    continue

                if status in {"invalid", "error"} and len(self.quality_samples) < 5:
                    sample = {
                        "url": result.get("url"),
                        "status": status,
                        "reasons": result.get("reasons"),
                        "error": result.get("error"),
                    }
                    self.quality_samples.append(sample)

        self.quality_stats["processed"] += batch_processed
        self.quality_stats["invalid"] += batch_invalid
        self.quality_stats["saved"] += batch_saved
        self.quality_stats["errors"] += batch_errors

        invalid_ratio = self.quality_stats["invalid"] / max(self.quality_stats["processed"], 1)
        logger.info(
            "quality_gate_snapshot",
            processed=self.quality_stats["processed"],
            invalid=self.quality_stats["invalid"],
            invalid_ratio=round(invalid_ratio, 4),
        )

        if self.quality_gate.should_halt(
            invalid_count=self.quality_stats["invalid"],
            total_count=self.quality_stats["processed"],
        ):
            raise DataQualityError(
                f"data_quality_gate_failed invalid_ratio={invalid_ratio:.2%} "
                f"processed={self.quality_stats['processed']} invalid={self.quality_stats['invalid']}"
            )

    def run(self):
        logger.info("Starting Harvest (batched)...")

        chk_file = self.checkpoint_file_sale if self.mode == "sale" else self.checkpoint_file_rent
        state_file = self.state_file_sale if self.mode == "sale" else self.state_file_rent

        tracker = PipelineRunTracker(db_path=self.db_path)
        run_id = tracker.start(step_name=f"harvest_{self.mode}", run_type="workflow", metadata={"mode": self.mode})

        seen_store = SeenUrlStore(path=self.seen_urls_db)
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
            logger.info("Seen-url DB ready", db=self.seen_urls_db, mode=self.mode, seen=seen_count)

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
                browser = p.chromium.launch(headless=self.headless)
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

            metadata = self._quality_payload()
            metadata["mode"] = self.mode
            tracker.finish(run_id=run_id, status="success", metadata=metadata)

        except DataQualityError as e:
            metadata = self._quality_payload()
            metadata["mode"] = self.mode
            metadata["error"] = str(e)
            tracker.finish(run_id=run_id, status="failed", metadata=metadata)
            logger.error("harvest_quality_gate_failed", mode=self.mode, error=str(e))
            raise
        except Exception as e:
            metadata = self._quality_payload()
            metadata["mode"] = self.mode
            metadata["error"] = str(e)
            tracker.finish(run_id=run_id, status="failed", metadata=metadata)
            raise
        finally:
            seen_store.close()

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, default="sale", choices=["sale", "rent"], help="Harvest mode: sale or rent")
    parser.add_argument("--clean", action="store_true", help="Clear database and checkpoints before starting")
    parser.add_argument(
        "--target-count",
        type=int,
        default=DEFAULT_TARGET_COUNT,
        help="Stop after collecting this many unique URLs",
    )
    parser.add_argument("--start-url", type=str, default=None, help="Single start URL (overrides default areas)")
    parser.add_argument(
        "--areas-file",
        type=str,
        default=None,
        help="JSON file containing a list of start URLs to crawl in order",
    )
    parser.add_argument(
        "--max-no-new-pages",
        type=int,
        default=DEFAULT_MAX_NO_NEW_PAGES,
        help="Per-area limit of consecutive pages with no new URLs before moving on",
    )
    parser.add_argument(
        "--max-pages-per-area",
        type=int,
        default=DEFAULT_MAX_PAGES_PER_AREA,
        help="Safety cap of pages visited per start URL",
    )
    parser.add_argument(
        "--process-batch-size",
        type=int,
        default=BATCH_SIZE,
        help="Process URLs in batches to reduce peak memory",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=MAX_WORKERS,
        help="Parallel workers for processing (reduce if memory is tight)",
    )
    parser.add_argument(
        "--no-vlm",
        action="store_true",
        help="Disable VLM image analysis (reduces memory/CPU and Ollama load)",
    )
    args = parser.parse_args(argv)

    defaults = load_app_config_safe()
    paths = defaults.paths

    if args.clean:
        logger.warning("CLEAN START: Deleting database and checkpoints...")
        db_path = str(defaults.pipeline.db_path)
        checkpoint_sale = str(paths.harvest_urls_sale)
        checkpoint_rent = str(paths.harvest_urls_rent)
        state_sale = str(paths.harvest_state_sale)
        state_rent = str(paths.harvest_state_rent)
        seen_urls_db = str(paths.harvest_seen_urls_db)

        if os.path.exists(db_path):
            os.remove(db_path)
        for path in (checkpoint_sale, checkpoint_rent, state_sale, state_rent, seen_urls_db):
            if os.path.exists(path):
                os.remove(path)
        ListingsRepository(
            db_url=resolve_db_url(
                db_url=defaults.pipeline.db_url,
                db_path=db_path,
            )
        )  # This creates the tables if missing

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
        app_config=defaults,
    )
    harvester.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
