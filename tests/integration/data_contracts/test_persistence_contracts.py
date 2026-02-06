from datetime import datetime

import pytest

from tests.helpers.assertions import assert_required_fields, assert_unique
from tests.helpers.contracts import CANONICAL_LISTING_REQUIRED_FIELDS
from tests.helpers.factories import make_canonical_listing

from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService
from src.platform.domain.models import DBListing


@pytest.mark.integration
def test_persistence_contract__canonical_listing__required_columns_non_null(tmp_path):
    # Arrange
    db_url = f"sqlite:///{tmp_path / 'listings.db'}"
    repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(repo)

    listing = make_canonical_listing(
        listing_id="listing-001",
        source_id="test",
        external_id="ext-001",
        listed_at=datetime(2024, 6, 1, 0, 0, 0),
        property_type="apartment",
        listing_type="sale",
    )

    # Act
    saved = persistence.save_listings([listing])

    # Assert
    assert saved == 1
    db_item = repo.get_listing_by_id(listing.id)
    assert db_item is not None

    # DBListing isn't a dict, but has attributes.
    assert_required_fields(
        db_item,
        ["id", "source_id", "external_id", "url", "title", "price", "surface_area_sqm"],
        context="db:listings",
    )


@pytest.mark.integration
def test_persistence_contract__ids_unique__upsert_does_not_duplicate(tmp_path):
    # Arrange
    db_url = f"sqlite:///{tmp_path / 'listings.db'}"
    repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(repo)

    listing = make_canonical_listing(
        listing_id="listing-unique",
        source_id="test",
        external_id="ext-unique",
        property_type="apartment",
        listing_type="sale",
    )

    # Act
    persistence.save_listings([listing])
    persistence.save_listings([listing])

    # Assert
    session = repo.storage.get_session()
    try:
        rows = session.query(DBListing.id).all()
    finally:
        session.close()

    ids = [r[0] for r in rows]
    assert_unique(ids, context="db:listings.id")
    assert ids.count("listing-unique") == 1
