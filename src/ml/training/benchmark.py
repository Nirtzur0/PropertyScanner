"""
Benchmark fusion valuation behavior against RF/XGBoost baselines under time+geo splits.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import structlog
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, median_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from src.listings.services.listing_adapter import db_listing_to_canonical
from src.ml.training.policy import (
    ProductReadinessError,
    enforce_fusion_benchmark_policy,
    format_product_readiness_error,
)
from src.platform.db.base import resolve_db_url
from src.platform.domain.models import DBListing
from src.platform.settings import AppConfig
from src.platform.storage import StorageService
from src.platform.utils.config import load_app_config_safe
from src.platform.utils.time import utcnow
from src.valuation.services.valuation import ValuationService

logger = structlog.get_logger(__name__)

FEATURE_COLUMNS_NUMERIC = [
    "surface_area_sqm",
    "bedrooms",
    "bathrooms",
    "floor",
    "has_elevator",
    "lat",
    "lon",
    "text_sentiment",
    "image_sentiment",
    "obs_days",
]
FEATURE_COLUMNS_CATEGORICAL = [
    "property_type",
    "geo_value",
    "listing_type",
]


@dataclass(frozen=True)
class SplitFrames:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame


def _safe_float(value: Any, default: float = np.nan) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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


def load_training_frame(
    *,
    db_url: str,
    listing_type: str = "sale",
    label_source: str = "auto",
    geo_key: str = "city",
    min_price: float = 10_000.0,
    min_surface_area_sqm: float = 10.0,
) -> pd.DataFrame:
    storage = StorageService(db_url=db_url)
    query = storage.engine.connect()
    try:
        df = pd.read_sql(
            """
            SELECT
              id, price, sold_price, listing_type, property_type,
              bedrooms, bathrooms, surface_area_sqm, floor, has_elevator,
              lat, lon, city, geohash, text_sentiment, image_sentiment,
              listed_at, updated_at, sold_at
            FROM listings
            WHERE price > 0
            """,
            query,
        )
    finally:
        query.close()

    if df.empty:
        raise ValueError("benchmark_dataset_empty")

    df["listing_type"] = df["listing_type"].fillna("sale").astype(str).str.lower()
    if listing_type in {"sale", "rent"}:
        df = df[df["listing_type"] == listing_type].copy()
    df["property_type"] = (
        df["property_type"]
        .fillna("apartment")
        .astype(str)
        .str.lower()
        .str.split(".")
        .str[-1]
    )
    geo_col = "geohash" if geo_key == "geohash" else "city"
    df["geo_value"] = (
        df[geo_col]
        .fillna("unknown")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["target_price"] = df.apply(lambda row: _target_price(row, label_source), axis=1)
    df["obs_date"] = df.apply(lambda row: _obs_date(row, label_source), axis=1)
    df["obs_date"] = pd.to_datetime(df["obs_date"], errors="coerce", utc=True)
    df["obs_days"] = (df["obs_date"].astype("int64") // 10**9) / 86400.0

    df["has_elevator"] = df["has_elevator"].fillna(False).astype(float)
    for col in (
        "surface_area_sqm",
        "bedrooms",
        "bathrooms",
        "floor",
        "lat",
        "lon",
        "text_sentiment",
        "image_sentiment",
    ):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[
        (df["target_price"] > float(min_price))
        & (df["surface_area_sqm"] > float(min_surface_area_sqm))
        & df["obs_date"].notna()
    ].copy()

    if len(df) < 200:
        raise ValueError("benchmark_insufficient_rows")

    return df.reset_index(drop=True)


def time_geo_split(
    df: pd.DataFrame,
    *,
    val_split: float = 0.1,
    test_split: float = 0.2,
    geo_key: str = "geo_value",
    split_seed: int = 42,
) -> SplitFrames:
    if val_split < 0 or test_split < 0 or (val_split + test_split) >= 1:
        raise ValueError("invalid_split_ratio")
    if df.empty:
        raise ValueError("split_empty_frame")

    sorted_df = df.sort_values("obs_date").reset_index(drop=True)
    n_total = len(sorted_df)
    n_test = max(1, int(n_total * test_split))
    test_df = sorted_df.iloc[-n_test:].copy()
    remaining = sorted_df.iloc[:-n_test].copy()
    if remaining.empty:
        raise ValueError("split_insufficient_remaining")

    groups: Dict[str, List[int]] = {}
    for i, value in enumerate(remaining[geo_key].tolist()):
        groups.setdefault(str(value), []).append(i)

    rng = np.random.default_rng(split_seed)
    geo_values = list(groups.keys())
    rng.shuffle(geo_values)

    n_val_target = max(1, int(len(remaining) * val_split))
    val_positions: List[int] = []
    for key in geo_values:
        if len(val_positions) >= n_val_target:
            break
        val_positions.extend(groups[key])
    val_positions = sorted(set(val_positions))

    val_df = remaining.iloc[val_positions].copy()
    train_df = remaining.drop(remaining.index[val_positions]).copy()
    if train_df.empty:
        raise ValueError("split_empty_train")

    return SplitFrames(train=train_df, val=val_df, test=test_df)


def _build_pipeline(model: Any) -> Pipeline:
    preprocess = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                    ]
                ),
                FEATURE_COLUMNS_NUMERIC,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="constant", fill_value="unknown")),
                        (
                            "encoder",
                            OrdinalEncoder(
                                handle_unknown="use_encoded_value",
                                unknown_value=-1,
                            ),
                        ),
                    ]
                ),
                FEATURE_COLUMNS_CATEGORICAL,
            ),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocess),
            ("model", model),
        ]
    )


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.maximum(np.abs(y_true), 1.0)
    return float(np.mean(np.abs((y_true - y_pred) / denom)) * 100.0)


def compute_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> Dict[str, float]:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(y_true_arr, y_pred_arr)),
        "mape": _mape(y_true_arr, y_pred_arr),
        "medae": float(median_absolute_error(y_true_arr, y_pred_arr)),
    }


def train_and_score_tree_models(
    *,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    split_seed: int,
) -> Dict[str, Dict[str, Any]]:
    x_train = train_df[FEATURE_COLUMNS_NUMERIC + FEATURE_COLUMNS_CATEGORICAL]
    y_train = train_df["target_price"].astype(float).to_numpy()
    x_test = test_df[FEATURE_COLUMNS_NUMERIC + FEATURE_COLUMNS_CATEGORICAL]
    y_test = test_df["target_price"].astype(float).to_numpy()

    results: Dict[str, Dict[str, Any]] = {}

    rf_model = _build_pipeline(
        RandomForestRegressor(
            n_estimators=300,
            max_depth=20,
            min_samples_leaf=2,
            random_state=split_seed,
            n_jobs=-1,
        )
    )
    rf_model.fit(x_train, y_train)
    rf_pred = rf_model.predict(x_test)
    results["random_forest"] = {
        "status": "ok",
        "metrics": compute_metrics(y_test, rf_pred),
        "predictions": rf_pred.tolist(),
        "params": {
            "n_estimators": 300,
            "max_depth": 20,
            "min_samples_leaf": 2,
        },
    }

    try:
        from xgboost import XGBRegressor

        xgb_model = _build_pipeline(
            XGBRegressor(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.85,
                colsample_bytree=0.85,
                objective="reg:squarederror",
                reg_lambda=1.0,
                random_state=split_seed,
                n_jobs=4,
            )
        )
        xgb_model.fit(x_train, y_train)
        xgb_pred = xgb_model.predict(x_test)
        results["xgboost"] = {
            "status": "ok",
            "metrics": compute_metrics(y_test, xgb_pred),
            "predictions": xgb_pred.tolist(),
            "params": {
                "n_estimators": 500,
                "max_depth": 6,
                "learning_rate": 0.05,
                "subsample": 0.85,
                "colsample_bytree": 0.85,
            },
        }
    except Exception as exc:
        logger.warning("xgboost_unavailable", error=str(exc))
        results["xgboost"] = {
            "status": "unavailable",
            "error": str(exc),
            "metrics": None,
            "predictions": [],
            "params": {},
        }

    return results


def evaluate_fusion_on_subset(
    *,
    db_url: str,
    test_df: pd.DataFrame,
    max_eval_samples: int,
    app_config: AppConfig,
) -> Dict[str, Any]:
    storage = StorageService(db_url=db_url)
    valuation = ValuationService(
        storage=storage,
        config=app_config.valuation,
        app_config=app_config,
        db_path=str(app_config.pipeline.db_path),
    )

    eval_df = test_df.sort_values("obs_date").tail(max_eval_samples).copy()
    eval_ids = eval_df["id"].astype(str).tolist()
    target_by_id = {
        str(row["id"]): float(row["target_price"])
        for _, row in eval_df.iterrows()
    }

    session = storage.get_session()
    try:
        rows = (
            session.query(DBListing)
            .filter(DBListing.id.in_(eval_ids))
            .all()
        )
    finally:
        session.close()
    by_id = {str(row.id): row for row in rows}

    predictions: Dict[str, float] = {}
    errors: Dict[str, str] = {}
    model_used = Counter()
    for listing_id in eval_ids:
        db_item = by_id.get(listing_id)
        if not db_item:
            errors[listing_id] = "missing_db_listing"
            continue
        try:
            listing = db_listing_to_canonical(db_item)
            analysis = valuation.evaluate_deal(listing, comps=None)
            predictions[listing_id] = float(analysis.fair_value_estimate)
            if analysis.evidence and analysis.evidence.model_used:
                model_used[str(analysis.evidence.model_used)] += 1
            else:
                model_used["unknown"] += 1
        except Exception as exc:
            errors[listing_id] = str(exc)

    success_ids = [listing_id for listing_id in eval_ids if listing_id in predictions]
    y_true = [target_by_id[i] for i in success_ids]
    y_pred = [predictions[i] for i in success_ids]
    metrics = compute_metrics(y_true, y_pred) if success_ids else None

    return {
        "status": "ok" if success_ids else "failed",
        "n_attempted": len(eval_ids),
        "n_success": len(success_ids),
        "coverage_ratio": float(len(success_ids) / max(len(eval_ids), 1)),
        "metrics": metrics,
        "model_used_counts": dict(model_used),
        "errors": errors,
        "success_ids": success_ids,
        "predictions": predictions,
    }


def build_gate_result(
    *,
    tree_results: Dict[str, Dict[str, Any]],
    fusion_result: Dict[str, Any],
    min_test_rows: int,
    fusion_min_coverage: float,
    fusion_mae_ratio_threshold: float,
    fusion_mape_ratio_threshold: float,
    require_xgboost: bool,
) -> Dict[str, Any]:
    reasons: List[str] = []

    rf_metrics = tree_results.get("random_forest", {}).get("metrics")
    xgb_payload = tree_results.get("xgboost", {})
    xgb_metrics = xgb_payload.get("metrics")

    tree_candidates: List[Tuple[str, Dict[str, float]]] = []
    if rf_metrics:
        tree_candidates.append(("random_forest", rf_metrics))
    if xgb_payload.get("status") == "ok" and xgb_metrics:
        tree_candidates.append(("xgboost", xgb_metrics))
    elif require_xgboost:
        reasons.append("xgboost_unavailable")

    if not tree_candidates:
        reasons.append("no_tree_baseline_metrics")

    attempted = int(fusion_result.get("n_attempted", 0))
    coverage = float(fusion_result.get("coverage_ratio", 0.0))
    fusion_metrics = fusion_result.get("metrics")
    if attempted < min_test_rows:
        reasons.append("insufficient_test_rows")
    if coverage < fusion_min_coverage:
        reasons.append("fusion_coverage_below_threshold")
    if not fusion_metrics:
        reasons.append("fusion_metrics_missing")

    comparison = None
    best_tree_name = None
    best_tree_metrics = None
    if tree_candidates:
        best_tree_name, best_tree_metrics = min(
            tree_candidates, key=lambda item: float(item[1]["mae"])
        )
        if fusion_metrics:
            mae_ratio = float(fusion_metrics["mae"]) / max(float(best_tree_metrics["mae"]), 1e-9)
            mape_ratio = float(fusion_metrics["mape"]) / max(float(best_tree_metrics["mape"]), 1e-9)
            if mae_ratio > fusion_mae_ratio_threshold:
                reasons.append("fusion_mae_regression_vs_best_tree")
            if mape_ratio > fusion_mape_ratio_threshold:
                reasons.append("fusion_mape_regression_vs_best_tree")
            comparison = {
                "best_tree_model": best_tree_name,
                "best_tree_metrics": best_tree_metrics,
                "fusion_metrics": fusion_metrics,
                "mae_ratio": round(mae_ratio, 4),
                "mape_ratio": round(mape_ratio, 4),
            }

    return {
        "pass": len(reasons) == 0,
        "reasons": reasons,
        "thresholds": {
            "min_test_rows": int(min_test_rows),
            "fusion_min_coverage": float(fusion_min_coverage),
            "fusion_mae_ratio_threshold": float(fusion_mae_ratio_threshold),
            "fusion_mape_ratio_threshold": float(fusion_mape_ratio_threshold),
            "require_xgboost": bool(require_xgboost),
        },
        "comparison": comparison,
        "best_tree_model": best_tree_name,
    }


def write_markdown_summary(report: Dict[str, Any], path: str) -> None:
    tree = report["models"]["tree_baselines"]
    fusion = report["models"]["fusion_service"]
    gate = report["gate"]

    lines = [
        "# Fusion vs Tree Baseline Benchmark",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Split: `time+geo` (`geo_key={report['config']['geo_key']}`, `seed={report['config']['split_seed']}`)",
        f"- Dataset rows: train `{report['dataset']['train_rows']}`, val `{report['dataset']['val_rows']}`, test `{report['dataset']['test_rows']}`",
        "",
        "## Model Metrics",
        "",
        "| Model | Status | MAE | MAPE | MedAE |",
        "| --- | --- | --- | --- | --- |",
    ]

    for key in ("random_forest", "xgboost"):
        payload = tree[key]
        metrics = payload.get("metrics")
        if payload.get("status") == "ok" and metrics:
            lines.append(
                f"| {key} | ok | {metrics['mae']:.2f} | {metrics['mape']:.2f}% | {metrics['medae']:.2f} |"
            )
        else:
            lines.append(f"| {key} | {payload.get('status')} | n/a | n/a | n/a |")

    fusion_metrics = fusion.get("metrics")
    if fusion_metrics:
        lines.append(
            f"| fusion_service | {fusion.get('status')} | {fusion_metrics['mae']:.2f} | {fusion_metrics['mape']:.2f}% | {fusion_metrics['medae']:.2f} |"
        )
    else:
        lines.append(f"| fusion_service | {fusion.get('status')} | n/a | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Fusion Coverage",
            "",
            f"- Attempted: `{fusion.get('n_attempted', 0)}`",
            f"- Success: `{fusion.get('n_success', 0)}`",
            f"- Coverage ratio: `{fusion.get('coverage_ratio', 0.0):.3f}`",
            "",
            "## Gate Result",
            "",
            f"- Pass: `{gate['pass']}`",
            f"- Reasons: `{', '.join(gate['reasons']) if gate['reasons'] else 'none'}`",
        ]
    )

    comparison = gate.get("comparison")
    if comparison:
        lines.extend(
            [
                "",
                "## Fusion vs Best Tree",
                "",
                f"- Best tree: `{comparison['best_tree_model']}`",
                f"- MAE ratio (fusion/best tree): `{comparison['mae_ratio']}`",
                f"- MAPE ratio (fusion/best tree): `{comparison['mape_ratio']}`",
            ]
        )

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(
    *,
    db_url: str,
    output_json: str,
    output_md: str,
    listing_type: str,
    label_source: str,
    geo_key: str,
    val_split: float,
    test_split: float,
    split_seed: int,
    max_fusion_eval: int,
    min_test_rows: int,
    fusion_min_coverage: float,
    fusion_mae_ratio_threshold: float,
    fusion_mape_ratio_threshold: float,
    require_xgboost: bool,
    app_config: AppConfig,
    research_only: bool = False,
) -> Dict[str, Any]:
    enforce_fusion_benchmark_policy(
        db_url=db_url,
        listing_type=listing_type,
        label_source=label_source,
        research_only=research_only,
    )
    frame = load_training_frame(
        db_url=db_url,
        listing_type=listing_type,
        label_source=label_source,
        geo_key=geo_key,
    )
    split = time_geo_split(
        frame,
        val_split=val_split,
        test_split=test_split,
        geo_key="geo_value",
        split_seed=split_seed,
    )

    train_for_tree = pd.concat([split.train, split.val], axis=0).reset_index(drop=True)
    tree_results = train_and_score_tree_models(
        train_df=train_for_tree,
        test_df=split.test,
        split_seed=split_seed,
    )

    fusion = evaluate_fusion_on_subset(
        db_url=db_url,
        test_df=split.test,
        max_eval_samples=max_fusion_eval,
        app_config=app_config,
    )

    success_ids = set(fusion.get("success_ids", []))
    if success_ids:
        subset = split.test[split.test["id"].astype(str).isin(success_ids)].copy()
        y_subset = subset["target_price"].astype(float).to_numpy()
        for key in ("random_forest", "xgboost"):
            payload = tree_results.get(key, {})
            preds = payload.get("predictions", [])
            if payload.get("status") == "ok" and preds and len(preds) == len(split.test):
                pred_map = dict(zip(split.test["id"].astype(str).tolist(), preds))
                subset_pred = [pred_map[str(i)] for i in subset["id"].tolist()]
                payload["fusion_subset_metrics"] = compute_metrics(y_subset, subset_pred)

    gate = build_gate_result(
        tree_results=tree_results,
        fusion_result=fusion,
        min_test_rows=min_test_rows,
        fusion_min_coverage=fusion_min_coverage,
        fusion_mae_ratio_threshold=fusion_mae_ratio_threshold,
        fusion_mape_ratio_threshold=fusion_mape_ratio_threshold,
        require_xgboost=require_xgboost,
    )

    report = {
        "generated_at": utcnow().isoformat(),
        "config": {
            "listing_type": listing_type,
            "label_source": label_source,
            "geo_key": geo_key,
            "val_split": float(val_split),
            "test_split": float(test_split),
            "split_seed": int(split_seed),
            "max_fusion_eval": int(max_fusion_eval),
        },
        "dataset": {
            "total_rows": int(len(frame)),
            "train_rows": int(len(split.train)),
            "val_rows": int(len(split.val)),
            "test_rows": int(len(split.test)),
            "test_min_date": split.test["obs_date"].min().isoformat() if not split.test.empty else None,
            "test_max_date": split.test["obs_date"].max().isoformat() if not split.test.empty else None,
        },
        "models": {
            "tree_baselines": tree_results,
            "fusion_service": fusion,
        },
        "gate": gate,
    }

    output_json_path = Path(output_json)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_markdown_summary(report, output_md)
    logger.info(
        "benchmark_report_written",
        output_json=str(output_json_path),
        output_md=str(output_md),
        gate_pass=bool(gate["pass"]),
    )
    return report


def main(argv: Optional[Iterable[str]] = None) -> int:
    defaults = load_app_config_safe()
    parser = argparse.ArgumentParser(
        description="Benchmark fusion valuation behavior vs RF/XGBoost under time+geo splits."
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=str(resolve_db_url(db_url=defaults.pipeline.db_url, db_path=defaults.pipeline.db_path)),
        help="SQLAlchemy DB URL",
    )
    parser.add_argument("--listing-type", type=str, default="sale", choices=["sale", "rent", "all"])
    parser.add_argument("--label-source", type=str, default="auto", choices=["auto", "ask", "sold"])
    parser.add_argument("--geo-key", type=str, default="city", choices=["city", "geohash"])
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--test-split", type=float, default=0.2)
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--max-fusion-eval", type=int, default=80)
    parser.add_argument("--min-test-rows", type=int, default=50)
    parser.add_argument("--fusion-min-coverage", type=float, default=0.6)
    parser.add_argument("--fusion-mae-ratio-threshold", type=float, default=1.2)
    parser.add_argument("--fusion-mape-ratio-threshold", type=float, default=1.2)
    parser.add_argument(
        "--require-xgboost",
        action="store_true",
        default=True,
        help="Treat missing XGBoost as a gate failure.",
    )
    parser.add_argument(
        "--allow-missing-xgboost",
        action="store_false",
        dest="require_xgboost",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/implementation/reports/fusion_tree_benchmark.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/implementation/reports/fusion_tree_benchmark.md",
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit non-zero when benchmark gate fails.",
    )
    parser.add_argument(
        "--research-only",
        action="store_true",
        help="Deprecated compatibility flag. Benchmarking now gates on dataset readiness instead.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = run_benchmark(
            db_url=args.db_url,
            output_json=args.output_json,
            output_md=args.output_md,
            listing_type=args.listing_type,
            label_source=args.label_source,
            geo_key=args.geo_key,
            val_split=args.val_split,
            test_split=args.test_split,
            split_seed=args.split_seed,
            max_fusion_eval=args.max_fusion_eval,
            min_test_rows=args.min_test_rows,
            fusion_min_coverage=args.fusion_min_coverage,
            fusion_mae_ratio_threshold=args.fusion_mae_ratio_threshold,
            fusion_mape_ratio_threshold=args.fusion_mape_ratio_threshold,
            require_xgboost=args.require_xgboost,
            app_config=defaults,
            research_only=args.research_only,
        )
    except ProductReadinessError as exc:
        print(format_product_readiness_error(exc), file=sys.stderr)
        return 2
    if args.fail_on_gate and not report["gate"]["pass"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
