
import logging
import sys
import os
import json

# Add src to path
sys.path.append(os.getcwd())

from src.listings.agents.crawlers.rightmove import RightmoveCrawlerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.platform.utils.compliance import ComplianceManager

# Configure basic logging
logging.basicConfig(level=logging.INFO)

def main():
    print("Initializing Compliance Manager...")
    compliance = ComplianceManager(user_agent="PropertyScanner/1.0")

    print("Initializing Rightmove Crawler...")
    config = {
        "base_url": "https://www.rightmove.co.uk",
        "rate_limit": {"period_seconds": 2},
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    crawler = RightmoveCrawlerAgent(config=config, compliance_manager=compliance)

    print("Initializing Rightmove Normalizer...")
    normalizer = RightmoveNormalizerAgent()

    # Search for property for sale in a specific region (London)
    # Using a known valid search URL structure
    search_url = "https://www.rightmove.co.uk/property-for-sale/find.html?searchType=SALE&locationIdentifier=REGION%5E87490&insId=1"
    
    payload = {
        "start_url": search_url,
        "max_pages": 1,
        "max_listings": 3 # Limit to 3 for testing
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
