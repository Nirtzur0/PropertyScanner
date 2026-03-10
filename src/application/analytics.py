from __future__ import annotations

import json
from hashlib import md5
from pathlib import Path
from typing import Any, Dict

import duckdb
import pandas as pd

from src.core.runtime import RuntimeConfig
from src.platform.utils.time import utcnow


class AnalyticsArtifactService:
    def __init__(self, *, runtime_config: RuntimeConfig) -> None:
        data_root = Path(runtime_config.paths.db_path).resolve().parent
        self.analytics_root = data_root / "analytics"

    def export_dataframe(
        self,
        frame: pd.DataFrame,
        *,
        namespace: str,
        stem: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        namespace_path = self.analytics_root / namespace
        namespace_path.mkdir(parents=True, exist_ok=True)

        metadata_payload = {
            **metadata,
            "namespace": namespace,
            "stem": stem,
            "generated_at": utcnow().isoformat(),
            "row_count": int(len(frame)),
            "columns": list(frame.columns),
        }
        fingerprint = md5(
            json.dumps(metadata_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:12]
        parquet_path = namespace_path / f"{stem}-{fingerprint}.parquet"
        metadata_path = namespace_path / f"{stem}-{fingerprint}.json"

        connection = duckdb.connect()
        try:
            connection.register("artifact_frame", frame)
            safe_path = str(parquet_path).replace("'", "''")
            connection.execute(f"COPY artifact_frame TO '{safe_path}' (FORMAT PARQUET)")
        finally:
            connection.close()

        metadata_path.write_text(
            json.dumps(
                {
                    **metadata_payload,
                    "parquet_path": str(parquet_path),
                    "metadata_path": str(metadata_path),
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "namespace": namespace,
            "parquet_path": str(parquet_path),
            "metadata_path": str(metadata_path),
            "row_count": int(len(frame)),
            "fingerprint": fingerprint,
        }
