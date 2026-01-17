from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

VIEW_OPTIONS = ["Atlas", "Deal Flow", "Signal Lab", "Investment Memo"]
DEFAULT_PRICE_RANGE = (120000, 1200000)
SCOUT_PROFILE_SORT = {
    "Balanced": ("Total Return 12m %", False),
    "Yield": ("Total Return 12m %", False),
    "Value": ("Total Return 12m %", False),
    "Momentum": ("Total Return 12m %", False),
}
SCOUT_PROFILE_REASON_ORDER = {
    "Balanced": ["return", "value", "yield", "momentum", "area", "score"],
    "Yield": ["return", "yield", "value", "momentum", "area", "score"],
    "Value": ["return", "value", "yield", "momentum", "area", "score"],
    "Momentum": ["return", "momentum", "area", "yield", "value", "score"],
}


def _format_ts(value):
    if not value:
        return "unknown"
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return "unknown"
    # Ensure input is timezone-aware UTC
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.tz_localize("UTC")
    else:
        dt = dt.tz_convert("UTC")

    now = pd.Timestamp.utcnow()
    delta = now - dt
    days = max(delta.days, 0)
    label = dt.strftime("%Y-%m-%d")
    if days <= 0:
        return f"{label} (today)"
    return f"{label} ({days}d ago)"


def _safe_num(value, default: float | None = 0.0) -> float | None:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_label(value, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except Exception:
        pass
    text = str(value).strip()
    return text if text else fallback


def _format_location(city, country) -> str:
    city_label = _safe_label(city, "")
    country_label = _safe_label(country, "")
    if city_label and country_label:
        return f"{city_label}, {country_label}"
    return city_label or country_label or "Unknown location"


def _safe_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _humanize_reason(reason: str) -> str:
    if not reason:
        return ""
    mapping = {
        "needs_harvest": "new listings needed",
        "needs_market_data": "market data stale",
        "needs_index": "search index stale",
        "needs_training": "model refresh needed",
        "needs_refresh": "signals stale",
        "status_unavailable": "status unavailable",
        "pipeline_status_failed": "status check failed",
    }
    return mapping.get(reason, reason.replace("_", " ").strip())


def _resolve_profile_sort(profile: str) -> tuple[str, bool]:
    sort_key, ascending = SCOUT_PROFILE_SORT.get(profile, SCOUT_PROFILE_SORT["Balanced"])
    return sort_key, ascending


def _build_deal_reasons(row, profile: str) -> list[str]:
    reasons = {}
    total_return = _safe_num(row.get("Total Return 12m %"), None)
    if total_return is not None:
        reasons["return"] = f"Expected return {total_return:+.1f}% (12m)"
    value_delta_pct = _safe_num(row.get("Value Delta %"), None)
    if value_delta_pct is not None:
        reasons["value"] = f"Priced {value_delta_pct * 100:+.1f}% vs fair value"

    yield_est = _safe_num(row.get("Yield %"), None)
    market_yield = _safe_num(row.get("Market Yield %"), None)
    if yield_est is not None:
        if market_yield is not None:
            delta = yield_est - market_yield
            reasons["yield"] = f"Yield {yield_est:.2f}% ({delta:+.2f} vs market)"
        else:
            reasons["yield"] = f"Yield {yield_est:.2f}%"

    momentum = _safe_num(row.get("Momentum %"), None)
    if momentum is not None:
        reasons["momentum"] = f"Momentum {momentum:+.1f}%"

    area = _safe_num(row.get("Area Sentiment"), None)
    if area is not None:
        reasons["area"] = f"Area signal {area:.2f}/1.00"

    score = _safe_num(row.get("Deal Score"), None)
    if score is not None:
        reasons["score"] = f"Deal score {score:.2f}"

    order = SCOUT_PROFILE_REASON_ORDER.get(profile, SCOUT_PROFILE_REASON_ORDER["Balanced"])
    ranked = [reasons[key] for key in order if key in reasons]
    return ranked[:3]


def _format_deal_reasons(row, profile: str) -> str:
    return " • ".join(_build_deal_reasons(row, profile))


def _build_intel_summary(row, profile: str) -> str:
    focus_intro = {
        "Balanced": "Picked for total return.",
        "Yield": "Picked for total return with an income tilt.",
        "Value": "Picked for total return with a value tilt.",
        "Momentum": "Picked for total return with a momentum tilt.",
    }
    intro = focus_intro.get(profile, "Picked for strong signals.")

    pieces = {}
    total_return = _safe_num(row.get("Total Return 12m %"), None)
    if total_return is not None:
        pieces["return"] = f"expected return {total_return:+.1f}% over 12m"
    value_delta_pct = _safe_num(row.get("Value Delta %"), None)
    if value_delta_pct is not None:
        if abs(value_delta_pct) < 0.02:
            pieces["value"] = "priced near fair value"
        else:
            pieces["value"] = f"priced {value_delta_pct * 100:+.1f}% vs fair value"

    yield_est = _safe_num(row.get("Yield %"), None)
    market_yield = _safe_num(row.get("Market Yield %"), None)
    if yield_est is not None and market_yield is not None:
        spread = yield_est - market_yield
        pieces["yield"] = f"yield {yield_est:.2f}% vs market {market_yield:.2f}% ({spread:+.2f}pp)"
    elif yield_est is not None:
        pieces["yield"] = f"yield {yield_est:.2f}%"

    momentum = _safe_num(row.get("Momentum %"), None)
    if momentum is not None:
        pieces["momentum"] = f"momentum {momentum:+.1f}%"

    area_sentiment = _safe_num(row.get("Area Sentiment"), None)
    area_development = _safe_num(row.get("Area Development"), None)
    if area_sentiment is not None and area_development is not None:
        pieces["area"] = f"area signals {area_sentiment:.2f}/{area_development:.2f}"

    income_weight = _safe_num(row.get("Income Weight"), None)
    if income_weight is not None and income_weight > 0:
        pieces["income"] = f"income blend {income_weight * 100:.0f}%"

    area_adjustment = _safe_num(row.get("Area Adjustment"), None)
    if area_adjustment is not None and abs(area_adjustment) > 0:
        pieces["adjustment"] = f"area adjustment {area_adjustment * 100:+.1f}%"

    uncertainty = _safe_num(row.get("Uncertainty %"), None)
    if uncertainty is not None:
        pieces["uncertainty"] = f"model range ±{uncertainty * 100:.0f}%"

    evidence = row.get("Evidence") or {}
    if isinstance(evidence, dict):
        calibration = evidence.get("calibration_status")
        if calibration == "calibrated":
            pieces["calibration"] = "calibrated intervals"

    order = SCOUT_PROFILE_REASON_ORDER.get(profile, SCOUT_PROFILE_REASON_ORDER["Balanced"])
    ordered_keys = order + ["income", "adjustment", "uncertainty", "calibration"]
    details = [pieces[key] for key in ordered_keys if key in pieces]
    if not details:
        return intro

    summary = "; ".join(details[:3])
    return f"{intro} {summary}."


def _format_intel_summary(row, profile: str) -> str:
    return _build_intel_summary(row, profile)


def _select_scout_picks(df: pd.DataFrame, profile: str, max_picks: int = 4) -> list:
    if df.empty:
        return []
    seen = set()
    picks = []

    def _add_pick(label: str, sort_col: str, ascending: bool) -> None:
        if sort_col not in df.columns:
            return
        ranked = df.sort_values(by=sort_col, ascending=ascending)
        for _, row in ranked.iterrows():
            listing_id = row.get("ID")
            if listing_id in seen:
                continue
            seen.add(listing_id)
            picks.append({"label": label, "row": row})
            break

    focus_map = {
        "Balanced": ("Return Leader", "Total Return 12m %", False),
        "Yield": ("Return Leader", "Total Return 12m %", False),
        "Value": ("Return Leader", "Total Return 12m %", False),
        "Momentum": ("Return Leader", "Total Return 12m %", False),
    }
    focus_label, focus_col, focus_asc = focus_map.get(profile, focus_map["Balanced"])
    _add_pick(focus_label, focus_col, focus_asc)
    _add_pick("Value Gap", "Value Delta %", True)
    _add_pick("Yield Leader", "Yield %", False)
    _add_pick("Momentum Leader", "Momentum %", False)
    _add_pick("Score Leader", "Deal Score", False)

    return picks[:max_picks]


def _widen_price_range(price_range: tuple[int, int], ceiling: int = 2000000) -> tuple[int, int]:
    low, high = price_range
    widened_low = max(0, int(low * 0.85))
    widened_high = min(ceiling, int(high * 1.15))
    if widened_low >= widened_high:
        widened_low = max(0, low - 50000)
        widened_high = min(ceiling, high + 50000)
    return widened_low, widened_high


def _action_label(action: dict) -> str:
    kind = action.get("type")
    if kind == "preflight":
        return "Refresh signals"
    if kind == "reset_filters":
        return "Reset lens"
    if kind == "set_view":
        view = action.get("view") or "view"
        return f"Open {view}"
    if kind == "select_listing":
        title = action.get("title") or "listing"
        return f"Open memo: {title}"
    if kind == "set_filters":
        payload = action.get("payload", {})
        parts = []
        if "selected_country" in payload:
            parts.append(f"Country = {payload['selected_country']}")
        if "selected_city" in payload:
            parts.append(f"City = {payload['selected_city']}")
        if "selected_types" in payload:
            types = payload["selected_types"] or []
            if types:
                parts.append(f"Types = {', '.join(types)}")
        if "scout_profile" in payload:
            parts.append(f"Focus = {payload['scout_profile']}")
        if "sort_by" in payload:
            parts.append(f"Sort by {payload['sort_by']}")
        if "sort_order" in payload:
            parts.append(f"Order {payload['sort_order']}")
        if parts:
            return "Adjust filters: " + ", ".join(parts)
        return "Adjust filters"
    return "Run action"


def _resolve_autonomy(actions, autonomy_mode: str, allow_refresh: bool):
    auto_actions = []
    pending = []
    safe_actions = {"set_filters", "set_view", "select_listing"}
    for action in actions:
        kind = action.get("type")
        if autonomy_mode == "Autopilot":
            if kind == "preflight" and not allow_refresh:
                pending.append(action)
            else:
                auto_actions.append(action)
        elif autonomy_mode == "Assisted":
            if kind in safe_actions:
                auto_actions.append(action)
            else:
                pending.append(action)
        else:
            pending.append(action)
    return auto_actions, pending


def _parse_prompt(prompt, available_countries, available_cities, available_types):
    actions = []
    responses = []
    if not prompt:
        return (
            actions,
            "Tell me what you're looking for: yield leaders, value gaps, momentum, a city, or the map.",
        )

    lower = prompt.lower().strip()

    if "refresh" in lower or "preflight" in lower:
        actions.append({"type": "preflight"})
        responses.append("Got it. Refreshing the signals now.")

    if "reset" in lower or "clear filters" in lower:
        actions.append({"type": "reset_filters"})
        responses.append("Resetting to the default lens.")

    for country in available_countries:
        if country.lower() in lower:
            actions.append({"type": "set_filters", "payload": {"selected_country": country}})
            responses.append(f"Focusing on {country}.")
            break

    for city in available_cities:
        if city.lower() in lower:
            actions.append({"type": "set_filters", "payload": {"selected_city": city}})
            responses.append(f"Zooming in on {city}.")
            break

    for prop_type in available_types:
        if prop_type.lower() in lower:
            actions.append({"type": "set_filters", "payload": {"selected_types": [prop_type]}})
            responses.append(f"Filtering to {prop_type} only.")
            break

    profile = None
    if "yield" in lower:
        profile = "Yield"
    elif "value gap" in lower or "undervalued" in lower:
        profile = "Value"
    elif "momentum" in lower:
        profile = "Momentum"

    if profile:
        actions.append({"type": "set_filters", "payload": {"scout_profile": profile}})
        responses.append(f"Prioritizing {profile.lower()} signals.")

    if "deal flow" in lower or "table" in lower:
        actions.append({"type": "set_view", "view": "Deal Flow"})
        responses.append("Opening the deal flow.")
    if "signal" in lower or "lab" in lower:
        actions.append({"type": "set_view", "view": "Signal Lab"})
        responses.append("Opening Signal Lab.")
    if "map" in lower or "atlas" in lower:
        actions.append({"type": "set_view", "view": "Atlas"})
        responses.append("Opening the map.")
    if "memo" in lower or "analysis" in lower:
        actions.append({"type": "set_view", "view": "Investment Memo"})
        responses.append("Opening the memo.")

    response = (
        " ".join(responses)
        if responses
        else "Try: 'yield leaders', 'value gap', 'momentum', a city name, or 'open the map'."
    )
    return actions, response


def _compose_orchestrator_prompt(filtered_df, pipeline_needs_refresh, pipeline_error):
    if pipeline_error:
        return "I can't read pipeline status right now. Want me to refresh or keep scouting on cached signals?"
    if pipeline_needs_refresh:
        return "Signals are a bit old. Want me to refresh, or keep scouting with what we have?"
    if filtered_df.empty:
        return "No matches under this lens. Want me to widen the budget, broaden location, or switch focus?"
    return (
        f"I found {len(filtered_df)} opportunities under this lens. Want yield leaders, undervalued deals, momentum, or the map?"
    )


def _build_suggestions(
    filtered_df: pd.DataFrame,
    pipeline_needs_refresh: bool,
    available_cities: Iterable[str],
    available_countries: Iterable[str],
    price_range: tuple[int, int],
) -> list[dict]:
    suggestions = []
    if pipeline_needs_refresh:
        suggestions.append(
            {
                "title": "Refresh signals",
                "body": "Pull the latest listings, market data, indices, and valuations.",
                "cta": "Run refresh",
                "action": {"type": "preflight"},
                "log": "Refreshing the signals.",
            }
        )

    if filtered_df.empty:
        widened_range = _widen_price_range(price_range)
        suggestions.extend(
            [
                {
                    "title": "Widen the budget",
                    "body": "Open up the range to surface more options.",
                    "cta": "Expand range",
                    "action": {"type": "set_filters", "payload": {"price_range": widened_range}},
                    "log": "Expanding the budget range.",
                },
                {
                    "title": "Broaden location",
                    "body": "Clear city and country locks to see more matches.",
                    "cta": "Show more places",
                    "action": {"type": "set_filters", "payload": {"selected_city": "All", "selected_country": "All"}},
                    "log": "Broadening location filters.",
                },
                {
                    "title": "Reset lens",
                    "body": "Return to the default scout profile.",
                    "cta": "Reset lens",
                    "action": {"type": "reset_filters"},
                    "log": "Reset to the default lens.",
                },
            ]
        )
        return suggestions

    top_city = (
        filtered_df["City"].dropna().value_counts().index[0]
        if "City" in filtered_df.columns and not filtered_df["City"].dropna().empty
        else None
    )
    top_pick_title = filtered_df.iloc[0]["Title"] if not filtered_df.empty else None

    suggestions.extend(
        [
            {
                "title": "Chase yield",
                "body": "Prioritize income leaders inside the total-return lens.",
                "cta": "Show yield picks",
                "action": {"type": "set_filters", "payload": {"scout_profile": "Yield"}},
                "log": "Tilting toward income leaders.",
            },
            {
                "title": "Spot mispricing",
                "body": "Surface value gaps while keeping total return in view.",
                "cta": "Find value gaps",
                "action": {"type": "set_filters", "payload": {"scout_profile": "Value"}},
                "log": "Tilting toward value gaps.",
            },
            {
                "title": "Ride momentum",
                "body": "Lean into momentum while preserving total return.",
                "cta": "Show momentum",
                "action": {"type": "set_filters", "payload": {"scout_profile": "Momentum"}},
                "log": "Tilting toward momentum.",
            },
            {
                "title": "Map the shortlist",
                "body": "See where the strongest deals cluster.",
                "cta": "Open map",
                "action": {"type": "set_view", "view": "Atlas"},
                "log": "Opening the map.",
            },
        ]
    )

    if top_city:
        suggestions.append(
            {
                "title": f"Zoom into {top_city}",
                "body": "Filter to the city with the most matches.",
                "cta": "Zoom in",
                "action": {"type": "set_filters", "payload": {"selected_city": top_city}},
                "log": f"Filtering to {top_city}.",
            }
        )
    if top_pick_title:
        suggestions.append(
            {
                "title": "Open the top memo",
                "body": "Jump to the strongest listing.",
                "cta": "Open memo",
                "action": {"type": "select_listing", "title": top_pick_title},
                "log": "Opening the top memo.",
            }
        )

    return suggestions
