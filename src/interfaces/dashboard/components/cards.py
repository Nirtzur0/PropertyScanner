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


def format_vlm_notes(value: object) -> str:
    """Formats VLM notes from JSON or text."""
    parsed = try_parse_json(value)
    if parsed is None:
        return normalize_text(value)
    if isinstance(parsed, str):
        return normalize_text(parsed)
    if not isinstance(parsed, dict):
        return normalize_text(value)

    parts: List[str] = []
    summary = normalize_text(parsed.get("summary") or "")
    if summary:
        parts.append(ensure_sentence(summary))

    condition = clean_label(parsed.get("condition"))
    quality = clean_label(parsed.get("quality"))
    luxury = clean_label(parsed.get("luxury_vs_fixer"))
    if condition and quality:
        parts.append(f"Looks {condition} with {quality} finishes.")
    elif condition:
        parts.append(f"Looks {condition}.")
    elif quality:
        parts.append(f"Finish quality appears {quality}.")

    if luxury and luxury not in {"standard"}:
        parts.append(f"Overall feel: {luxury}.")

    details = []
    layout = clean_label(parsed.get("layout"))
    lighting = clean_label(parsed.get("lighting"))
    view_type = clean_label(parsed.get("view_type"))
    staging = clean_label(parsed.get("staging"))
    if layout:
        details.append(f"layout {layout}")
    if lighting:
        details.append(f"lighting {lighting}")
    if view_type and view_type != "none":
        details.append(f"view {view_type}")
    if staging:
        details.append(f"staging {staging}")
    if details:
        parts.append("Also notes " + ", ".join(details) + ".")

    rooms = format_list(parsed.get("rooms", []), max_items=6)
    if rooms:
        parts.append(f"Rooms spotted: {', '.join(rooms)}.")

    drivers = format_list(parsed.get("value_drivers", []), max_items=4)
    features = format_list(parsed.get("features", []), max_items=4)
    if drivers:
        parts.append(f"Highlights: {', '.join(drivers)}.")
    elif features:
        parts.append(f"Features: {', '.join(features)}.")

    red_flags = format_list(parsed.get("red_flags", []), max_items=3)
    if red_flags:
        parts.append(f"Watchouts: {', '.join(red_flags)}.")

    return " ".join([p for p in parts if p]).strip()


def format_description_from_analysis(data: Dict[str, Any]) -> str:
    """Formats listing description from structured analysis data."""
    parts: List[str] = []

    financial = data.get("financial_analysis") or {}
    if isinstance(financial, dict):
        summary = normalize_text(financial.get("summary") or "")
        if summary:
            parts.append(ensure_sentence(summary))

        positives = format_list(financial.get("positive_drivers", []), max_items=4)
        negatives = format_list(financial.get("negative_drivers", []), max_items=4)
        capex = format_list(financial.get("capex_risks", []), max_items=3)
        deal_breakers = format_list(financial.get("deal_breakers", []), max_items=3)

        if positives:
            parts.append(f"Upside: {', '.join(positives)}.")

        risk_items = []
        for items in (negatives, capex, deal_breakers):
            for item in items:
                if item not in risk_items:
                    risk_items.append(item)
        if risk_items:
            parts.append(f"Risks: {', '.join(risk_items[:6])}.")

    condition = data.get("condition_assessment") or {}
    if isinstance(condition, dict):
        condition_bits = []
        overall = clean_label(condition.get("overall_condition"))
        finish = clean_label(condition.get("finish_quality"))
        scope = clean_label(condition.get("renovation_scope"))
        luxury = clean_label(condition.get("luxury_vs_fixer"))
        if overall:
            condition_bits.append(overall)
        if finish:
            condition_bits.append(f"{finish} finishes")
        if scope:
            condition_bits.append(f"renovation scope {scope}")
        if condition_bits:
            parts.append("Condition: " + ", ".join(condition_bits) + ".")
        if luxury and luxury not in {"standard"}:
            parts.append(f"Overall feel: {luxury}.")

    facts = data.get("facts") or {}
    if isinstance(facts, dict):
        feature_map = {
            "has_elevator": "elevator",
            "has_pool": "pool",
            "has_garage": "garage",
            "has_parking": "parking",
            "has_terrace": "terrace",
            "has_balcony": "balcony",
            "has_garden": "garden",
            "has_storage_room": "storage room",
            "has_air_conditioning": "air conditioning",
            "has_heating": "heating",
            "has_doorman": "doorman",
            "has_security_system": "security system",
            "has_accessibility": "accessibility features",
            "is_furnished": "furnished",
            "is_new_build": "new build",
            "is_renovated": "renovated",
            "has_tourist_license": "tourist license",
        }
        risk_map = {
            "renovation_needed": "renovation needed",
            "is_occupied": "occupied",
            "has_tenant": "tenant in place",
            "has_squatters": "squatters reported",
            "has_vpo_restriction": "vpo restriction",
        }
        features = [label for key, label in feature_map.items() if facts.get(key) is True]
        flags = [label for key, label in risk_map.items() if facts.get(key) is True]

        if features:
            parts.append(f"Features mentioned: {', '.join(features[:7])}.")
        if flags:
            parts.append(f"Flags: {', '.join(flags[:6])}.")

        floor = facts.get("floor")
        unit_position = clean_label(facts.get("unit_position"))
        orientation = clean_label(facts.get("orientation"))
        natural_light = clean_label(facts.get("natural_light"))
        position_bits = []
        if floor is not None:
            position_bits.append(f"floor {floor}")
        if unit_position:
            position_bits.append(unit_position)
        if orientation:
            position_bits.append(f"{orientation} orientation")
        if natural_light:
            position_bits.append(f"light {natural_light}")
        if position_bits:
            parts.append("Position: " + ", ".join(position_bits) + ".")

    extraction = data.get("extraction") or {}
    if isinstance(extraction, dict):
        prop_type = clean_label(extraction.get("property_type"))
        neighborhood = normalize_text(extraction.get("neighborhood") or "")
        district = normalize_text(extraction.get("city_or_district") or "")
        if prop_type or neighborhood or district:
            pieces = []
            if prop_type:
                pieces.append(prop_type)
            if neighborhood:
                pieces.append(neighborhood)
            if district and district not in pieces:
                pieces.append(district)
            if pieces:
                parts.append("Context: " + ", ".join(pieces) + ".")

    return " ".join([p for p in parts if p]).strip()

def format_generic_json_description(data: dict) -> str:
    """Formats a generic JSON description."""
    parts: List[str] = []
    used_keys = set()
    
    for key in ("summary", "description", "overview", "text", "details"):
        text = normalize_text(data.get(key) or "")
        if text:
            parts.append(ensure_sentence(text))
            used_keys.add(key)
            break
            
    list_groups = [
        ("Highlights", ["highlights", "features", "amenities"]),
        ("Rooms", ["rooms"]),
        ("Pros", ["positive_drivers", "positives", "value_drivers"]),
        ("Cons", ["negative_drivers", "negatives", "red_flags"]),
    ]
    for label, keys in list_groups:
        items = []
        used_key = None
        for key in keys:
            items = format_list(data.get(key), max_items=5)
            if items:
                used_key = key
                break
        if items:
            parts.append(f"{label}: {', '.join(items)}.")
            if used_key:
                used_keys.add(used_key)
                
    scalar_count = 0
    for key, value in data.items():
        if key in used_keys:
            continue
        if isinstance(value, (str, int, float)):
             text = normalize_text(value)
             if not text:
                 continue
             if text.lower() in {"unknown", "none", "null"}:
                 continue
             parts.append(f"{humanize_token(key).capitalize()}: {text}.")
             scalar_count += 1
        if scalar_count >= 3:
            break
            
    return " ".join([p for p in parts if p]).strip()

def format_listing_description(value: object) -> str:
    """Master function to format listing descriptions from various sources."""
    parsed = try_parse_json(value)
    if parsed is None:
        return normalize_text(value)
    if isinstance(parsed, list):
        items = format_list(parsed, max_items=10)
        return ", ".join(items) if items else ""
    if not isinstance(parsed, dict):
        return normalize_text(value)

    if any(key in parsed for key in ("financial_analysis", "facts", "condition_assessment", "extraction")):
        formatted = format_description_from_analysis(parsed)
        if formatted:
            return formatted

    formatted = format_generic_json_description(parsed)
    return formatted or normalize_text(value)
