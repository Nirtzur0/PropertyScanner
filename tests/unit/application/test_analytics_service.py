from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from src.application.analytics import AnalyticsArtifactService
from src.core.runtime import RuntimeConfig


def test_analytics_service__exports_parquet_and_metadata(tmp_path: Path) -> None:
    runtime = RuntimeConfig.model_validate({"paths": {"db_path": str(tmp_path / "analytics.db")}})
    service = AnalyticsArtifactService(runtime_config=runtime)
    frame = pd.DataFrame([{"source_id": "pisos", "invalid_rows": 5}])

    artifact = service.export_dataframe(
        frame,
        namespace="quality",
        stem="audit",
        metadata={"dataset_kind": "source_quality_audit"},
    )

    parquet_path = Path(artifact["parquet_path"])
    metadata_path = Path(artifact["metadata_path"])
    assert parquet_path.exists()
    assert metadata_path.exists()

    rows = duckdb.sql(f"SELECT * FROM read_parquet('{str(parquet_path)}')").fetchall()
    assert rows == [("pisos", 5)]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["dataset_kind"] == "source_quality_audit"
    assert metadata["row_count"] == 1
