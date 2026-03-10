from __future__ import annotations

from pathlib import Path

from src.application.workspace import WorkspaceService
from src.platform.domain.models import AgentRun, DBListing
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def _storage(tmp_path: Path) -> StorageService:
    return StorageService(db_url=f"sqlite:///{tmp_path / 'workspace.db'}")


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
