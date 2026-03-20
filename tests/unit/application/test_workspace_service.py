from __future__ import annotations

from pathlib import Path

import pytest

from src.application.sources import SourceCapabilityService
from src.application.workspace import WorkspaceService
from src.core.runtime import RuntimeConfig
from src.platform.domain.models import AgentRun, DBListing
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def _storage(tmp_path: Path) -> StorageService:
    return StorageService(db_url=f"sqlite:///{tmp_path / 'workspace.db'}")


def _runtime_config(tmp_path: Path) -> RuntimeConfig:
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        """
sources:
  sources:
    - id: "pisos"
      name: "Pisos"
      enabled: true
      countries: ["ES"]
    - id: "rightmove_uk"
      name: "Rightmove"
      enabled: true
      countries: ["GB"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    crawler_status_path = tmp_path / "crawler_status.md"
    crawler_status_path.write_text(
        """
| Crawler | Notes | Status |
| --- | --- | --- |
| Pisos | local | Operational |
| Rightmove | blocked | Blocked |
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return RuntimeConfig.model_validate(
        {
            "paths": {
                "db_path": str(tmp_path / "workspace.db"),
                "sources_config_path": str(sources_path),
                "docs_crawler_status_path": str(crawler_status_path),
            }
        }
    )


def test_workspace_service__persists_product_objects_and_command_history(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    session = storage.get_session()
    try:
        session.add(
            DBListing(
                id="listing-1",
                source_id="pisos",
                external_id="1",
                url="https://example.com/1",
                title="Listing",
                description="desc",
                price=250000.0,
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
            )
        )
        session.add(
            DBListing(
                id="comp-1",
                source_id="pisos",
                external_id="comp-1",
                url="https://example.com/comp-1",
                title="Comp 1",
                description="desc",
                price=255000.0,
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
            )
        )
        session.add(
            AgentRun(
                id="run-1",
                query="Find value",
                target_areas=["Madrid"],
                strategy="balanced",
                plan={"steps": [{"action": "preflight"}]},
                status="success",
                summary="Ran successfully",
                listings_count=3,
                evaluations_count=2,
                top_listing_ids=["listing-1"],
                ui_blocks=[{"type": "comparison_table"}],
            )
        )
        session.commit()
    finally:
        session.close()

    service = WorkspaceService(storage=storage)

    watchlist = service.create_watchlist(
        name="Priority",
        description="Core list",
        listing_ids=["listing-1"],
        filters={"city": "Madrid"},
    )
    saved_search = service.create_saved_search(
        name="Madrid search",
        query="madrid",
        filters={"city": "Madrid"},
        sort={"field": "price", "direction": "asc"},
    )
    memo = service.create_memo(
        title="Committee memo",
        listing_id="listing-1",
        assumptions=["Stable demand"],
        risks=["Source degraded"],
        sections=[{"heading": "Decision", "body": "Hold for review"}],
    )
    comp_review = service.create_comp_review(
        listing_id="listing-1",
        selected_comp_ids=["comp-1"],
        overrides={"fair_value_adjustment_pct": 0.05},
    )

    assert watchlist["listing_ids"] == ["listing-1"]
    assert saved_search["filters"]["city"] == "Madrid"
    assert memo["listing_id"] == "listing-1"
    assert comp_review["listing_id"] == "listing-1"

    exported = service.export_memo(memo["id"])
    assert "Committee memo" in exported["content"]
    assert "Stable demand" in exported["content"]

    assert len(service.list_watchlists()) == 1
    assert len(service.list_saved_searches()) == 1
    assert len(service.list_memos()) == 1
    assert len(service.list_comp_reviews(listing_id="listing-1")) == 1
    assert service.get_memo(memo["id"])["title"] == "Committee memo"

    runs = service.list_command_center_runs(limit=5)
    assert len(runs) == 1
    assert runs[0]["id"] == "run-1"


def test_workspace_service__rejects_comp_review_when_target_not_ready(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    session = storage.get_session()
    try:
        session.add(
            DBListing(
                id="listing-missing-area",
                source_id="pisos",
                external_id="listing-missing-area",
                url="https://example.com/listing-missing-area",
                title="Listing Missing Area",
                description="desc",
                price=250000.0,
                currency="EUR",
                property_type="apartment",
                bedrooms=2,
                bathrooms=1,
                surface_area_sqm=None,
                city="Madrid",
                country="ES",
                lat=40.4168,
                lon=-3.7038,
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()

    service = WorkspaceService(storage=storage)

    with pytest.raises(ValueError, match="comp_review_target_not_ready:target_surface_area_required"):
        service.create_comp_review(listing_id="listing-missing-area", selected_comp_ids=["comp-1"])


def test_workspace_service__rejects_invalid_comp_review_payloads(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    runtime_config = _runtime_config(tmp_path)
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
                    price=250000.0,
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
                    external_id="comp-1",
                    url="https://example.com/comp-1",
                    title="Comp 1",
                    description="desc",
                    price=245000.0,
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
                    id="isolated",
                    source_id="pisos",
                    external_id="isolated",
                    url="https://example.com/isolated",
                    title="Isolated",
                    description="desc",
                    price=150000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=1,
                    bathrooms=1,
                    surface_area_sqm=45.0,
                    city="Valencia",
                    country="ES",
                    lat=39.4699,
                    lon=-0.3763,
                    listing_type="sale",
                    fetched_at=utcnow(),
                    updated_at=utcnow(),
                    status="active",
                ),
                DBListing(
                    id="blocked-comp",
                    source_id="rightmove_uk",
                    external_id="blocked-comp",
                    url="https://example.com/blocked-comp",
                    title="Blocked Comp",
                    description="desc",
                    price=247000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=81.0,
                    city="Madrid",
                    country="ES",
                    lat=40.4172,
                    lon=-3.7041,
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

    source_capability_service = SourceCapabilityService(storage=storage, runtime_config=runtime_config)
    service = WorkspaceService(storage=storage, source_capability_service=source_capability_service)

    with pytest.raises(ValueError, match="comp_review_selection_overlap"):
        service.create_comp_review(
            listing_id="target",
            selected_comp_ids=["comp-1"],
            rejected_comp_ids=["comp-1"],
        )

    with pytest.raises(ValueError, match="comp_review_target_cannot_be_its_own_comp"):
        service.create_comp_review(listing_id="target", selected_comp_ids=["target"])

    with pytest.raises(ValueError, match="comp_review_comp_not_found:missing-comp"):
        service.create_comp_review(listing_id="target", selected_comp_ids=["missing-comp"])

    with pytest.raises(ValueError, match="comp_review_comp_not_eligible:isolated"):
        service.create_comp_review(listing_id="target", selected_comp_ids=["isolated"])

    with pytest.raises(ValueError, match="comp_review_comp_not_eligible:blocked-comp"):
        service.create_comp_review(listing_id="target", selected_comp_ids=["blocked-comp"])
