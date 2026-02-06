from datetime import datetime, timedelta

from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.listings.services.listing_persistence import ListingPersistenceService
from src.market.services.market_analytics import MarketAnalyticsService
from src.platform.domain.schema import CanonicalListing, GeoLocation, ListingStatus, PropertyType


def _seed_linear_price_trend(*, persistence: ListingPersistenceService, now: datetime, count: int = 50) -> None:
    listings = []
    base_price = 300000.0
    base_sqm = 100.0

    for i in range(count):
        listed_at = now - timedelta(days=(count - i))
        price = base_price * (1 + (i * 0.005))

        listings.append(
            CanonicalListing(
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
                    country="ES",
                ),
                listed_at=listed_at,
                status=ListingStatus.ACTIVE,
            )
        )

    persistence.save_listings(listings)


def test_analyze_listing__positive_trend_seeded__momentum_positive(tmp_path, monkeypatch):
    # Arrange
    now = datetime(2024, 6, 1)
    monkeypatch.setattr("src.market.services.market_analytics.utcnow", lambda: now)
    db_path = tmp_path / "analytics.db"
    db_url = f"sqlite:///{db_path}"

    repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(repo)
    _seed_linear_price_trend(persistence=persistence, now=now, count=50)

    analytics = MarketAnalyticsService(db_path=str(db_path))

    db_target = repo.get_listing_by_id("listing_49")
    assert db_target is not None
    target = db_listing_to_canonical(db_target)

    # Act
    profile = analytics.analyze_listing(target)

    # Assert
    assert profile.zone_id == "madrid"
    assert profile.momentum_score > 0
    assert profile.liquidity_score > 0.5
