
import logging
import sys
import os
import json

# Add src to path
sys.path.append(os.getcwd())

from src.agents.crawlers.zoopla import ZooplaCrawlerAgent
from src.agents.processors.zoopla import ZooplaNormalizerAgent
from src.utils.compliance import ComplianceManager

# Configure basic logging
logging.basicConfig(level=logging.INFO)

def main():
    print("Initializing Compliance Manager...")
    compliance = ComplianceManager(user_agent="PropertyScanner/1.0")

    print("Initializing Zoopla Crawler...")
    config = {
        "base_url": "https://www.zoopla.co.uk",
        "rate_limit": {"period_seconds": 2},
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    crawler = ZooplaCrawlerAgent(config=config, compliance_manager=compliance)

    print("Initializing Zoopla Normalizer...")
    normalizer = ZooplaNormalizerAgent()

    # Search for property for sale in London
    search_url = "https://www.zoopla.co.uk/for-sale/property/london/?q=London&results_sort=newest_listings&search_source=home"
    
    payload = {
        "start_url": search_url,
        "max_pages": 1,
        "max_listings": 3
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

if __name__ == "__main__":
    main()
