from __future__ import annotations

from pathlib import Path

from src.listings.services.observation_persistence import ObservationPersistenceService
from src.platform.domain.models import ListingEntity, ListingObservation
from src.platform.domain.schema import CanonicalListing, Currency, GeoLocation, PropertyType, RawListing
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def _storage(tmp_path: Path) -> StorageService:
    return StorageService(db_url=f"sqlite:///{tmp_path / 'observations.db'}")


def _canonical() -> CanonicalListing:
    return CanonicalListing(
        id="listing-1",
        source_id="pisos",
        external_id="ext-1",
        url="https://example.com/listing-1",
        title="Apartment",
        price=250000.0,
        currency=Currency.EUR,
        listing_type="sale",
        property_type=PropertyType.APARTMENT,
        bedrooms=2,
        bathrooms=1,
        surface_area_sqm=80.0,
        location=GeoLocation(
            lat=40.4,
            lon=-3.7,
            address_full="Street 1",
            city="Madrid",
            country="ES",
        ),
    )


def test_observation_persistence__records_bronze_silver_and_entity(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    service = ObservationPersistenceService(storage=storage)

    raw = RawListing(
        source_id="pisos",
        external_id="ext-1",
        url="https://example.com/listing-1",
        raw_data={"html": "<html></html>"},
        fetched_at=utcnow(),
    )
    listing = _canonical()

    assert service.record_raw_observations([raw]) == 1
    assert service.record_normalized_observations([listing], status="silver_validated") == 1
    assert service.upsert_listing_entities([listing]) == 1

    session = storage.get_session()
    try:
        assert session.query(ListingObservation).count() == 2
        entity = session.query(ListingEntity).one()
        assert entity.canonical_listing_id == "listing-1"
        assert entity.source_links[0]["source_id"] == "pisos"
    finally:
        session.close()


def test_observation_persistence__persists_rejection_reasons(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    service = ObservationPersistenceService(storage=storage)
    listing = _canonical()

    service.record_normalized_observations(
        [listing],
        status="silver_rejected",
        rejection_reasons={"listing-1": ["missing_surface_area"]},
    )
    session = storage.get_session()
    try:
        row = session.query(ListingObservation).one()
        assert row.status == "silver_rejected"
        assert row.normalized_payload["rejection_reasons"] == ["missing_surface_area"]
    finally:
        session.close()
