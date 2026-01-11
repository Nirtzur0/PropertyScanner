
import sqlite3
import json
import tqdm
from src.training.dataset import VLMImageDescriber
from src.training.dataset import PropertyDataset
import ast
import structlog

logger = structlog.get_logger()

def batch_process_vlm(db_path="data/listings.db"):
    # Initialize describer
    describer = VLMImageDescriber()
    if not describer._check_availability():
        print("VLM not available. Ensure Ollama is running.")
        return

    # Load listings needing processing
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT id, image_urls 
        FROM listings 
        WHERE (vlm_description IS NULL OR vlm_description = '') 
        AND image_urls IS NOT NULL AND image_urls != '[]' AND image_urls != ''
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("All listings already have VLM descriptions.")
        return

    print(f"Processing {len(rows)} listings with VLM...")
    
    conn = sqlite3.connect(db_path)
    try:
        for i, row in enumerate(tqdm.tqdm(rows)):
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
                    continue
                    
                # Generate description
                desc = describer.describe_images(image_urls[:2])
                
                if desc:
                    conn.execute(
                        "UPDATE listings SET vlm_description = ? WHERE id = ?",
                        (desc, listing_id)
                    )
                    if i % 10 == 0:
                        conn.commit()
            except Exception as e:
                logger.warning("batch_vlm_failed", id=listing_id, error=str(e))
        
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    batch_process_vlm()
