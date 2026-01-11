
import logging
import sys
import os
from src.agents.crawlers.immobiliare import ImmobiliareCrawlerAgent
from src.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.utils.compliance import ComplianceManager

def test_immobiliare_extraction():
    print("=== Immobiliare.it Extraction Verification ===")
    
    compliance = ComplianceManager(user_agent="TestBot/1.0") 
    crawler = ImmobiliareCrawlerAgent({}, compliance)
    normalizer = ImmobiliareNormalizerAgent()
    
    # Try a simple city like Firenze (Florence)
    url = "https://www.immobiliare.it/vendita-case/firenze/"
    
    print(f"Crawling {url}...")
    
    try:
        response = crawler.run({"start_url": url, "limit": 3})
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return

    if response.status != "success":
        print(f"Crawl Failed: {response.errors}")
        # Even if failed, if we got some data let's inspect
    
    raw_listings = response.data
    print(f"Fetched {len(raw_listings)} listings.")
    
    if not raw_listings:
        print("No listings found.")
        return

    # Normalize
    norm_response = normalizer.run({"raw_listings": raw_listings})
    canonical_listings = norm_response.data
    
    print(f"Normalized {len(canonical_listings)} listings.")
    
    print("\n--- Sample Listing ---")
    for item in canonical_listings:
        print(f"ID: {item.external_id}")
        print(f"Title: {item.title}")
        print(f"Price: {item.price}")
        print(f"Desc Length: {len(item.description)}")
        if item.bedrooms: print(f"Bedrooms: {item.bedrooms}")
        if item.surface_area_sqm: print(f"SQM: {item.surface_area_sqm}")
        print(f"Images: {len(item.image_urls)}")
        print("-" * 20)

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    test_immobiliare_extraction()
