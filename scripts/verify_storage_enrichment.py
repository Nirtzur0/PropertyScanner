from src.services.storage import StorageService
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.core.domain.models import DBListing
import time

def test_full_flow():
    print("Initializing StorageService (with integrated EnrichmentService)...")
    storage = StorageService("sqlite:///:memory:") # Use in-memory DB for test
    
    # Create a listing with coordinate but NO city
    loc = GeoLocation(
        lat=48.8566, 
        lon=2.3522, 
        address_full="Paris Address", 
        city="", # Missing city!
        country="FR"
    )
    
    listing = CanonicalListing(
        id="test_id_123",
        source_id="src_1",
        external_id="ext_1",
        url="http://example.com",
        title="Paris Apartment with View",
        description="A beautiful apartment in Paris.",
        price=500000,
        property_type="apartment",
        location=loc
    )
    
    print("Saving listing with missing city and description...")
    storage.save_listings([listing])
    
    print("Retrieving listing from DB...")
    db_item = storage.get_listing("test_id_123")
    
    # Verify Description Persistence
    print(f"Description: {db_item.description}")
    assert db_item.description == "A beautiful apartment in Paris.", "Description failed to persist!"
    
    # Verify Coordinates Persistence
    print(f"Lat: {db_item.lat}, Lon: {db_item.lon}")
    assert db_item.lat == 48.8566, "Latitude failed to persist!"
    
    # Verify Auto-Enrichment
    print(f"City (should be enriched): {db_item.city}")
    assert db_item.city == "Paris", f"Enrichment failed! Expected Paris, got {db_item.city}"
    
    print("Verification Successful!")

if __name__ == "__main__":
    test_full_flow()
