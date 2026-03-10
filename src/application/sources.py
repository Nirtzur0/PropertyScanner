from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import pandas as pd
import yaml
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.core.runtime import RuntimeConfig
from src.platform.domain.models import DataQualityEvent, SourceContractRun
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def _norm_source_base(source_id: str) -> str:
    source_id = str(source_id).strip().lower()
    if "_" in source_id:
        return source_id.split("_", 1)[0]
    return source_id


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


class SourceCapabilityReport(BaseModel):
    source_id: str
    name: str
    enabled: bool
    countries: List[str] = Field(default_factory=list)
    status: str
    reasons: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class SourceCapabilitySummary(BaseModel):
    generated_at: str
    summary: Dict[str, int]
    sources: List[SourceCapabilityReport]


@dataclass(frozen=True)
class SourceCatalogEntry:
    source_id: str
    name: str
    enabled: bool
    countries: List[str]


class SourceCapabilityService:
    def __init__(self, *, storage: StorageService, runtime_config: RuntimeConfig) -> None:
        self.storage = storage
        self.runtime_config = runtime_config

    def load_source_catalog(self) -> List[SourceCatalogEntry]:
        config_path = self.runtime_config.paths.sources_config_path
        with config_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        entries = payload.get("sources", {}).get("sources", [])
        results: List[SourceCatalogEntry] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            results.append(
                SourceCatalogEntry(
                    source_id=str(item.get("id") or "").strip(),
                    name=str(item.get("name") or item.get("id") or "").strip(),
                    enabled=bool(item.get("enabled", False)),
                    countries=list(item.get("countries") or []),
                )
            )
        return [entry for entry in results if entry.source_id]

    def _discover_contract_support(self, source_id: str) -> Dict[str, bool]:
        base = _norm_source_base(source_id)
        repo_root = Path(__file__).resolve().parents[2]
        fixtures_root = repo_root / "tests" / "resources" / "html"
        tests_root = repo_root / "tests" / "unit" / "listings" / "normalizers"
        fixture_files = [
            fixtures_root / f"{base}.html",
            fixtures_root / f"{base}_search.html",
        ]
        test_files = list(tests_root.glob(f"test_{base}*.py"))
        return {
            "has_fixture_html": any(path.exists() for path in fixture_files),
            "has_contract_test": bool(test_files),
        }

    def _load_doc_status(self) -> Dict[str, str]:
        path = self.runtime_config.paths.docs_crawler_status_path
        if not path.exists():
            return {}
        status_by_source: Dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [cell.strip(" `*") for cell in line.split("|")[1:-1]]
            if len(cells) < 3:
                continue
            if not cells[0] or cells[0].lower() == "crawler":
                continue
            status_text = cells[2].lower()
            base = _norm_source_base(cells[0])
            if "blocked" in status_text:
                status_by_source[base] = "blocked"
            elif "operational" in status_text:
                status_by_source[base] = "operational"
        return status_by_source

    @staticmethod
    def _severity_for_reason(reason: str) -> str:
        if reason in {
            "crawler_status_blocked",
            "price_corruption_high",
            "area_corruption_high",
            "stale_rows",
            "stale_or_missing_rows",
        }:
            return "error"
        return "warning"

    def _persist_audit(self, summary: SourceCapabilitySummary) -> None:
        generated_at = pd.to_datetime(summary.generated_at, format="mixed", errors="coerce")
        created_at = generated_at.to_pydatetime() if generated_at is not None and not pd.isna(generated_at) else utcnow()

        session = self.storage.get_session()
        try:
            for report in summary.sources:
                session.add(
                    SourceContractRun(
                        id=uuid4().hex,
                        source_id=report.source_id,
                        status=report.status,
                        metrics={
                            **report.metrics,
                            "name": report.name,
                            "enabled": report.enabled,
                            "countries": report.countries,
                            "reasons": report.reasons,
                        },
                        created_at=created_at,
                    )
                )
                for reason in report.reasons:
                    session.add(
                        DataQualityEvent(
                            id=uuid4().hex,
                            source_id=report.source_id,
                            listing_id=None,
                            field_name="source_contract",
                            severity=self._severity_for_reason(reason),
                            code=reason,
                            details={
                                "status": report.status,
                                "name": report.name,
                                "metrics": report.metrics,
                            },
                            created_at=created_at,
                        )
                    )
            session.commit()
        finally:
            session.close()

    def audit_sources(self, *, persist: bool = False) -> SourceCapabilitySummary:
        thresholds = self.runtime_config.quality
        now = utcnow()
        doc_status = self._load_doc_status()
        query = text(
            """
            SELECT
                source_id,
                COUNT(*) AS row_count,
                SUM(CASE WHEN price IS NULL OR price < 10000 OR price > 15000000 THEN 1 ELSE 0 END) AS invalid_price_count,
                SUM(CASE WHEN surface_area_sqm IS NULL OR surface_area_sqm < 5 OR surface_area_sqm > 5000 THEN 1 ELSE 0 END) AS invalid_surface_area_count,
                MAX(COALESCE(fetched_at, updated_at, listed_at)) AS last_seen
            FROM listings
            GROUP BY source_id
            """
        )
        with self.storage.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        db_metrics = {str(row["source_id"]): row for row in rows}

        reports: List[SourceCapabilityReport] = []
        summary = {"supported": 0, "experimental": 0, "degraded": 0, "blocked": 0}
        for entry in self.load_source_catalog():
            metrics_row = db_metrics.get(entry.source_id, {})
            row_count = int(metrics_row.get("row_count") or 0)
            invalid_price_count = int(metrics_row.get("invalid_price_count") or 0)
            invalid_surface_area_count = int(metrics_row.get("invalid_surface_area_count") or 0)
            last_seen_raw = metrics_row.get("last_seen")
            last_seen = pd.to_datetime(last_seen_raw, format="mixed", errors="coerce") if last_seen_raw else None
            contract_support = self._discover_contract_support(entry.source_id)
            doc_state = doc_status.get(_norm_source_base(entry.source_id), "unknown")

            invalid_price_ratio = _safe_ratio(invalid_price_count, row_count)
            invalid_surface_area_ratio = _safe_ratio(invalid_surface_area_count, row_count)

            reasons: List[str] = []
            status = "experimental"
            if doc_state == "blocked":
                status = "blocked"
                reasons.append("crawler_status_blocked")
            else:
                if row_count == 0:
                    reasons.append("no_rows")
                if row_count < thresholds.experimental_min_rows:
                    reasons.append("insufficient_rows")
                if invalid_price_ratio > thresholds.degraded_invalid_ratio_max:
                    reasons.append("price_corruption_high")
                elif invalid_price_ratio > thresholds.supported_invalid_ratio_max:
                    reasons.append("price_corruption_present")
                if invalid_surface_area_ratio > thresholds.degraded_invalid_ratio_max:
                    reasons.append("area_corruption_high")
                elif invalid_surface_area_ratio > thresholds.supported_invalid_ratio_max:
                    reasons.append("area_corruption_present")
                if not contract_support["has_fixture_html"]:
                    reasons.append("fixture_missing")
                if not contract_support["has_contract_test"]:
                    reasons.append("contract_test_missing")
                freshness_deadline = now - timedelta(days=thresholds.freshness_days)
                if last_seen is None:
                    reasons.append("stale_or_missing_rows")
                elif last_seen.to_pydatetime() < freshness_deadline:
                    reasons.append("stale_rows")

                if row_count >= thresholds.experimental_min_rows and not reasons:
                    status = "supported"
                elif any(reason in reasons for reason in ("price_corruption_high", "area_corruption_high", "stale_rows")):
                    status = "degraded"
                else:
                    status = "experimental"

            summary[status] += 1
            reports.append(
                SourceCapabilityReport(
                    source_id=entry.source_id,
                    name=entry.name,
                    enabled=entry.enabled,
                    countries=entry.countries,
                    status=status,
                    reasons=reasons,
                    metrics={
                        "row_count": row_count,
                        "invalid_price_count": invalid_price_count,
                        "invalid_surface_area_count": invalid_surface_area_count,
                        "invalid_price_ratio": round(invalid_price_ratio, 6),
                        "invalid_surface_area_ratio": round(invalid_surface_area_ratio, 6),
                        "last_seen": last_seen.isoformat() if last_seen is not None and not pd.isna(last_seen) else None,
                        **contract_support,
                        "doc_state": doc_state,
                    },
                )
            )

        summary_payload = SourceCapabilitySummary(
            generated_at=now.isoformat(),
            summary=summary,
            sources=sorted(reports, key=lambda item: (item.status, item.source_id)),
        )
        if persist:
            self._persist_audit(summary_payload)
        return summary_payload
