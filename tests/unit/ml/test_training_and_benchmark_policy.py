from __future__ import annotations

from pathlib import Path

import pytest

from src.ml.training.policy import (
    ProductReadinessError,
    enforce_fusion_benchmark_policy,
    enforce_fusion_training_policy,
)
from src.platform.domain.models import DBListing
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'policy.db'}"


def _seed_sale_listing(tmp_path: Path) -> str:
    db_url = _db_url(tmp_path)
    storage = StorageService(db_url=db_url)
    session = storage.get_session()
    try:
        session.add(
            DBListing(
                id="sale-1",
                source_id="pisos",
                external_id="1",
                url="https://example.com/1",
                title="Sale",
                price=200000.0,
                currency="EUR",
                property_type="apartment",
                surface_area_sqm=80.0,
                city="Madrid",
                country="ES",
                lat=40.4,
                lon=-3.7,
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()
    return db_url


def test_training_policy__allows_rent_without_research_flag(tmp_path: Path) -> None:
    db_url = _seed_sale_listing(tmp_path)
    readiness = enforce_fusion_training_policy(
        db_url=db_url,
        listing_type="rent",
        label_source="ask",
        research_only=False,
    )
    assert readiness["ready"] is True


def test_training_policy__blocks_sale_training_without_closed_labels(tmp_path: Path) -> None:
    db_url = _seed_sale_listing(tmp_path)
    with pytest.raises(ProductReadinessError) as exc_info:
        enforce_fusion_training_policy(
            db_url=db_url,
            listing_type="sale",
            label_source="auto",
            research_only=False,
        )
    assert exc_info.value.code == "sale_training_not_ready"
    assert exc_info.value.details["closed_label_rows"] == 0


def test_benchmark_policy__blocks_sale_benchmark_without_sold_labels(tmp_path: Path) -> None:
    db_url = _seed_sale_listing(tmp_path)
    with pytest.raises(ProductReadinessError) as exc_info:
        enforce_fusion_benchmark_policy(
            db_url=db_url,
            listing_type="sale",
            label_source="ask",
            research_only=False,
        )
    assert exc_info.value.code == "sale_benchmark_requires_closed_labels"
