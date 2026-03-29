from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from datetime import timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.adapters.http import app as app_module
from src.application.container import ServiceContainer
from src.core.runtime import RuntimeConfig
from src.platform.domain.models import DBListing, SourceContractRun
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
    - id: "idealista"
      name: "Idealista"
      enabled: true
      countries: ["ES"]
    - id: "idealista_shadow"
      name: "Idealista Shadow"
      enabled: true
      countries: ["ES"]
    - id: "mild_feed"
      name: "Mild Feed"
      enabled: true
      countries: ["ES"]
    - id: "fresh_feed"
      name: "Fresh Feed"
      enabled: true
      countries: ["ES"]
    - id: "laggy_feed"
      name: "Laggy Feed"
      enabled: true
      countries: ["ES"]
    - id: "severe_feed"
      name: "Severe Feed"
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
| Idealista | local | Operational |
| Rightmove | blocked | Blocked |
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
            },
            "quality": {
                "experimental_min_rows": 1,
            },
        }
    )
    container = ServiceContainer(runtime_config)
    session = container.storage.get_session()
    try:
        stale_seen_at = utcnow() - timedelta(days=31 * 24)
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
                    id="idealista-clean",
                    source_id="idealista",
                    external_id="idealista-clean",
                    url="https://example.com/idealista-clean",
                    title="Idealista Clean",
                    description="desc",
                    price=243000.0,
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
                    id="experimental-mirror",
                    source_id="idealista_shadow",
                    external_id="experimental-mirror",
                    url="https://example.com/experimental-mirror",
                    title="Experimental Mirror",
                    description="desc",
                    price=246000.0,
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
                    id="mild-degraded",
                    source_id="mild_feed",
                    external_id="mild-degraded",
                    url="https://example.com/mild-degraded",
                    title="Mild Degraded",
                    description="desc",
                    price=246000.0,
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
                    id="fresh-recency",
                    source_id="fresh_feed",
                    external_id="fresh-recency",
                    url="https://example.com/fresh-recency",
                    title="Fresh Recency",
                    description="desc",
                    price=245000.0,
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
                    id="laggy-recency",
                    source_id="laggy_feed",
                    external_id="laggy-recency",
                    url="https://example.com/laggy-recency",
                    title="Laggy Recency",
                    description="desc",
                    price=244500.0,
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
                    fetched_at=utcnow() - timedelta(days=10),
                    updated_at=utcnow() - timedelta(days=10),
                    status="active",
                ),
                DBListing(
                    id="severe-degraded",
                    source_id="severe_feed",
                    external_id="severe-degraded",
                    url="https://example.com/severe-degraded",
                    title="Severe Degraded",
                    description="desc",
                    price=246500.0,
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
                    id="degraded-mirror",
                    source_id="pisos",
                    external_id="degraded-mirror",
                    url="https://example.com/degraded-mirror",
                    title="Degraded Mirror",
                    description="desc",
                    price=246000.0,
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
                    id="stale-comp",
                    source_id="pisos",
                    external_id="stale-comp",
                    url="https://example.com/stale-comp",
                    title="Stale Comp",
                    description="desc",
                    price=239000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=80.0,
                    city="Madrid",
                    country="ES",
                    lat=40.4175,
                    lon=-3.7045,
                    listing_type="sale",
                    listed_at=stale_seen_at,
                    fetched_at=stale_seen_at,
                    updated_at=stale_seen_at,
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
                DBListing(
                    id="blocked-comp",
                    source_id="rightmove_uk",
                    external_id="blocked-comp",
                    url="https://example.com/blocked-comp",
                    title="Blocked Comp",
                    description="desc",
                    price=246000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=81.0,
                    city="Madrid",
                    country="ES",
                    lat=40.4176,
                    lon=-3.7046,
                    listing_type="sale",
                    fetched_at=utcnow(),
                    updated_at=utcnow(),
                    status="active",
                ),
                SourceContractRun(
                    id="idealista-supported-run",
                    source_id="idealista",
                    status="supported",
                    metrics={"row_count": 1},
                    created_at=utcnow(),
                ),
                SourceContractRun(
                    id="fresh-feed-supported-run",
                    source_id="fresh_feed",
                    status="supported",
                    metrics={"row_count": 1},
                    created_at=utcnow(),
                ),
                SourceContractRun(
                    id="laggy-feed-supported-run",
                    source_id="laggy_feed",
                    status="supported",
                    metrics={"row_count": 1},
                    created_at=utcnow() - timedelta(days=13),
                ),
            ]
        )
        session.add_all(
            [
                *[
                    DBListing(
                        id=f"mild-valid-{index}",
                        source_id="mild_feed",
                        external_id=f"mild-valid-{index}",
                        url=f"https://example.com/mild-valid-{index}",
                        title=f"Mild Valid {index}",
                        description="desc",
                        price=220000.0 + float(index * 1000),
                        currency="EUR",
                        property_type="apartment",
                        bedrooms=2,
                        bathrooms=1,
                        surface_area_sqm=78.0 + float(index),
                        city="Valencia",
                        country="ES",
                        lat=39.4699,
                        lon=-0.3763,
                        listing_type="sale",
                        fetched_at=utcnow(),
                        updated_at=utcnow(),
                        status="active",
                    )
                    for index in range(4)
                ],
                DBListing(
                    id="mild-invalid-1",
                    source_id="mild_feed",
                    external_id="mild-invalid-1",
                    url="https://example.com/mild-invalid-1",
                    title="Mild Invalid 1",
                    description="desc",
                    price=1.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=1.0,
                    city="Valencia",
                    country="ES",
                    lat=39.4698,
                    lon=-0.3764,
                    listing_type="sale",
                    fetched_at=utcnow(),
                    updated_at=utcnow(),
                    status="active",
                ),
                DBListing(
                    id="severe-valid-1",
                    source_id="severe_feed",
                    external_id="severe-valid-1",
                    url="https://example.com/severe-valid-1",
                    title="Severe Valid 1",
                    description="desc",
                    price=221000.0,
                    currency="EUR",
                    property_type="apartment",
                    bedrooms=2,
                    bathrooms=1,
                    surface_area_sqm=78.0,
                    city="Seville",
                    country="ES",
                    lat=37.3891,
                    lon=-5.9845,
                    listing_type="sale",
                    fetched_at=utcnow(),
                    updated_at=utcnow(),
                    status="active",
                ),
                *[
                    DBListing(
                        id=f"severe-invalid-{index}",
                        source_id="severe_feed",
                        external_id=f"severe-invalid-{index}",
                        url=f"https://example.com/severe-invalid-{index}",
                        title=f"Severe Invalid {index}",
                        description="desc",
                        price=1.0,
                        currency="EUR",
                        property_type="apartment",
                        bedrooms=2,
                        bathrooms=1,
                        surface_area_sqm=1.0,
                        city="Seville",
                        country="ES",
                        lat=37.3890,
                        lon=-5.9846,
                        listing_type="sale",
                        fetched_at=utcnow(),
                        updated_at=utcnow(),
                        status="active",
                    )
                    for index in range(3)
                ],
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
    assert "overview" in workbench.json()
    assert workbench.json()["overview"]["needs_data_count"] >= 1
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
    assert listing_context.json()["media_summary"]["count"] == 0
    assert listing_context.json()["evidence_summary"]["available"] is False
    assert any(item["code"] == "images_missing" for item in listing_context.json()["data_gaps"])

    valuation = client.post("/api/v1/valuations", json={"listing_id": "target", "persist": True})
    assert valuation.status_code == 200
    assert valuation.json()["listing_id"] == "target"
    assert valuation.json()["fair_value_estimate"] > 0
    assert "evidence" in valuation.json()
    top_comps = valuation.json()["evidence"].get("top_comps", [])
    assert len(top_comps) >= 3

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

    trust_summary = client.get("/api/v1/pipeline/trust-summary")
    assert trust_summary.status_code == 200
    assert "freshness" in trust_summary.json()
    assert "top_blockers" in trust_summary.json()

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

    listing_context_after = client.get("/api/v1/workbench/listings/target/context")
    assert listing_context_after.status_code == 200
    assert listing_context_after.json()["evidence_summary"]["available"] is True
    assert listing_context_after.json()["evidence_summary"]["comp_count"] >= 3
    assert len(listing_context_after.json()["provenance_timeline"]) >= 2

    comp_workspace = client.get("/api/v1/comp-reviews/target/workspace")
    assert comp_workspace.status_code == 200
    assert comp_workspace.json()["target"]["id"] == "target"
    assert len(comp_workspace.json()["candidate_pool"]) >= 3
    candidate_ids = [item["id"] for item in comp_workspace.json()["candidate_pool"]]
    assert candidate_ids[0] == "idealista-clean"
    experimental_index = next(
        index for index, item in enumerate(comp_workspace.json()["candidate_pool"]) if item["id"] == "experimental-mirror"
    )
    assert experimental_index > 0
    assert candidate_ids.index("fresh-recency") < candidate_ids.index("laggy-recency")
    assert candidate_ids.index("mild-degraded") < candidate_ids.index("severe-degraded")
    assert all(item["id"] != "bad-price" for item in comp_workspace.json()["candidate_pool"])
    assert all(item["id"] != "stale-comp" for item in comp_workspace.json()["candidate_pool"])
    assert all(item["id"] != "blocked-comp" for item in comp_workspace.json()["candidate_pool"])
    assert len(comp_workspace.json()["pinned_comps"]) == 2
    assert comp_workspace.json()["save_review"]["ready"] is True
    assert comp_workspace.json()["publish_to_memo"]["ready"] is False
    assert comp_workspace.json()["delta_preview"]["retained_count"] >= 2

    missing_area_workspace = client.get("/api/v1/comp-reviews/missing-area/workspace")
    assert missing_area_workspace.status_code == 200
    assert missing_area_workspace.json()["save_review"]["ready"] is False
    assert missing_area_workspace.json()["save_review"]["reason"] == "target_surface_area_required"

    invalid_comp_review = client.post(
        "/api/v1/comp-reviews",
        json={
            "listing_id": "missing-area",
            "selected_comp_ids": ["comp-1"],
        },
    )
    assert invalid_comp_review.status_code == 400
    assert invalid_comp_review.json()["detail"] == "comp_review_target_not_ready:target_surface_area_required"

    ineligible_comp_review = client.post(
        "/api/v1/comp-reviews",
        json={
            "listing_id": "target",
            "selected_comp_ids": ["isolated"],
        },
    )
    assert ineligible_comp_review.status_code == 400
    assert ineligible_comp_review.json()["detail"] == "comp_review_comp_not_eligible:isolated"

    blocked_source_comp_review = client.post(
        "/api/v1/comp-reviews",
        json={
            "listing_id": "target",
            "selected_comp_ids": ["blocked-comp"],
        },
    )
    assert blocked_source_comp_review.status_code == 400
    assert blocked_source_comp_review.json()["detail"] == "comp_review_comp_not_eligible:blocked-comp"

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
    ui_event = client.post(
        "/api/v1/ui-events",
        json={
            "event_name": "workbench_listing_opened",
            "route": "/workbench",
            "subject_type": "listing",
            "subject_id": "target",
            "context": {"source": "rail"},
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert ui_event.status_code == 200
    assert ui_event.json()["status"] == "recorded"


def test_fastapi_local_api__valuations_return_structured_unavailable_errors(tmp_path, monkeypatch) -> None:
    container = _container(tmp_path)
    # Force baseline valuation so error codes are predictable
    container.full_valuation = None
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


def test_fastapi_local_api__valuation_reuses_one_source_audit_snapshot_per_request(monkeypatch) -> None:
    calls: list[int] = []
    captured: dict[str, object] = {}

    class _AuditReport:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def model_dump(self, *, mode: str = "json") -> dict:
            assert mode == "json"
            return self.payload

    class _Sources:
        def audit_sources(self, *, persist: bool = False) -> _AuditReport:
            calls.append(len(calls) + 1)
            payload = {
                "sources": [
                    {
                        "source_id": "pisos",
                        "status": f"supported-{len(calls)}",
                        "metrics": {"snapshot_id": len(calls)},
                    }
                ]
            }
            return _AuditReport(payload)

    class _Valuation:
        def evaluate_listing_id(
            self,
            listing_id: str,
            *,
            persist: bool = False,
            source_status_by_source: dict[str, str] | None = None,
            source_metrics_by_source: dict[str, dict] | None = None,
        ) -> SimpleNamespace:
            captured["listing_id"] = listing_id
            captured["persist"] = persist
            captured["source_status_by_source"] = dict(source_status_by_source or {})
            captured["source_metrics_by_source"] = dict(source_metrics_by_source or {})
            return SimpleNamespace(listing_id=listing_id, market_signals={"comp_count": 3.0})

    container = SimpleNamespace(sources=_Sources(), valuation=_Valuation(), full_valuation=None)
    monkeypatch.setattr(app_module, "get_container", lambda: container)
    monkeypatch.setattr(app_module, "model_to_dict", lambda analysis: analysis.__dict__)
    client = TestClient(app_module.app)

    response = client.post("/api/v1/valuations", json={"listing_id": "target", "persist": False})

    assert response.status_code == 200
    assert calls == [1]
    assert captured["listing_id"] == "target"
    assert captured["persist"] is False
    assert captured["source_status_by_source"] == {"pisos": "supported-1"}
    assert captured["source_metrics_by_source"] == {"pisos": {"snapshot_id": 1}}


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
