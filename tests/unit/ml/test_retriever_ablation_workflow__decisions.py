from src.ml.training.retriever_ablation import (
    build_decomposition_diagnostics,
    build_semantic_retrieval_decision,
)


def test_build_semantic_retrieval_decision__keep_when_mae_improves_without_coverage_drop():
    decision = build_semantic_retrieval_decision(
        geo_structure={
            "coverage_ratio": 0.90,
            "metrics": {"mae": 100_000.0, "mape": 18.0, "medae": 75_000.0},
        },
        semantic={
            "coverage_ratio": 0.89,
            "metrics": {"mae": 95_000.0, "mape": 17.1, "medae": 71_000.0},
        },
        min_mae_improvement=0.02,
        max_coverage_drop=0.05,
    )

    assert decision["decision"] == "keep"
    assert decision["status"] == "supported"
    assert decision["reasons"] == []


def test_build_semantic_retrieval_decision__simplify_when_improvement_is_below_threshold():
    decision = build_semantic_retrieval_decision(
        geo_structure={
            "coverage_ratio": 0.90,
            "metrics": {"mae": 100_000.0, "mape": 18.0, "medae": 75_000.0},
        },
        semantic={
            "coverage_ratio": 0.89,
            "metrics": {"mae": 99_500.0, "mape": 17.9, "medae": 74_500.0},
        },
        min_mae_improvement=0.02,
        max_coverage_drop=0.05,
    )

    assert decision["decision"] == "simplify"
    assert "semantic_mae_improvement_below_threshold" in decision["reasons"]


def test_build_decomposition_diagnostics__warns_on_land_structure_gap():
    diagnostics = build_decomposition_diagnostics(
        segment_metrics={
            "land": {"n": 32.0, "mae": 180_000.0},
            "structure": {"n": 240.0, "mae": 100_000.0},
        },
        min_segment_samples=20,
        mae_gap_threshold=0.25,
    )

    assert diagnostics["status"] == "warn_mae_gap"
    assert diagnostics["decision"] == "prioritize_decomposition_packet"
    assert "land_structure_mae_gap_exceeds_threshold" in diagnostics["reasons"]

