from __future__ import annotations

from src.application.valuation import ComparableBaselineValuationService
from src.platform.domain.models import DBListing
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def test_comparable_baseline_valuation_service__values_listing_from_local_comps(tmp_path) -> None:
    db_path = tmp_path / "valuation.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        rows = [
            DBListing(
                id="target",
                source_id="pisos",
                external_id="target",
                url="https://example.com/target",
                title="Target",
                description="desc",
                price=200000.0,
                currency="EUR",
                property_type="apartment",
                bedrooms=2,
                bathrooms=1,
                surface_area_sqm=80.0,
                city="Madrid",
                country="ES",
                lat=40.4168,
                lon=-3.7038,
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            ),
            DBListing(
                id="comp-1",
                source_id="pisos",
                external_id="1",
                url="https://example.com/1",
                title="Comp 1",
                description="desc",
                price=240000.0,
                currency="EUR",
                property_type="apartment",
                bedrooms=2,
                bathrooms=1,
                surface_area_sqm=82.0,
                city="Madrid",
                country="ES",
                lat=40.4170,
                lon=-3.7039,
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            ),
            DBListing(
                id="comp-2",
                source_id="pisos",
                external_id="2",
                url="https://example.com/2",
                title="Comp 2",
                description="desc",
                price=248000.0,
                currency="EUR",
                property_type="apartment",
                bedrooms=2,
                bathrooms=1,
                surface_area_sqm=81.0,
                city="Madrid",
                country="ES",
                lat=40.4171,
                lon=-3.7041,
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            ),
            DBListing(
                id="comp-3",
                source_id="pisos",
                external_id="3",
                url="https://example.com/3",
                title="Comp 3",
                description="desc",
                price=252000.0,
                currency="EUR",
                property_type="apartment",
                bedrooms=3,
                bathrooms=2,
                surface_area_sqm=85.0,
                city="Madrid",
                country="ES",
                lat=40.4172,
                lon=-3.7042,
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            ),
        ]
        session.add_all(rows)
        session.commit()
    finally:
        session.close()

    analysis = ComparableBaselineValuationService(storage=storage).evaluate_listing_id("target")

    assert analysis.listing_id == "target"
    assert analysis.fair_value_estimate > 0
    assert analysis.deal_score >= 0
    assert analysis.evidence is not None
    assert len(analysis.evidence.top_comps) >= 3
