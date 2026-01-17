from datetime import datetime, timedelta
from src.platform.domain.schema import CanonicalListing, GeoLocation, ListingStatus, PropertyType
from src.market.services.market_analytics import MarketAnalyticsService
from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService

def create_seed_data(persistence, count=50):
    """Seed data using ListingPersistenceService."""
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
    
    persistence.save_listings(listings)

def test_market_analytics_momentum(test_db_path, db_session):
    """
    Test that MarketAnalyticsService correctly identifies a positive price trend.
    """
    db_url = f"sqlite:///{test_db_path}"
    listings_repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(listings_repo)
    create_seed_data(persistence, count=50)
    
    # Init Analytics Service (it uses db_path, NOT db_url usually, check definition)
    # MarketAnalyticsService(db_path: str = "data/listings.db")
    analytics = MarketAnalyticsService(db_path=test_db_path)
    
    # Retrieve one listing to analyze
    target = listings_repo.get_listing_by_id("listing_49")
    
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
