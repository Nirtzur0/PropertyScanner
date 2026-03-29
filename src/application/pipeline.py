from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from src.application.analytics import AnalyticsArtifactService
from src.core.runtime import RuntimeConfig
from src.platform.db.base import resolve_db_url
from src.platform.pipeline.state import PipelineStateService
from src.platform.storage import StorageService
from src.application.model_readiness import ModelReadinessService
from src.application.reporting import ReportingService
from src.application.sources import SourceCapabilityService
from src.platform.utils.config import load_app_config_safe


class PipelineApplicationService:
    def __init__(
        self,
        *,
        storage: StorageService,
        runtime_config: RuntimeConfig,
        source_capability_service: SourceCapabilityService,
        model_readiness_service: ModelReadinessService,
        reporting_service: ReportingService,
        analytics_service: AnalyticsArtifactService | None = None,
    ) -> None:
        self.storage = storage
        self.runtime_config = runtime_config
        self.source_capability_service = source_capability_service
        self.model_readiness_service = model_readiness_service
        self.reporting_service = reporting_service
        self.analytics_service = analytics_service or AnalyticsArtifactService(runtime_config=runtime_config)

    @property
    def db_url(self) -> str:
        return resolve_db_url(db_path=self.runtime_config.paths.db_path)

    def _source_audit_snapshot(self, *, persist: bool = False) -> Dict[str, Any]:
        return self.source_capability_service.audit_sources(persist=persist).model_dump(mode="json")

    def _pipeline_status_with_source_audit(self, source_audit: Dict[str, Any]) -> Dict[str, Any]:
        state = PipelineStateService(db_path=str(self.runtime_config.paths.db_path)).snapshot().to_dict()
        state["source_capabilities"] = source_audit
        state["model_readiness"] = self.model_readiness_service.sale_training_readiness()
        return state

    def pipeline_status(self) -> Dict[str, Any]:
        return self._pipeline_status_with_source_audit(self._source_audit_snapshot())

    def pipeline_trust_summary(self) -> Dict[str, Any]:
        source_audit = self._source_audit_snapshot()
        pipeline_state = self._pipeline_status_with_source_audit(source_audit)
        return self.reporting_service.pipeline_trust_summary(
            pipeline_state=pipeline_state,
            source_audit=source_audit,
        )

    # NOTE: Workflow methods use lazy imports intentionally. The workflow
    # modules (listings.workflows, market.workflows, valuation.workflows,
    # ml.training) pull in heavyweight dependencies (Playwright, torch,
    # sentence-transformers, etc.) that should not load at container init.
    # This is NOT hiding circular dependencies — it's deferred loading.

    def run_crawl(
        self,
        *,
        source_ids: Optional[List[str]] = None,
        max_listings: int = 0,
        max_pages: int = 1,
        page_size: int = 24,
        run_vlm: bool = False,
    ) -> Dict[str, Any]:
        from src.listings.workflows.unified_crawl import run_backfill

        results = run_backfill(
            source_ids=source_ids,
            max_listings=max_listings,
            max_pages=max_pages,
            page_size=page_size,
            run_vlm=run_vlm,
        )
        return {"results": results}

    def run_market_data(self) -> Dict[str, Any]:
        from src.market.workflows.market_data import build_market_data

        build_market_data(db_path=str(self.runtime_config.paths.db_path))
        return {"status": "ok"}

    def run_index(self, *, listing_type: str = "all", limit: int = 0) -> Dict[str, Any]:
        from src.valuation.workflows.indexing import build_vector_index

        indexed = build_vector_index(
            db_url=self.db_url,
            listing_type=listing_type,
            limit=limit,
        )
        return {"status": "ok", "indexed": indexed}

    def run_benchmark(self, *, listing_type: str = "sale", label_source: str = "auto", geo_key: str = "city") -> Dict[str, Any]:
        benchmark_config = {
            "listing_type": listing_type,
            "label_source": label_source,
            "geo_key": geo_key,
            "db_url": self.db_url,
        }
        benchmark_run_id = self.reporting_service.start_benchmark_run(
            config=benchmark_config,
            output_json_path=str(self.runtime_config.paths.benchmark_json_path),
            output_md_path=str(self.runtime_config.paths.benchmark_md_path),
        )
        sale_readiness = self.model_readiness_service.sale_training_readiness()
        if listing_type == "sale" and not sale_readiness["ready"]:
            report = {
                "benchmark_run_id": benchmark_run_id,
                "status": "blocked",
                "reason": "sale_benchmark_blocked_by_closed_label_readiness",
                "sale_model_readiness": sale_readiness,
            }
            self.reporting_service.complete_benchmark_run(
                benchmark_run_id,
                status="blocked",
                report=report,
                metrics={
                    "sale_model_readiness": sale_readiness,
                    "gate": {"pass": False, "reasons": sale_readiness["reasons"]},
                },
            )
            return report
        benchmark_label_source = label_source
        if listing_type == "sale" and benchmark_label_source == "auto":
            benchmark_label_source = "sold"
        try:
            from src.ml.training.benchmark import load_training_frame, run_benchmark

            frame = load_training_frame(
                db_url=self.db_url,
                listing_type=listing_type,
                label_source=benchmark_label_source,
                geo_key=geo_key,
            )
            dataset_artifact = self.analytics_service.export_dataframe(
                frame,
                namespace="benchmarks",
                stem=f"{listing_type}-{benchmark_label_source}-{geo_key}",
                metadata={
                    "dataset_kind": "benchmark",
                    "listing_type": listing_type,
                    "label_source": benchmark_label_source,
                    "geo_key": geo_key,
                    "db_url": self.db_url,
                },
            )
            report = run_benchmark(
                db_url=self.db_url,
                output_json=str(self.runtime_config.paths.benchmark_json_path),
                output_md=str(self.runtime_config.paths.benchmark_md_path),
                listing_type=listing_type,
                label_source=benchmark_label_source,
                geo_key=geo_key,
                val_split=0.1,
                test_split=0.2,
                split_seed=42,
                max_fusion_eval=80,
                min_test_rows=50,
                fusion_min_coverage=0.6,
                fusion_mae_ratio_threshold=1.2,
                fusion_mape_ratio_threshold=1.2,
                require_xgboost=True,
                app_config=load_app_config_safe(),
                research_only=True,
            )
        except Exception as exc:
            self.reporting_service.fail_benchmark_run(benchmark_run_id, error=str(exc))
            raise

        report["benchmark_run_id"] = benchmark_run_id
        report["dataset_artifact"] = dataset_artifact
        if listing_type == "sale":
            report["sale_model_readiness"] = sale_readiness
        benchmark_status = "succeeded" if bool(report.get("gate", {}).get("pass")) else "failed_gate"
        self.reporting_service.complete_benchmark_run(
            benchmark_run_id,
            status=benchmark_status,
            report=report,
            metrics={
                "gate": report.get("gate", {}),
                "dataset": report.get("dataset", {}),
                "sale_model_readiness": sale_readiness if listing_type == "sale" else None,
            },
        )
        return report

    def export_source_quality_snapshot(self, *, source_status_by_source: Dict[str, str]) -> Dict[str, Any]:
        audit = self.reporting_service.audit_serving_eligibility(source_status_by_source=source_status_by_source)
        source_rows = []
        for source_id, invalid_rows in sorted((audit.get("by_source") or {}).items()):
            source_rows.append({"source_id": str(source_id), "invalid_rows": int(invalid_rows)})
        frame = pd.DataFrame(source_rows or [{"source_id": "none", "invalid_rows": 0}])
        artifact = self.analytics_service.export_dataframe(
            frame,
            namespace="quality",
            stem="serving-eligibility-audit",
            metadata={
                "dataset_kind": "source_quality_audit",
                "summary": audit,
            },
        )
        return {
            "audit": audit,
            "artifact": artifact,
        }

    def run_preflight(
        self,
        *,
        source_ids: Optional[List[str]] = None,
        max_listings: int = 0,
        max_pages: int = 1,
        page_size: int = 24,
        skip_crawl: bool = False,
        skip_market_data: bool = False,
        skip_index: bool = False,
        skip_training: bool = False,
    ) -> Dict[str, Any]:
        initial = self.pipeline_status()
        steps: List[Dict[str, Any]] = []
        state = PipelineStateService(db_path=str(self.runtime_config.paths.db_path)).snapshot()

        if state.needs_crawl and not skip_crawl:
            result = self.run_crawl(
                source_ids=source_ids,
                max_listings=max_listings,
                max_pages=max_pages,
                page_size=page_size,
            )
            steps.append({"step": "crawl", "result": result})

        if state.needs_market_data and not skip_market_data:
            result = self.run_market_data()
            steps.append({"step": "market_data", "result": result})

        if state.needs_index and not skip_index:
            result = self.run_index()
            steps.append({"step": "index", "result": result})

        readiness = self.model_readiness_service.sale_training_readiness()
        if not skip_training:
            if readiness["ready"]:
                steps.append({"step": "training", "result": {"status": "deferred_to_model_reset_packet"}})
            else:
                steps.append({"step": "training", "result": {"status": "blocked", "reasons": readiness["reasons"]}})

        final_source_audit = self._source_audit_snapshot(persist=True)
        final_status = self._pipeline_status_with_source_audit(final_source_audit)

        return {
            "initial_status": initial,
            "steps": steps,
            "final_status": final_status,
        }
