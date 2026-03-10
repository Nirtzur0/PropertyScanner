from __future__ import annotations

from sqlalchemy import text

from src.listings.workflows.unified_crawl import (
    UnifiedCrawlRunner,
    UnifiedCrawlSettings,
    UnifiedSourcePlan,
)
from src.platform.agents.base import AgentResponse
from src.platform.settings import AppConfig
from src.platform.storage import StorageService
from tests.helpers.factories import make_canonical_listing, make_raw_listing


class _DummyCrawler:
    def run(self, _payload):
        raw = make_raw_listing(
            source_id="imovirtual_pt",
            external_id="IDTEST1",
            url="https://example.com/listing/IDTEST1",
            html_snippet="<html>detail</html>",
            fetched_at="2026-03-10T12:00:00Z",
        )
        return AgentResponse(
            status="success",
            data=[raw],
            metadata={
                "search_fetch_ok": True,
                "search_pages_attempted": 1,
                "search_pages_succeeded": 1,
                "listing_urls_discovered": 1,
                "listing_urls_fetched": 1,
                "detail_fetch_success_ratio": 1.0,
            },
        )


class _DummyNormalizer:
    def run(self, payload):
        raw = payload["raw_listings"][0]
        listing = make_canonical_listing(
            listing_id="listing-1",
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title="Apartment Porto",
            price=250000.0,
            surface_area_sqm=75.0,
            bedrooms=2,
            bathrooms=1,
            property_type="apartment",
            listing_type="sale",
        )
        return AgentResponse(status="success", data=[listing])


def test_unified_crawl_runner__persists_observations_entities_and_source_contract_runs(tmp_path, monkeypatch):
    db_path = tmp_path / "crawl.db"
    app_config = AppConfig.model_validate(
        {
            "pipeline": {"db_path": str(db_path), "db_url": f"sqlite:///{db_path}"},
        }
    )
    runner = UnifiedCrawlRunner(
        app_config=app_config,
        db_url=f"sqlite:///{db_path}",
        settings=UnifiedCrawlSettings(enable_fusion=False, enable_augment=False, source_workers=1),
    )
    monkeypatch.setattr(
        "src.listings.workflows.unified_crawl.AgentFactory.create_crawler",
        lambda *args, **kwargs: _DummyCrawler(),
    )
    monkeypatch.setattr(
        "src.listings.workflows.unified_crawl.AgentFactory.create_normalizer",
        lambda *args, **kwargs: _DummyNormalizer(),
    )

    result = runner.run_source(UnifiedSourcePlan(source_id="imovirtual_pt"))

    assert result["saved"] == 1
    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        observation_count = session.execute(text("SELECT COUNT(*) FROM listing_observations")).scalar_one()
        entity_count = session.execute(text("SELECT COUNT(*) FROM listing_entities")).scalar_one()
        source_runs = session.execute(
            text("SELECT source_id, status, metrics FROM source_contract_runs ORDER BY created_at DESC")
        ).fetchall()
    finally:
        session.close()
        runner.close()

    assert observation_count == 2
    assert entity_count == 1
    assert len(source_runs) == 1
    assert source_runs[0][0] == "imovirtual_pt"
    assert source_runs[0][1] in {"supported", "degraded"}
