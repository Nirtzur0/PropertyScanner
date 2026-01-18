
import json
import tqdm
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.listings.services.vlm import VLMImageDescriber

import ast
import structlog
from typing import Optional
from src.platform.settings import AppConfig
from src.listings.repositories.listings import ListingsRepository
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger()

def process_single_listing(describer, row):
    """
    Worker function to process a single listing.
    Returns (listing_id, description, error)
    """
    listing_id = row['id']
    image_urls_raw = row['image_urls']
    
    try:
        # Resilient parsing
        if isinstance(image_urls_raw, str):
            try:
                image_urls = json.loads(image_urls_raw)
            except json.JSONDecodeError:
                image_urls = ast.literal_eval(image_urls_raw)
        else:
            image_urls = image_urls_raw
            
        if not image_urls:
            return listing_id, None, None
            
        # Generate description
        desc = describer.describe_images(image_urls, max_images=2)
        return listing_id, desc, None
        
    except Exception as e:
        return listing_id, None, str(e)

def batch_process_vlm(
    db_path: Optional[str] = None,
    override: bool = False,
    max_workers: int = 4,
    *,
    app_config: Optional[AppConfig] = None,
):
    """
    Batch process listings to generate VLM descriptions.
    
    Args:
        db_path: Path to listings database
        override: If True, re-process listings that already have descriptions
        max_workers: Number of parallel threads for VLM inference
    """
    app_config = app_config or load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)

    # Initialize describer
    describer = VLMImageDescriber(
        config=app_config.vlm,
        image_selector_config=app_config.image_selector,
    )
    if not describer._check_availability():
        print("VLM not available. Ensure Ollama is running.")
        return

    repo = ListingsRepository(db_path=db_path)
    rows = repo.fetch_vlm_candidates(override=override)

    if not rows:
        print("All listings already have VLM descriptions (use --override to re-process).")
        return

    print(f"Processing {len(rows)} listings with VLM (workers={max_workers})...")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            # Note: We pass 'describer' to workers. Since VLMImageDescriber creates 
            # new requests/connections inside describe_images, it should be thread-safe enough
            # for this simple usage (Ollama client is HTTP based).
            future_to_id = {
                executor.submit(process_single_listing, describer, row): row['id'] 
                for row in rows
            }
            
            # Process results as they complete
            processed_count = 0
            pending_updates = []
            for future in tqdm.tqdm(as_completed(future_to_id), total=len(rows)):
                listing_id, desc, error = future.result()
                
                if error:
                    logger.warning("vlm_processing_failed", id=listing_id, error=error)
                    continue
                    
                if desc:
                    pending_updates.append((listing_id, desc))
                    
                    # Commit every 10 updates to balance safety and speed
                    if len(pending_updates) >= 10:
                        processed_count += repo.update_vlm_descriptions(pending_updates)
                        pending_updates = []

            if pending_updates:
                processed_count += repo.update_vlm_descriptions(pending_updates)
            print(f"Completed. Updated {processed_count} listings.")
            
    except KeyboardInterrupt:
        print("\nStopping...")
        executor.shutdown(wait=False, cancel_futures=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate VLM descriptions for listings")
    defaults = load_app_config_safe()
    parser.add_argument("--db", default=str(defaults.pipeline.db_path), help="Path to database")
    parser.add_argument("--override", action="store_true", help="Override existing descriptions")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    
    args = parser.parse_args()
    
    batch_process_vlm(
        db_path=args.db,
        override=args.override,
        max_workers=args.workers,
        app_config=defaults,
    )
