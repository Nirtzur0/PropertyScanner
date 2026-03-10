from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import Any, Dict, List
from uuid import uuid4

import pandas as pd
import yaml
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.core.runtime import RuntimeConfig
from src.listings.source_ids import canonicalize_source_id, source_aliases
from src.platform.domain.models import DataQualityEvent, SourceContractRun
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def _norm_source_base(source_id: str) -> str:
    source_id = canonicalize_source_id(str(source_id).strip().lower())
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

    def _load_latest_contract_runs(self) -> Dict[str, Dict[str, Any]]:
        query = text(
            """
            SELECT source_id, status, metrics, created_at
            FROM source_contract_runs
            ORDER BY created_at DESC
            """
        )
        with self.storage.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        latest: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            canonical = canonicalize_source_id(str(row["source_id"] or ""))
            if not canonical or canonical in latest:
                continue
            metrics = row["metrics"] or {}
            if isinstance(metrics, str):
                try:
                    metrics = json.loads(metrics)
                except json.JSONDecodeError:
                    metrics = {"raw_metrics": metrics}
            latest[canonical] = {
                "status": str(row["status"] or ""),
                "metrics": dict(metrics or {}),
                "created_at": pd.to_datetime(row["created_at"], format="mixed", errors="coerce"),
            }
        return latest

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
        latest_runs = self._load_latest_contract_runs()
        query = text(
            """
            SELECT
                source_id,
                COUNT(*) AS row_count,
                SUM(CASE WHEN title IS NOT NULL AND title != '' THEN 1 ELSE 0 END) AS title_count,
                SUM(CASE WHEN price IS NOT NULL AND price > 0 THEN 1 ELSE 0 END) AS price_count,
                SUM(CASE WHEN surface_area_sqm IS NOT NULL THEN 1 ELSE 0 END) AS surface_area_count,
                SUM(CASE WHEN city IS NOT NULL AND city != '' AND country IS NOT NULL AND country != '' THEN 1 ELSE 0 END) AS location_count,
                SUM(CASE WHEN bedrooms IS NOT NULL THEN 1 ELSE 0 END) AS bedrooms_count,
                SUM(CASE WHEN bathrooms IS NOT NULL THEN 1 ELSE 0 END) AS bathrooms_count,
                SUM(CASE WHEN image_urls IS NOT NULL AND image_urls != '[]' THEN 1 ELSE 0 END) AS image_urls_count,
                SUM(CASE WHEN price IS NULL OR price < 10000 OR price > 15000000 THEN 1 ELSE 0 END) AS invalid_price_count,
                SUM(CASE WHEN surface_area_sqm IS NULL OR surface_area_sqm < 5 OR surface_area_sqm > 5000 THEN 1 ELSE 0 END) AS invalid_surface_area_count,
                MAX(COALESCE(fetched_at, updated_at, listed_at)) AS last_seen
            FROM listings
            GROUP BY source_id
            """
        )
        with self.storage.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        db_metrics: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            canonical = canonicalize_source_id(str(row["source_id"] or ""))
            if not canonical:
                continue
            target = db_metrics.setdefault(
                canonical,
                {
                    "row_count": 0,
                    "title_count": 0,
                    "price_count": 0,
                    "surface_area_count": 0,
                    "location_count": 0,
                    "bedrooms_count": 0,
                    "bathrooms_count": 0,
                    "image_urls_count": 0,
                    "invalid_price_count": 0,
                    "invalid_surface_area_count": 0,
                    "last_seen": None,
                    "aliases": set(),
                },
            )
            target["row_count"] += int(row.get("row_count") or 0)
            target["title_count"] += int(row.get("title_count") or 0)
            target["price_count"] += int(row.get("price_count") or 0)
            target["surface_area_count"] += int(row.get("surface_area_count") or 0)
            target["location_count"] += int(row.get("location_count") or 0)
            target["bedrooms_count"] += int(row.get("bedrooms_count") or 0)
            target["bathrooms_count"] += int(row.get("bathrooms_count") or 0)
            target["image_urls_count"] += int(row.get("image_urls_count") or 0)
            target["invalid_price_count"] += int(row.get("invalid_price_count") or 0)
            target["invalid_surface_area_count"] += int(row.get("invalid_surface_area_count") or 0)
            target["aliases"].add(str(row.get("source_id") or canonical))
            last_seen_raw = row.get("last_seen")
            last_seen = pd.to_datetime(last_seen_raw, format="mixed", errors="coerce") if last_seen_raw else None
            if last_seen is not None and not pd.isna(last_seen):
                current_last_seen = target.get("last_seen")
                if current_last_seen is None or pd.isna(current_last_seen) or last_seen > current_last_seen:
                    target["last_seen"] = last_seen

        reports: List[SourceCapabilityReport] = []
        summary = {"supported": 0, "experimental": 0, "degraded": 0, "blocked": 0}
        for entry in self.load_source_catalog():
            canonical_source_id = canonicalize_source_id(entry.source_id)
            metrics_row = db_metrics.get(canonical_source_id, {})
            row_count = int(metrics_row.get("row_count") or 0)
            title_count = int(metrics_row.get("title_count") or 0)
            price_count = int(metrics_row.get("price_count") or 0)
            surface_area_count = int(metrics_row.get("surface_area_count") or 0)
            location_count = int(metrics_row.get("location_count") or 0)
            bedrooms_count = int(metrics_row.get("bedrooms_count") or 0)
            bathrooms_count = int(metrics_row.get("bathrooms_count") or 0)
            image_urls_count = int(metrics_row.get("image_urls_count") or 0)
            invalid_price_count = int(metrics_row.get("invalid_price_count") or 0)
            invalid_surface_area_count = int(metrics_row.get("invalid_surface_area_count") or 0)
            last_seen_raw = metrics_row.get("last_seen")
            last_seen = pd.to_datetime(last_seen_raw, format="mixed", errors="coerce") if last_seen_raw else None
            contract_support = self._discover_contract_support(entry.source_id)
            doc_state = doc_status.get(_norm_source_base(entry.source_id), "unknown")
            latest_run = latest_runs.get(canonical_source_id)
            latest_run_status = str((latest_run or {}).get("status") or "")
            latest_run_created_at = (latest_run or {}).get("created_at")
            latest_run_metrics = dict((latest_run or {}).get("metrics") or {})

            invalid_price_ratio = _safe_ratio(invalid_price_count, row_count)
            invalid_surface_area_ratio = _safe_ratio(invalid_surface_area_count, row_count)

            reasons: List[str] = []
            status = "experimental"
            recent_run_available = (
                latest_run_created_at is not None
                and not pd.isna(latest_run_created_at)
                and latest_run_created_at.to_pydatetime() >= now - timedelta(days=thresholds.freshness_days)
            )
            if recent_run_available and latest_run_status == "blocked":
                status = "blocked"
                reasons.append("latest_run_blocked")
            elif recent_run_available and latest_run_status == "policy_blocked":
                status = "blocked"
                reasons.append("latest_run_policy_blocked")
            elif doc_state == "blocked":
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
                if recent_run_available and latest_run_status and latest_run_status not in {"supported"}:
                    reasons.append(f"latest_run_{latest_run_status}")

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
                        "canonical_source_id": canonical_source_id,
                        "source_aliases": sorted(source_aliases(canonical_source_id) | set(metrics_row.get("aliases") or set())),
                        "row_count": row_count,
                        "title_coverage_ratio": round(_safe_ratio(title_count, row_count), 6),
                        "price_coverage_ratio": round(_safe_ratio(price_count, row_count), 6),
                        "surface_area_coverage_ratio": round(_safe_ratio(surface_area_count, row_count), 6),
                        "location_coverage_ratio": round(_safe_ratio(location_count, row_count), 6),
                        "bedrooms_coverage_ratio": round(_safe_ratio(bedrooms_count, row_count), 6),
                        "bathrooms_coverage_ratio": round(_safe_ratio(bathrooms_count, row_count), 6),
                        "image_urls_coverage_ratio": round(_safe_ratio(image_urls_count, row_count), 6),
                        "invalid_price_count": invalid_price_count,
                        "invalid_surface_area_count": invalid_surface_area_count,
                        "invalid_price_ratio": round(invalid_price_ratio, 6),
                        "invalid_surface_area_ratio": round(invalid_surface_area_ratio, 6),
                        "last_seen": last_seen.isoformat() if last_seen is not None and not pd.isna(last_seen) else None,
                        "latest_run_status": latest_run_status or None,
                        "latest_run_created_at": (
                            latest_run_created_at.isoformat()
                            if latest_run_created_at is not None and not pd.isna(latest_run_created_at)
                            else None
                        ),
                        "latest_run_metrics": latest_run_metrics,
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
