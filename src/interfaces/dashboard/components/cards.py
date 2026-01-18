from typing import List, Dict, Any, Optional
import re
from src.interfaces.dashboard.utils.formatting import (
    normalize_text, 
    ensure_sentence, 
    clean_label, 
    format_list, 
    humanize_token, 
    try_parse_json,
    truncate_text,
    append_unique,
    safe_num
)

def build_scorecard_items(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Builds a list of scorecard items (KPIs) for a property."""
    positives: List[Dict[str, Any]] = []
    negatives: List[Dict[str, Any]] = []

    def add_item(is_positive: bool, label: str, detail: str) -> None:
        bucket = positives if is_positive else negatives
        bucket.append(
            {"label": label, "detail": detail, "positive": is_positive}
        )

    value_delta_pct = safe_num(row.get("Value Delta %"), None)
    if value_delta_pct is not None:
        pct = value_delta_pct * 100
        if pct >= 3:
            add_item(True, "Value", f"Under fair value by {pct:.1f}%")
        elif pct <= -3:
            add_item(False, "Value", f"Over fair value by {abs(pct):.1f}%")

    yield_est = safe_num(row.get("Yield %"), None)
    market_yield = safe_num(row.get("Market Yield %"), None)
    if yield_est is not None:
        if market_yield is not None:
            spread = yield_est - market_yield
            if spread >= 0.5:
                add_item(True, "Yield", f"{yield_est:.2f}% (+{spread:.2f}pp vs market)")
            elif spread <= -0.5:
                add_item(False, "Yield", f"{yield_est:.2f}% ({spread:.2f}pp vs market)")
        elif yield_est >= 5.0:
            add_item(True, "Yield", f"{yield_est:.2f}% gross yield")
        elif yield_est <= 3.0:
            add_item(False, "Yield", f"{yield_est:.2f}% gross yield")

    price_to_rent = safe_num(row.get("Price-to-Rent (yrs)"), None)
    market_pr = safe_num(row.get("Market P/R (yrs)"), None)
    if price_to_rent is not None and market_pr is not None:
        gap = price_to_rent - market_pr
        if gap <= -2:
            add_item(True, "Price/Rent", f"{price_to_rent:.1f}y vs {market_pr:.1f}y market")
        elif gap >= 2:
            add_item(False, "Price/Rent", f"{price_to_rent:.1f}y vs {market_pr:.1f}y market")

    score = safe_num(row.get("Deal Score"), None)
    if score is not None:
        if score >= 0.7:
            add_item(True, "Deal score", f"{score:.2f} strong signal")
        elif score <= 0.4:
            add_item(False, "Deal score", f"{score:.2f} weak signal")

    momentum = safe_num(row.get("Momentum %"), None)
    if momentum is not None:
        if momentum >= 3:
            add_item(True, "Momentum", f"{momentum:+.1f}% momentum")
        elif momentum <= -3:
            add_item(False, "Momentum", f"{momentum:+.1f}% momentum")

    area_sentiment = safe_num(row.get("Area Sentiment"), None)
    if area_sentiment is not None:
        if area_sentiment >= 0.6:
            add_item(True, "Area sentiment", f"{area_sentiment:.2f}/1.00 positive")
        elif area_sentiment <= 0.4:
            add_item(False, "Area sentiment", f"{area_sentiment:.2f}/1.00 weak")

    liquidity = safe_num(row.get("Liquidity"), None)
    if liquidity is not None:
        if liquidity >= 0.6:
            add_item(True, "Liquidity", f"{liquidity:.2f}/1.00 healthy")
        elif liquidity <= 0.4:
            add_item(False, "Liquidity", f"{liquidity:.2f}/1.00 thin")

    uncertainty = safe_num(row.get("Uncertainty %"), None)
    if uncertainty is not None and uncertainty >= 0.2:
        add_item(False, "Model range", f"Uncertainty ±{uncertainty * 100:.0f}%")

    total_return = safe_num(row.get("Total Return 12m %"), None)
    if total_return is not None:
        if total_return >= 6:
            add_item(True, "Total return", f"{total_return:+.1f}% (12m)")
        elif total_return <= 0:
            add_item(False, "Total return", f"{total_return:+.1f}% (12m)")

    items = positives[:3] + negatives[:3]
    return items


def build_swot(row: Dict[str, Any], reasons: List[str], thesis: object) -> Dict[str, List[str]]:
    """Builds SWOT analysis dictionary."""
    strengths: List[str] = []
    weaknesses: List[str] = []
    opportunities: List[str] = []
    threats: List[str] = []

    for reason in reasons or []:
        append_unique(strengths, reason, limit=5)

    value_delta_pct = safe_num(row.get("Value Delta %"), None)
    if value_delta_pct is not None:
        pct = value_delta_pct * 100
        if pct >= 3:
            append_unique(strengths, f"Priced {pct:.1f}% below fair value")
        elif pct <= -3:
            append_unique(weaknesses, f"Priced {abs(pct):.1f}% above fair value")

    yield_est = safe_num(row.get("Yield %"), None)
    market_yield = safe_num(row.get("Market Yield %"), None)
    if yield_est is not None and market_yield is not None:
        spread = yield_est - market_yield
        if spread >= 0.5:
            append_unique(strengths, f"Yield {yield_est:.2f}% (+{spread:.2f}pp vs market)")
        elif spread <= -0.5:
            append_unique(weaknesses, f"Yield {yield_est:.2f}% ({spread:.2f}pp vs market)")

    price_to_rent = safe_num(row.get("Price-to-Rent (yrs)"), None)
    market_pr = safe_num(row.get("Market P/R (yrs)"), None)
    if price_to_rent is not None and market_pr is not None:
        gap = price_to_rent - market_pr
        if gap <= -2:
            append_unique(strengths, f"Price-to-rent {price_to_rent:.1f}y vs {market_pr:.1f}y market")
        elif gap >= 2:
            append_unique(weaknesses, f"Price-to-rent {price_to_rent:.1f}y vs {market_pr:.1f}y market")

    score = safe_num(row.get("Deal Score"), None)
    if score is not None:
        if score >= 0.7:
            append_unique(strengths, f"Strong deal score ({score:.2f})")
        elif score <= 0.4:
            append_unique(weaknesses, f"Weak deal score ({score:.2f})")

    momentum = safe_num(row.get("Momentum %"), None)
    if momentum is not None:
        if momentum >= 3:
            append_unique(strengths, f"Positive momentum ({momentum:+.1f}%)")
        elif momentum <= -3:
            append_unique(weaknesses, f"Negative momentum ({momentum:+.1f}%)")

    area_sentiment = safe_num(row.get("Area Sentiment"), None)
    if area_sentiment is not None:
        if area_sentiment >= 0.6:
            append_unique(strengths, f"Healthy area sentiment ({area_sentiment:.2f}/1.00)")
        elif area_sentiment <= 0.4:
            append_unique(weaknesses, f"Weak area sentiment ({area_sentiment:.2f}/1.00)")

    liquidity = safe_num(row.get("Liquidity"), None)
    if liquidity is not None:
        if liquidity >= 0.6:
            append_unique(strengths, f"Liquid market ({liquidity:.2f}/1.00)")
        elif liquidity <= 0.4:
            append_unique(weaknesses, f"Thin liquidity ({liquidity:.2f}/1.00)")

    total_return = safe_num(row.get("Total Return 12m %"), None)
    if total_return is not None and total_return >= 6:
        append_unique(opportunities, f"Total return {total_return:+.1f}% over 12m")
    price_return = safe_num(row.get("Price Return 12m %"), None)
    if price_return is not None and price_return >= 4:
        append_unique(opportunities, f"Projected price return {price_return:+.1f}% (12m)")

    catchup = safe_num(row.get("Catchup"), None)
    if catchup is not None and catchup >= 0.6:
        append_unique(opportunities, f"Catch-up signal ({catchup:.2f})")

    area_dev = safe_num(row.get("Area Development"), None)
    if area_dev is not None and area_dev >= 0.6:
        append_unique(opportunities, f"Area development signal ({area_dev:.2f})")

    thesis_text = truncate_text(thesis, 140)
    if thesis_text:
        append_unique(opportunities, thesis_text)

    uncertainty = safe_num(row.get("Uncertainty %"), None)
    if uncertainty is not None and uncertainty >= 0.2:
        append_unique(threats, f"High model uncertainty (±{uncertainty * 100:.0f}%)")

    if price_return is not None and price_return <= 0:
        append_unique(threats, f"Projected price return {price_return:+.1f}% (12m)")

    if total_return is not None and total_return <= 2:
        append_unique(threats, f"Low total return outlook ({total_return:+.1f}% 12m)")

    if liquidity is not None and liquidity <= 0.4:
        append_unique(threats, "Liquidity constraints could slow exits")

    if area_sentiment is not None and area_sentiment <= 0.4:
        append_unique(threats, "Area sentiment drags near-term demand")

    comps = row.get("Comps") or []
    if not comps:
        append_unique(threats, "Limited comps to validate pricing")

    return {
        "strengths": strengths[:5],
        "weaknesses": weaknesses[:5],
        "opportunities": opportunities[:5],
        "threats": threats[:5],
    }



