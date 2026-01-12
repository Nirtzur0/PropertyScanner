from src.services.storage import StorageService
from src.core.domain.schema import CanonicalListing
from src.core.domain.models import DBListing
from datetime import datetime, timedelta

def test_source_dates():
    print("Initializing StorageService...")
    storage = StorageService("sqlite:///:memory:") 
    
    # --- Test Backdating Logic ---
    print("\nTest: Source Date Backdating")
    
    # 1. First Scrape: "Today"
    now = datetime.utcnow()
    listing_today = CanonicalListing(
        id="t1", source_id="s1", external_id="e1", url="http://x",
        title="Test Backdate", price=100000, status="active", property_type="apartment"
    )
    # listed_at is None by default in CanonicalListing, so Storage uses NOW.
    storage.save_listings([listing_today])
    
    with storage.get_session() as session:
        db_item = session.query(DBListing).filter_by(id="t1").first()
        print(f"Initial Listed At: {db_item.listed_at}")
        initial_listed = db_item.listed_at
        assert initial_listed is not None
        
    # 2. Re-Scrape: Found "datePosted" was actually 2 months ago
    real_listed_date = now - timedelta(days=60)
    listing_older = CanonicalListing(
        id="t1", source_id="s1", external_id="e1", url="http://x",
        title="Test Backdate", price=100000, status="active", property_type="apartment",
        listed_at=real_listed_date
    )
    
    print(f"Updating with Source Date: {real_listed_date}")
    storage.save_listings([listing_older])
    
    with storage.get_session() as session:
        db_item = session.query(DBListing).filter_by(id="t1").first()
        print(f"Updated Listed At: {db_item.listed_at}")
        
        # Verify it updated to the OLDER date
        # Allow small precision error
        diff = abs((db_item.listed_at - real_listed_date).total_seconds())
        assert diff < 5, "DB failed to backdate listed_at!"
        
    # 3. Mark Sold using Storage logic (which calcs DOM)
    listing_sold = listing_older.model_copy()
    listing_sold.status = "sold"
    
    print("Marking as SOLD...")
    storage.save_listings([listing_sold])
    
    with storage.get_session() as session:
        db_item = session.query(DBListing).filter_by(id="t1").first()
        print(f"Sold At: {db_item.sold_at}")
        print(f"DOM: {db_item.dom}")
        
        # DOM should be ~60 days (since listed 60 days ago + sold today)
        # If it used the "initial scrape" date, DOM would be 0.
        assert db_item.dom is not None
        assert 59 <= db_item.dom <= 61, f"DOM calculation wrong! Got {db_item.dom}, expected ~60"

    print("Verification Successful!")

if __name__ == "__main__":
    test_source_dates()
