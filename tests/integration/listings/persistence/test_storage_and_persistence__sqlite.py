from datetime import datetime

import pytest

from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService
from src.platform.domain.models import DBListing
from src.platform.domain.schema import GeoLocation, ListingStatus, PropertyType
from src.platform.storage import StorageService
from tests.helpers.factories import make_canonical_listing

pytestmark = pytest.mark.integration


def test_storage_service__sqlite_db_url__creates_engine_and_tables(tmp_path):
    # Arrange
    db_url = f"sqlite:///{tmp_path / 'listings.db'}"

    # Act
    service = StorageService(db_url=db_url)

    # Assert
    assert service.engine is not None
    repo = ListingsRepository(db_url=db_url)
    assert repo.has_table("listings") is True


def test_save_listings__new_listing__persists_and_loads_by_id(tmp_path):
    # Arrange
    db_url = f"sqlite:///{tmp_path / 'listings.db'}"
    repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(repo)

    listing = make_canonical_listing(
        listing_id="test_listing_001",
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
            country="ES",
        ),
        listing_type="sale",
        property_type=PropertyType.APARTMENT,
        status=ListingStatus.ACTIVE,
        listed_at=datetime(2024, 6, 1, 0, 0, 0),
    )

    # Act
    saved = persistence.save_listings([listing])

    # Assert
    assert saved == 1
    retrieved = repo.get_listing_by_id("test_listing_001")
    assert retrieved is not None
    assert retrieved.id == "test_listing_001"
    assert retrieved.city == "madrid"
    assert retrieved.price == 350000.0

    session = repo.storage.get_session()
    try:
        raw_row = session.query(DBListing).filter_by(id="test_listing_001").first()
    finally:
        session.close()

    assert raw_row is not None
    assert raw_row.title == "Test Apartment in Madrid"


def test_save_listings__same_id_saved_twice__updates_fields(tmp_path):
    # Arrange
    db_url = f"sqlite:///{tmp_path / 'listings.db'}"
    repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(repo)

    listing_v1 = make_canonical_listing(
        listing_id="test_listing_002",
        source_id="test_1",
        external_id="ext_1",
        url="http://example.com/2",
        title="Original Title",
        price=100000.0,
        surface_area_sqm=50.0,
        listing_type="sale",
        property_type=PropertyType.APARTMENT,
        status=ListingStatus.ACTIVE,
    )
    persistence.save_listings([listing_v1])

    listing_v2 = make_canonical_listing(
        listing_id="test_listing_002",
        source_id="test_1",
        external_id="ext_1",
        url="http://example.com/2",
        title="New Title",
        price=95000.0,
        surface_area_sqm=50.0,
        listing_type="sale",
        property_type=PropertyType.APARTMENT,
        status=ListingStatus.ACTIVE,
    )

    # Act
    persistence.save_listings([listing_v2])

    # Assert
    retrieved = repo.get_listing_by_id("test_listing_002")
    assert retrieved is not None
    assert retrieved.title == "New Title"
    assert retrieved.price == 95000.0
