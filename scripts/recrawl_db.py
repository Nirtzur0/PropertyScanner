
import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from src.services.storage import StorageService
from src.agents.crawlers.idealista import IdealistaCrawlerAgent
from src.agents.crawlers.pisos import PisosCrawlerAgent
from src.agents.crawlers.immobiliare import ImmobiliareCrawlerAgent
from src.agents.processors.idealista import IdealistaNormalizerAgent
from src.agents.processors.pisos import PisosNormalizerAgent
from src.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.agents.analysts.enricher import EnrichmentAgent
from src.utils.compliance import ComplianceManager

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def recrawl_database():
    storage = StorageService()
    compliance = ComplianceManager(user_agent="PropertyScannerBot/1.0")
    
    # Initialize agents
    crawler_idealista = IdealistaCrawlerAgent(config={}, compliance=compliance)
    crawler_pisos = PisosCrawlerAgent(config={}, compliance_manager=compliance)
    crawler_immobiliare = ImmobiliareCrawlerAgent(config={}, compliance_manager=compliance)
    
    norm_idealista = IdealistaNormalizerAgent()
    norm_pisos = PisosNormalizerAgent()
    norm_immobiliare = ImmobiliareNormalizerAgent()
    
    enricher = EnrichmentAgent(compliance=compliance)
    
    print("Fetching listings with missing data from DB...")
    
    conn = sqlite3.connect('data/listings.db')
    # Focus on those missing critical fields
    query = """
    SELECT id, source_id, external_id, url 
    FROM listings 
    WHERE bathrooms IS NULL 
       OR floor IS NULL 
       OR has_elevator IS NULL
       OR energy_rating IS NULL
       OR city = 'Unknown'
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"Found {len(df)} listings needing enrichment.")
    
    # Batch by source
    idealista_urls = df[df['source_id'].str.contains('idealista', case=False)]['url'].tolist()
    pisos_urls = df[df['source_id'].str.contains('pisos', case=False)]['url'].tolist()
    immo_urls = df[df['source_id'].str.contains('immobiliare', case=False)]['url'].tolist()
    
    print(f"Idealista Targets: {len(idealista_urls)}")
    print(f"Pisos Targets: {len(pisos_urls)}")
    print(f"Immobiliare Targets: {len(immo_urls)}")
    
    # --- Process Idealista ---
    if idealista_urls:
        print("\nStarting Idealista Recrawl...")
        # Skip if all are unknown.local
        valid_idealista = [u for u in idealista_urls if "unknown.local" not in u]
        if not valid_idealista:
            print("  > Skipping Idealista: All URLs are unknown.local")
        else:
            # Chunking because Playwright might get heavy
            batch_size = 5 # Small batch for safety/testing
            for batch in chunks(valid_idealista, batch_size):
                print(f"Processing batch of {len(batch)} URLs...")
                try:
                    # Crawl
                    crawl_res = crawler_idealista.run({"target_urls": batch, "start_url": "https://www.idealista.com/"})
                    raw_listings = crawl_res.data
                    
                    # Normalize
                    norm_res = norm_idealista.run({"raw_listings": raw_listings})
                    canonical_listings = norm_res.data
                    
                    # Enrich (Geocoding/LLM)
                    if canonical_listings:
                        enrich_res = enricher.run({"listings": canonical_listings})
                        canonical_listings = enrich_res.data
                    
                    # Save
                    if canonical_listings:
                        storage.save_listings(canonical_listings)
                        print(f"  > Saved/Updated {len(canonical_listings)} listings.")
                    else:
                        print("  > No valid listings extracted from batch.")
                        
                except Exception as e:
                    print(f"Error in Idealista batch: {e}")

    # --- Process Pisos ---
    if pisos_urls:
        print("\nStarting Pisos Recrawl...")
        batch_size = 10
        for batch in chunks(pisos_urls, batch_size):
            print(f"Processing batch of {len(batch)} URLs...")
            try:
                # Crawl
                crawl_res = crawler_pisos.run({"target_urls": batch, "start_url": "https://www.pisos.com/"})
                raw_listings = crawl_res.data
                
                # Normalize
                norm_res = norm_pisos.run({"raw_listings": raw_listings})
                canonical_listings = norm_res.data
                
                # Enrich (Geocoding/LLM)
                if canonical_listings:
                    enrich_res = enricher.run({"listings": canonical_listings})
                    canonical_listings = enrich_res.data
                
                # Save
                if canonical_listings:
                    storage.save_listings(canonical_listings)
                    print(f"  > Saved/Updated {len(canonical_listings)} listings.")
                else:
                    print("  > No valid listings extracted from batch.")
            
            except Exception as e:
                print(f"Error in Pisos batch: {e}")

    # --- Process Immobiliare ---
    if immo_urls:
        print("\nStarting Immobiliare Recrawl...")
        batch_size = 5
        for batch in chunks(immo_urls, batch_size):
            print(f"Processing batch of {len(batch)} URLs...")
            try:
                # Crawl
                crawl_res = crawler_immobiliare.run({"target_urls": batch, "start_url": "https://www.immobiliare.it/"})
                raw_listings = crawl_res.data
                
                # Normalize
                norm_res = norm_immobiliare.run({"raw_listings": raw_listings})
                canonical_listings = norm_res.data
                
                # Enrich (Geocoding/LLM)
                if canonical_listings:
                    enrich_res = enricher.run({"listings": canonical_listings})
                    canonical_listings = enrich_res.data
                
                # Save
                if canonical_listings:
                    storage.save_listings(canonical_listings)
                    print(f"  > Saved/Updated {len(canonical_listings)} listings.")
                else:
                    print("  > No valid listings extracted from batch.")
            
            except Exception as e:
                print(f"Error in Immobiliare batch: {e}")

    print("\nRecrawl complete.")

if __name__ == "__main__":
    recrawl_database()
