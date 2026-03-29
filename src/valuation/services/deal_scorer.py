"""
Deal scoring — computes a 0-1 deal score from valuation, yield, and market signals.

Extracted from :class:`ValuationService` to keep scoring logic isolated and testable.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from src.platform.domain.schema import CanonicalListing, EvidencePack


def compute_deal_score(
    listing: CanonicalListing,
    fair_value: float,
    uncertainty: float,
    evidence: EvidencePack,
    market_signals: Dict[str, float],
    rental_yield: float,
) -> Tuple[float, List[str]]:
    """Return ``(score, flags)`` where score is in [0, 1]."""
    flags: List[str] = []

    if not listing.price or listing.price <= 0:
        raise ValueError("invalid_listing_price")
    if rental_yield is None or rental_yield <= 0:
        raise ValueError("missing_rental_yield")

    market_yield = market_signals.get("market_yield")
    momentum = market_signals.get("momentum")
    liquidity = market_signals.get("liquidity")
    catchup = market_signals.get("catchup")
    area_sentiment = market_signals.get("area_sentiment")
    area_development = market_signals.get("area_development")
    area_confidence = market_signals.get("area_confidence")

    if market_yield is None or market_yield <= 0:
        raise ValueError("missing_market_yield")
    if momentum is None or liquidity is None or catchup is None:
        raise ValueError("missing_market_signals")

    diff_pct = (fair_value - listing.price) / listing.price
    yield_spread = (rental_yield - market_yield) / market_yield

    value_component = float(np.tanh(diff_pct / 0.15))
    yield_component = float(np.tanh(yield_spread / 0.03))
    momentum_component = float(np.tanh(momentum / 0.05))
    liquidity_component = float((liquidity - 0.5) / 0.5)
    catchup_component = float((catchup - 0.5) / 0.5)

    if area_sentiment is not None and area_development is not None:
        sent_component = (float(area_sentiment) - 0.5) / 0.5
        dev_component = (float(area_development) - 0.5) / 0.5
        area_component = float(0.5 * (sent_component + dev_component))
        if area_confidence is not None:
            area_component = float(area_component * max(0.0, min(1.0, float(area_confidence))))
    else:
        area_component = 0.0

    raw_score = (
        0.32 * value_component
        + 0.23 * yield_component
        + 0.18 * momentum_component
        + 0.09 * liquidity_component
        + 0.08 * catchup_component
        + 0.10 * area_component
    )

    conviction = max(0.0, 1.0 - (uncertainty / 0.35))
    score = (0.5 + 0.5 * raw_score) * conviction
    score = max(0.0, min(1.0, score))

    # --- flags ---
    if uncertainty > 0.25:
        flags.append("high_uncertainty")
    if diff_pct > 0.15:
        flags.append("undervalued")
    if diff_pct > 0.25:
        flags.append("deep_value")
    if diff_pct < -0.15:
        flags.append("overpriced")
    if yield_spread > 0.01:
        flags.append("yield_advantage")
    if yield_spread < -0.01:
        flags.append("yield_disadvantage")
    if momentum > 0.03:
        flags.append("strong_momentum")
    if momentum < -0.03:
        flags.append("negative_momentum")
    if liquidity < 0.3:
        flags.append("low_liquidity")
    if area_sentiment is not None:
        if area_sentiment > 0.65:
            flags.append("positive_area_sentiment")
        if area_sentiment < 0.35:
            flags.append("negative_area_sentiment")
    if area_development is not None and area_development > 0.65:
        flags.append("strong_development")
    if evidence.calibration_status != "calibrated":
        flags.append("uncalibrated")

    return score, flags
