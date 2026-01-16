import pytest
import os
from datetime import datetime, timedelta
from src.core.domain.schema import CanonicalListing, GeoLocation, ListingStatus, PropertyType
from src.core.domain.models import DBListing
from src.services.market_analytics import MarketAnalyticsService
from src.services.storage import StorageService

def create_seed_data(storage, count=50):
    """Refactored helper using StorageService to assist with DB seeding."""
    listings = []
    base_price = 300000.0
    base_sqm = 100.0
    
    for i in range(count):
        # Create a linear trend: Price increasing over time
        date_offset = count - i
        listed_at = datetime.now() - timedelta(days=date_offset * 1)
        
        # Growing price trend
        price = base_price * (1 + (i * 0.005)) # 0.5% growth per listing step
        
        l = CanonicalListing(
            id=f"listing_{i}",
            source_id="test",
            external_id=f"ext_{i}",
            url=f"http://test.com/{i}",
            title=f"Test Property {i}",
            price=price,
            surface_area_sqm=base_sqm,
            property_type=PropertyType.APARTMENT,
            location=GeoLocation(
                city="madrid",
                lat=40.0,
                lon=-3.0,
                address_full="Test Address",
                country="ES"
            ),
            listed_at=listed_at,
            status=ListingStatus.ACTIVE
        )
        listings.append(l)
    
    storage.save_listings(listings)

def test_market_analytics_momentum(test_db_path, db_session):
    """
    Test that MarketAnalyticsService correctly identifies a positive price trend.
    """
    db_url = f"sqlite:///{test_db_path}"
    storage = StorageService(db_url=db_url)
    create_seed_data(storage, count=50)
    
    # Init Analytics Service (it uses db_path, NOT db_url usually, check definition)
    # MarketAnalyticsService(db_path: str = "data/listings.db")
    analytics = MarketAnalyticsService(db_path=test_db_path)
    
    # Retrieve one listing to analyze
    target = storage.get_listing("listing_49")
    
    # Manual conversion since storage._db_to_canonical is not available publicly
    l_input = CanonicalListing(
        id=target.id,
        source_id=target.source_id,
        external_id=target.external_id,
        url=target.url,
        title=target.title,
        price=target.price,
        surface_area_sqm=target.surface_area_sqm,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(
            city=target.city,
            lat=target.lat or 40.0, 
            lon=target.lon or -3.0,
            address_full=target.address_full or "Test Address",
            country=target.country or "ES"
        ),
        listed_at=target.listed_at,
        status=ListingStatus(target.status) if target.status else ListingStatus.ACTIVE
    )
    
    profile = analytics.analyze_listing(l_input)
    
    assert profile.zone_id == "madrid"
    # We created a positive trend (price increasing with i, date increasing with i)
    assert profile.momentum_score > 0
    # Last listing is recent, so liquidity (age-based) should be high (near 1.0)
    assert profile.liquidity_score > 0.5
