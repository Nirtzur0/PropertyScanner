from datetime import datetime, timedelta, timezone

import pandas as pd

from src.ml.training.benchmark import build_gate_result, time_geo_split


def _frame(rows: int = 100) -> pd.DataFrame:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    items = []
    for i in range(rows):
        items.append(
            {
                "id": f"id-{i}",
                "obs_date": base + timedelta(days=i),
                "geo_value": "madrid" if i % 2 == 0 else "barcelona",
                "target_price": 200000.0 + (i * 250.0),
                "surface_area_sqm": 90.0 + (i % 5),
                "bedrooms": 2,
                "bathrooms": 1,
                "floor": 3,
                "has_elevator": 1.0,
                "lat": 40.4,
                "lon": -3.7,
                "text_sentiment": 0.1,
                "image_sentiment": 0.1,
                "obs_days": float(i),
                "property_type": "apartment",
                "listing_type": "sale",
            }
        )
    return pd.DataFrame(items)


def test_time_geo_split__keeps_latest_rows_in_test():
    df = _frame(rows=100)
    split = time_geo_split(df, val_split=0.1, test_split=0.2, split_seed=7)

    assert len(split.test) == 20
    assert split.test["obs_date"].min() > split.train["obs_date"].max()
    assert len(split.train) + len(split.val) + len(split.test) == 100
    assert not split.train.empty


def test_build_gate_result__fails_when_fusion_regresses():
    tree = {
        "random_forest": {"metrics": {"mae": 10000.0, "mape": 5.0, "medae": 9000.0}},
        "xgboost": {"status": "ok", "metrics": {"mae": 9000.0, "mape": 4.5, "medae": 8000.0}},
    }
    fusion = {
        "n_attempted": 80,
        "coverage_ratio": 0.9,
        "metrics": {"mae": 13000.0, "mape": 6.1, "medae": 10000.0},
    }
    gate = build_gate_result(
        tree_results=tree,
        fusion_result=fusion,
        min_test_rows=50,
        fusion_min_coverage=0.6,
        fusion_mae_ratio_threshold=1.2,
        fusion_mape_ratio_threshold=1.2,
        require_xgboost=True,
    )

    assert gate["pass"] is False
    assert "fusion_mae_regression_vs_best_tree" in gate["reasons"]


def test_build_gate_result__passes_when_within_thresholds():
    tree = {
        "random_forest": {"metrics": {"mae": 11000.0, "mape": 5.2, "medae": 9800.0}},
        "xgboost": {"status": "ok", "metrics": {"mae": 10000.0, "mape": 4.9, "medae": 9100.0}},
    }
    fusion = {
        "n_attempted": 80,
        "coverage_ratio": 0.8,
        "metrics": {"mae": 10800.0, "mape": 5.3, "medae": 9500.0},
    }
    gate = build_gate_result(
        tree_results=tree,
        fusion_result=fusion,
        min_test_rows=50,
        fusion_min_coverage=0.6,
        fusion_mae_ratio_threshold=1.2,
        fusion_mape_ratio_threshold=1.2,
        require_xgboost=True,
    )

    assert gate["pass"] is True
    assert gate["reasons"] == []
    assert gate["best_tree_model"] == "xgboost"


def test_build_gate_result__requires_xgboost_when_flag_enabled():
    tree = {
        "random_forest": {"metrics": {"mae": 11000.0, "mape": 5.2, "medae": 9800.0}},
        "xgboost": {"status": "unavailable", "metrics": None},
    }
    fusion = {
        "n_attempted": 80,
        "coverage_ratio": 0.8,
        "metrics": {"mae": 11200.0, "mape": 5.4, "medae": 9950.0},
    }
    gate = build_gate_result(
        tree_results=tree,
        fusion_result=fusion,
        min_test_rows=50,
        fusion_min_coverage=0.6,
        fusion_mae_ratio_threshold=1.2,
        fusion_mape_ratio_threshold=1.2,
        require_xgboost=True,
    )

    assert gate["pass"] is False
    assert "xgboost_unavailable" in gate["reasons"]


def test_build_gate_result__allows_missing_xgboost_when_flag_disabled():
    tree = {
        "random_forest": {"metrics": {"mae": 11000.0, "mape": 5.2, "medae": 9800.0}},
        "xgboost": {"status": "unavailable", "metrics": None},
    }
    fusion = {
        "n_attempted": 80,
        "coverage_ratio": 0.8,
        "metrics": {"mae": 11200.0, "mape": 5.4, "medae": 9950.0},
    }
    gate = build_gate_result(
        tree_results=tree,
        fusion_result=fusion,
        min_test_rows=50,
        fusion_min_coverage=0.6,
        fusion_mae_ratio_threshold=1.2,
        fusion_mape_ratio_threshold=1.2,
        require_xgboost=False,
    )

    assert gate["pass"] is True
    assert "xgboost_unavailable" not in gate["reasons"]
    assert gate["best_tree_model"] == "random_forest"
