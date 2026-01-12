import sys
import os
import argparse
from tqdm import tqdm

# Add project root to path
sys.path.append(os.getcwd())

from src.services.storage import StorageService
from src.services.valuation import ValuationService
from src.services.retrieval import CompRetriever
from src.services.valuation_persister import ValuationPersister
from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing, GeoLocation

def run_batch_processor(city: str = None, limit: int = None, force: bool = False):
    print(f"Starting Valuation Batch Processor (City={city}, Limit={limit}, Force={force})")
    
    # 1. Setup Services
    storage = StorageService()
    session = storage.get_session()
    valuation_service = ValuationService(storage)
    persister = ValuationPersister(session)
    # CompRetriever is handled inside ValuationService mostly, or we init here if needed explicitly
    
    try:
        # 2. Fetch Candidates
        query = session.query(DBListing).filter(DBListing.status == 'active')
        if city and city != "All":
            query = query.filter(DBListing.city == city)
            
        listings = query.all()
        print(f"Found {len(listings)} active listings candidates.")
        
        if limit:
            listings = listings[:limit]
            
        processed_count = 0
        skipped_count = 0
        
        # 3. Process Loop
        pbar = tqdm(listings, desc="Valuing Properties")
        for db_item in pbar:
            # Check cache unless forced
            if not force:
                existing = persister.get_latest_valuation(db_item.id)
                if existing:
                    skipped_count += 1
                    continue
            
            # Reconstruct Domain Object
            loc = GeoLocation(
                lat=db_item.lat or 0.0, 
                lon=db_item.lon or 0.0, 
                address_full=db_item.address_full or "Unknown",
                city=db_item.city or "Unknown",
                country="ES" 
            )
            
            # Skip invalid location (though DB should be clean)
            # if not loc: 
            #     continue

            listing = CanonicalListing(
                id=db_item.id,
                source_id=db_item.source_id,
                external_id=db_item.external_id,
                title=db_item.title,
                price=float(db_item.price),
                currency=db_item.currency,
                property_type=db_item.property_type,
                bedrooms=db_item.bedrooms,
                bathrooms=db_item.bathrooms,
                surface_area_sqm=db_item.surface_area_sqm,
                location=loc,
                image_urls=db_item.image_urls or [],
                description=db_item.description,
                vlm_description=db_item.vlm_description,
                url=db_item.url
            )
            
            # Run Inference (Expensive Step)
            # We use trace=False for speed in batch
            try:
                analysis = valuation_service.evaluate_deal(listing)
                
                # Persist Result
                persister.save_valuation(db_item.id, analysis)
                processed_count += 1
                
            except Exception as e:
                print(f"Error valuing {db_item.id}: {e}")
                
        print(f"\nBatch Complete!")
        print(f"Processed (New/Updated): {processed_count}")
        print(f"Skipped (Cached): {skipped_count}")

    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", type=str, help="Filter by city name")
    parser.add_argument("--limit", type=int, help="Limit number of items processed")
    parser.add_argument("--force", action="store_true", help="Force re-evaluation even if fresh")
    args = parser.parse_args()
    
    run_batch_processor(args.city, args.limit, args.force)
