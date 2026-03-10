from __future__ import annotations

from pathlib import Path

from src.interfaces.api.pipeline import PipelineAPI
from src.platform.domain.models import Base, SourceContractRun
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow
from src.platform.settings import AppConfig, PipelineConfig, SourceConfig, SourcesConfig


def _build_api() -> PipelineAPI:
    app_config = AppConfig(
        pipeline=PipelineConfig(db_path=":memory:", db_url="sqlite:///:memory:"),
        sources=SourcesConfig(
            sources=[
                SourceConfig(id="pisos", name="Pisos.com", enabled=True, countries=["ES"]),
                SourceConfig(id="realtor_us", name="Realtor.com", enabled=False, countries=["US"]),
                SourceConfig(id="idealista_it", name="Idealista Italy", enabled=False, countries=["IT"]),
                SourceConfig(id="custom_source", name="Custom Source", enabled=True, countries=["PT"]),
            ]
        ),
    )
    return PipelineAPI(app_config=app_config)


def test_source_support_summary__classifies_supported_blocked_fallback(tmp_path: Path) -> None:
    crawler_status_doc = tmp_path / "crawler_status.md"
    crawler_status_doc.write_text(
        "\n".join(
            [
                "| Crawler | Country | Status | Verification Result | Notes |",
                "| :--- | :--- | :--- | :--- | :--- |",
                "| **Pisos.com** | Spain | ✅ **Operational** | Passing | - |",
                "| **Realtor** | USA | ❌ **Blocked** | Failing | - |",
                "| **Idealista** | Spain | ❌ **Blocked** | Failing | - |",
            ]
        ),
        encoding="utf-8",
    )

    api = _build_api()
    summary = api.source_support_summary(crawler_status_path=str(crawler_status_doc))

    assert summary["summary"] == {"supported": 1, "blocked": 2, "fallback": 1}
    by_id = {row["id"]: row for row in summary["sources"]}

    assert by_id["pisos"]["runtime_label"] == "supported"
    assert by_id["realtor_us"]["runtime_label"] == "blocked"
    assert by_id["idealista_it"]["runtime_label"] == "blocked"
    assert by_id["custom_source"]["runtime_label"] == "fallback"


def test_pipeline_status__embeds_source_support_summary(tmp_path: Path, monkeypatch) -> None:
    crawler_status_doc = tmp_path / "crawler_status.md"
    crawler_status_doc.write_text(
        "\n".join(
            [
                "| Crawler | Country | Status | Verification Result | Notes |",
                "| :--- | :--- | :--- | :--- | :--- |",
                "| **Pisos.com** | Spain | ✅ **Operational** | Passing | - |",
            ]
        ),
        encoding="utf-8",
    )

    class _FakeSnapshot:
        def to_dict(self):
            return {
                "listings_count": 12,
                "listings_last_seen": "2026-02-09T12:00:00Z",
                "needs_refresh": False,
                "reasons": [],
            }

    monkeypatch.setattr(
        "src.interfaces.api.pipeline.PipelineStateService.snapshot",
        lambda self: _FakeSnapshot(),
    )

    api = _build_api()
    payload = api.pipeline_status(crawler_status_path=str(crawler_status_doc))

    assert payload["listings_count"] == 12
    assert "source_support" in payload
    assert payload["source_support"]["summary"]["supported"] == 1
    assert "assumption_badges" in payload

    badges = {badge["id"]: badge for badge in payload["assumption_badges"]}
    assert badges["source_coverage"]["artifact_ids"] == ["lit-case-shiller-1988"]
    assert badges["source_coverage"]["status"] == "caution"
    assert "fallback" in badges["source_coverage"]["summary"]
    assert badges["conditional_coverage"]["artifact_ids"] == ["lit-conformal-tutorial-2021"]
    assert badges["conditional_coverage"]["status"] == "caution"
    assert badges["jackknife_fallback"]["status"] == "caution"
    assert "unseen" in badges["jackknife_fallback"]["summary"]
    assert "under-sampled" in badges["jackknife_fallback"]["summary"]
    assert "under-covered" in badges["jackknife_fallback"]["summary"]
    assert badges["decomposition_diagnostics"]["status"] == "gap"


def test_source_support_summary__prefers_latest_source_contract_run_over_doc(tmp_path: Path) -> None:
    db_path = tmp_path / "support.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    Base.metadata.create_all(storage.engine)

    session = storage.get_session()
    try:
        session.add(
            SourceContractRun(
                id="run-1",
                source_id="imovirtual_pt",
                status="supported",
                metrics={"persisted_count": 3},
                created_at=utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    crawler_status_doc = tmp_path / "crawler_status.md"
    crawler_status_doc.write_text(
        "\n".join(
            [
                "| Crawler | Country | Status | Verification Result | Notes |",
                "| :--- | :--- | :--- | :--- | :--- |",
                "| **Imovirtual** | Portugal | ❌ **Blocked** | Failing | - |",
            ]
        ),
        encoding="utf-8",
    )

    app_config = AppConfig(
        pipeline=PipelineConfig(db_path=str(db_path), db_url=f"sqlite:///{db_path}"),
        sources=SourcesConfig(
            sources=[
                SourceConfig(id="imovirtual_pt", name="Imovirtual", enabled=True, countries=["PT"]),
            ]
        ),
    )
    api = PipelineAPI(app_config=app_config)

    summary = api.source_support_summary(crawler_status_path=str(crawler_status_doc))
    by_id = {row["id"]: row for row in summary["sources"]}

    assert summary["summary"] == {"supported": 1, "blocked": 0, "fallback": 0}
    assert by_id["imovirtual_pt"]["runtime_label"] == "supported"
    assert by_id["imovirtual_pt"]["reason"] == "source_contract_supported"
