
import sqlite3
import json
import tqdm
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.training.dataset import VLMImageDescriber

import ast
import structlog

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
        # We process max 2 images per listing as per original logic implicit in slice
        desc = describer.describe_images(image_urls[:2])
        return listing_id, desc, None
        
    except Exception as e:
        return listing_id, None, str(e)

def batch_process_vlm(db_path="data/listings.db", override=False, max_workers=4):
    """
    Batch process listings to generate VLM descriptions.
    
    Args:
        db_path: Path to SQLite database
        override: If True, re-process listings that already have descriptions
        max_workers: Number of parallel threads for VLM inference
    """
    # Initialize describer
    describer = VLMImageDescriber()
    if not describer._check_availability():
        print("VLM not available. Ensure Ollama is running.")
        return

    # Load listings needing processing
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    query = """
        SELECT id, image_urls 
        FROM listings 
        WHERE image_urls IS NOT NULL AND image_urls != '[]' AND image_urls != ''
    """
    
    if not override:
        query += " AND (vlm_description IS NULL OR vlm_description = '')"
        
    cursor = conn.execute(query)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("All listings already have VLM descriptions (use --override to re-process).")
        return

    print(f"Processing {len(rows)} listings with VLM (workers={max_workers})...")
    
    # We use a separate connection for writing to avoid threading issues
    write_conn = sqlite3.connect(db_path)
    
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
            for future in tqdm.tqdm(as_completed(future_to_id), total=len(rows)):
                listing_id, desc, error = future.result()
                
                if error:
                    logger.warning("vlm_processing_failed", id=listing_id, error=error)
                    continue
                    
                if desc:
                    write_conn.execute(
                        "UPDATE listings SET vlm_description = ? WHERE id = ?",
                        (desc, listing_id)
                    )
                    processed_count += 1
                    
                    # Commit every 10 updates to balance safety and speed
                    if processed_count % 10 == 0:
                        write_conn.commit()
            
            write_conn.commit()
            print(f"Completed. Updated {processed_count} listings.")
            
    except KeyboardInterrupt:
        print("\nStopping...")
        executor.shutdown(wait=False, cancel_futures=True)
    finally:
        write_conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate VLM descriptions for listings")
    parser.add_argument("--db", default="data/listings.db", help="Path to database")
    parser.add_argument("--override", action="store_true", help="Override existing descriptions")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    
    args = parser.parse_args()
    
    batch_process_vlm(db_path=args.db, override=args.override, max_workers=args.workers)
