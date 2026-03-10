"""
Retriever ablation harness for geo/structure/semantic comp-selection decisions.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import structlog

from src.platform.db.base import resolve_db_url
from src.platform.domain.schema import CanonicalListing, GeoLocation
from src.platform.settings import AppConfig
from src.platform.storage import StorageService
from src.platform.utils.config import load_app_config_safe
from src.platform.utils.time import utcnow

logger = structlog.get_logger(__name__)

_ALLOWED_PROPERTY_TYPES = {"apartment", "house", "land", "commercial", "other"}


@dataclass(frozen=True)
class AblationMode:
    name: str
    use_semantic: bool
    require_structure: bool


GEO_ONLY = AblationMode(name="geo_only", use_semantic=False, require_structure=False)
GEO_STRUCTURE = AblationMode(name="geo_structure", use_semantic=False, require_structure=True)
GEO_STRUCTURE_SEMANTIC = AblationMode(
    name="geo_structure_semantic", use_semantic=True, require_structure=True
)


def _safe_float(value: Any, default: float = np.nan) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_property_type(value: Any) -> str:
    raw = str(value or "other").strip().lower()
    if "." in raw:
        raw = raw.split(".")[-1]
    if raw not in _ALLOWED_PROPERTY_TYPES:
        return "other"
    return raw


def _target_price(row: pd.Series, label_source: str) -> float:
    listing_type = str(row.get("listing_type") or "sale").strip().lower()
    ask_price = _safe_float(row.get("price"), default=np.nan)
    sold_price = _safe_float(row.get("sold_price"), default=np.nan)

    if listing_type == "rent":
        return ask_price
    if label_source == "sold":
        return sold_price
    if label_source == "ask":
        return ask_price
    if not np.isnan(sold_price) and sold_price > 0:
        return sold_price
    return ask_price


def _obs_date(row: pd.Series, label_source: str) -> Optional[pd.Timestamp]:
    sold_at = pd.to_datetime(row.get("sold_at"), errors="coerce", utc=True)
    listed_at = pd.to_datetime(row.get("listed_at"), errors="coerce", utc=True)
    updated_at = pd.to_datetime(row.get("updated_at"), errors="coerce", utc=True)

    if label_source == "sold" and pd.notna(sold_at):
        return sold_at
    if pd.notna(listed_at):
        return listed_at
    if pd.notna(updated_at):
        return updated_at
    if pd.notna(sold_at):
        return sold_at
    return None


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.maximum(np.abs(y_true), 1.0)
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)


def compute_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> Dict[str, float]:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    if len(y_true_arr) == 0:
        return {}
    abs_err = np.abs(y_true_arr - y_pred_arr)
    return {
        "mae": float(np.mean(abs_err)),
        "mape": _mape(y_true_arr, y_pred_arr),
        "medae": float(np.median(abs_err)),
    }


def build_semantic_retrieval_decision(
    *,
    geo_structure: Dict[str, Any],
    semantic: Dict[str, Any],
    min_mae_improvement: float,
    max_coverage_drop: float,
) -> Dict[str, Any]:
    reasons: List[str] = []
    base_metrics = geo_structure.get("metrics") or {}
    sem_metrics = semantic.get("metrics") or {}

    base_cov = float(geo_structure.get("coverage_ratio", 0.0))
    sem_cov = float(semantic.get("coverage_ratio", 0.0))
    coverage_drop = max(base_cov - sem_cov, 0.0)

    base_mae = float(base_metrics.get("mae", 0.0) or 0.0)
    sem_mae = float(sem_metrics.get("mae", 0.0) or 0.0)

    if not base_metrics or not sem_metrics or base_mae <= 0:
        return {
            "decision": "defer",
            "status": "insufficient_metrics",
            "reasons": ["missing_comparable_metrics"],
            "thresholds": {
                "min_mae_improvement": float(min_mae_improvement),
                "max_coverage_drop": float(max_coverage_drop),
            },
            "comparison": {},
        }

    mae_improvement = (base_mae - sem_mae) / base_mae
    if coverage_drop > max_coverage_drop:
        reasons.append("semantic_coverage_drop_exceeds_threshold")

    if mae_improvement >= min_mae_improvement and not reasons:
        decision = "keep"
        status = "supported"
    else:
        decision = "simplify"
        status = "supported"
        if mae_improvement < min_mae_improvement:
            reasons.append("semantic_mae_improvement_below_threshold")

    return {
        "decision": decision,
        "status": status,
        "reasons": reasons,
        "thresholds": {
            "min_mae_improvement": float(min_mae_improvement),
            "max_coverage_drop": float(max_coverage_drop),
        },
        "comparison": {
            "geo_structure_mae": round(base_mae, 4),
            "semantic_mae": round(sem_mae, 4),
            "mae_improvement_ratio": round(mae_improvement, 4),
            "geo_structure_coverage": round(base_cov, 4),
            "semantic_coverage": round(sem_cov, 4),
            "coverage_drop": round(coverage_drop, 4),
        },
    }


def build_decomposition_diagnostics(
    *,
    segment_metrics: Dict[str, Dict[str, float]],
    min_segment_samples: int,
    mae_gap_threshold: float,
) -> Dict[str, Any]:
    land = segment_metrics.get("land") or {}
    structure = segment_metrics.get("structure") or {}
    land_n = int(land.get("n", 0) or 0)
    structure_n = int(structure.get("n", 0) or 0)

    if land_n < min_segment_samples or structure_n < min_segment_samples:
        return {
            "status": "insufficient_segment_samples",
            "decision": "keep_gap_visible",
            "reasons": ["segment_sample_floor_not_met"],
            "thresholds": {
                "min_segment_samples": int(min_segment_samples),
                "mae_gap_threshold": float(mae_gap_threshold),
            },
            "comparison": {
                "land_n": land_n,
                "structure_n": structure_n,
            },
        }

    land_mae = float(land.get("mae", 0.0) or 0.0)
    structure_mae = float(structure.get("mae", 0.0) or 0.0)
    mae_gap_ratio = abs(land_mae - structure_mae) / max(structure_mae, 1.0)

    status = "warn_mae_gap" if mae_gap_ratio > mae_gap_threshold else "ok"
    decision = "prioritize_decomposition_packet" if status != "ok" else "monitor"

    reasons = []
    if status != "ok":
        reasons.append("land_structure_mae_gap_exceeds_threshold")

    return {
        "status": status,
        "decision": decision,
        "reasons": reasons,
        "thresholds": {
            "min_segment_samples": int(min_segment_samples),
            "mae_gap_threshold": float(mae_gap_threshold),
        },
        "comparison": {
            "land_n": land_n,
            "structure_n": structure_n,
            "land_mae": round(land_mae, 4),
            "structure_mae": round(structure_mae, 4),
            "mae_gap_ratio": round(mae_gap_ratio, 4),
        },
    }


def build_embedding_drift_proxy(
    *,
    retriever_metadata: Dict[str, Any],
    app_config: AppConfig,
    max_index_age_days: int,
) -> Dict[str, Any]:
    expected_model = str(app_config.valuation.retriever_model_name)
    expected_vlm_policy = str(app_config.valuation.retriever_vlm_policy)
    actual_model = str(retriever_metadata.get("model_name") or "")
    actual_vlm_policy = str(retriever_metadata.get("vlm_policy") or "")

    fingerprint = retriever_metadata.get("index_fingerprint") or {}
    mtime_raw = fingerprint.get("mtime")
    index_age_days: Optional[int] = None
    if isinstance(mtime_raw, (int, float)) and mtime_raw > 0:
        updated_at = datetime.fromtimestamp(float(mtime_raw), tz=timezone.utc)
        index_age_days = int((datetime.now(timezone.utc) - updated_at).days)

    reasons: List[str] = []
    if actual_model != expected_model:
        reasons.append("retriever_model_mismatch")
    if actual_vlm_policy != expected_vlm_policy:
        reasons.append("retriever_vlm_policy_mismatch")
    if index_age_days is not None and index_age_days > max_index_age_days:
        reasons.append("retriever_index_staleness_proxy")

    status = "warn" if reasons else "ok"
    return {
        "status": status,
        "reasons": reasons,
        "expected_model_name": expected_model,
        "actual_model_name": actual_model,
        "expected_vlm_policy": expected_vlm_policy,
        "actual_vlm_policy": actual_vlm_policy,
        "index_age_days": index_age_days,
        "max_index_age_days": int(max_index_age_days),
    }


def _haversine_distance_array(
    *,
    lat: float,
    lon: float,
    cand_lat: np.ndarray,
    cand_lon: np.ndarray,
) -> np.ndarray:
    r = 6371.0
    lat1 = np.radians(lat)
    lon1 = np.radians(lon)
    lat2 = np.radians(cand_lat)
    lon2 = np.radians(cand_lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return r * c


def _to_datetime(value: Any) -> Optional[datetime]:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def _weighted_prediction(prices: Sequence[float], weights: Sequence[float]) -> Optional[float]:
    if not prices:
        return None
    p = np.asarray(prices, dtype=float)
    w = np.asarray(weights, dtype=float)
    if np.any(w < 0):
        return None
    if np.sum(w) <= 0:
        return float(np.median(p))
    return float(np.average(p, weights=w))


def _bedroom_compatible(target_bedrooms: Optional[int], comp_bedrooms: Optional[int]) -> bool:
    if target_bedrooms is None:
        return True
    if comp_bedrooms is None:
        return False
    if target_bedrooms <= 1:
        return comp_bedrooms == target_bedrooms
    return abs(comp_bedrooms - target_bedrooms) <= 1


def _load_ablation_frame(
    *,
    db_url: str,
    listing_type: str,
    label_source: str,
    min_price: float,
    max_price: float,
    min_surface_area_sqm: float,
) -> pd.DataFrame:
    storage = StorageService(db_url=db_url)
    conn = storage.engine.connect()
    try:
        frame = pd.read_sql(
            """
            SELECT
              id, source_id, external_id, url, title, description, vlm_description,
              price, sold_price, listing_type, property_type, bedrooms, bathrooms,
              surface_area_sqm, lat, lon, city, geohash, listed_at, updated_at, sold_at
            FROM listings
            WHERE price > 0
            """,
            conn,
        )
    finally:
        conn.close()

    if frame.empty:
        raise ValueError("retriever_ablation_dataset_empty")

    frame["id"] = frame["id"].astype(str)
    frame["listing_type"] = frame["listing_type"].fillna("sale").astype(str).str.lower()
    if listing_type in {"sale", "rent"}:
        frame = frame[frame["listing_type"] == listing_type].copy()
    frame["property_type_norm"] = frame["property_type"].map(_normalize_property_type)
    frame["target_price"] = frame.apply(lambda row: _target_price(row, label_source), axis=1)
    frame["obs_date"] = frame.apply(lambda row: _obs_date(row, label_source), axis=1)
    frame["obs_date"] = pd.to_datetime(frame["obs_date"], errors="coerce", utc=True)
    frame["surface_area_sqm"] = pd.to_numeric(frame["surface_area_sqm"], errors="coerce")
    frame["bedrooms"] = pd.to_numeric(frame["bedrooms"], errors="coerce")
    frame["lat"] = pd.to_numeric(frame["lat"], errors="coerce")
    frame["lon"] = pd.to_numeric(frame["lon"], errors="coerce")
    frame["target_price"] = pd.to_numeric(frame["target_price"], errors="coerce")

    frame = frame[
        (frame["target_price"] > float(min_price))
        & (frame["target_price"] < float(max_price))
        & (frame["surface_area_sqm"] > float(min_surface_area_sqm))
        & frame["obs_date"].notna()
    ].copy()
    if len(frame) < 300:
        raise ValueError("retriever_ablation_insufficient_rows")
    return frame.sort_values("obs_date").reset_index(drop=True)


def _evaluate_mode(
    *,
    frame: pd.DataFrame,
    mode: AblationMode,
    retriever: Any,
    num_comps: int,
    max_radius_km: float,
    size_ratio_tolerance: float,
    target_indices: List[int],
) -> Dict[str, Any]:
    by_id = frame.set_index("id", drop=False)
    rows: List[Dict[str, Any]] = []
    min_ratio = 1.0 - size_ratio_tolerance
    max_ratio = 1.0 + size_ratio_tolerance

    for target_idx in target_indices:
        target = frame.iloc[target_idx]
        target_lat = _safe_float(target.get("lat"))
        target_lon = _safe_float(target.get("lon"))
        target_date = target.get("obs_date")
        if np.isnan(target_lat) or np.isnan(target_lon) or pd.isna(target_date):
            continue

        comp_entries: List[Tuple[str, float]] = []
        if mode.use_semantic:
            if retriever is None:
                continue
            target_listing = CanonicalListing(
                id=str(target["id"]),
                source_id=str(target.get("source_id") or "unknown"),
                external_id=str(target.get("external_id") or target["id"]),
                url=str(target.get("url") or "http://example.invalid"),
                title=str(target.get("title") or ""),
                description=target.get("description"),
                price=float(target["target_price"]),
                currency="EUR",
                listing_type=str(target.get("listing_type") or "sale"),
                property_type=str(target.get("property_type_norm") or "other"),
                bedrooms=int(target["bedrooms"]) if pd.notna(target["bedrooms"]) else None,
                bathrooms=None,
                surface_area_sqm=float(target["surface_area_sqm"]),
                floor=None,
                has_elevator=None,
                location=GeoLocation(
                    lat=float(target_lat),
                    lon=float(target_lon),
                    address_full=str(target.get("title") or ""),
                    city=str(target.get("city") or "unknown"),
                    country="unknown",
                ),
                image_urls=[],
                vlm_description=target.get("vlm_description"),
                text_sentiment=None,
                image_sentiment=None,
                listed_at=_to_datetime(target.get("listed_at")),
                updated_at=_to_datetime(target.get("updated_at")),
                status="active",
            )
            comps = retriever.retrieve_comps(
                target=target_listing,
                k=num_comps,
                max_radius_km=max_radius_km,
                exclude_self=True,
                strict_filters=True,
                listing_type=str(target.get("listing_type") or "sale"),
                max_listed_at=target_date.to_pydatetime(),
                exclude_duplicate_external=True,
            )
            for comp in comps:
                if comp.id not in by_id.index:
                    continue
                score = float(comp.similarity_score or 0.0)
                if score <= 0:
                    continue
                comp_entries.append((str(comp.id), score))
        else:
            candidate_mask = (
                (frame["id"] != target["id"])
                & (frame["listing_type"] == target["listing_type"])
                & frame["lat"].notna()
                & frame["lon"].notna()
                & (frame["obs_date"] <= target_date)
            )
            candidates = frame[candidate_mask].copy()
            if candidates.empty:
                continue
            distances = _haversine_distance_array(
                lat=float(target_lat),
                lon=float(target_lon),
                cand_lat=candidates["lat"].to_numpy(dtype=float),
                cand_lon=candidates["lon"].to_numpy(dtype=float),
            )
            candidates["_dist_km"] = distances
            candidates = candidates[candidates["_dist_km"] <= max_radius_km].copy()
            if candidates.empty:
                continue
            if mode.require_structure:
                target_type = str(target.get("property_type_norm") or "other")
                target_sqm = _safe_float(target.get("surface_area_sqm"), default=0.0)
                if target_sqm <= 0:
                    continue
                candidates = candidates[candidates["property_type_norm"] == target_type].copy()
                if candidates.empty:
                    continue
                sqm = candidates["surface_area_sqm"].to_numpy(dtype=float)
                ratio = sqm / target_sqm
                candidates = candidates[(ratio >= min_ratio) & (ratio <= max_ratio)].copy()
                if candidates.empty:
                    continue
                target_bedrooms = int(target["bedrooms"]) if pd.notna(target["bedrooms"]) else None
                candidates = candidates[
                    candidates["bedrooms"].apply(
                        lambda value: _bedroom_compatible(
                            target_bedrooms,
                            int(value) if pd.notna(value) else None,
                        )
                    )
                ].copy()
            candidates = candidates.sort_values("_dist_km").head(num_comps)
            for _, row in candidates.iterrows():
                dist = float(row["_dist_km"])
                comp_entries.append((str(row["id"]), 1.0 / (1.0 + dist)))

        if len(comp_entries) < num_comps:
            continue

        comp_prices: List[float] = []
        comp_weights: List[float] = []
        for comp_id, weight in comp_entries[:num_comps]:
            comp = by_id.loc[comp_id]
            if isinstance(comp, pd.DataFrame):
                comp = comp.iloc[0]
            comp_price = _safe_float(comp.get("target_price"), default=np.nan)
            if np.isnan(comp_price) or comp_price <= 0:
                continue
            comp_prices.append(comp_price)
            comp_weights.append(weight)

        if len(comp_prices) < num_comps:
            continue
        pred = _weighted_prediction(comp_prices, comp_weights)
        if pred is None:
            continue

        target_price = float(target["target_price"])
        segment = "land" if str(target.get("property_type_norm") or "") == "land" else "structure"
        rows.append(
            {
                "target_id": str(target["id"]),
                "target_price": target_price,
                "pred_price": pred,
                "segment": segment,
            }
        )

    y_true = [row["target_price"] for row in rows]
    y_pred = [row["pred_price"] for row in rows]
    segment_metrics: Dict[str, Dict[str, float]] = {}
    for segment in ("land", "structure"):
        seg_rows = [row for row in rows if row["segment"] == segment]
        seg_true = [row["target_price"] for row in seg_rows]
        seg_pred = [row["pred_price"] for row in seg_rows]
        metrics = compute_metrics(seg_true, seg_pred) if seg_rows else {}
        segment_metrics[segment] = {"n": float(len(seg_rows)), **metrics}

    return {
        "status": "ok",
        "n_attempted": int(len(target_indices)),
        "n_success": int(len(rows)),
        "coverage_ratio": float(len(rows) / max(len(target_indices), 1)),
        "metrics": compute_metrics(y_true, y_pred),
        "segment_metrics": segment_metrics,
    }


def _write_markdown_report(report: Dict[str, Any], output_path: str) -> None:
    modes = report["modes"]
    decisions = report["decisions"]

    lines = [
        "# Retriever Ablation Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Listing type: `{report['config']['listing_type']}`",
        f"- Label source: `{report['config']['label_source']}`",
        f"- Targets: `{report['config']['max_targets']}`",
        "",
        "## Mode Metrics",
        "",
        "| Mode | Status | Coverage | MAE | MAPE | MedAE |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for mode_name in ("geo_only", "geo_structure", "geo_structure_semantic"):
        payload = modes.get(mode_name, {})
        metrics = payload.get("metrics") or {}
        lines.append(
            "| {mode} | {status} | {cov:.3f} | {mae} | {mape} | {medae} |".format(
                mode=mode_name,
                status=payload.get("status", "unknown"),
                cov=float(payload.get("coverage_ratio", 0.0)),
                mae=f"{float(metrics.get('mae')):.2f}" if metrics.get("mae") is not None else "n/a",
                mape=f"{float(metrics.get('mape')):.2f}%" if metrics.get("mape") is not None else "n/a",
                medae=f"{float(metrics.get('medae')):.2f}" if metrics.get("medae") is not None else "n/a",
            )
        )

    sem = decisions["semantic_retrieval"]
    decomp = decisions["decomposition_diagnostics"]
    drift = decisions["embedding_drift_proxy"]
    lines.extend(
        [
            "",
            "## Decisions",
            "",
            f"- Semantic retrieval decision: `{sem['decision']}` ({sem['status']})",
            f"- Semantic reasons: `{', '.join(sem.get('reasons') or ['none'])}`",
            f"- Decomposition diagnostics status: `{decomp['status']}` ({decomp['decision']})",
            f"- Decomposition reasons: `{', '.join(decomp.get('reasons') or ['none'])}`",
            f"- Embedding drift proxy: `{drift['status']}`",
            f"- Drift reasons: `{', '.join(drift.get('reasons') or ['none'])}`",
            "",
            "## Thresholds",
            "",
            f"- Semantic min MAE improvement: `{sem['thresholds']['min_mae_improvement']}`",
            f"- Semantic max coverage drop: `{sem['thresholds']['max_coverage_drop']}`",
            f"- Decomposition min segment samples: `{decomp['thresholds']['min_segment_samples']}`",
            f"- Decomposition MAE gap threshold: `{decomp['thresholds']['mae_gap_threshold']}`",
        ]
    )
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_retriever_ablation(
    *,
    db_url: str,
    output_json: str,
    output_md: str,
    listing_type: str,
    label_source: str,
    max_targets: int,
    num_comps: int,
    max_radius_km: float,
    size_ratio_tolerance: float,
    min_mae_improvement: float,
    max_coverage_drop: float,
    min_segment_samples: int,
    mae_gap_threshold: float,
    max_index_age_days: int,
    require_semantic: bool,
    app_config: AppConfig,
) -> Dict[str, Any]:
    frame = _load_ablation_frame(
        db_url=db_url,
        listing_type=listing_type,
        label_source=label_source,
        min_price=10_000.0,
        max_price=15_000_000.0,
        min_surface_area_sqm=10.0,
    )
    target_indices = (
        frame[frame["lat"].notna() & frame["lon"].notna()]
        .sort_values("obs_date")
        .tail(max_targets)
        .index.tolist()
    )
    if not target_indices:
        raise ValueError("retriever_ablation_no_geo_targets")

    retriever = None
    semantic_status = "ok"
    try:
        from src.valuation.services.retrieval import build_retriever

        retriever = build_retriever(
            strict_model_match=True,
            app_config=app_config,
        )
    except Exception as exc:  # pragma: no cover - environment specific
        semantic_status = f"unavailable:{exc}"
        logger.warning("retriever_ablation_semantic_unavailable", error=str(exc))

    modes: Dict[str, Dict[str, Any]] = {}
    for mode in (GEO_ONLY, GEO_STRUCTURE, GEO_STRUCTURE_SEMANTIC):
        if mode.use_semantic and retriever is None:
            modes[mode.name] = {
                "status": semantic_status,
                "n_attempted": int(len(target_indices)),
                "n_success": 0,
                "coverage_ratio": 0.0,
                "metrics": {},
                "segment_metrics": {},
            }
            continue
        modes[mode.name] = _evaluate_mode(
            frame=frame,
            mode=mode,
            retriever=retriever,
            num_comps=num_comps,
            max_radius_km=max_radius_km,
            size_ratio_tolerance=size_ratio_tolerance,
            target_indices=target_indices,
        )

    semantic_decision = build_semantic_retrieval_decision(
        geo_structure=modes["geo_structure"],
        semantic=modes["geo_structure_semantic"],
        min_mae_improvement=min_mae_improvement,
        max_coverage_drop=max_coverage_drop,
    )
    if require_semantic and modes["geo_structure_semantic"]["status"] != "ok":
        semantic_decision["decision"] = "defer"
        semantic_decision["status"] = "semantic_unavailable"
        semantic_decision["reasons"] = ["semantic_mode_not_available"]

    decomposition = build_decomposition_diagnostics(
        segment_metrics=modes["geo_structure_semantic"].get("segment_metrics") or {},
        min_segment_samples=min_segment_samples,
        mae_gap_threshold=mae_gap_threshold,
    )

    retriever_metadata = retriever.get_metadata() if retriever is not None else {}
    embedding_drift = build_embedding_drift_proxy(
        retriever_metadata=retriever_metadata,
        app_config=app_config,
        max_index_age_days=max_index_age_days,
    )

    report = {
        "generated_at": utcnow().isoformat(),
        "config": {
            "listing_type": listing_type,
            "label_source": label_source,
            "max_targets": int(max_targets),
            "num_comps": int(num_comps),
            "max_radius_km": float(max_radius_km),
            "size_ratio_tolerance": float(size_ratio_tolerance),
        },
        "dataset": {
            "rows": int(len(frame)),
            "target_rows": int(len(target_indices)),
            "min_obs_date": frame["obs_date"].min().isoformat(),
            "max_obs_date": frame["obs_date"].max().isoformat(),
        },
        "modes": modes,
        "decisions": {
            "semantic_retrieval": semantic_decision,
            "decomposition_diagnostics": decomposition,
            "embedding_drift_proxy": embedding_drift,
        },
        "retriever_metadata": retriever_metadata,
    }

    output_json_path = Path(output_json)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown_report(report, output_md)

    logger.info(
        "retriever_ablation_report_written",
        output_json=str(output_json_path),
        output_md=output_md,
        semantic_decision=semantic_decision["decision"],
        decomposition_status=decomposition["status"],
    )
    return report


def main(argv: Optional[Iterable[str]] = None) -> int:
    defaults = load_app_config_safe()
    parser = argparse.ArgumentParser(
        description="Run retriever ablations: geo-only vs geo+structure vs geo+structure+semantic."
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=str(resolve_db_url(db_url=defaults.pipeline.db_url, db_path=defaults.pipeline.db_path)),
    )
    parser.add_argument("--listing-type", type=str, default="sale", choices=["sale", "rent", "all"])
    parser.add_argument("--label-source", type=str, default="auto", choices=["auto", "ask", "sold"])
    parser.add_argument("--max-targets", type=int, default=120)
    parser.add_argument("--num-comps", type=int, default=5)
    parser.add_argument("--max-radius-km", type=float, default=5.0)
    parser.add_argument("--size-ratio-tolerance", type=float, default=0.2)
    parser.add_argument("--semantic-min-mae-improvement", type=float, default=0.02)
    parser.add_argument("--semantic-max-coverage-drop", type=float, default=0.05)
    parser.add_argument("--min-segment-samples", type=int, default=20)
    parser.add_argument("--decomposition-mae-gap-threshold", type=float, default=0.25)
    parser.add_argument("--max-index-age-days", type=int, default=45)
    parser.add_argument(
        "--require-semantic",
        action="store_true",
        default=True,
        help="Treat semantic mode unavailability as a deferred decision signal.",
    )
    parser.add_argument(
        "--allow-missing-semantic",
        action="store_false",
        dest="require_semantic",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/implementation/reports/retriever_ablation_report.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/implementation/reports/retriever_ablation_report.md",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    run_retriever_ablation(
        db_url=args.db_url,
        output_json=args.output_json,
        output_md=args.output_md,
        listing_type=args.listing_type,
        label_source=args.label_source,
        max_targets=args.max_targets,
        num_comps=args.num_comps,
        max_radius_km=args.max_radius_km,
        size_ratio_tolerance=args.size_ratio_tolerance,
        min_mae_improvement=args.semantic_min_mae_improvement,
        max_coverage_drop=args.semantic_max_coverage_drop,
        min_segment_samples=args.min_segment_samples,
        mae_gap_threshold=args.decomposition_mae_gap_threshold,
        max_index_age_days=args.max_index_age_days,
        require_semantic=args.require_semantic,
        app_config=defaults,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
