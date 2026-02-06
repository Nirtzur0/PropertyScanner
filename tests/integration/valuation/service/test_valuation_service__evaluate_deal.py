from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService
from src.platform.domain.schema import CanonicalListing, GeoLocation, ListingStatus, PropertyType
from src.platform.storage import StorageService
from src.valuation.services.valuation import ValuationService

pytestmark = pytest.mark.integration


def _seed_comps(*, persistence: ListingPersistenceService, city: str, listed_at: datetime) -> None:
    listings = []
    for i in range(5):
        listings.append(
            CanonicalListing(
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
                listed_at=listed_at,
                status=ListingStatus.ACTIVE,
            )
        )
    persistence.save_listings(listings)

def test_evaluate_deal__missing_listing_price__returns_deal_analysis(tmp_path):
    # Arrange
    db_path = tmp_path / "valuation.db"
    db_url = f"sqlite:///{db_path}"

    storage = StorageService(db_url=db_url)
    repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(repo)

    now = datetime(2024, 6, 1, 0, 0, 0)
    _seed_comps(persistence=persistence, city="madrid", listed_at=now - timedelta(days=30))

    # Avoid model downloads / heavy runtime deps: mock retriever boundary.
    fake_retriever = MagicMock()
    fake_retriever.retrieve_comps.return_value = []
    fake_retriever.get_metadata.return_value = {}

    with patch("src.valuation.services.valuation.build_retriever", return_value=fake_retriever), patch(
        "src.ml.services.fusion_model.TORCH_AVAILABLE", False
    ):
        service = ValuationService(storage=storage, db_path=str(db_path))

        target = CanonicalListing(
            id="target_1",
            source_id="test",
            external_id="t_1",
            url="http://test.com/t",
            title="Target Property",
            price=0.0,  # Unknown price
            surface_area_sqm=100.0,
            property_type=PropertyType.APARTMENT,
            bedrooms=2,
            bathrooms=1,
            location=GeoLocation(
                city="madrid",
                address_full="Target Addr",
                country="ES",
                lat=40.4168,
                lon=-3.7038,
            ),
            listed_at=now,
            status=ListingStatus.ACTIVE,
        )

        # Act
        analysis = service.evaluate_deal(target, valuation_date=now)

    # Assert
    assert analysis is not None
    assert analysis.listing_id == "target_1"
    assert 0.0 <= analysis.deal_score <= 1.0
    assert analysis.fair_value_estimate > 0
    assert analysis.evidence is not None
    assert "missing_listing_price" in (analysis.flags or [])
