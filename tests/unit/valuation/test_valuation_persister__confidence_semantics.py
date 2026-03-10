import pytest

from src.platform.domain.models import DBListing
from src.platform.domain.schema import (
    CompEvidence,
    DealAnalysis,
    EvidencePack,
    ValuationProjection,
)
from src.valuation.services.valuation_persister import ValuationPersister


def _seed_listing(db_session, listing_id: str) -> None:
    db_session.add(
        DBListing(
            id=listing_id,
            source_id="test",
            external_id=f"ext-{listing_id}",
            url=f"https://example.com/{listing_id}",
            title="Seed Listing",
            price=300000.0,
        )
    )
    db_session.commit()


def _build_analysis(
    *,
    listing_id: str,
    calibration_status: str,
    uncertainty_pct: float,
    volatility: float,
    projection_score: float,
    comp_count: int,
    index_disagreement: bool = False,
) -> DealAnalysis:
    comps = [
        CompEvidence(
            id=f"comp-{i}",
            observed_month="2024-06",
            raw_price=280000.0 + (i * 1000.0),
            adj_factor=1.01,
            adj_price=282800.0 + (i * 1000.0),
            attention_weight=1.0 / max(comp_count, 1),
        )
        for i in range(comp_count)
    ]
    evidence = EvidencePack(
        model_used="fusion",
        anchor_price=300000.0,
        anchor_std=18000.0,
        top_comps=comps,
        calibration_status=calibration_status,
        index_disagreement=index_disagreement,
    )
    projection = ValuationProjection(
        metric="price",
        months_future=12,
        years_future=1.0,
        predicted_value=320000.0,
        confidence_interval_low=300000.0,
        confidence_interval_high=340000.0,
        confidence_score=projection_score,
        scenario_name="baseline",
    )
    return DealAnalysis(
        listing_id=listing_id,
        fair_value_estimate=315000.0,
        fair_value_uncertainty_pct=uncertainty_pct,
        investment_thesis="test thesis",
        projections=[projection],
        market_signals={"volatility": volatility},
        evidence=evidence,
    )


def test_save_valuation__persists_confidence_components(db_session):
    listing_id = "listing-high-confidence"
    _seed_listing(db_session, listing_id)

    analysis = _build_analysis(
        listing_id=listing_id,
        calibration_status="calibrated",
        uncertainty_pct=0.08,
        volatility=0.05,
        projection_score=0.82,
        comp_count=8,
    )

    valuation = ValuationPersister(db_session).save_valuation(listing_id, analysis)

    assert 0.0 < valuation.confidence_score <= 1.0
    assert valuation.confidence_score > 0.70

    components = valuation.evidence.get("confidence_components")
    assert components is not None
    assert components["calibration_status"] == "calibrated"
    assert components["comp_count"] == 8
    assert components["uncertainty_pct"] == pytest.approx(0.08, abs=1e-6)


def test_save_valuation__confidence_drops_for_weaker_signals(db_session):
    high_listing_id = "listing-confidence-high"
    low_listing_id = "listing-confidence-low"
    _seed_listing(db_session, high_listing_id)
    _seed_listing(db_session, low_listing_id)

    high_quality = _build_analysis(
        listing_id=high_listing_id,
        calibration_status="calibrated",
        uncertainty_pct=0.06,
        volatility=0.05,
        projection_score=0.85,
        comp_count=10,
    )
    weak_quality = _build_analysis(
        listing_id=low_listing_id,
        calibration_status="uncalibrated",
        uncertainty_pct=0.32,
        volatility=0.45,
        projection_score=0.35,
        comp_count=1,
        index_disagreement=True,
    )

    high_valuation = ValuationPersister(db_session).save_valuation(high_listing_id, high_quality)
    weak_valuation = ValuationPersister(db_session).save_valuation(low_listing_id, weak_quality)

    assert weak_valuation.confidence_score < high_valuation.confidence_score
    assert weak_valuation.confidence_score <= 0.55
    assert weak_valuation.evidence["confidence_components"]["index_disagreement_penalty"] == pytest.approx(0.05, abs=1e-6)
