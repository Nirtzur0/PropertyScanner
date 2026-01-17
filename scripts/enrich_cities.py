
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.platform.storage import StorageService
from src.platform.domain.models import DBListing
from sqlalchemy import or_

def enrich_existing():
    storage = StorageService()
    session = storage.get_session()
    
    # Find listings with lat/lon but Unknown city
    query = session.query(DBListing).filter(
        DBListing.lat.isnot(None),
        DBListing.lon.isnot(None),
        or_(DBListing.city == None, DBListing.city == "Unknown")
    )
    
    unknown_count = query.count()
    print(f"Found {unknown_count} listings with coordinates but Unknown city.")
    
    if unknown_count == 0:
        return
        
    listings = query.limit(1000).all() # Process in batches if many
    
    enriched_count = 0
    for listing in listings:
        if storage.enrichment_service.enrich_db_listing(listing):
            enriched_count += 1
            if enriched_count % 100 == 0:
                print(f"Enriched {enriched_count}...")
                session.commit()
    
    session.commit()
    print(f"Enrichment complete. Total enriched: {enriched_count}")
    session.close()

if __name__ == "__main__":
    enrich_existing()
