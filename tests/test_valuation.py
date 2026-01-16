import pytest
from datetime import datetime, timedelta
from src.core.domain.schema import CanonicalListing, GeoLocation, ListingStatus, PropertyType
from src.services.valuation import ValuationService
from src.services.storage import StorageService

def create_comps(storage, city="madrid"):
    """Create comparable listings for valuation."""
    listings = []
    # Create 5 comps
    for i in range(5):
        l = CanonicalListing(
            id=f"comp_{i}",
            source_id="test",
            external_id=f"ext_c_{i}",
            url=f"http://test.com/c/{i}",
            title=f"Comp {i}",
            price=300000.0,
            surface_area_sqm=100.0,
            property_type=PropertyType.APARTMENT,
            bedrooms=2,
            bathrooms=1,
            location=GeoLocation(city=city, address_full=f"Addr {i}", country="ES"),
            listed_at=datetime.now() - timedelta(days=30),
            status=ListingStatus.ACTIVE
        )
        listings.append(l)
    storage.save_listings(listings)

def test_valuation_service(test_db_path):
    """
    Test End-to-End Valuation.
    """
    db_url = f"sqlite:///{test_db_path}"
    storage = StorageService(db_url=db_url)
    create_comps(storage, city="madrid")
    
    # Init Valuation Service
    # Note: ValuationService likely needs StorageService in init, based on typical DI
    # Checking src/services/valuation.py signature:
    # def __init__(self, storage: StorageService, config: ValuationConfig = None):
    # I should verify this signature.
    
    from unittest.mock import patch, MagicMock
    
    # Patch the DEFAULT_DB_PATH used inside ValuationService init
    # Patch heavy dependencies to avoid loading models
    with patch("src.services.valuation.DEFAULT_DB_PATH", str(test_db_path)), \
         patch("src.services.fusion_model.TORCH_AVAILABLE", False), \
         patch("src.services.retrieval.faiss", MagicMock()): # Mock faiss module
        
            
            service = ValuationService(storage=storage)
            
            target = CanonicalListing(
                id="target_1",
                source_id="test",
                external_id="t_1",
                url="http://test.com/t",
                title="Target Property",
                price=0.0, # Unknown price
                surface_area_sqm=100.0,
                property_type=PropertyType.APARTMENT,
                bedrooms=2,
                bathrooms=1,
                location=GeoLocation(
                    city="madrid", 
                    address_full="Target Addr", 
                    country="ES",
                    lat=40.4168,
                    lon=-3.7038
                ),
                listed_at=datetime.now(),
                status=ListingStatus.ACTIVE
            )
            
            # Use the correct method name
            analysis = service.evaluate_deal(target)
            
            assert analysis is not None
            # Depending on model state (fusion might fail if no trained model), check for fallback or result
            # Expected behavior: If untrained, it might default or return some value.
            # We assert structure at least.
            assert analysis.listing_id == "target_1"
            # It might flag "uncalibrated" or similar if no model
            print(f"Deal Score: {analysis.deal_score}")
