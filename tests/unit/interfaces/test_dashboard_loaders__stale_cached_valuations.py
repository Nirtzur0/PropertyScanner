from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.interfaces.dashboard.services.loaders import fetch_listings_dataframe
from src.platform.domain.models import Base, DBListing, PropertyValuation
from src.platform.utils.time import utcnow


class _Storage:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_session(self):
        return self._session_factory()


class _UnusedRetriever:
    def retrieve_comps(self, listing, k=3):  # pragma: no cover - defensive
        raise AssertionError("cached valuation path should be used")


class _UnusedValuationService:
    def evaluate_deal(self, listing, comps=None):  # pragma: no cover - defensive
        raise AssertionError("cached valuation path should be used")


def test_fetch_listings_dataframe__uses_stale_cached_valuations_for_dashboard() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    session = Session()
    try:
        session.add(
            DBListing(
                id="listing-1",
                source_id="source",
                external_id="ext-1",
                url="https://example.com/listing-1",
                title="Lisbon Apartment",
                price=250000.0,
                currency="EUR",
                property_type="apartment",
                city="Lisbon",
                country="PT",
                lat=38.7223,
                lon=-9.1393,
                updated_at=utcnow(),
            )
        )
        session.add(
            PropertyValuation(
                id="valuation-1",
                listing_id="listing-1",
                model_version="v1",
                created_at=utcnow() - timedelta(days=45),
                fair_value=275000.0,
                price_range_low=250000.0,
                price_range_high=300000.0,
                confidence_score=0.72,
                evidence={
                    "thesis": "Cached valuation",
                    "projections": [],
                    "rent_projections": [],
                    "yield_projections": [],
                    "signals": {"momentum": 0.03},
                    "evidence": {},
                },
            )
        )
        session.commit()
    finally:
        session.close()

    storage = _Storage(Session)

    df = fetch_listings_dataframe(
        storage,
        _UnusedValuationService(),
        _UnusedRetriever(),
        selected_country="All",
        selected_city="All",
        selected_types=["apartment"],
        max_listings=10,
    )

    assert len(df) == 1
    row = df.iloc[0]
    assert row["Title"] == "Lisbon Apartment"
    assert row["Fair Value"] == 275000.0
    assert row["Deal Score"] == 0.72
