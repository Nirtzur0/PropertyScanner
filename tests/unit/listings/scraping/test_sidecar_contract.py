from __future__ import annotations

from pathlib import Path

from src.listings.scraping.sidecar import CrawlPlan, load_results, write_plan


def test_sidecar_contract__writes_plan_and_loads_results(tmp_path: Path) -> None:
    result_path = tmp_path / "results.ndjson"
    plan = CrawlPlan(
        job_id="job-1",
        source_id="pisos",
        mode="search",
        start_urls=["https://example.com/search"],
        max_pages=1,
        max_listings=10,
        page_size=24,
        proxy_policy={"mode": "direct"},
        session_policy={"persistCookiesPerSession": True},
        snapshot_dir=str(tmp_path / "snapshots"),
        result_path=str(result_path),
    )

    plan_path = write_plan(plan, plan_path=tmp_path / "plan.json")
    assert plan_path.exists()
    assert Path(plan.snapshot_dir).exists()

    result_path.write_text('{"url":"https://example.com","status":"ok"}\n', encoding="utf-8")
    results = load_results(result_path)
    assert results == [{"url": "https://example.com", "status": "ok"}]
