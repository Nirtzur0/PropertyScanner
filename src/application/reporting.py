from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from src.application.serving import evaluate_serving_eligibility
from src.listings.source_ids import canonicalize_source_id
from src.platform.domain.models import BenchmarkRun, CoverageReport, DataQualityEvent, SourceContractRun
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


class ReportingService:
    def __init__(self, *, storage: StorageService) -> None:
        self.storage = storage

    def start_benchmark_run(
        self,
        *,
        config: Dict[str, Any],
        output_json_path: str,
        output_md_path: str,
    ) -> str:
        benchmark_run_id = uuid4().hex
        session = self.storage.get_session()
        try:
            session.add(
                BenchmarkRun(
                    id=benchmark_run_id,
                    status="running",
                    config=config,
                    metrics={},
                    output_json_path=output_json_path,
                    output_md_path=output_md_path,
                    created_at=utcnow(),
                )
            )
            session.commit()
        finally:
            session.close()
        return benchmark_run_id

    def complete_benchmark_run(
        self,
        benchmark_run_id: str,
        *,
        status: str,
        report: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> None:
        session = self.storage.get_session()
        try:
            row = session.query(BenchmarkRun).filter(BenchmarkRun.id == benchmark_run_id).first()
            if row is None:
                raise ValueError("benchmark_run_not_found")
            row.status = status
            row.metrics = {
                **metrics,
                "report_generated_at": report.get("generated_at"),
            }
            row.output_json_path = str(report.get("output_json_path") or row.output_json_path or "")
            row.output_md_path = str(report.get("output_md_path") or row.output_md_path or "")
            row.completed_at = utcnow()
            session.commit()
        finally:
            session.close()

    def fail_benchmark_run(self, benchmark_run_id: str, *, error: str) -> None:
        session = self.storage.get_session()
        try:
            row = session.query(BenchmarkRun).filter(BenchmarkRun.id == benchmark_run_id).first()
            if row is None:
                raise ValueError("benchmark_run_not_found")
            row.status = "failed"
            row.metrics = {"error": error}
            row.completed_at = utcnow()
            session.commit()
        finally:
            session.close()

    def persist_segmented_coverage_report(self, report: Dict[str, Any]) -> List[str]:
        created_at = utcnow()
        inserted_ids: List[str] = []
        session = self.storage.get_session()
        try:
            for segment in report.get("segments", []):
                coverage_id = uuid4().hex
                session.add(
                    CoverageReport(
                        id=coverage_id,
                        listing_type=str(segment.get("listing_type") or "unknown"),
                        segment_key=str(segment.get("bucket_key") or "unknown"),
                        segment_value=str(segment.get("horizon_label") or segment.get("horizon_months") or "unknown"),
                        sample_size=int(segment.get("n_samples") or 0),
                        empirical_coverage=(
                            float(segment["coverage_rate"])
                            if segment.get("coverage_rate") is not None
                            else None
                        ),
                        avg_interval_width=(
                            float(segment["avg_interval_width"])
                            if segment.get("avg_interval_width") is not None
                            else None
                        ),
                        status=str(segment.get("status") or "pending"),
                        report={
                            **segment,
                            "target_coverage": report.get("target_coverage"),
                            "coverage_floor": report.get("coverage_floor"),
                            "min_samples": report.get("min_samples"),
                        },
                        created_at=created_at,
                    )
                )
                inserted_ids.append(coverage_id)
            session.commit()
        finally:
            session.close()
        return inserted_ids

    def list_benchmark_runs(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = (
                session.query(BenchmarkRun)
                .order_by(BenchmarkRun.created_at.desc())
                .limit(max(1, min(limit, 100)))
                .all()
            )
            return [
                {
                    "id": row.id,
                    "status": row.status,
                    "config": dict(row.config or {}),
                    "metrics": dict(row.metrics or {}),
                    "output_json_path": row.output_json_path,
                    "output_md_path": row.output_md_path,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                }
                for row in rows
            ]
        finally:
            session.close()

    def list_coverage_reports(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = (
                session.query(CoverageReport)
                .order_by(CoverageReport.created_at.desc())
                .limit(max(1, min(limit, 200)))
                .all()
            )
            return [
                {
                    "id": row.id,
                    "listing_type": row.listing_type,
                    "segment_key": row.segment_key,
                    "segment_value": row.segment_value,
                    "sample_size": row.sample_size,
                    "empirical_coverage": row.empirical_coverage,
                    "avg_interval_width": row.avg_interval_width,
                    "status": row.status,
                    "report": dict(row.report or {}),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
        finally:
            session.close()

    def list_data_quality_events(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = (
                session.query(DataQualityEvent)
                .order_by(DataQualityEvent.created_at.desc())
                .limit(max(1, min(limit, 500)))
                .all()
            )
            return [
                {
                    "id": row.id,
                    "source_id": row.source_id,
                    "listing_id": row.listing_id,
                    "field_name": row.field_name,
                    "severity": row.severity,
                    "code": row.code,
                    "details": dict(row.details or {}),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
        finally:
            session.close()

    def record_data_quality_event(
        self,
        *,
        source_id: str,
        listing_id: str | None,
        field_name: str,
        severity: str,
        code: str,
        details: Dict[str, Any],
    ) -> str:
        source_id = canonicalize_source_id(source_id)
        session = self.storage.get_session()
        try:
            existing = (
                session.query(DataQualityEvent)
                .filter(DataQualityEvent.source_id == source_id)
                .filter(DataQualityEvent.listing_id == listing_id)
                .filter(DataQualityEvent.field_name == field_name)
                .filter(DataQualityEvent.code == code)
                .first()
            )
            if existing is not None:
                return str(existing.id)
            event_id = uuid4().hex
            session.add(
                DataQualityEvent(
                    id=event_id,
                    source_id=source_id,
                    listing_id=listing_id,
                    field_name=field_name,
                    severity=severity,
                    code=code,
                    details=dict(details),
                    created_at=utcnow(),
                )
            )
            session.commit()
            return event_id
        finally:
            session.close()

    def audit_serving_eligibility(self, *, source_status_by_source: Dict[str, str] | None = None) -> Dict[str, Any]:
        from src.platform.domain.models import DBListing

        source_status_by_source = source_status_by_source or {}
        session = self.storage.get_session()
        try:
            rows = session.query(DBListing).all()
        finally:
            session.close()

        invalid = 0
        by_source: Dict[str, int] = {}
        for row in rows:
            canonical_source_id = canonicalize_source_id(str(row.source_id))
            source_status = str(
                source_status_by_source.get(canonical_source_id)
                or source_status_by_source.get(str(row.source_id))
                or "experimental"
            )
            eligibility = evaluate_serving_eligibility(row, source_status=source_status)
            if eligibility.eligible:
                continue
            invalid += 1
            by_source[canonical_source_id] = by_source.get(canonical_source_id, 0) + 1
            self.record_data_quality_event(
                source_id=canonical_source_id,
                listing_id=str(row.id),
                field_name=str(eligibility.field_name or "listing"),
                severity="error",
                code=str(eligibility.code or "serving_ineligible"),
                details={
                    "reason": eligibility.reason,
                    "source_status": source_status,
                    "price": row.price,
                    "surface_area_sqm": row.surface_area_sqm,
                    "bedrooms": row.bedrooms,
                    "bathrooms": row.bathrooms,
                    "lat": row.lat,
                    "lon": row.lon,
                },
            )
        return {
            "total_rows": len(rows),
            "invalid_rows": invalid,
            "by_source": by_source,
        }

    def list_source_contract_runs(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = (
                session.query(SourceContractRun)
                .order_by(SourceContractRun.created_at.desc())
                .limit(max(1, min(limit, 200)))
                .all()
            )
            return [
                {
                    "id": row.id,
                    "source_id": row.source_id,
                    "status": row.status,
                    "metrics": dict(row.metrics or {}),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
        finally:
            session.close()
