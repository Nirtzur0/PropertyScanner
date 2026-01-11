
import logging
import sys
import os
import time
from src.agents.crawlers.idealista import IdealistaCrawlerAgent
from src.agents.processors.idealista import IdealistaNormalizerAgent
from src.utils.compliance import ComplianceManager

def test_idealista_extraction():
    print("=== Idealista Extraction Verification ===")
    
    # Init Agents
    compliance = ComplianceManager(user_agent="Googlebot/2.1") 
    # Config: base_url is needed
    crawler = IdealistaCrawlerAgent({"base_url": "https://www.idealista.com"}, compliance)
    normalizer = IdealistaNormalizerAgent()
    
    # Target: A specific search area in Madrid
    # Using a slightly less competitive area might have less aggressive blocking?
    # Let's try Centro though.
    search_path = "/venta-viviendas/madrid/centro/"
    
    print(f"Crawling {search_path}...")
    
    try:
        response = crawler.run({"search_path": search_path})
    except Exception as e:
        print(f"CRITICAL CRAWL ERROR: {e}")
        return

    if response.status != "success":
        print(f"Crawl Failed: {response.errors}")
        return

    raw_listings = response.data
    print(f"Fetched {len(raw_listings)} listings.")
    
    if not raw_listings:
        print("No listings found (likely blocked or empty page). check debug screenshots.")
        return

    # Normalize
    norm_response = normalizer.run({"raw_listings": raw_listings})
    canonical_listings = norm_response.data
    
    print(f"Normalized {len(canonical_listings)} listings.")
    
    if not canonical_listings:
        print("No listings normalized!")
        return
        
    # Check content of first successes
    print("\n--- Sample Listing ---")
    for item in canonical_listings[:3]:
        print(f"ID: {item.external_id}")
        print(f"Title: {item.title}")
        print(f"Price: {item.price}")
        print(f"Desc Length: {len(item.description or '')}")
        print(f"Images: {len(item.image_urls)}")
        print(f"Feature: {item.bedrooms} bed, {item.surface_area_sqm} m2")
        print("-" * 20)
    
    # success criteria
    valid_descs = sum(1 for i in canonical_listings if i.description and len(i.description) > 50)
    print(f"\nlistings with description > 50 chars: {valid_descs}/{len(canonical_listings)}")

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    test_idealista_extraction()
