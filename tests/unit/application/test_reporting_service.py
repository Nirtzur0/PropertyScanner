from __future__ import annotations

import json
from pathlib import Path

from src.application.model_readiness import ModelReadinessService
from src.application.pipeline import PipelineApplicationService
from src.application.reporting import ReportingService
from src.application.sources import SourceCapabilityService
from src.core.runtime import RuntimeConfig
from src.platform.domain.models import BenchmarkRun, CoverageReport, DataQualityEvent, SourceContractRun
from src.platform.utils.time import utcnow
from src.platform.settings import AppConfig
from src.platform.storage import StorageService
from src.valuation.workflows.calibration import update_calibrators


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
    return RuntimeConfig.model_validate(
        {
            "paths": {
                "db_path": str(tmp_path / "reporting.db"),
                "sources_config_path": str(sources_path),
                "docs_crawler_status_path": str(crawler_status_path),
                "benchmark_json_path": str(tmp_path / "benchmark.json"),
                "benchmark_md_path": str(tmp_path / "benchmark.md"),
            }
        }
    )


def test_pipeline_application_service__blocks_sale_benchmark_without_closed_labels(tmp_path: Path) -> None:
    runtime_config = _runtime_config(tmp_path)
    storage = StorageService(db_url=f"sqlite:///{runtime_config.paths.db_path}")
    sources = SourceCapabilityService(storage=storage, runtime_config=runtime_config)
    readiness = ModelReadinessService(storage=storage, runtime_config=runtime_config)
    reporting = ReportingService(storage=storage)
    service = PipelineApplicationService(
        storage=storage,
        runtime_config=runtime_config,
        source_capability_service=sources,
        model_readiness_service=readiness,
        reporting_service=reporting,
    )
    report = service.run_benchmark()

    session = storage.get_session()
    try:
        run = session.query(BenchmarkRun).one()
    finally:
        session.close()

    assert report["benchmark_run_id"] == run.id
    assert run.status == "blocked"
    assert report["reason"] == "sale_benchmark_blocked_by_closed_label_readiness"
    assert "closed_label_floor_not_met" in run.metrics["gate"]["reasons"]
    assert run.output_json_path == str(runtime_config.paths.benchmark_json_path)


def test_update_calibrators__persists_segmented_coverage_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "coverage.db"
    input_path = tmp_path / "samples.jsonl"
    output_path = tmp_path / "registry.json"
    coverage_path = tmp_path / "coverage.json"

    samples = []
    for i in range(25):
        actual = 240000.0 + float(i)
        samples.append(
            {
                "region_id": "madrid",
                "property_type": "sale",
                "horizon_months": 0,
                "actual": actual,
                "pred_q10": actual - 5000.0,
                "pred_q50": actual,
                "pred_q90": actual + 5000.0,
            }
        )
    input_path.write_text("".join(f"{json.dumps(sample)}\n" for sample in samples), encoding="utf-8")

    app_config = AppConfig.model_validate({"pipeline": {"db_path": str(db_path)}})
    update_calibrators(
        input_path=str(input_path),
        output_path=str(output_path),
        coverage_output_path=str(coverage_path),
        app_config=app_config,
        coverage_min_samples=20,
        coverage_floor=0.8,
    )

    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        rows = session.query(CoverageReport).all()
    finally:
        session.close()

    assert len(rows) >= 1
    assert any(row.listing_type == "sale" and row.segment_value == "spot" for row in rows)


def test_reporting_service__lists_operational_artifacts(tmp_path: Path) -> None:
    runtime_config = _runtime_config(tmp_path)
    storage = StorageService(db_url=f"sqlite:///{runtime_config.paths.db_path}")
    reporting = ReportingService(storage=storage)

    session = storage.get_session()
    try:
        session.add(
            SourceContractRun(
                id="source-run-1",
                source_id="pisos",
                status="degraded",
                metrics={"row_count": 10},
                created_at=utcnow(),
            )
        )
        session.add(
            DataQualityEvent(
                id="dq-1",
                source_id="pisos",
                listing_id=None,
                field_name="price",
                severity="error",
                code="price_corruption_high",
                details={"invalid_ratio": 0.42},
                created_at=utcnow(),
            )
        )
        session.add(
            BenchmarkRun(
                id="benchmark-1",
                status="succeeded",
                config={"listing_type": "sale"},
                metrics={"gate": {"pass": True}},
                output_json_path=str(tmp_path / "benchmark.json"),
                output_md_path=str(tmp_path / "benchmark.md"),
                created_at=utcnow(),
            )
        )
        session.add(
            CoverageReport(
                id="coverage-1",
                listing_type="sale",
                segment_key="region_id",
                segment_value="madrid",
                sample_size=25,
                empirical_coverage=0.91,
                avg_interval_width=12000.0,
                status="pass",
                report={"coverage_floor": 0.8},
                created_at=utcnow(),
            )
        )
        session.commit()
    finally:
        session.close()

    assert reporting.list_benchmark_runs(limit=10)[0]["id"] == "benchmark-1"
    assert reporting.list_coverage_reports(limit=10)[0]["id"] == "coverage-1"
    assert reporting.list_data_quality_events(limit=10)[0]["id"] == "dq-1"
    assert reporting.list_source_contract_runs(limit=10)[0]["id"] == "source-run-1"
