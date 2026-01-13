
import sys
import os
import time
import random
from typing import List

# Add project root to path
sys.path.append(os.getcwd())

from src.agents.crawlers.pisos import PisosCrawlerAgent
from src.agents.processors.pisos import PisosNormalizerAgent
from src.services.storage import StorageService
from src.utils.compliance import ComplianceManager

def run_batch_crawl():
    # Configuration
    base_url = "https://www.pisos.com/venta/pisos-espana/"
    target_count = 1000
    listings_per_page = 30 # Approximation
    max_pages = (target_count // listings_per_page) + 5 # Buffer
    
    print(f"Targeting ~{target_count} listings. Will crawl approx {max_pages} search pages.")
    
    # dependencies
    storage = StorageService()
    compliance = ComplianceManager(user_agent="PropertyScannerBot/1.0")
    
    crawler = PisosCrawlerAgent(config={}, compliance_manager=compliance)
    normalizer = PisosNormalizerAgent()
    
    total_saved = 0
    
    for page_num in range(1, max_pages + 1):
        if total_saved >= target_count:
            print(f"Reached target of {target_count} (Total Saved: {total_saved}). Stopping.")
            break
            
        # Construct URL
        if page_num == 1:
            url = base_url
        else:
            # Format: https://www.pisos.com/venta/pisos-espana/{page_num}/
            # Ensure no trailing slash if not needed, but typically it is fine.
            url = f"{base_url}{page_num}/"
            
        print(f"\n--- Processing Search Page {page_num}/{max_pages}: {url} ---")
        
        try:
            # 1. Crawl Search Page & Detail Pages
            # The agent handles finding listings on the start_url and then visiting them.
            crawl_response = crawler.run({"start_url": url})
            
            if crawl_response.status == "failure":
                print(f"Failed to crawl page {page_num}: {crawl_response.errors}")
                continue
                
            raw_listings = crawl_response.data
            print(f"  > Extracted {len(raw_listings)} raw listings.")
            
            if not raw_listings:
                print("  > No listings found. Stopping or retrying...")
                # If page 1 has no listings, something is wrong. 
                # If page 50 has no listings, we might be at end.
                if page_num > 1:
                    print("  > Assuming end of results.")
                    break
                else:
                    continue

            # 2. Normalize
            norm_response = normalizer.run({"raw_listings": raw_listings})
            canonical_listings = norm_response.data
            
            # 3. Save
            if canonical_listings:
                storage.save_listings(canonical_listings)
                count = len(canonical_listings)
                total_saved += count
                print(f"  > Saved {count} listings. Total so far: {total_saved}")
            else:
                print("  > No valid canonical listings produced.")
                
            # Random delay between search pages
            sleep_time = random.uniform(5, 10)
            print(f"  > Sleeping {sleep_time:.2f}s before next page...")
            time.sleep(sleep_time)
            
        except Exception as e:
            print(f"Error on page {page_num}: {e}")
            # Continue to next page despite error
            continue
            
    print(f"\nBatch crawl complete. Total listings saved: {total_saved}")

if __name__ == "__main__":
    run_batch_crawl()
