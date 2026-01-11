
import sys
import os
from src.agents.analysts.market_trends import MarketDynamicsAgent
from src.core.domain.schema import CanonicalListing, GeoLocation, PropertyType, Currency
from datetime import datetime

def test_market_trends():
    print("=== Market Trends Verification ===")
    
    agent = MarketDynamicsAgent()
    
    # 1. Create a Mock Listing (representing a property in Madrid)
    mock_listing = CanonicalListing(
        id="test_123",
        source_id="manual",
        external_id="ext_1",
        url="http://example.com",
        title="Test Appt in Madrid",
        price=300000.0,
        currency=Currency.EUR,
        property_type=PropertyType.APARTMENT,
        surface_area_sqm=100.0,
        location=GeoLocation(
            lat=40.4168, lon=-3.7038, city="madrid", address_full="Gran Via", country="ES"
        ),
        updated_at=datetime.now()
    )
    
    print(f"Analyzing listing in: {mock_listing.location.city}")
    
    # 2. Run Agent
    # Note: This relies on REAL data in data/listings.db.
    # If the DB is empty, it will return default/zero stats.
    response = agent.run({"listing": mock_listing})
    
    if response.status != "success":
        print(f"Analysis Failed: {response.errors}")
        return
        
    profile = response.data
    print("\n--- Market Profile Result ---")
    print(f"Zone: {profile.zone_id}")
    print(f"Avg Price/sqm: {profile.avg_price_sqm:.2f} €")
    print(f"Momentum (Growth): {profile.momentum_score*100:.2f}%")
    print(f"Liquidity Score: {profile.liquidity_score:.2f}")
    print(f"Catchup Potential: {profile.catchup_potential}")
    
    print("\n--- Projections ---")
    for proj in profile.projections:
        print(f"Year {proj.years_future}: {proj.predicted_value:,.0f} € (Conf: {proj.confidence_score:.2f})")

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    test_market_trends()
