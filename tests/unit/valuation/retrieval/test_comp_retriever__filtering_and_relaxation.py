from unittest.mock import MagicMock

import numpy as np
import pytest

from src.platform.domain.schema import CanonicalListing, GeoLocation
from src.valuation.services.retrieval import CompRetriever, IndexedListing


def _make_target(*, bedrooms: int = 2, sqm: float = 80.0) -> CanonicalListing:
    return CanonicalListing(
        id="target",
        source_id="manual",
        external_id="ext_target",
        url="http://example.com/target",
        title="Target Property",
        price=150000.0,
        bedrooms=bedrooms,
        bathrooms=1,
        surface_area_sqm=sqm,
        location=GeoLocation(lat=40.0, lon=-3.0, address_full="Here", city="Madrid", country="Spain"),
        property_type="apartment",
        listing_type="sale",
    )


@pytest.fixture
def retriever(monkeypatch) -> CompRetriever:
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384

    def encode(_text, **_kwargs):
        return np.zeros(384, dtype="float32")

    mock_model.encode.side_effect = encode

    monkeypatch.setattr("src.valuation.services.retrieval.SentenceTransformer", lambda *args, **kwargs: mock_model)

    r = CompRetriever(index_path="non_existent", metadata_path="non_existent")
    r.model = mock_model
    r.index = MagicMock()

    r.listings = {}

    def add(int_id: int, title: str, beds: int, sqm: float):
        r.listings[int_id] = IndexedListing(
            id=f"id_{int_id}",
            int_id=int_id,
            title=title,
            price=100000.0,
            listing_type="sale",
            surface_area_sqm=sqm,
            bedrooms=beds,
            lat=40.0,
            lon=-3.0,
            snapshot_id="snap",
        )

    # 0-3 are structurally compatible.
    add(0, "Perfect", 2, 80.0)
    add(1, "Good Size", 2, 85.0)
    add(2, "Small Bed", 1, 70.0)
    add(3, "Big Bed", 3, 90.0)

    # 4-7 should be filtered under strict_filters.
    add(4, "Studio", 0, 40.0)
    add(5, "Villa", 5, 200.0)
    add(6, "Tiny", 2, 30.0)
    add(7, "Huge", 2, 200.0)

    n = len(r.listings)
    indices = np.array([[i for i in range(n)]], dtype="int64")
    distances = np.array([[0.1 * i for i in range(n)]], dtype="float32")

    r.index.ntotal = n
    r.index.search.return_value = (distances, indices)

    return r


def test_retrieve_comps__strict_filters__rejects_outliers(retriever: CompRetriever):
    # Arrange
    target = _make_target(bedrooms=2, sqm=80.0)

    # Act
    comps = retriever.retrieve_comps(
        target=target,
        k=4,
        max_radius_km=5.0,
        strict_filters=True,
    )

    # Assert
    comp_ids = [c.id for c in comps]
    assert set(comp_ids) == {"id_0", "id_1", "id_2", "id_3"}


def test_retrieve_comps__no_strict_matches__relaxes_to_fill_k(monkeypatch):
    # Arrange
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384
    mock_model.encode.side_effect = lambda _text, **_kwargs: np.zeros(384, dtype="float32")
    monkeypatch.setattr("src.valuation.services.retrieval.SentenceTransformer", lambda *a, **k: mock_model)

    r = CompRetriever(index_path="non_existent", metadata_path="non_existent")
    r.model = mock_model
    r.index = MagicMock()

    r.listings = {
        4: IndexedListing(
            id="id_4",
            int_id=4,
            title="Studio",
            price=100000.0,
            listing_type="sale",
            surface_area_sqm=40.0,
            bedrooms=0,
            lat=40.0,
            lon=-3.0,
            snapshot_id="snap",
        ),
        5: IndexedListing(
            id="id_5",
            int_id=5,
            title="Villa",
            price=100000.0,
            listing_type="sale",
            surface_area_sqm=200.0,
            bedrooms=5,
            lat=40.0,
            lon=-3.0,
            snapshot_id="snap",
        ),
    }

    r.index.ntotal = 2
    r.index.search.return_value = (
        np.array([[0.1, 0.2]], dtype="float32"),
        np.array([[4, 5]], dtype="int64"),
    )

    target = _make_target(bedrooms=2, sqm=80.0)

    # Act
    comps = r.retrieve_comps(target=target, k=2)

    # Assert
    comp_ids = [c.id for c in comps]
    assert comp_ids == ["id_4", "id_5"]
