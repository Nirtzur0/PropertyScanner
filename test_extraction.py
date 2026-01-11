
import logging
import sys
import os
import structlog
from src.agents.crawlers.pisos import PisosCrawlerAgent
from src.agents.processors.pisos import PisosNormalizerAgent
from src.utils.compliance import ComplianceManager

# Configure basic logging


def test_extraction():
    print("=== Extraction Verification ===")
    
    # Init Agents
    compliance = ComplianceManager(user_agent="TestBot/1.0")
    crawler = PisosCrawlerAgent({}, compliance)
    normalizer = PisosNormalizerAgent()
    
    # Test URL (Madrid)
    url = "https://www.pisos.com/venta/pisos-madrid/"
    
    print(f"Crawling {url}...")
    # This will now visit detail pages (limit is set to 15 in the code, but we just want to see 1)
    response = crawler.run({"start_url": url})
    
    if response.status != "success":
        print(f"Crawl Failed: {response.errors}")
        return

    raw_listings = response.data
    print(f"Fetched {len(raw_listings)} raw listings (detail pages).")
    
    # Normalize
    norm_response = normalizer.run({"raw_listings": raw_listings})
    canonical_listings = norm_response.data
    
    print(f"Normalized {len(canonical_listings)} listings.")
    
    if not canonical_listings:
        print("No listings normalized!")
        if norm_response.errors:
            print("Errors encountered:")
            for err in norm_response.errors:
                print(f"- {err}")
        return
        
    # Check content
    print("\n--- Sample Listing ---")
    item = canonical_listings[0]
    print(f"Title: {item.title}")
    print(f"Price: {item.price}")
    print(f"Bedrooms: {item.bedrooms}")
    print(f"Sqm: {item.surface_area_sqm}")
    print(f"Description Length: {len(item.description)}")
    print(f"Description Snippet: {item.description[:100]}...")
    print(f"Image Count: {len(item.image_urls)}")
    
    if len(item.description) > 50:
        print("\nSUCCESS: Description extracted!")
    else:
        print("\nFAILURE: Description missing or too short.")

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    test_extraction()
