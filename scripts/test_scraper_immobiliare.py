
import logging
import sys
import os
import json

# Add src to path
sys.path.append(os.getcwd())

from src.listings.agents.crawlers.immobiliare import ImmobiliareCrawlerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.platform.utils.compliance import ComplianceManager

# Configure basic logging
logging.basicConfig(level=logging.INFO)

def main():
    print("Initializing Compliance Manager...")
    compliance = ComplianceManager(user_agent="PropertyScanner/1.0")

    print("Initializing Immobiliare Crawler...")
    config = {
        "base_url": "https://www.immobiliare.it",
        "rate_limit": {"period_seconds": 3},
        "id": "immobiliare_it"
    }
    crawler = ImmobiliareCrawlerAgent(config=config, compliance_manager=compliance)

    print("Initializing Immobiliare Normalizer...")
    normalizer = ImmobiliareNormalizerAgent()

    # Search for property for sale in Milano
    search_url = "https://www.immobiliare.it/vendita-case/milano/"
    
    payload = {
        "start_url": search_url,
        "max_pages": 1,
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
