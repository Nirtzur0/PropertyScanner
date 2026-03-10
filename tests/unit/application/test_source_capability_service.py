from __future__ import annotations

from pathlib import Path

from src.application.sources import SourceCapabilityService
from src.core.runtime import RuntimeConfig
from src.platform.domain.models import DBListing, DataQualityEvent, SourceContractRun
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


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
                "db_path": str(tmp_path / "listings.db"),
                "sources_config_path": str(sources_path),
                "docs_crawler_status_path": str(crawler_status_path),
            }
        }
    )


def test_source_capability_service__classifies_sources_by_quality_and_status(tmp_path: Path) -> None:
    runtime_config = _runtime_config(tmp_path)
    storage = StorageService(db_url=f"sqlite:///{runtime_config.paths.db_path}")

    session = storage.get_session()
    try:
        session.add(
            DBListing(
                id="listing-1",
                source_id="pisos",
                external_id="1",
                url="https://example.com/1",
                title="Flat 1",
                description="desc",
                price=250000.0,
                currency="EUR",
                property_type="apartment",
                bedrooms=2,
                bathrooms=1,
                surface_area_sqm=80.0,
                city="Madrid",
                country="ES",
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()

    report = SourceCapabilityService(storage=storage, runtime_config=runtime_config).audit_sources()
    by_source = {item.source_id: item for item in report.sources}

    assert by_source["rightmove_uk"].status == "blocked"
    assert by_source["pisos"].status in {"experimental", "degraded", "supported"}
    assert by_source["pisos"].metrics["row_count"] == 1


def test_source_capability_service__persists_contract_runs_and_quality_events(tmp_path: Path) -> None:
    runtime_config = _runtime_config(tmp_path)
    storage = StorageService(db_url=f"sqlite:///{runtime_config.paths.db_path}")

    session = storage.get_session()
    try:
        session.add(
            DBListing(
                id="listing-corrupt",
                source_id="pisos",
                external_id="corrupt",
                url="https://example.com/corrupt",
                title="Broken Flat",
                description="desc",
                price=1.0,
                currency="EUR",
                property_type="apartment",
                bedrooms=2,
                bathrooms=1,
                surface_area_sqm=1.0,
                city="Madrid",
                country="ES",
                listing_type="sale",
                fetched_at=utcnow(),
                updated_at=utcnow(),
                status="active",
            )
        )
        session.commit()
    finally:
        session.close()

    SourceCapabilityService(storage=storage, runtime_config=runtime_config).audit_sources(persist=True)

    session = storage.get_session()
    try:
        contract_runs = session.query(SourceContractRun).all()
        events = session.query(DataQualityEvent).all()
    finally:
        session.close()

    assert len(contract_runs) == 2
    assert any(run.source_id == "pisos" and run.status == "degraded" for run in contract_runs)
    event_codes = {event.code for event in events}
    assert "crawler_status_blocked" in event_codes
    assert "price_corruption_high" in event_codes
    assert "area_corruption_high" in event_codes
