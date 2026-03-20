from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.application.pipeline import PipelineApplicationService
from src.core.runtime import RuntimeConfig
from src.platform.storage import StorageService


def _runtime_config(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig.model_validate(
        {
            "paths": {
                "db_path": str(tmp_path / "pipeline.db"),
                "sources_config_path": str(tmp_path / "sources.yaml"),
                "docs_crawler_status_path": str(tmp_path / "crawler_status.md"),
                "benchmark_json_path": str(tmp_path / "benchmark.json"),
                "benchmark_md_path": str(tmp_path / "benchmark.md"),
            }
        }
    )


def test_pipeline_application_service__trust_summary_reuses_one_source_audit_snapshot(tmp_path: Path, monkeypatch) -> None:
    runtime_config = _runtime_config(tmp_path)
    storage = StorageService(db_url=f"sqlite:///{runtime_config.paths.db_path}")
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
            return _AuditReport(
                {
                    "summary": {"supported": 1, "blocked": 0},
                    "sources": [
                        {
                            "source_id": "pisos",
                            "status": f"supported-{len(calls)}",
                            "metrics": {"snapshot_id": len(calls)},
                        }
                    ],
                }
            )

    class _Readiness:
        def sale_training_readiness(self) -> dict:
            return {"ready": True, "reasons": []}

    class _Reporting:
        def pipeline_trust_summary(self, *, pipeline_state: dict, source_audit: dict) -> dict:
            captured["pipeline_state"] = pipeline_state
            captured["source_audit"] = source_audit
            return {"status": "ok", "source_summary": source_audit["summary"]}

    class _Snapshot:
        def to_dict(self) -> dict:
            return {"needs_refresh": False, "reasons": []}

    monkeypatch.setattr("src.application.pipeline.PipelineStateService.snapshot", lambda self: _Snapshot())

    service = PipelineApplicationService(
        storage=storage,
        runtime_config=runtime_config,
        source_capability_service=_Sources(),
        model_readiness_service=_Readiness(),
        reporting_service=_Reporting(),
    )

    payload = service.pipeline_trust_summary()

    assert payload["status"] == "ok"
    assert calls == [1]
    assert captured["source_audit"] == {
        "summary": {"supported": 1, "blocked": 0},
        "sources": [{"source_id": "pisos", "status": "supported-1", "metrics": {"snapshot_id": 1}}],
    }
    assert captured["pipeline_state"] == {
        "needs_refresh": False,
        "reasons": [],
        "source_capabilities": captured["source_audit"],
        "model_readiness": {"ready": True, "reasons": []},
    }


def test_pipeline_application_service__preflight_reuses_one_persisted_final_source_audit_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_config = _runtime_config(tmp_path)
    storage = StorageService(db_url=f"sqlite:///{runtime_config.paths.db_path}")
    calls: list[bool] = []

    class _AuditReport:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def model_dump(self, *, mode: str = "json") -> dict:
            assert mode == "json"
            return self.payload

    class _Sources:
        def audit_sources(self, *, persist: bool = False) -> _AuditReport:
            calls.append(persist)
            call_id = len(calls)
            return _AuditReport(
                {
                    "summary": {"supported": 1, "blocked": 0},
                    "sources": [
                        {
                            "source_id": "pisos",
                            "status": f"supported-{call_id}",
                            "metrics": {"snapshot_id": call_id, "persist": persist},
                        }
                    ],
                }
            )

    class _Readiness:
        def sale_training_readiness(self) -> dict:
            return {"ready": False, "reasons": ["sale_labels_missing"]}

    class _Reporting:
        pass

    class _Snapshot:
        needs_crawl = False
        needs_market_data = False
        needs_index = False

        def to_dict(self) -> dict:
            return {"needs_refresh": False, "reasons": []}

    monkeypatch.setattr("src.application.pipeline.PipelineStateService.snapshot", lambda self: _Snapshot())

    service = PipelineApplicationService(
        storage=storage,
        runtime_config=runtime_config,
        source_capability_service=_Sources(),
        model_readiness_service=_Readiness(),
        reporting_service=_Reporting(),
    )

    payload = service.run_preflight(
        skip_crawl=True,
        skip_market_data=True,
        skip_index=True,
        skip_training=False,
    )

    assert calls == [False, True]
    assert payload["initial_status"]["source_capabilities"] == {
        "summary": {"supported": 1, "blocked": 0},
        "sources": [{"source_id": "pisos", "status": "supported-1", "metrics": {"snapshot_id": 1, "persist": False}}],
        }
    assert payload["final_status"]["source_capabilities"] == {
        "summary": {"supported": 1, "blocked": 0},
        "sources": [{"source_id": "pisos", "status": "supported-2", "metrics": {"snapshot_id": 2, "persist": True}}],
    }
    assert payload["final_status"]["model_readiness"] == {"ready": False, "reasons": ["sale_labels_missing"]}
    assert payload["steps"] == [
        {"step": "training", "result": {"status": "blocked", "reasons": ["sale_labels_missing"]}}
    ]
