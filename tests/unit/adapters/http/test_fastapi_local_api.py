from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.adapters.http import app as app_module
from src.application.container import ServiceContainer
from src.core.runtime import RuntimeConfig
from src.platform.domain.models import DBListing
from src.platform.utils.time import utcnow


def _container(tmp_path: Path) -> ServiceContainer:
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        """
sources:
  sources:
    - id: "pisos"
      name: "Pisos"
      enabled: true
      countries: ["ES"]
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
""".strip()
        + "\n",
        encoding="utf-8",
    )
    runtime_config = RuntimeConfig.model_validate(
        {
            "paths": {
                "db_path": str(tmp_path / "api.db"),
                "sources_config_path": str(sources_path),
                "docs_crawler_status_path": str(crawler_status_path),
                "benchmark_json_path": str(tmp_path / "benchmark.json"),
                "benchmark_md_path": str(tmp_path / "benchmark.md"),
            }
        }
    )
    container = ServiceContainer(runtime_config)
    session = container.storage.get_session()
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
                    id="missing-area",
                    source_id="pisos",
                    external_id="missing-area",
                    url="https://example.com/missing-area",
                    title="Missing Area",
                    description="desc",
                    price=205000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=None,
                    city="Madrid",
                    country="ES",
                    lat=40.4169,
                    lon=-3.7037,
                    listing_type="sale",
                    fetched_at=utcnow(),
                    updated_at=utcnow(),
                    status="active",
                ),
                DBListing(
                    id="ready-unvalued",
                    source_id="pisos",
                    external_id="ready-unvalued",
                    url="https://example.com/ready-unvalued",
                    title="Ready Unvalued",
                    description="desc",
                    price=215000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=79.0,
                    city="Madrid",
                    country="ES",
                    lat=40.4173,
                    lon=-3.7043,
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
    return container


def test_fastapi_local_api__health_sources_listings_and_valuations(tmp_path, monkeypatch) -> None:
    container = _container(tmp_path)
    monkeypatch.setattr(app_module, "get_container", lambda: container)
    client = TestClient(app_module.app)

    health = client.get("/api/v1/health")
    assert health.status_code == 200

    sources = client.get("/api/v1/sources")
    assert sources.status_code == 200
    assert "sources" in sources.json()

    workbench = client.get("/api/v1/workbench/explore", params={"country": "ES"})
    assert workbench.status_code == 200
    assert workbench.json()["stats"]["tracked"] >= 1
    markers = {item["id"]: item for item in workbench.json()["markers"]}
    assert markers["target"]["valuation_status"] == "not_evaluated"
    assert markers["target"]["valuation_ready"] is True
    assert markers["ready-unvalued"]["valuation_status"] == "not_evaluated"
    assert markers["missing-area"]["valuation_status"] == "missing_required_fields"
    assert markers["isolated"]["valuation_status"] == "insufficient_comps"
    assert "bad-price" not in markers

    layers = client.get("/api/v1/workbench/layers")
    assert layers.status_code == 200
    assert any(item["id"] == "value_opportunity" for item in layers.json()["overlays"])

    listings = client.get("/api/v1/listings")
    assert listings.status_code == 200
    assert listings.json()["total"] >= 1

    listing_context = client.get("/api/v1/workbench/listings/target/context")
    assert listing_context.status_code == 200
    assert listing_context.json()["listing"]["title"] == "Target"
    assert listing_context.json()["can_run_valuation"] is True

    valuation = client.post("/api/v1/valuations", json={"listing_id": "target", "persist": True})
    assert valuation.status_code == 200
    assert valuation.json()["listing_id"] == "target"
    assert valuation.json()["market_signals"]["comp_count"] >= 3.0

    workbench_after = client.get("/api/v1/workbench/explore", params={"country": "ES"})
    assert workbench_after.status_code == 200
    refreshed_markers = {item["id"]: item for item in workbench_after.json()["markers"]}
    assert refreshed_markers["target"]["valuation_status"] == "available"

    job = client.post(
        "/api/v1/jobs/preflight",
        json={
            "skip_crawl": True,
            "skip_market_data": True,
            "skip_index": True,
            "skip_training": True,
        },
    )
    assert job.status_code == 200
    assert job.json()["job_type"] == "preflight"

    jobs = client.get("/api/v1/job-runs")
    assert jobs.status_code == 200
    assert jobs.json()["total"] >= 1

    watchlist = client.post(
        "/api/v1/watchlists",
        json={
            "name": "Core Madrid",
            "description": "Priority lens",
            "listing_ids": ["target"],
            "filters": {"city": "Madrid"},
        },
    )
    assert watchlist.status_code == 200
    assert watchlist.json()["name"] == "Core Madrid"

    saved_search = client.post(
        "/api/v1/saved-searches",
        json={
            "name": "Madrid Apartments",
            "query": "Madrid apartments",
            "filters": {"city": "Madrid", "listing_type": "sale"},
            "sort": {"field": "price", "direction": "asc"},
        },
    )
    assert saved_search.status_code == 200

    memo = client.post(
        "/api/v1/memos",
        json={
            "title": "Target memo",
            "listing_id": "target",
            "assumptions": ["Comparable supply remains stable"],
            "risks": ["Source support is degraded"],
            "sections": [{"heading": "Summary", "body": "Prioritize manual review."}],
        },
    )
    assert memo.status_code == 200
    memo_id = memo.json()["id"]

    exported = client.post(f"/api/v1/memos/{memo_id}/export")
    assert exported.status_code == 200
    assert exported.json()["memo_id"] == memo_id
    assert "Target memo" in exported.json()["content"]

    comp_review = client.post(
        "/api/v1/comp-reviews",
        json={
            "listing_id": "target",
            "selected_comp_ids": ["comp-1", "comp-2"],
            "rejected_comp_ids": ["comp-3"],
            "overrides": {"fair_value_adjustment_pct": 0.03},
        },
    )
    assert comp_review.status_code == 200
    assert comp_review.json()["listing_id"] == "target"

    assert client.get("/api/v1/watchlists").json()["total"] == 1
    assert client.get("/api/v1/saved-searches").json()["total"] == 1
    assert client.get("/api/v1/memos").json()["total"] == 1
    assert client.get("/api/v1/comp-reviews?listing_id=target").json()["total"] == 1
    assert client.get("/api/v1/command-center/runs").status_code == 200
    assert client.get("/api/v1/benchmarks").status_code == 200
    source_status_by_source = {
        str(item["source_id"]): str(item["status"])
        for item in sources.json()["sources"]
        if item.get("source_id")
    }
    container.reporting.audit_serving_eligibility(source_status_by_source=source_status_by_source)
    quality_events = client.get("/api/v1/data-quality-events")
    assert quality_events.status_code == 200
    assert any(item["listing_id"] == "bad-price" for item in quality_events.json()["items"])
    assert client.get("/api/v1/coverage-reports").status_code == 200
    assert client.get("/api/v1/source-contract-runs").status_code == 200


def test_fastapi_local_api__valuations_return_structured_unavailable_errors(tmp_path, monkeypatch) -> None:
    container = _container(tmp_path)
    monkeypatch.setattr(app_module, "get_container", lambda: container)
    client = TestClient(app_module.app)

    missing_area = client.post("/api/v1/valuations", json={"listing_id": "missing-area", "persist": False})
    assert missing_area.status_code == 422
    assert missing_area.json()["detail"]["code"] == "target_surface_area_required"
    assert missing_area.json()["detail"]["status"] == "unavailable"

    insufficient_comps = client.post("/api/v1/valuations", json={"listing_id": "isolated", "persist": False})
    assert insufficient_comps.status_code == 422
    assert insufficient_comps.json()["detail"]["code"] == "insufficient_comps"
    assert "enough comparable" in insufficient_comps.json()["detail"]["message"].lower()


def test_fastapi_local_api__spa_routes_serve_html_and_api_routes_stay_json(tmp_path, monkeypatch) -> None:
    container = _container(tmp_path)
    frontend_dist = tmp_path / "frontend-dist"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("<html><body>app shell</body></html>", encoding="utf-8")
    monkeypatch.setattr(app_module, "get_container", lambda: container)
    monkeypatch.setattr(app_module, "_FRONTEND_DIST", frontend_dist)
    client = TestClient(app_module.app)

    for route in ("/watchlists", "/memos", "/listings/target", "/comp-reviews/target"):
        response = client.get(route)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "app shell" in response.text

    assert client.get("/api/v1/watchlists").headers["content-type"].startswith("application/json")
    assert client.get("/api/v1/memos").headers["content-type"].startswith("application/json")
    assert client.get("/api/v1/listings/target").headers["content-type"].startswith("application/json")
    assert client.get("/api/v1/comp-reviews").headers["content-type"].startswith("application/json")
