from __future__ import annotations

from datetime import timedelta

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


def test_comparable_baseline_valuation_service__excludes_out_of_range_price_comps(tmp_path) -> None:
    db_path = tmp_path / "valuation.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        session.add_all(
            [
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
                    bedrooms=2,
                    bathrooms=1,
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
                DBListing(
                    id="bad-price",
                    source_id="pisos",
                    external_id="bad-price",
                    url="https://example.com/bad-price",
                    title="Bad Price",
                    description="desc",
                    price=170000100006.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=82.0,
                    city="Madrid",
                    country="ES",
                    lat=40.4174,
                    lon=-3.7044,
                    listing_type="sale",
                    fetched_at=utcnow(),
                    updated_at=utcnow(),
                    status="active",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    analysis = ComparableBaselineValuationService(storage=storage).evaluate_listing_id("target")
    top_comp_ids = [comp.id for comp in analysis.evidence.top_comps]

    assert "bad-price" not in top_comp_ids
    assert set(top_comp_ids) == {"comp-1", "comp-2", "comp-3"}


def test_comparable_baseline_valuation_service__excludes_stale_comps_older_than_max_age(tmp_path) -> None:
    db_path = tmp_path / "valuation.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    stale_seen_at = utcnow() - timedelta(days=31 * 24)
    session = storage.get_session()
    try:
        session.add_all(
            [
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
                    bedrooms=2,
                    bathrooms=1,
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
                DBListing(
                    id="stale-comp",
                    source_id="pisos",
                    external_id="stale-comp",
                    url="https://example.com/stale-comp",
                    title="Stale Comp",
                    description="desc",
                    price=239000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=80.0,
                    city="Madrid",
                    country="ES",
                    lat=40.4173,
                    lon=-3.7043,
                    listing_type="sale",
                    listed_at=stale_seen_at,
                    fetched_at=stale_seen_at,
                    updated_at=stale_seen_at,
                    status="active",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    analysis = ComparableBaselineValuationService(storage=storage).evaluate_listing_id("target")
    top_comp_ids = [comp.id for comp in analysis.evidence.top_comps]

    assert "stale-comp" not in top_comp_ids
    assert set(top_comp_ids) == {"comp-1", "comp-2", "comp-3"}


def test_comparable_baseline_valuation_service__demotes_degraded_source_comps_below_supported_rows(tmp_path) -> None:
    db_path = tmp_path / "valuation.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        session.add_all(
            [
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
                    id="degraded-mirror",
                    source_id="pisos",
                    external_id="degraded-mirror",
                    url="https://example.com/degraded-mirror",
                    title="Degraded Mirror",
                    description="desc",
                    price=246000.0,
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
                    id="idealista-clean",
                    source_id="idealista",
                    external_id="idealista-clean",
                    url="https://example.com/idealista-clean",
                    title="Idealista Clean",
                    description="desc",
                    price=243000.0,
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
                    id="comp-3",
                    source_id="pisos",
                    external_id="comp-3",
                    url="https://example.com/comp-3",
                    title="Comp 3",
                    description="desc",
                    price=252000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
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
        )
        session.commit()
    finally:
        session.close()

    analysis = ComparableBaselineValuationService(storage=storage).evaluate_listing_id(
        "target",
        source_status_by_source={"pisos": "degraded", "idealista": "supported"},
    )
    top_comp_ids = [comp.id for comp in analysis.evidence.top_comps]

    assert top_comp_ids[0] == "idealista-clean"
    assert top_comp_ids.index("degraded-mirror") > top_comp_ids.index("idealista-clean")


def test_comparable_baseline_valuation_service__demotes_experimental_source_comps_below_supported_rows(tmp_path) -> None:
    db_path = tmp_path / "valuation.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        session.add_all(
            [
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
                    id="experimental-mirror",
                    source_id="idealista_shadow",
                    external_id="experimental-mirror",
                    url="https://example.com/experimental-mirror",
                    title="Experimental Mirror",
                    description="desc",
                    price=246000.0,
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
                    id="idealista-clean",
                    source_id="idealista",
                    external_id="idealista-clean",
                    url="https://example.com/idealista-clean",
                    title="Idealista Clean",
                    description="desc",
                    price=243000.0,
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
                    id="comp-3",
                    source_id="pisos",
                    external_id="comp-3",
                    url="https://example.com/comp-3",
                    title="Comp 3",
                    description="desc",
                    price=252000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
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
        )
        session.commit()
    finally:
        session.close()

    analysis = ComparableBaselineValuationService(storage=storage).evaluate_listing_id(
        "target",
        source_status_by_source={"idealista": "supported", "idealista_shadow": "experimental", "pisos": "supported"},
    )
    top_comp_ids = [comp.id for comp in analysis.evidence.top_comps]

    assert top_comp_ids[0] == "idealista-clean"
    assert top_comp_ids.index("experimental-mirror") > top_comp_ids.index("idealista-clean")


def test_comparable_baseline_valuation_service__ranks_mildly_degraded_rows_above_severely_degraded_rows(tmp_path) -> None:
    db_path = tmp_path / "valuation.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        session.add_all(
            [
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
                    id="mild-degraded",
                    source_id="mild_feed",
                    external_id="mild-degraded",
                    url="https://example.com/mild-degraded",
                    title="Mild Degraded",
                    description="desc",
                    price=246000.0,
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
                    id="severe-degraded",
                    source_id="severe_feed",
                    external_id="severe-degraded",
                    url="https://example.com/severe-degraded",
                    title="Severe Degraded",
                    description="desc",
                    price=246500.0,
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
                    id="idealista-clean",
                    source_id="idealista",
                    external_id="idealista-clean",
                    url="https://example.com/idealista-clean",
                    title="Idealista Clean",
                    description="desc",
                    price=243000.0,
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
            ]
        )
        session.commit()
    finally:
        session.close()

    analysis = ComparableBaselineValuationService(storage=storage).evaluate_listing_id(
        "target",
        source_status_by_source={
            "idealista": "supported",
            "mild_feed": "degraded",
            "severe_feed": "degraded",
        },
        source_metrics_by_source={
            "mild_feed": {
                "invalid_price_ratio": 0.1,
                "invalid_surface_area_ratio": 0.0,
                "title_coverage_ratio": 1.0,
                "price_coverage_ratio": 1.0,
                "surface_area_coverage_ratio": 1.0,
                "location_coverage_ratio": 1.0,
            },
            "severe_feed": {
                "invalid_price_ratio": 0.5,
                "invalid_surface_area_ratio": 0.25,
                "title_coverage_ratio": 0.8,
                "price_coverage_ratio": 0.75,
                "surface_area_coverage_ratio": 0.7,
                "location_coverage_ratio": 1.0,
            },
        },
    )
    top_comp_ids = [comp.id for comp in analysis.evidence.top_comps]

    assert top_comp_ids[0] == "idealista-clean"
    assert top_comp_ids.index("mild-degraded") < top_comp_ids.index("severe-degraded")


def test_comparable_baseline_valuation_service__prefers_fresher_source_evidence_within_same_status(tmp_path) -> None:
    db_path = tmp_path / "valuation.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        session.add_all(
            [
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
                    id="fresh-recency",
                    source_id="fresh_feed",
                    external_id="fresh-recency",
                    url="https://example.com/fresh-recency",
                    title="Fresh Recency",
                    description="desc",
                    price=245000.0,
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
                    id="laggy-recency",
                    source_id="laggy_feed",
                    external_id="laggy-recency",
                    url="https://example.com/laggy-recency",
                    title="Laggy Recency",
                    description="desc",
                    price=244500.0,
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
                    fetched_at=utcnow() - timedelta(days=10),
                    updated_at=utcnow() - timedelta(days=10),
                    status="active",
                ),
                DBListing(
                    id="comp-3",
                    source_id="pisos",
                    external_id="comp-3",
                    url="https://example.com/comp-3",
                    title="Comp 3",
                    description="desc",
                    price=252000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
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
        )
        session.commit()
    finally:
        session.close()

    analysis = ComparableBaselineValuationService(storage=storage).evaluate_listing_id(
        "target",
        source_status_by_source={"fresh_feed": "supported", "laggy_feed": "supported", "pisos": "supported"},
        source_metrics_by_source={
            "fresh_feed": {
                "invalid_price_ratio": 0.0,
                "invalid_surface_area_ratio": 0.0,
                "title_coverage_ratio": 1.0,
                "price_coverage_ratio": 1.0,
                "surface_area_coverage_ratio": 1.0,
                "location_coverage_ratio": 1.0,
                "freshness_window_days": 14,
                "last_seen_age_days": 0.0,
                "latest_run_age_days": 0.0,
            },
            "laggy_feed": {
                "invalid_price_ratio": 0.0,
                "invalid_surface_area_ratio": 0.0,
                "title_coverage_ratio": 1.0,
                "price_coverage_ratio": 1.0,
                "surface_area_coverage_ratio": 1.0,
                "location_coverage_ratio": 1.0,
                "freshness_window_days": 14,
                "last_seen_age_days": 10.0,
                "latest_run_age_days": 13.0,
            },
        },
    )
    top_comp_ids = [comp.id for comp in analysis.evidence.top_comps]

    assert top_comp_ids.index("fresh-recency") < top_comp_ids.index("laggy-recency")
