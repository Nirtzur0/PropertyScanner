
import logging
import sys
import os
import json

# Add src to path
sys.path.append(os.getcwd())

from src.listings.agents.crawlers.pisos import PisosCrawlerAgent
from src.listings.agents.processors.pisos import PisosNormalizerAgent
from src.platform.utils.compliance import ComplianceManager

# Configure basic logging
logging.basicConfig(level=logging.INFO)

def main():
    print("Initializing Compliance Manager...")
    compliance = ComplianceManager(user_agent="PropertyScanner/1.0")

    print("Initializing Pisos Crawler...")
    config = {
        "base_url": "https://www.pisos.com",
        "rate_limit": {"period_seconds": 2},
        "id": "pisos"
    }
    crawler = PisosCrawlerAgent(config=config, compliance_manager=compliance)

    print("Initializing Pisos Normalizer...")
    normalizer = PisosNormalizerAgent()

    # Search for property for sale in Madrid
    search_url = "https://www.pisos.com/venta/pisos-madrid/"
    
    payload = {
        "start_url": search_url,
        "max_pages": 1,
        "max_listings": 3 # Attempt to limit? The crawler doesn't seem to respect max_listings in logic, 
                          # but it iterates 'items'. I can't control it easily via payload unless I modify crawler.
                          # But the crawler loops 'items'.
    }

    print(f"Running Crawler on {search_url}...")
    crawler_response = crawler.run(payload)
    
    if crawler_response.status != "success":
        print(f"Crawler failed: {crawler_response.errors}")
        return

    print(f"Crawler successful. Found {len(crawler_response.data)} raw listings.")
    
    norm_payload = {
        "raw_listings": crawler_response.data
    }
    
    print("Running Normalizer...")
    norm_response = normalizer.run(norm_payload)
    
    if norm_response.status != "success":
        print(f"Normalizer failed: {norm_response.errors}")
        return

    print(f"Normalizer successful. Normalized {len(norm_response.data)} listings.")
    
    for listing in norm_response.data:
        print("---")
        print(f"Title: {listing.title}")
        print(f"Price: {listing.price} {listing.currency}")
        print(f"Location: {listing.location.address_full} ({listing.location.zip_code})")
        print(f"URL: {listing.url}")
        print(f"Attrs: Beds={listing.bedrooms}, Baths={listing.bathrooms}, Size={listing.surface_area_sqm}")

if __name__ == "__main__":
    main()
