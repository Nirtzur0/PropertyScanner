import logging
import structlog
import sys
import os
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

# Adjust path
sys.path.append(os.getcwd())

from src.core.domain.schema import RawListing
from src.agents.processors.pisos import PisosNormalizerAgent

def debug_url(url):
    print(f"--- Debugging URL: {url} ---")
    
    html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        stealth = Stealth()
        stealth.apply_stealth_sync(page)
        
        print("Fetching page...")
        page.goto(url, timeout=60000)
        html = page.content()
        browser.close()
    
    if not html:
        print("Failed to fetch HTML")
        return

    raw = RawListing(
        source_id="pisos",
        external_id="debug",
        url=url,
        raw_data={"html_snippet": html},
        fetched_at=datetime.utcnow()
    )
    
    print("Normalizing...")
    normalizer = PisosNormalizerAgent()
    response = normalizer.run({"raw_listings": [raw]})
    
    if not response.data:
        print("Normalization returned NO data.")
        print(f"Errors: {response.errors}")
        return

    canonical = response.data[0]
    print("\n--- Canonical Listing Fields ---")
    data = canonical.model_dump()
    for k, v in data.items():
        print(f"{k}: {v}")
    
    return canonical

if __name__ == "__main__":
    # Use a known active URL from previous logs or a generic one
    test_url = "https://www.pisos.com/comprar/piso-puerta_de_madrid_el_juncal28802-58365750785_271200/"
    # Alternative: "https://www.pisos.com/venta/pisos-madrid/" to get a list and pick one? No, direct link is better.
    # If that one is dead, we might need another.
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        
    debug_url(test_url)
