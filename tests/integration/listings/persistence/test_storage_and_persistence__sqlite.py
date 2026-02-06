import pytest
from src.platform.domain.schema import CanonicalListing, GeoLocation, ListingStatus
from src.platform.domain.models import DBListing
from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow

def test_storage_service_init(test_db_path):
    """Test that StorageService initializes correctly with a file path."""
    db_url = f"sqlite:///{test_db_path}"
    service = StorageService(db_url=db_url)
    assert service.engine is not None

def test_save_and_retrieve_listing(db_session, test_db_path):
    """
    Test saving a CanonicalListing to the real DB and retrieving it.
    Uses the db_session fixture for isolation, but the repository owns its session,
    so we need to be careful with transaction locking if using SQLite on disk.
    """
    db_url = f"sqlite:///{test_db_path}"
    listings_repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(listings_repo)
    
    # Create a real listing object
    listing = CanonicalListing(
        id="test_listing_001",
        source_id="idealista_123",
        external_id="ext_123",
        url="https://www.idealista.com/inmueble/123/",
        title="Test Apartment in Madrid",
        price=350000.0,
        surface_area_sqm=85.0,
        bedrooms=2,
        bathrooms=1,
        location=GeoLocation(
            city="madrid",
            lat=40.4168,
            lon=-3.7038,
            address_full="Calle Mayor, 1",
            country="ES"
        ),
        listing_type="sale",
        property_type="apartment",
        status=ListingStatus.ACTIVE,
        listed_at=utcnow()
    )
    
    # Save
    count = persistence.save_listings([listing])
    assert count == 1
    
    # Retrieve via Service
    retrieved = listings_repo.get_listing_by_id("test_listing_001")
    assert retrieved is not None
    assert retrieved.id == "test_listing_001"
    assert retrieved.city == "madrid"
    assert retrieved.price == 350000.0
    
    # Verify via Raw Session (ensure it's actually in DB)
    raw_row = db_session.query(DBListing).filter_by(id="test_listing_001").first()
    assert raw_row is not None
    assert raw_row.title == "Test Apartment in Madrid"

def test_update_existing_listing(test_db_path):
    """Test that re-saving an existing listing updates it correctly."""
    db_url = f"sqlite:///{test_db_path}"
    listings_repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(listings_repo)
    
    listing_v1 = CanonicalListing(
        id="test_listing_002",
        source_id="test_1",
        external_id="ext_1",
        url="http://example.com/2",
        title="Original Title",
        price=100000.0,
        surface_area_sqm=50,
        listing_type="sale",
        property_type="apartment",
        status=ListingStatus.ACTIVE
    )
    persistence.save_listings([listing_v1])
    
    listing_v2 = CanonicalListing(
        id="test_listing_002",
        source_id="test_1",
        external_id="ext_1",
        url="http://example.com/2",
        title="New Title",
        price=95000.0, # Price drop
        surface_area_sqm=50,
        listing_type="sale",
        property_type="apartment",
        status=ListingStatus.ACTIVE
    )
    persistence.save_listings([listing_v2])
    
    retrieved = listings_repo.get_listing_by_id("test_listing_002")
    assert retrieved.title == "New Title"
    assert retrieved.price == 95000.0
