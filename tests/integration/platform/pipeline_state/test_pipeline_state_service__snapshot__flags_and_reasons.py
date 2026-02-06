from datetime import datetime, timedelta
import os

import pytest

from src.platform.pipeline.state import PipelinePolicy, PipelineStateService
from src.platform.settings import PathsConfig
from src.platform.storage import StorageService
from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService
from src.platform.domain.schema import GeoLocation, PropertyType
from tests.helpers.factories import make_canonical_listing


pytestmark = pytest.mark.integration


def _touch(path: str, *, mtime: datetime) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def test_snapshot__empty_db_and_missing_artifacts__needs_crawl_and_market_data(tmp_path, monkeypatch):
    # Arrange
    now = datetime(2024, 6, 1, 0, 0, 0)
    monkeypatch.setattr("src.platform.pipeline.state.utcnow", lambda: now)

    db_path = tmp_path / "state.db"
    db_url = f"sqlite:///{db_path}"
    StorageService(db_url=db_url)  # create schema/migrations

    paths = PathsConfig(
        default_db_path=db_path,
        vector_metadata_path=tmp_path / "vector_metadata.json",
        lancedb_path=tmp_path / "vector_index.lancedb",
        fusion_model_path=tmp_path / "fusion_model.pt",
    )

    svc = PipelineStateService(
        db_path=str(db_path),
        policy=PipelinePolicy(max_listing_age_days=7, max_market_data_age_days=30, min_listings_for_training=200),
        paths=paths,
    )

    # Act
    snapshot = svc.snapshot()

    # Assert
    assert snapshot.needs_crawl is True
    assert snapshot.needs_market_data is True
    assert snapshot.needs_refresh is True
    assert "no_listings" in snapshot.reasons
    assert "market_data_missing" in snapshot.reasons


def test_snapshot__fresh_listings_and_stale_index__needs_index(tmp_path, monkeypatch):
    # Arrange
    now = datetime(2024, 6, 1, 0, 0, 0)
    monkeypatch.setattr("src.platform.pipeline.state.utcnow", lambda: now)

    db_path = tmp_path / "state.db"
    db_url = f"sqlite:///{db_path}"
    StorageService(db_url=db_url)

    repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(repo)

    listing = make_canonical_listing(
        listing_id="listing-1",
        source_id="test",
        external_id="ext-1",
        url="https://example.com/1",
        title="Test",
        price=100000.0,
        surface_area_sqm=50.0,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(address_full="x", city="madrid", country="ES", lat=40.0, lon=-3.0),
        listed_at=now,
    )
    persistence.save_listings([listing])

    meta_path = str(tmp_path / "vector_metadata.json")
    index_path = str(tmp_path / "vector_index.lancedb")

    # Make index older than listings.
    _touch(meta_path, mtime=now - timedelta(days=1))
    _touch(index_path, mtime=now - timedelta(days=1))

    paths = PathsConfig(
        default_db_path=db_path,
        vector_metadata_path=meta_path,
        lancedb_path=index_path,
        fusion_model_path=tmp_path / "fusion_model.pt",
    )

    svc = PipelineStateService(
        db_path=str(db_path),
        policy=PipelinePolicy(max_listing_age_days=7, max_market_data_age_days=30, min_listings_for_training=200),
        paths=paths,
    )

    # Act
    snapshot = svc.snapshot()

    # Assert
    assert snapshot.needs_crawl is False
    assert snapshot.needs_index is True
    assert "index_behind_listings" in snapshot.reasons
