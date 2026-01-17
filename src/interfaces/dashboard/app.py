import sys
import os
import html
import json
import random
import re

# Add project root to path (robustly, for when running from various dirs)
# src/interfaces/dashboard/app.py -> ../.. -> project_root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Prevent Mac OMP segfaults (Critical for PyDeck/Torch on Mac)
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.express as px

from src.interfaces.api.pipeline import PipelineAPI
from src.interfaces.dashboard.scout_logic import (
    DEFAULT_PRICE_RANGE,
    VIEW_OPTIONS,
    _action_label,
    _build_deal_reasons,
    _build_suggestions,
    _compose_orchestrator_prompt,
    _format_deal_reasons,
    _format_intel_summary,
    _format_location,
    _format_ts,
    _humanize_reason,
    _parse_prompt,
    _resolve_autonomy,
    _resolve_profile_sort,
    _safe_list,
    _safe_num,
    _select_scout_picks,
)
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.listings.services.image_selection import ImageSelector
from src.platform.utils.config import load_app_config_safe
from src.platform.pipeline.state import PipelineStateService
from src.platform.domain.models import DBListing
from src.platform.domain.schema import DealAnalysis, ValuationProjection

# Page Config
st.set_page_config(page_title="Property Scanner | The Scout", layout="wide", page_icon="🦅")


# Custom CSS
def load_css():
    with open(os.path.join(os.path.dirname(__file__), "assets/style.css")) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css()


@st.cache_resource
def get_services():
    api = PipelineAPI()
    app_config = load_app_config_safe()
    selector = ImageSelector(config=app_config.image_selector)
    return api.storage, api.valuation, api.retriever, selector


storage, valuation, retriever, image_selector = get_services()


@st.cache_data(ttl=600)
def load_filter_options():
    session = storage.get_session()
    try:
        rows = session.query(DBListing.country, DBListing.city).distinct().all()
        cities = sorted({city for _, city in rows if city})
        countries = sorted({country for country, _ in rows if country})
        cities_by_country = {}
        for country, city in rows:
            if not country or not city:
                continue
            cities_by_country.setdefault(country, set()).add(city)
        cities_by_country = {country: sorted(list(cities)) for country, cities in cities_by_country.items()}
        types = [t[0] for t in session.query(DBListing.property_type).distinct().all() if t[0]]
        types = sorted(set(types))
    finally:
        session.close()
    return cities, types, countries, cities_by_country


@st.cache_data(ttl=900)
def _rank_images(image_urls: list[str], max_images: int = 6) -> list[str]:
    if not image_urls:
        return []
    selection = image_selector.select(image_urls, max_images=max_images)
    if selection and selection.selected:
        return [item.url for item in selection.selected]
    return list(image_urls)[:max_images]


@st.cache_data(ttl=900)
def _rank_images_sample(image_urls: list[str], sample_size: int = 5) -> list[str]:
    if not image_urls:
        return []
    urls = [str(url) for url in image_urls if url]
    if not urls:
        return []
    sample_size = max(1, min(sample_size, len(urls)))
    sampled = random.sample(urls, sample_size)
    ranked_subset = _rank_images(sampled, max_images=sample_size)
    ranked_set = set(ranked_subset)
    remainder = [url for url in urls if url not in ranked_set]
    return ranked_subset + remainder


def _format_budget_range(min_value: float, max_value: float) -> str:
    def _shorten(value: float) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}m"
        return f"{value / 1_000:.0f}k"

    return f"€{_shorten(min_value)}–€{_shorten(max_value)}"


def _build_lens_chips(
    selected_country: str,
    selected_city: str,
    selected_types: list[str],
    min_price: float,
    max_price: float,
    default_range: tuple[int, int],
    available_types: list[str],
) -> list[str]:
    chips: list[str] = []
    if selected_city and selected_city != "All":
        chips.append(selected_city)
    elif selected_country and selected_country != "All":
        chips.append(selected_country)

    if selected_types and len(selected_types) < len(available_types):
        if len(selected_types) <= 2:
            chips.append(", ".join(selected_types))
        else:
            chips.append(f"{len(selected_types)} types")

    if (min_price, max_price) != default_range:
        chips.append(_format_budget_range(min_price, max_price))

    if not chips:
        chips.append("All markets")
    return chips


def _resolve_plotly_selection(selection, data: pd.DataFrame, id_col: str = "ID") -> pd.DataFrame:
    if selection is None or data.empty:
        return data.iloc[0:0]
    selection_data = getattr(selection, "selection", None)
    if not isinstance(selection_data, dict):
        return data.iloc[0:0]
    points = selection_data.get("points") or []
    if not points:
        return data.iloc[0:0]
    selected_ids = []
    for point in points:
        custom = point.get("customdata") if isinstance(point, dict) else None
        if isinstance(custom, (list, tuple)) and custom:
            selected_ids.append(str(custom[0]))
    if not selected_ids:
        return data.iloc[0:0]
    return data[data[id_col].astype(str).isin(selected_ids)]


def _normalize_column(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    min_val = values.min()
    max_val = values.max()
    if pd.isna(min_val) or pd.isna(max_val) or max_val == min_val:
        return pd.Series([0.5] * len(series), index=series.index)
    return (values - min_val) / (max_val - min_val)


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).replace("\x00", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _humanize_token(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _clean_label(value: object) -> str:
    text = _humanize_token(value)
    if not text:
        return ""
    if text in {"unknown", "none", "n/a", "null"}:
        return ""
    return text


def _format_list(value: object, max_items: int = 4) -> list[str]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    results: list[str] = []
    for item in items:
        label = _clean_label(item)
        if not label:
            continue
        if label in results:
            continue
        results.append(label)
        if len(results) >= max_items:
            break
    return results


def _ensure_sentence(text: str) -> str:
    text = _normalize_text(text)
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text


def _try_parse_json(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*", "", text).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            snippet = match.group(1)
            try:
                return json.loads(snippet)
            except Exception:
                return None
    return None


def _format_vlm_notes(value: object) -> str:
    parsed = _try_parse_json(value)
    if parsed is None:
        return _normalize_text(value)
    if isinstance(parsed, str):
        return _normalize_text(parsed)
    if not isinstance(parsed, dict):
        return _normalize_text(value)

    parts: list[str] = []
    summary = _normalize_text(parsed.get("summary") or "")
    if summary:
        parts.append(_ensure_sentence(summary))

    condition = _clean_label(parsed.get("condition"))
    quality = _clean_label(parsed.get("quality"))
    luxury = _clean_label(parsed.get("luxury_vs_fixer"))
    if condition and quality:
        parts.append(f"Looks {condition} with {quality} finishes.")
    elif condition:
        parts.append(f"Looks {condition}.")
    elif quality:
        parts.append(f"Finish quality appears {quality}.")

    if luxury and luxury not in {"standard"}:
        parts.append(f"Overall feel: {luxury}.")

    details = []
    layout = _clean_label(parsed.get("layout"))
    lighting = _clean_label(parsed.get("lighting"))
    view_type = _clean_label(parsed.get("view_type"))
    staging = _clean_label(parsed.get("staging"))
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

    rooms = _format_list(parsed.get("rooms", []), max_items=6)
    if rooms:
        parts.append(f"Rooms spotted: {', '.join(rooms)}.")

    drivers = _format_list(parsed.get("value_drivers", []), max_items=4)
    features = _format_list(parsed.get("features", []), max_items=4)
    if drivers:
        parts.append(f"Highlights: {', '.join(drivers)}.")
    elif features:
        parts.append(f"Features: {', '.join(features)}.")

    red_flags = _format_list(parsed.get("red_flags", []), max_items=3)
    if red_flags:
        parts.append(f"Watchouts: {', '.join(red_flags)}.")

    return " ".join([p for p in parts if p]).strip()


def _format_description_from_analysis(data: dict) -> str:
    parts: list[str] = []

    financial = data.get("financial_analysis") or {}
    if isinstance(financial, dict):
        summary = _normalize_text(financial.get("summary") or "")
        if summary:
            parts.append(_ensure_sentence(summary))

        positives = _format_list(financial.get("positive_drivers", []), max_items=4)
        negatives = _format_list(financial.get("negative_drivers", []), max_items=4)
        capex = _format_list(financial.get("capex_risks", []), max_items=3)
        deal_breakers = _format_list(financial.get("deal_breakers", []), max_items=3)

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
        overall = _clean_label(condition.get("overall_condition"))
        finish = _clean_label(condition.get("finish_quality"))
        scope = _clean_label(condition.get("renovation_scope"))
        luxury = _clean_label(condition.get("luxury_vs_fixer"))
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
        unit_position = _clean_label(facts.get("unit_position"))
        orientation = _clean_label(facts.get("orientation"))
        natural_light = _clean_label(facts.get("natural_light"))
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
        prop_type = _clean_label(extraction.get("property_type"))
        neighborhood = _normalize_text(extraction.get("neighborhood") or "")
        district = _normalize_text(extraction.get("city_or_district") or "")
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


def _format_generic_json_description(data: dict) -> str:
    parts: list[str] = []
    used_keys = set()

    for key in ("summary", "description", "overview", "text", "details"):
        text = _normalize_text(data.get(key) or "")
        if text:
            parts.append(_ensure_sentence(text))
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
            items = _format_list(data.get(key), max_items=5)
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
            text = _normalize_text(value)
            if not text:
                continue
            if text.lower() in {"unknown", "none", "null"}:
                continue
            parts.append(f"{_humanize_token(key).capitalize()}: {text}.")
            scalar_count += 1
        if scalar_count >= 3:
            break

    return " ".join([p for p in parts if p]).strip()


def _format_listing_description(value: object) -> str:
    parsed = _try_parse_json(value)
    if parsed is None:
        return _normalize_text(value)
    if isinstance(parsed, list):
        items = _format_list(parsed, max_items=10)
        return ", ".join(items) if items else ""
    if not isinstance(parsed, dict):
        return _normalize_text(value)

    if any(key in parsed for key in ("financial_analysis", "facts", "condition_assessment", "extraction")):
        formatted = _format_description_from_analysis(parsed)
        if formatted:
            return formatted

    formatted = _format_generic_json_description(parsed)
    return formatted or _normalize_text(value)


def _truncate_text(value: object, limit: int = 140) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    if len(text) <= limit:
        return text
    cutoff = max(0, limit - 3)
    return text[:cutoff].rstrip() + "..."


def _escape_html(value: object) -> str:
    return html.escape(_normalize_text(value))


def _append_unique(items: list[str], text: object, limit: int = 5) -> None:
    if len(items) >= limit:
        return
    cleaned = _normalize_text(text)
    if not cleaned:
        return
    if cleaned in items:
        return
    items.append(cleaned)


def _build_scorecard_items(row) -> list[dict]:
    positives: list[dict] = []
    negatives: list[dict] = []

    def add_item(is_positive: bool, label: str, detail: str) -> None:
        bucket = positives if is_positive else negatives
        bucket.append(
            {"label": label, "detail": detail, "positive": is_positive}
        )

    value_delta_pct = _safe_num(row.get("Value Delta %"), None)
    if value_delta_pct is not None:
        pct = value_delta_pct * 100
        if pct >= 3:
            add_item(True, "Value", f"Under fair value by {pct:.1f}%")
        elif pct <= -3:
            add_item(False, "Value", f"Over fair value by {abs(pct):.1f}%")

    yield_est = _safe_num(row.get("Yield %"), None)
    market_yield = _safe_num(row.get("Market Yield %"), None)
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

    price_to_rent = _safe_num(row.get("Price-to-Rent (yrs)"), None)
    market_pr = _safe_num(row.get("Market P/R (yrs)"), None)
    if price_to_rent is not None and market_pr is not None:
        gap = price_to_rent - market_pr
        if gap <= -2:
            add_item(True, "Price/Rent", f"{price_to_rent:.1f}y vs {market_pr:.1f}y market")
        elif gap >= 2:
            add_item(False, "Price/Rent", f"{price_to_rent:.1f}y vs {market_pr:.1f}y market")

    score = _safe_num(row.get("Deal Score"), None)
    if score is not None:
        if score >= 0.7:
            add_item(True, "Deal score", f"{score:.2f} strong signal")
        elif score <= 0.4:
            add_item(False, "Deal score", f"{score:.2f} weak signal")

    momentum = _safe_num(row.get("Momentum %"), None)
    if momentum is not None:
        if momentum >= 3:
            add_item(True, "Momentum", f"{momentum:+.1f}% momentum")
        elif momentum <= -3:
            add_item(False, "Momentum", f"{momentum:+.1f}% momentum")

    area_sentiment = _safe_num(row.get("Area Sentiment"), None)
    if area_sentiment is not None:
        if area_sentiment >= 0.6:
            add_item(True, "Area sentiment", f"{area_sentiment:.2f}/1.00 positive")
        elif area_sentiment <= 0.4:
            add_item(False, "Area sentiment", f"{area_sentiment:.2f}/1.00 weak")

    liquidity = _safe_num(row.get("Liquidity"), None)
    if liquidity is not None:
        if liquidity >= 0.6:
            add_item(True, "Liquidity", f"{liquidity:.2f}/1.00 healthy")
        elif liquidity <= 0.4:
            add_item(False, "Liquidity", f"{liquidity:.2f}/1.00 thin")

    uncertainty = _safe_num(row.get("Uncertainty %"), None)
    if uncertainty is not None and uncertainty >= 0.2:
        add_item(False, "Model range", f"Uncertainty ±{uncertainty * 100:.0f}%")

    total_return = _safe_num(row.get("Total Return 12m %"), None)
    if total_return is not None:
        if total_return >= 6:
            add_item(True, "Total return", f"{total_return:+.1f}% (12m)")
        elif total_return <= 0:
            add_item(False, "Total return", f"{total_return:+.1f}% (12m)")

    items = positives[:3] + negatives[:3]
    return items


def _build_swot(row, reasons: list[str], thesis: object) -> dict:
    strengths: list[str] = []
    weaknesses: list[str] = []
    opportunities: list[str] = []
    threats: list[str] = []

    for reason in reasons or []:
        _append_unique(strengths, reason, limit=5)

    value_delta_pct = _safe_num(row.get("Value Delta %"), None)
    if value_delta_pct is not None:
        pct = value_delta_pct * 100
        if pct >= 3:
            _append_unique(strengths, f"Priced {pct:.1f}% below fair value")
        elif pct <= -3:
            _append_unique(weaknesses, f"Priced {abs(pct):.1f}% above fair value")

    yield_est = _safe_num(row.get("Yield %"), None)
    market_yield = _safe_num(row.get("Market Yield %"), None)
    if yield_est is not None and market_yield is not None:
        spread = yield_est - market_yield
        if spread >= 0.5:
            _append_unique(strengths, f"Yield {yield_est:.2f}% (+{spread:.2f}pp vs market)")
        elif spread <= -0.5:
            _append_unique(weaknesses, f"Yield {yield_est:.2f}% ({spread:.2f}pp vs market)")

    price_to_rent = _safe_num(row.get("Price-to-Rent (yrs)"), None)
    market_pr = _safe_num(row.get("Market P/R (yrs)"), None)
    if price_to_rent is not None and market_pr is not None:
        gap = price_to_rent - market_pr
        if gap <= -2:
            _append_unique(strengths, f"Price-to-rent {price_to_rent:.1f}y vs {market_pr:.1f}y market")
        elif gap >= 2:
            _append_unique(weaknesses, f"Price-to-rent {price_to_rent:.1f}y vs {market_pr:.1f}y market")

    score = _safe_num(row.get("Deal Score"), None)
    if score is not None:
        if score >= 0.7:
            _append_unique(strengths, f"Strong deal score ({score:.2f})")
        elif score <= 0.4:
            _append_unique(weaknesses, f"Weak deal score ({score:.2f})")

    momentum = _safe_num(row.get("Momentum %"), None)
    if momentum is not None:
        if momentum >= 3:
            _append_unique(strengths, f"Positive momentum ({momentum:+.1f}%)")
        elif momentum <= -3:
            _append_unique(weaknesses, f"Negative momentum ({momentum:+.1f}%)")

    area_sentiment = _safe_num(row.get("Area Sentiment"), None)
    if area_sentiment is not None:
        if area_sentiment >= 0.6:
            _append_unique(strengths, f"Healthy area sentiment ({area_sentiment:.2f}/1.00)")
        elif area_sentiment <= 0.4:
            _append_unique(weaknesses, f"Weak area sentiment ({area_sentiment:.2f}/1.00)")

    liquidity = _safe_num(row.get("Liquidity"), None)
    if liquidity is not None:
        if liquidity >= 0.6:
            _append_unique(strengths, f"Liquid market ({liquidity:.2f}/1.00)")
        elif liquidity <= 0.4:
            _append_unique(weaknesses, f"Thin liquidity ({liquidity:.2f}/1.00)")

    total_return = _safe_num(row.get("Total Return 12m %"), None)
    if total_return is not None and total_return >= 6:
        _append_unique(opportunities, f"Total return {total_return:+.1f}% over 12m")
    price_return = _safe_num(row.get("Price Return 12m %"), None)
    if price_return is not None and price_return >= 4:
        _append_unique(opportunities, f"Projected price return {price_return:+.1f}% (12m)")

    catchup = _safe_num(row.get("Catchup"), None)
    if catchup is not None and catchup >= 0.6:
        _append_unique(opportunities, f"Catch-up signal ({catchup:.2f})")

    area_dev = _safe_num(row.get("Area Development"), None)
    if area_dev is not None and area_dev >= 0.6:
        _append_unique(opportunities, f"Area development signal ({area_dev:.2f})")

    thesis_text = _truncate_text(thesis, 140)
    if thesis_text:
        _append_unique(opportunities, thesis_text)

    uncertainty = _safe_num(row.get("Uncertainty %"), None)
    if uncertainty is not None and uncertainty >= 0.2:
        _append_unique(threats, f"High model uncertainty (±{uncertainty * 100:.0f}%)")

    if price_return is not None and price_return <= 0:
        _append_unique(threats, f"Projected price return {price_return:+.1f}% (12m)")

    if total_return is not None and total_return <= 2:
        _append_unique(threats, f"Low total return outlook ({total_return:+.1f}% 12m)")

    if liquidity is not None and liquidity <= 0.4:
        _append_unique(threats, "Liquidity constraints could slow exits")

    if area_sentiment is not None and area_sentiment <= 0.4:
        _append_unique(threats, "Area sentiment drags near-term demand")

    comps = row.get("Comps") or []
    if not comps:
        _append_unique(threats, "Limited comps to validate pricing")

    return {
        "strengths": strengths[:5],
        "weaknesses": weaknesses[:5],
        "opportunities": opportunities[:5],
        "threats": threats[:5],
    }


@st.cache_data(ttl=120)
def load_pipeline_status():
    try:
        return PipelineStateService().snapshot().to_dict()
    except Exception as e:
        return {"error": str(e), "needs_refresh": False, "reasons": ["status_unavailable"]}


def _ensure_session_defaults(available_cities, available_types, available_countries, cities_by_country):
    state = st.session_state
    if "selected_country" not in state:
        state.selected_country = "All"
    if state.selected_country != "All" and state.selected_country not in available_countries:
        state.selected_country = "All"

    city_pool = (
        available_cities
        if state.selected_country == "All"
        else cities_by_country.get(state.selected_country, [])
    )
    if "selected_city" not in state:
        state.selected_city = "All"
    if state.selected_city != "All" and state.selected_city not in city_pool:
        state.selected_city = "All"

    if "selected_types" not in state:
        state.selected_types = list(available_types)
    else:
        state.selected_types = [t for t in state.selected_types if t in available_types]
        if not state.selected_types and available_types:
            state.selected_types = list(available_types)

    if "price_range" not in state:
        state.price_range = DEFAULT_PRICE_RANGE
    if "max_listings" not in state:
        state.max_listings = 300
    if "sort_by" not in state:
        state.sort_by = "Deal Score"
    if "sort_order" not in state:
        state.sort_order = "Desc"
    if "scout_profile" not in state:
        state.scout_profile = "Balanced"
    if "active_view" not in state:
        state.active_view = VIEW_OPTIONS[0]
    if "selected_title" not in state:
        state.selected_title = None
    if "orchestrator_log" not in state:
        state.orchestrator_log = []
    if "orchestrator_input" not in state:
        state.orchestrator_input = ""
    if "autonomy_mode" not in state:
        state.autonomy_mode = "Assisted"
    if "allow_refresh" not in state:
        state.allow_refresh = True
    if "pending_actions" not in state:
        state.pending_actions = []
    if "ai_response" not in state:
        state.ai_response = ""
    if "last_plan" not in state:
        state.last_plan = []
    if "deal_page" not in state:
        state.deal_page = 1
    if "deal_page_size" not in state:
        state.deal_page_size = 12
    if "lens_expanded" not in state:
        state.lens_expanded = False


def _log_orchestrator(role: str, text: str) -> None:
    st.session_state.orchestrator_log.append({"role": role, "text": text})


def _reset_filters(available_cities, available_types, available_countries) -> None:
    st.session_state.selected_country = "All"
    st.session_state.selected_city = "All"
    st.session_state.selected_types = list(available_types)
    st.session_state.price_range = DEFAULT_PRICE_RANGE
    st.session_state.max_listings = 300
    st.session_state.sort_by = "Deal Score"
    st.session_state.sort_order = "Desc"
    st.session_state.scout_profile = "Balanced"


def _select_projection(projections: list, target_months: int = 12):
    if not projections:
        return None
    try:
        exact = [p for p in projections if getattr(p, "months_future", None) == target_months]
        if exact:
            return exact[0]
        return min(
            projections,
            key=lambda p: abs(getattr(p, "months_future", target_months) - target_months),
        )
    except Exception:
        return None


def _apply_action(action, available_cities, available_types, available_countries):
    kind = action.get("type")
    if kind == "set_filters":
        for key, value in action.get("payload", {}).items():
            if key in st.session_state:
                st.session_state[key] = value
    elif kind == "set_view":
        st.session_state.active_view = action.get("view", VIEW_OPTIONS[0])
    elif kind == "select_listing":
        st.session_state.selected_title = action.get("title")
        st.session_state.active_view = "Investment Memo"
    elif kind == "reset_filters":
        _reset_filters(available_cities, available_types, available_countries)
    elif kind == "preflight":
        api = PipelineAPI()
        with st.spinner("Refreshing pipeline artifacts..."):
            api.preflight()
        load_pipeline_status.clear()
        load_filter_options.clear()


available_cities, available_types, available_countries, cities_by_country = load_filter_options()
_ensure_session_defaults(available_cities, available_types, available_countries, cities_by_country)

# --- Pipeline Status ---
pipeline_status = load_pipeline_status()
pipeline_needs_refresh = bool(pipeline_status.get("needs_refresh"))
pipeline_error = pipeline_status.get("error")
pipeline_reasons = pipeline_status.get("reasons") or []
if pipeline_error:
    pipeline_state_text = "Degraded"
    pipeline_reason_text = f"Status unavailable: {pipeline_error}"
    pipeline_badge = "Error"
    pipeline_badge_class = "pipeline-badge pipeline-badge--stale"
else:
    pipeline_state_text = "Refresh due" if pipeline_needs_refresh else "Live"
    reason_parts = [_humanize_reason(reason) for reason in pipeline_reasons if reason]
    pipeline_reason_text = ", ".join(reason_parts) if reason_parts else "Signals are current"
    pipeline_badge = "Refresh" if pipeline_needs_refresh else "Live"
    pipeline_badge_class = "pipeline-badge pipeline-badge--fresh" if not pipeline_needs_refresh else "pipeline-badge pipeline-badge--stale"

pipeline_listings = int(pipeline_status.get("listings_count", 0) or 0)
pipeline_listings_at = _format_ts(pipeline_status.get("listings_last_seen"))
pipeline_market_at = _format_ts(pipeline_status.get("market_data_at"))
pipeline_index_at = _format_ts(pipeline_status.get("index_at"))
pipeline_model_at = _format_ts(pipeline_status.get("model_at"))

left_col = st.container()

selected_country = st.session_state.selected_country
selected_city = st.session_state.selected_city
selected_types = st.session_state.selected_types
min_price, max_price = st.session_state.price_range

# --- Lens HUD ---
with left_col:
    lens_chips = _build_lens_chips(
        selected_country,
        selected_city,
        selected_types,
        min_price,
        max_price,
        DEFAULT_PRICE_RANGE,
        available_types,
    )
    chips_html = "".join([f"<span class='lens-chip'>{html.escape(c)}</span>" for c in lens_chips])
    hud_cols = st.columns([6, 1])
    with hud_cols[0]:
        st.markdown(
            f"""
            <div class="lens-hud-bar">
                <span class="lens-hud-title">Lens</span>
                <div class="lens-hud-chips">{chips_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hud_cols[1]:
        toggle_label = "Hide" if st.session_state.lens_expanded else "Tune"
        if st.button(toggle_label, key="lens_toggle", use_container_width=True):
            st.session_state.lens_expanded = not st.session_state.lens_expanded
            st.rerun()

    if st.session_state.lens_expanded:
        lens_cols = st.columns([1.1, 1.1, 1.6])
        with lens_cols[0]:
            selected_country = st.selectbox(
                "Country", ["All"] + available_countries, key="selected_country"
            )
        with lens_cols[1]:
            city_pool = (
                available_cities
                if selected_country == "All"
                else cities_by_country.get(selected_country, [])
            )
            selected_city = st.selectbox("City", ["All"] + city_pool, key="selected_city")
        with lens_cols[2]:
            min_price, max_price = st.slider(
                "Budget",
                0,
                2000000,
                st.session_state.price_range,
                key="price_range",
                step=10000,
                format="%d€",
            )

        with st.expander("More filters", expanded=False):
            selected_types = st.multiselect(
                "Property Type",
                available_types,
                default=st.session_state.selected_types,
                key="selected_types",
            )
            st.caption(f"Scout focus: {st.session_state.scout_profile}")

        qa_cols = st.columns(2)
        if qa_cols[0].button("Reset lens", use_container_width=True):
            _reset_filters(available_cities, available_types, available_countries)
            st.rerun()
        if qa_cols[1].button("Refresh signals", use_container_width=True):
            _apply_action({"type": "preflight"}, available_cities, available_types, available_countries)
            st.rerun()

        with st.expander("System status", expanded=False):
            st.caption(f"Pipeline: {pipeline_state_text}")
            st.progress(100 if pipeline_badge == "Live" else 50)
            st.text(f"Listings tracked: {pipeline_listings}")
            st.text(f"Listings updated: {pipeline_listings_at}")


# --- Load Data ---
max_listings = st.session_state.max_listings
session = storage.get_session()
raw_rows = []
failed_valuations = 0
try:
    query = session.query(DBListing).order_by(DBListing.updated_at.desc())
    if selected_country != "All":
        query = query.filter(DBListing.country == selected_country)
    if selected_city != "All":
        query = query.filter(DBListing.city == selected_city)
    if selected_types:
        query = query.filter(DBListing.property_type.in_(selected_types))
    listings_db = query.limit(max_listings).all()

    if listings_db:
        progress_bar = st.progress(0, text="Scoring listings and signals...")

    persister = None
    try:
        from src.valuation.services.valuation_persister import ValuationPersister

        persister = ValuationPersister(session)
    except Exception:
        persister = None

    for i, db_item in enumerate(listings_db):
        listing = db_listing_to_canonical(db_item)

        cached_val = persister.get_latest_valuation(db_item.id) if persister else None
        comps = []
        ext_signals = {}

        if cached_val:
            projections = [
                ValuationProjection(**p) for p in cached_val.evidence.get("projections", [])
            ]
            rent_projections = [
                ValuationProjection(**p) for p in cached_val.evidence.get("rent_projections", [])
            ]
            yield_projections = [
                ValuationProjection(**p) for p in cached_val.evidence.get("yield_projections", [])
            ]
            rent_est = None
            if rent_projections:
                rent_est = min(rent_projections, key=lambda p: p.months_future).predicted_value

            yield_est = None
            if yield_projections:
                yield_est = min(yield_projections, key=lambda p: p.months_future).predicted_value
            elif db_item.gross_yield:
                yield_est = db_item.gross_yield

            analysis = DealAnalysis(
                listing_id=db_item.id,
                fair_value_estimate=cached_val.fair_value,
                fair_value_uncertainty_pct=0.10,
                deal_score=cached_val.confidence_score,
                investment_thesis=cached_val.evidence.get("thesis", "Cached Analysis"),
                market_signals=cached_val.evidence.get("signals", {}),
                projections=projections,
                rent_projections=rent_projections,
                yield_projections=yield_projections,
                evidence=None,
                rental_yield_estimate=yield_est,
            )
            ext_signals = (
                cached_val.evidence.get("evidence", {}).get("external_signals", {})
                if cached_val.evidence
                else {}
            )
        else:
            try:
                comps = retriever.retrieve_comps(listing, k=3)
                analysis = valuation.evaluate_deal(listing, comps=comps)
                if persister:
                    try:
                        persister.save_valuation(db_item.id, analysis)
                    except Exception:
                        pass
                if analysis.evidence and analysis.evidence.external_signals:
                    ext_signals = analysis.evidence.external_signals
            except Exception:
                failed_valuations += 1
                continue

        evidence_payload = None
        if cached_val:
            evidence_payload = cached_val.evidence.get("evidence", {}) if cached_val.evidence else {}
        elif analysis.evidence:
            try:
                evidence_payload = analysis.evidence.dict()
            except Exception:
                evidence_payload = None

        signals = analysis.market_signals or {}
        momentum = signals.get("momentum")
        liquidity = signals.get("liquidity")
        catchup = signals.get("catchup")
        market_yield = signals.get("market_yield")
        price_to_rent_years = _safe_num(signals.get("price_to_rent_years"), None)
        market_price_to_rent_years = _safe_num(signals.get("market_price_to_rent_years"), None)
        area_sentiment = signals.get("area_sentiment")
        area_development = signals.get("area_development")

        rent_est = db_item.estimated_rent
        if not rent_est and getattr(analysis, "rent_projections", None):
            rent_est = min(analysis.rent_projections, key=lambda p: p.months_future).predicted_value

        yield_est = getattr(analysis, "rental_yield_estimate", None)
        if yield_est is None and db_item.gross_yield:
            yield_est = db_item.gross_yield
        if yield_est is None and getattr(analysis, "yield_projections", None):
            yield_est = min(analysis.yield_projections, key=lambda p: p.months_future).predicted_value

        value_delta = None
        value_delta_pct = None
        if listing.price and listing.price > 0 and analysis.fair_value_estimate:
            value_delta = analysis.fair_value_estimate - listing.price
            value_delta_pct = value_delta / listing.price

        projected_value_12m = _safe_num(signals.get("projected_value_12m"), None)
        price_return_12m_pct = _safe_num(signals.get("price_return_12m_pct"), None)
        if price_return_12m_pct is None and projected_value_12m is not None and listing.price and listing.price > 0:
            price_return_12m_pct = (
                (projected_value_12m - listing.price) / listing.price
            ) * 100
        if price_return_12m_pct is None and listing.price and listing.price > 0:
            proj_12m = _select_projection(getattr(analysis, "projections", []), 12)
            if proj_12m and getattr(proj_12m, "predicted_value", None):
                projected_value_12m = float(proj_12m.predicted_value)
                price_return_12m_pct = (
                    (projected_value_12m - listing.price) / listing.price
                ) * 100
            elif value_delta_pct is not None:
                price_return_12m_pct = value_delta_pct * 100

        total_return_12m_pct = _safe_num(signals.get("total_return_12m_pct"), None)
        if total_return_12m_pct is None and (price_return_12m_pct is not None or yield_est is not None):
            total_return_12m_pct = (price_return_12m_pct or 0.0) + (yield_est or 0.0)

        image_urls = [str(url) for url in listing.image_urls] if listing.image_urls else []
        raw_rows.append(
            {
                "ID": listing.id,
                "Title": listing.title,
                "Price": listing.price,
                "Sqm": listing.surface_area_sqm,
                "Bedrooms": listing.bedrooms,
                "City": listing.location.city if listing.location else None,
                "Country": listing.location.country if listing.location else None,
                "Property Type": str(listing.property_type),
                "Deal Score": analysis.deal_score,
                "Fair Value": analysis.fair_value_estimate,
                "Uncertainty %": analysis.fair_value_uncertainty_pct,
                "Value Delta": value_delta,
                "Value Delta %": value_delta_pct,
                "Projected Value 12m": projected_value_12m,
                "Price Return 12m %": price_return_12m_pct,
                "Total Return 12m %": total_return_12m_pct,
                "Rent Est": rent_est,
                "Yield %": yield_est,
                "Market Yield %": market_yield,
                "Price-to-Rent (yrs)": price_to_rent_years,
                "Market P/R (yrs)": market_price_to_rent_years,
                "Momentum %": (momentum * 100) if momentum is not None else None,
                "Liquidity": liquidity,
                "Catchup": catchup,
                "Area Sentiment": area_sentiment,
                "Area Development": area_development,
                "Income Weight": ext_signals.get("income_weight"),
                "Area Adjustment": ext_signals.get("area_adjustment"),
                "Thesis": analysis.investment_thesis,
                "URL": str(listing.url),
                "lat": listing.location.lat if listing.location else None,
                "lon": listing.location.lon if listing.location else None,
                "Image": image_urls[0] if image_urls else None,
                "Images": image_urls,
                "Desc": listing.description,
                "VLM Desc": listing.vlm_description,
                "Projections": analysis.projections,
                "Rent Projections": getattr(analysis, "rent_projections", []),
                "Yield Projections": getattr(analysis, "yield_projections", []),
                "Signals": signals,
                "Evidence": evidence_payload,
                "Comps": comps if comps else [],
            }
        )

        if listings_db:
            progress_bar.progress((i + 1) / len(listings_db))

    if listings_db:
        progress_bar.empty()

finally:
    session.close()

if failed_valuations:
    st.warning(f"{failed_valuations} listings could not be valued and were skipped.")

df = pd.DataFrame(raw_rows)

if df.empty:
    st.markdown(
        "<div class='empty-state'><h2>No listings yet</h2><p>Run a harvest or backfill to load listings.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

# --- Normalize & Filter ---
for col in [
    "Yield %",
    "Deal Score",
    "Value Delta %",
    "Momentum %",
    "Area Sentiment",
    "Price Return 12m %",
    "Total Return 12m %",
    "Price-to-Rent (yrs)",
    "Market P/R (yrs)",
]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

filtered_df = df.copy()
filtered_df["Yield %"] = filtered_df["Yield %"].fillna(0)
filtered_df["Momentum %"] = filtered_df["Momentum %"].fillna(0)
filtered_df["Area Sentiment"] = filtered_df["Area Sentiment"].fillna(0.5)
filtered_df["Value Delta %"] = filtered_df["Value Delta %"].fillna(0)

filtered_df = filtered_df[
    (filtered_df["Price"] >= min_price)
    & (filtered_df["Price"] <= max_price)
]

scout_profile = st.session_state.scout_profile
sort_key, ascending = _resolve_profile_sort(scout_profile)
if sort_key not in filtered_df.columns:
    sort_key = "Deal Score"
filtered_df = filtered_df.sort_values(by=sort_key, ascending=ascending)
filtered_df["Why"] = filtered_df.apply(lambda row: _format_deal_reasons(row, scout_profile), axis=1)
filtered_df["Intel Summary"] = filtered_df.apply(lambda row: _format_intel_summary(row, scout_profile), axis=1)
scout_picks = _select_scout_picks(filtered_df, scout_profile, max_picks=4)

if not filtered_df.empty:
    titles = list(filtered_df["Title"].unique())
    if st.session_state.selected_title not in titles:
        st.session_state.selected_title = titles[0]
else:
    st.session_state.selected_title = None

orchestrator_prompt = _compose_orchestrator_prompt(
    filtered_df, pipeline_needs_refresh, pipeline_error
)

st.markdown('<div id="scout-command-center"></div>', unsafe_allow_html=True)
with st.form("scout_command_center", clear_on_submit=True):
    input_cols = st.columns([3, 1])
    with input_cols[0]:
        prompt = st.text_input(
            "Scout Command",
            key="orchestrator_input",
            placeholder="Ask the Scout... (⌘K)",
            label_visibility="collapsed",
        )
    with input_cols[1]:
        submitted = st.form_submit_button("Scout it", use_container_width=True)

    with st.expander("Options", expanded=False):
        autonomy_mode = st.selectbox(
            "Mode",
            options=["Advisory", "Assisted", "Autopilot"],
            key="autonomy_mode",
        )
        refresh = st.checkbox(
            "Allow refreshes", key="allow_refresh", help="Let me pull fresh data when needed"
        )

if submitted and prompt:
    _log_orchestrator("user", prompt)
    actions, response = _parse_prompt(
        prompt, available_countries, available_cities, available_types
    )
    _log_orchestrator("assistant", response)
    st.session_state.ai_response = response
    auto_actions, pending = _resolve_autonomy(actions, autonomy_mode, refresh)
    st.session_state.last_plan = [
        {"label": _action_label(a), "status": "auto" if a in auto_actions else "approval"}
        for a in actions
    ]
    st.session_state.pending_actions = pending
    if auto_actions:
        for action in auto_actions:
            _apply_action(action, available_cities, available_types, available_countries)
        st.rerun()

components.html(
    """
    <script>
    (function() {
      const doc = window.parent.document;
      if (!doc) return;

      function attach() {
        // Robustly find the form by looking for the unique input inside it
        const input = doc.querySelector('input[aria-label="Scout Command"]');
        if (!input) {
             // Retry if input not found yet
             setTimeout(attach, 300);
             return;
        }
        
        const form = input.closest('[data-testid="stForm"]');
        if (!form) {
          console.warn("Scout Command Center: Input found but form container missing.");
          setTimeout(attach, 300);
          return;
        }
        
        if (!form.classList.contains("scout-command-center")) {
            form.classList.add("scout-command-center");
            console.log("Scout Command Center: Floating style applied.");
        }
      }

      function focusInput() {
        const input = doc.querySelector('input[aria-label="Scout Command"]');
        if (input) {
          input.focus();
          input.select();
        }
      }

      // Initial attach
      attach();

      // Re-attach on DOM mutations (e.g. valid for Streamlit reruns)
      const observer = new MutationObserver(() => {
          attach();
      });
      observer.observe(doc.body, { childList: true, subtree: true });

      if (!window.parent.__scout_cmd_shortcut) {
        window.parent.__scout_cmd_shortcut = true;
        doc.addEventListener("keydown", (e) => {
          const key = (e.key || "").toLowerCase();
          if ((e.metaKey || e.ctrlKey) && key === "k") {
            e.preventDefault();
            focusInput();
          }
        });
      }
    })();
    </script>
    """,
    height=0,
)

with left_col:
    console_expanded = bool(
        st.session_state.pending_actions or st.session_state.ai_response
    )
    with st.expander("Scout Console", expanded=console_expanded):
        st.caption(orchestrator_prompt)
        st.caption(f"Scout focus: {scout_profile} • Ranked by {sort_key}")

        if st.session_state.ai_response and not st.session_state.pending_actions:
            st.info(st.session_state.ai_response, icon="🤖")

        if st.session_state.pending_actions:
            st.markdown("##### Awaiting your OK")
            if st.button("Approve all", key="approve_all", use_container_width=True):
                for action in st.session_state.pending_actions:
                    _apply_action(action, available_cities, available_types, available_countries)
                st.session_state.pending_actions = []
                st.rerun()

            for idx, action in enumerate(st.session_state.pending_actions):
                with st.expander(f"{_action_label(action)}", expanded=True):
                    if st.button("Approve", key=f"app_{idx}"):
                        _apply_action(action, available_cities, available_types, available_countries)
                        st.session_state.pending_actions.pop(idx)
                        st.rerun()

    with st.expander("Suggested next moves", expanded=False):
        suggestions = _build_suggestions(
            filtered_df,
            pipeline_needs_refresh,
            available_cities,
            available_countries,
            st.session_state.price_range,
        )
        if suggestions:
            for idx, suggestion in enumerate(suggestions[:4]):
                st.markdown(f"**{suggestion['title']}**")
                st.caption(suggestion["body"])
                if st.button(
                    suggestion["cta"],
                    key=f"quick_action_{idx}",
                    use_container_width=True,
                    help=suggestion["body"],
                ):
                    log = suggestion.get("log")
                    if log:
                        _log_orchestrator("assistant", log)
                    _apply_action(
                        suggestion["action"],
                        available_cities,
                        available_types,
                        available_countries,
                    )
                    st.rerun()
        else:
            st.caption("No quick moves right now.")

    # --- Scout Briefing (collapsed to keep functionality on top) ---
    with st.expander("Scout Briefing", expanded=False):
        st.markdown("#### Market pulse")
        avg_price = filtered_df["Price"].mean() if not filtered_df.empty else 0
        avg_price = float(avg_price) if pd.notna(avg_price) else 0
        avg_yield = filtered_df["Yield %"].mean() if not filtered_df.empty else 0
        avg_yield = float(avg_yield) if pd.notna(avg_yield) else 0
        median_delta = filtered_df["Value Delta %"].median() if not filtered_df.empty else 0
        median_delta = float(median_delta) if pd.notna(median_delta) else 0
        avg_momentum = filtered_df["Momentum %"].mean() if not filtered_df.empty else 0
        avg_momentum = float(avg_momentum) if pd.notna(avg_momentum) else 0
        avg_return = filtered_df["Total Return 12m %"].mean() if not filtered_df.empty else 0
        avg_return = float(avg_return) if pd.notna(avg_return) else 0
        avg_liquidity = filtered_df["Liquidity"].mean() if not filtered_df.empty else 0.5
        avg_liquidity = float(avg_liquidity) if pd.notna(avg_liquidity) else 0.5
        avg_area = filtered_df["Area Sentiment"].mean() if not filtered_df.empty else 0.5
        avg_area = float(avg_area) if pd.notna(avg_area) else 0.5

        momentum_score = np.tanh((avg_momentum or 0) / 4.0)
        liquidity_score = (avg_liquidity or 0.5) - 0.5
        area_score = (avg_area or 0.5) - 0.5
        market_heat_index = int(np.clip(50 + 30 * momentum_score + 25 * liquidity_score + 20 * area_score, 0, 100))

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Signal pulse", market_heat_index, help="Momentum-driven composite index")
        m2.metric("Opportunities", len(filtered_df))
        m3.metric("Avg yield", f"{avg_yield:.2f}%")
        m4.metric("Avg return 12m", f"{avg_return:+.1f}%")
        m5.metric("Value gap", f"{median_delta * 100:+.1f}%")
        m6.metric("Avg price", f"{avg_price/1000:.0f}k")

    st.divider()

    # --- Main Navigation (Tabs) ---
    tab_atlas, tab_flow, tab_memo, tab_lab = st.tabs(
        ["🗺 Atlas", "📋 Deal Flow", "📑 Memo", "🧪 Signal Lab"]
    )

    # --- TAB: ATLAS ---
    with tab_atlas:
        st.markdown("### Atlas")
        color_mode = st.radio(
            "Pin colors",
            options=["Deal Score", "Yield %"],
            horizontal=True,
            key="atlas_color_mode",
        )
        st.caption("Hover a pin for the listing card.")

        import pydeck as pdk

        map_data = filtered_df.dropna(subset=["lat", "lon"]).copy()
        map_data["lat"] = pd.to_numeric(map_data["lat"], errors="coerce")
        map_data["lon"] = pd.to_numeric(map_data["lon"], errors="coerce")
        map_data = map_data.dropna(subset=["lat", "lon"])
        if map_data.empty:
            st.info("No listings to map yet.")
        else:
            st.caption(f"{len(map_data)} listings on the map")
            map_pick_rows = []
            for pick in scout_picks:
                row = pick["row"]
                if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
                    map_pick_rows.append(row.to_dict())

            if map_pick_rows:
                top_map_picks = pd.DataFrame(map_pick_rows)
            else:
                top_map_picks = map_data.sort_values(by=sort_key, ascending=ascending).head(4)

            keep_cols = [
                "lat",
                "lon",
                "Title",
                "City",
                "Country",
                "Price",
                "Yield %",
                "Deal Score",
                "Image",
                "Intel Summary",
            ]
            map_data = map_data[keep_cols]
            map_data["Image"] = map_data["Image"].fillna("").astype(str)
            # Use transparent pixel for missing images to prevent src="" (which fetches current page)
            transparent_pixel = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
            map_data["Image"] = map_data["Image"].apply(lambda x: x if x.strip() else transparent_pixel)
            map_data["LocationLabel"] = map_data.apply(
                lambda r: _format_location(r.get("City"), r.get("Country")),
                axis=1,
            )

            def _format_price(value: object) -> str:
                num = _safe_num(value, None)
                return f"{num:,.0f} €" if num is not None else "n/a"

            def _format_percent(value: object) -> str:
                num = _safe_num(value, None)
                return f"{num:.2f}%" if num is not None else "n/a"

            def _format_score(value: object) -> str:
                num = _safe_num(value, None)
                return f"{num:.2f}" if num is not None else "n/a"

            map_data["PriceLabel"] = map_data["Price"].apply(_format_price)
            map_data["YieldLabel"] = map_data["Yield %"].apply(_format_percent)
            map_data["DealScoreLabel"] = map_data["Deal Score"].apply(_format_score)
            map_data["IntelLabel"] = map_data["Intel Summary"].apply(
                lambda v: _truncate_text(v, 140) if pd.notna(v) else ""
            )
            map_data["YieldValue"] = pd.to_numeric(map_data["Yield %"], errors="coerce")
            map_data["ScoreValue"] = pd.to_numeric(map_data["Deal Score"], errors="coerce")

            def get_score_color(score, is_focused: bool = False):
                if is_focused:
                    return [209, 136, 69, 255]
                score = _safe_num(score, 0.0) or 0.0
                score = max(0.0, min(score, 1.0))
                base = np.array([55, 80, 107])
                mid = np.array([47, 111, 98])
                peak = np.array([193, 147, 91])
                if score < 0.5:
                    ratio = score / 0.5
                    color = base + (mid - base) * ratio
                else:
                    ratio = (score - 0.5) / 0.5
                    color = mid + (peak - mid) * ratio
                return [int(c) for c in color] + [190]

            yield_values = map_data["YieldValue"].dropna()
            if not yield_values.empty:
                low = float(np.nanpercentile(yield_values, 10))
                high = float(np.nanpercentile(yield_values, 90))
                if high <= low:
                    high = low + 1.0
            else:
                low, high = 0.0, 1.0

            def get_yield_color(value, is_focused: bool = False):
                if is_focused:
                    return [209, 136, 69, 255]
                val = _safe_num(value, None)
                if val is None:
                    return [120, 126, 133, 140]
                ratio = (val - low) / (high - low) if high > low else 0.0
                ratio = max(0.0, min(ratio, 1.0))
                start = np.array([49, 84, 140])
                end = np.array([210, 162, 108])
                color = start + (end - start) * ratio
                return [int(c) for c in color] + [190]

            focused_title = st.session_state.selected_title

            if color_mode == "Yield %":
                map_data["color"] = map_data.apply(
                    lambda r: get_yield_color(
                        r["YieldValue"], is_focused=(r["Title"] == focused_title)
                    ),
                    axis=1,
                )
            else:
                map_data["color"] = map_data.apply(
                    lambda r: get_score_color(
                        r["ScoreValue"], is_focused=(r["Title"] == focused_title)
                    ),
                    axis=1,
                )

            if focused_title and (map_data["Title"] == focused_title).any():
                focus_row = map_data[map_data["Title"] == focused_title].iloc[0]
                view_state = pdk.ViewState(
                    latitude=focus_row["lat"],
                    longitude=focus_row["lon"],
                    zoom=14.6,
                    pitch=45,
                    bearing=-10,
                    transition_duration=1200,
                    transition_easing="TRANSITION_EASING_CUBIC_IN_OUT",
                )
                map_data["radius"] = map_data["Title"].apply(
                    lambda t: 220 if t == focused_title else 70
                )
            else:
                view_state = pdk.ViewState(
                    latitude=map_data["lat"].mean(),
                    longitude=map_data["lon"].mean(),
                    zoom=11.4,
                    pitch=0,
                    bearing=0,
                    transition_duration=1200,
                )
                map_data["radius"] = 90

            tooltip_html = (
                "<div style='background: var(--surface-strong); color: var(--ink); "
                "padding: 10px 12px; border-radius: 14px; border: 1px solid rgba(21, 19, 16, 0.12); "
                "box-shadow: var(--shadow-soft); width: 260px;'>"
                "<div style='display:flex; gap:10px; align-items:flex-start;'>"
                "<img src='{Image}' style='width:86px; height:86px; object-fit:cover; "
                "border-radius:10px; flex:0 0 auto;' onerror='this.style.display=\"none\"'/>"
                "<div style='display:flex; flex-direction:column; gap:4px;'>"
                "<div style='font-weight:600; font-size:0.9rem; color: var(--ink-strong); line-height:1.2;'>"
                "{Title}</div>"
                "<div style='font-size:0.75rem; color: var(--muted);'>{LocationLabel}</div>"
                "<div style='font-size:0.8rem; color: var(--accent-4);'>{PriceLabel}</div>"
                "</div></div>"
                "<div style='margin-top:8px; font-size:0.75rem; color: var(--muted);'>"
                "Yield {YieldLabel} • Deal {DealScoreLabel}</div>"
                "<div style='margin-top:6px; font-size:0.75rem; color: var(--ink);'>{IntelLabel}</div>"
                "</div>"
            )

            st.pydeck_chart(
                pdk.Deck(
                    map_provider="carto",
                    map_style="light",
                    initial_view_state=view_state,
                    layers=[
                        pdk.Layer(
                            "ScatterplotLayer",
                            data=map_data,
                            get_position="[lon, lat]",
                            get_fill_color="color",
                            get_radius="radius",
                            pickable=True,
                            auto_highlight=True,
                            stroked=True,
                            get_line_color=[248, 245, 239],
                            line_width_min_pixels=1,
                            opacity=0.9,
                        )
                    ],
                    tooltip={
                        "html": tooltip_html,
                        "style": {"backgroundColor": "transparent", "color": "inherit"},
                    },
                ),
                use_container_width=True,
                height=680,
            )

            st.markdown("#### Spotlight")
            st.caption("Pick a listing to zoom in and explore.")

            if focused_title:
                if st.button("Reset View", key="atlas_reset_map_view"):
                    st.session_state.selected_title = None
                    st.rerun()

            cols = st.columns(2)
            for idx, (_, row) in enumerate(top_map_picks.iterrows()):
                col = cols[idx % 2]
                with col:
                    is_active = focused_title and row["Title"] == focused_title
                    border_color = (
                        "2px solid var(--accent)"
                        if is_active
                        else "1px solid rgba(21, 19, 16, 0.12)"
                    )
                    bg_color = "var(--bg-veil)" if is_active else "var(--surface-strong)"
                    location = _format_location(row.get("City"), row.get("Country"))
                    yield_value = _safe_num(row.get("Yield %"), None)
                    yield_label = f"{yield_value:.1f}% Yield" if yield_value is not None else "Yield n/a"

                    st.markdown(
                        f"""
                        <div style="
                            border: {border_color};
                            background: {bg_color};
                            padding: 12px;
                            border-radius: 14px;
                            margin-bottom: 10px;
                        ">
                            <div style="font-size:0.85rem; font-weight:bold;">{row['Title']}</div>
                            <div style="font-size:0.75rem; color:var(--muted);">{location}</div>
                            <div style="font-size:0.9rem; color:var(--accent-3); margin-top:4px;">{yield_label}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if row.get("Intel Summary"):
                        st.caption(row["Intel Summary"])

                    if st.button("Focus", key=f"atlas_focus_{idx}"):
                        st.session_state.selected_title = row["Title"]
                        st.rerun()

    # --- TAB: DEAL FLOW ---
    with tab_flow:
        if scout_picks:
            st.markdown("**Scout picks**")
            pick_cols = st.columns(len(scout_picks))
            for col, pick in zip(pick_cols, scout_picks):
                with col:
                    row = pick["row"]
                    label = pick["label"]

                    ranked_images = _rank_images_sample(_safe_list(row.get("Images")))
                    img_url = ranked_images[0] if ranked_images else None
                    if img_url and isinstance(img_url, str) and img_url.strip():
                        st.image(img_url, use_container_width=True)
                    else:
                        st.markdown(
                            "<div style='height: 120px; background: var(--surface-strong); display:flex; "
                            "align-items:center; justify-content:center; color:var(--muted);'>"
                            "Image coming soon</div>",
                            unsafe_allow_html=True,
                        )

                    st.caption(label)
                    st.markdown(f"**{row['Title']}**")
                    location = _format_location(row.get("City"), row.get("Country"))
                    st.caption(f"{location} • {row['Price']:,.0f} €")
                    total_return = _safe_num(row.get("Total Return 12m %"), None)
                    total_return_label = f"{total_return:+.1f}%" if total_return is not None else "n/a"
                    st.markdown(
                        f"Return 12m: **{total_return_label}** "
                        f"| Yield: **{row['Yield %']:.2f}%**"
                    )
                    if row.get("Intel Summary"):
                        st.caption(row["Intel Summary"])
                    if st.button("View Memo", key=f"btn_view_{row['ID']}"):
                        st.session_state.selected_title = row["Title"]
                        st.session_state.active_view = "Investment Memo"
                        st.toast(
                            f"Selected {row['Title']}. Open the Memo tab to view details."
                        )
        else:
            st.caption("No picks under this lens yet.")

        st.markdown("---")

        total_cards = len(filtered_df)
        if total_cards == 0:
            st.info("No listings to display.")
        else:
            page_cols = st.columns([1, 1, 2])
            with page_cols[0]:
                page_size = st.selectbox(
                    "Cards per page",
                    options=[12, 24, 48],
                    key="deal_page_size",
                )
            total_pages = max(1, int(np.ceil(total_cards / page_size)))
            if st.session_state.deal_page > total_pages:
                st.session_state.deal_page = total_pages
            with page_cols[1]:
                page = st.number_input(
                    "Page",
                    min_value=1,
                    max_value=total_pages,
                    value=st.session_state.deal_page,
                    step=1,
                    key="deal_page",
                )
            start_idx = (page - 1) * page_size
            end_idx = min(start_idx + page_size, total_cards)
            with page_cols[2]:
                st.caption(f"Showing {start_idx + 1}–{end_idx} of {total_cards}")

            page_df = filtered_df.iloc[start_idx:end_idx]
            # Grid Layout: Row-major for correct mobile stacking
            # We iterate in chunks of 3 to ensure that on mobile (where columns stack),
            # the user sees Item 1, 2, 3... sequentially, rather than 1, 4, 7... (column-major).
            cols_per_row = 3
            for i in range(0, len(page_df), cols_per_row):
                row_chunk = page_df.iloc[i : i + cols_per_row]
                row_cols = st.columns(cols_per_row)
                
                for j, (db_idx, row) in enumerate(row_chunk.iterrows()):
                    with row_cols[j]:
                        title = _escape_html(row.get("Title") or "Untitled")
                        location = _escape_html(
                            _format_location(row.get("City"), row.get("Country"))
                        )
                        price_value = _safe_num(row.get("Price"), None)
                        price_label = f"{price_value:,.0f} €" if price_value is not None else "Price n/a"
                        yield_value = _safe_num(row.get("Yield %"), None)
                        yield_label = (
                            f"{yield_value:.2f}% Yield" if yield_value is not None else "Yield n/a"
                        )
                        scout_take = row.get("Intel Summary") or row.get("Why") or "No summary yet."
                        scout_take = _escape_html(_truncate_text(scout_take, 160))

                        image_url = _normalize_text(row.get("Image"))
                        if not image_url:
                            images = _safe_list(row.get("Images"))
                            if images:
                                image_url = _normalize_text(images[0])

                        transparent_pixel = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                        final_img_url = image_url if image_url else transparent_pixel
                        
                        if image_url:
                            image_html = (
                                "<img class='deal-image' "
                                f"src='{html.escape(final_img_url)}' "
                                "onerror=\"this.style.display='none'\"/>"
                            )
                        else:
                            image_html = "<div class='image-placeholder'>No image yet</div>"

                        st.markdown(
                            f"""
                            <div class="deal-card">
                                {image_html}
                                <div class="deal-title">{title}</div>
                                <div class="deal-meta">{location}</div>
                                <div class="deal-metrics">
                                    <span class="deal-badge">{yield_label}</span>
                                    <span class="deal-price">{price_label}</span>
                                </div>
                                <div class="deal-take">
                                    <span class="deal-take-label">Scout&apos;s Take</span>
                                    {scout_take}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        url = row.get("URL")
                        if url:
                            st.markdown(
                                f"<a class='deal-link' href='{html.escape(str(url))}' target='_blank'>Open listing</a>",
                                unsafe_allow_html=True,
                            )
                        
                        # Unique key using db_idx (index in dataframe) + page + i + j
                        if st.button("Open Memo", key=f"open_memo_{db_idx}_{i}_{j}"):
                            st.session_state.selected_title = row.get("Title")
                            st.session_state.active_view = "Investment Memo"
                            st.rerun()

    # --- TAB: MEMO ---
    with tab_memo:
        if not filtered_df.empty:
            current_titles = list(filtered_df["Title"].unique())
            if st.session_state.selected_title not in current_titles:
                st.session_state.selected_title = current_titles[0]

            selected_title = st.selectbox(
                "Pick a property",
                current_titles,
                index=current_titles.index(st.session_state.selected_title),
                key="selected_title_box",
            )
            st.session_state.selected_title = selected_title

            item = filtered_df[filtered_df["Title"] == selected_title].iloc[0]
            reasons = _build_deal_reasons(item, scout_profile)

            m_col1, m_col2 = st.columns([1, 1])

            with m_col1:
                ranked_images = _rank_images_sample(_safe_list(item.get("Images")))
                if ranked_images:
                    theater_images = ranked_images[:8]
                    theater_key = f"theater_idx_{item.get('ID')}"
                    if (
                        theater_key in st.session_state
                        and st.session_state[theater_key] > len(theater_images)
                    ):
                        st.session_state[theater_key] = len(theater_images)

                    st.markdown("### Theater Mode")
                    frame_index = st.slider(
                        "Image",
                        min_value=1,
                        max_value=len(theater_images),
                        value=st.session_state.get(theater_key, 1),
                        key=theater_key,
                        label_visibility="collapsed",
                    )
                    frame_url = theater_images[frame_index - 1]
                    transparent_pixel = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                    final_frame_url = frame_url if frame_url and str(frame_url).strip() else transparent_pixel
                    
                    st.markdown(
                        f"""
                        <div class="theater-frame">
                            <img class="theater-image" src="{html.escape(str(final_frame_url))}"
                                 onerror="this.style.display='none'"/>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.caption(f"Frame {frame_index} of {len(theater_images)}")

                    thumb_cols = st.columns(min(len(theater_images), 5))
                    for idx, col in enumerate(thumb_cols):
                        with col:
                            st.image(theater_images[idx], use_container_width=True)
                else:
                    st.info("No images yet.")

                st.markdown("### Scout Notes")
                scout_notes = _format_vlm_notes(item.get("VLM Desc"))
                st.info(scout_notes or "No vision summary yet.")
                st.text_area(
                    "Listing description",
                    _format_listing_description(item.get("Desc")) or "No description yet.",
                    height=150,
                )

            with m_col2:
                st.markdown(f"## {item.get('Title')}")
                location = _format_location(item.get("City"), item.get("Country"))
                st.caption(f"{location} | {item.get('Property Type')}")

                f1, f2, f3 = st.columns(3)
                f1.metric("Ask Price", f"{item.get('Price'):,.0f} €")
                f2.metric(
                    "Fair Value",
                    f"{item.get('Fair Value'):,.0f} €",
                    delta=f"{item.get('Value Delta %') * 100:+.1f}%",
                )
                f3.metric("Deal Score", f"{item.get('Deal Score'):.2f}")

                f4, f5, f6, f7, f8 = st.columns(5)
                f4.metric("Est. Rent", f"{item.get('Rent Est'):,.0f} €")
                f5.metric("Gross Yield", f"{item.get('Yield %'):.2f}%")
                f6.metric("Market Yield", f"{item.get('Market Yield %'):.2f}%")
                price_to_rent = _safe_num(item.get("Price-to-Rent (yrs)"), None)
                market_pr = _safe_num(item.get("Market P/R (yrs)"), None)
                pr_label = f"{price_to_rent:.1f}y" if price_to_rent is not None else "n/a"
                pr_delta = None
                if price_to_rent is not None and market_pr is not None:
                    pr_delta = f"{price_to_rent - market_pr:+.1f}y vs market"
                f7.metric("Price/Rent", pr_label, delta=pr_delta)
                total_return = _safe_num(item.get("Total Return 12m %"), None)
                total_return_label = f"{total_return:+.1f}%" if total_return is not None else "n/a"
                f8.metric("Return 12m", total_return_label)

                scorecard_items = _build_scorecard_items(item)
                st.markdown("### Scorecard")
                if scorecard_items:
                    scorecard_html = ["<div class='scorecard-grid'>"]
                    for entry in scorecard_items:
                        tone = "scorecard-good" if entry["positive"] else "scorecard-bad"
                        chip = "Pro" if entry["positive"] else "Con"
                        label = _escape_html(entry["label"])
                        detail = _escape_html(entry["detail"])
                        scorecard_html.append(
                            f"""
                            <div class="scorecard-item {tone}">
                                <span class="scorecard-chip">{chip}</span>
                                <div class="scorecard-label">{label}</div>
                                <div class="scorecard-detail">{detail}</div>
                            </div>
                            """
                        )
                    scorecard_html.append("</div>")
                    st.markdown("".join(scorecard_html), unsafe_allow_html=True)
                else:
                    st.caption("Not enough signals to score yet.")

                intel_summary = item.get("Intel Summary")
                thesis_text = item.get("Thesis")
                take_cols = st.columns(2)
                with take_cols[0]:
                    scout_take = intel_summary or (reasons[0] if reasons else "")
                    scout_take = _truncate_text(scout_take, 180)
                    if scout_take:
                        st.markdown(
                            f"""
                            <div class="memo-card">
                                <div class="memo-card-title">Scout&apos;s Take</div>
                                <div class="memo-card-body">{_escape_html(scout_take)}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                with take_cols[1]:
                    thesis_trimmed = _truncate_text(thesis_text, 180)
                    if thesis_trimmed:
                        st.markdown(
                            f"""
                            <div class="memo-card memo-card--accent">
                                <div class="memo-card-title">Investment Thesis</div>
                                <div class="memo-card-body">{_escape_html(thesis_trimmed)}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.caption("Thesis pending.")

                swot = _build_swot(item, reasons, thesis_text)
                st.markdown("### SWOT")
                swot_html = ["<div class='swot-grid'>"]
                swot_blocks = [
                    ("Strengths", "swot-strength", swot["strengths"]),
                    ("Weaknesses", "swot-weakness", swot["weaknesses"]),
                    ("Opportunities", "swot-opportunity", swot["opportunities"]),
                    ("Threats", "swot-threat", swot["threats"]),
                ]
                for title, cls, items in swot_blocks:
                    list_items = items or ["Not enough signals yet."]
                    list_html = "".join([f"<li>{_escape_html(i)}</li>" for i in list_items])
                    swot_html.append(
                        f"""
                        <div class="swot-card {cls}">
                            <div class="swot-title">{_escape_html(title)}</div>
                            <ul class="swot-list">{list_html}</ul>
                        </div>
                        """
                    )
                swot_html.append("</div>")
                st.markdown("".join(swot_html), unsafe_allow_html=True)

                st.markdown("### Deep signal readout")
                evidence = item.get("Evidence") or {}
                s_col1, s_col2 = st.columns(2, gap="large")

                with s_col1:
                    st.markdown("#### Value stack")
                    ask_price = _safe_num(item.get("Price"), None)
                    fair_value = _safe_num(item.get("Fair Value"), None)
                    uncertainty = _safe_num(item.get("Uncertainty %"), 0.1)
                    anchor_price = _safe_num(
                        evidence.get("anchor_price")
                        if isinstance(evidence, dict)
                        else None,
                        None,
                    )

                    value_rows = []
                    if ask_price:
                        value_rows.append({"Metric": "Ask", "EUR": ask_price})
                    if anchor_price:
                        value_rows.append({"Metric": "Comp Anchor", "EUR": anchor_price})
                    if fair_value:
                        value_rows.append({"Metric": "Fair Value", "EUR": fair_value})

                    if value_rows:
                        value_df = pd.DataFrame(value_rows).set_index("Metric")
                        st.bar_chart(value_df, height=220)
                        if fair_value and uncertainty is not None:
                            low = fair_value * (1 - uncertainty)
                            high = fair_value * (1 + uncertainty)
                            st.caption(f"Fair value range: €{low:,.0f} – €{high:,.0f}")
                    else:
                        st.caption("Not enough data to build the value stack yet.")

                    st.markdown("#### Yield vs market")
                    yield_est = _safe_num(item.get("Yield %"), None)
                    market_yield = _safe_num(item.get("Market Yield %"), None)
                    if yield_est is not None or market_yield is not None:
                        yield_rows = []
                        if yield_est is not None:
                            yield_rows.append({"Metric": "Listing", "Yield %": yield_est})
                        if market_yield is not None:
                            yield_rows.append({"Metric": "Market", "Yield %": market_yield})
                        yield_df = pd.DataFrame(yield_rows).set_index("Metric")
                        st.bar_chart(yield_df, height=180)
                        if yield_est is not None and market_yield is not None:
                            spread = yield_est - market_yield
                            st.caption(f"Yield spread: {spread:+.2f}pp")
                        price_to_rent = _safe_num(item.get("Price-to-Rent (yrs)"), None)
                        market_pr = _safe_num(item.get("Market P/R (yrs)"), None)
                        if price_to_rent is not None and market_pr is not None:
                            st.caption(f"Price-to-rent: {price_to_rent:.1f}y vs {market_pr:.1f}y market")
                        elif price_to_rent is not None:
                            st.caption(f"Price-to-rent: {price_to_rent:.1f}y")
                    else:
                        st.caption("Yield signals aren't available yet.")

                with s_col2:
                    st.markdown("#### Comp price map")
                    comp_rows = []
                    if isinstance(evidence, dict) and evidence.get("top_comps"):
                        for comp in evidence.get("top_comps", []):
                            price = _safe_num(
                                comp.get("adj_price") or comp.get("raw_price"), None
                            )
                            similarity = _safe_num(
                                comp.get("similarity_score")
                                or comp.get("attention_weight"),
                                0.0,
                            )
                            if price:
                                comp_rows.append(
                                    {"Price": price, "Similarity": similarity}
                                )
                    if not comp_rows:
                        comps = _safe_list(item.get("Comps"))
                        for comp in comps:
                            price = _safe_num(getattr(comp, "price", None), None)
                            similarity = _safe_num(
                                getattr(comp, "similarity_score", None), 0.0
                            )
                            if price:
                                comp_rows.append(
                                    {"Price": price, "Similarity": similarity}
                                )
                    if comp_rows:
                        comp_df = pd.DataFrame(comp_rows)
                        st.scatter_chart(comp_df, x="Price", y="Similarity", height=240)
                        st.caption(
                            "Higher similarity means closer comps; prices are time-adjusted when available."
                        )
                    else:
                        st.caption("No comps to chart yet.")

                st.markdown("### Stress Test")
                projections = _safe_list(item.get("Projections"))
                if projections:
                    proj_rows = []
                    for p in projections:
                        months = getattr(p, "months_future", None)
                        value = getattr(p, "predicted_value", None)
                        if months is None or value is None:
                            continue
                        proj_rows.append({"Month": int(months), "Baseline": float(value)})
                    proj_df = pd.DataFrame(proj_rows)
                    proj_df = proj_df.sort_values("Month")

                    base_cap = _safe_num(
                        item.get("Market Yield %") or item.get("Yield %"), 4.5
                    )
                    base_cap = max(2.0, min(float(base_cap), 10.0))

                    s_col1, s_col2, s_col3 = st.columns(3)
                    rent_growth = s_col1.slider(
                        "Rent growth (annual)",
                        min_value=-2.0,
                        max_value=8.0,
                        value=2.5,
                        step=0.5,
                        format="%.1f%%",
                        key=f"stress_rent_{item.get('ID')}",
                    )
                    vacancy_rate = s_col2.slider(
                        "Vacancy rate",
                        min_value=0.0,
                        max_value=20.0,
                        value=5.0,
                        step=0.5,
                        format="%.1f%%",
                        key=f"stress_vacancy_{item.get('ID')}",
                    )
                    exit_cap = s_col3.slider(
                        "Exit cap rate",
                        min_value=2.0,
                        max_value=10.0,
                        value=base_cap,
                        step=0.25,
                        format="%.2f%%",
                        key=f"stress_exit_cap_{item.get('ID')}",
                    )

                    rent_factor = (1 + rent_growth / 100) ** (proj_df["Month"] / 12)
                    vacancy_factor = max(0.0, 1 - vacancy_rate / 100)
                    base_cap_rate = max(0.01, base_cap / 100)
                    exit_cap_rate = max(0.01, exit_cap / 100)
                    cap_factor = base_cap_rate / exit_cap_rate

                    proj_df["Stress"] = (
                        proj_df["Baseline"] * rent_factor * vacancy_factor * cap_factor
                    )
                    chart_df = proj_df.set_index("Month")[["Baseline", "Stress"]]
                    st.line_chart(chart_df, height=240)
                    st.caption("Baseline comes from the model; sliders apply stress to test downside risk.")
                else:
                    st.caption("No forecast data to stress test yet.")

                st.markdown("### Comparable sales")
                comps = _safe_list(item.get("Comps"))
                if comps:
                    c_data = []
                    for c in comps[:3]:
                        c_data.append(
                            {
                                "Price": c.price,
                                "Sqm": c.features.get("sqm") if c.features else 0,
                                "Similarity": c.similarity_score,
                            }
                        )
                    st.dataframe(c_data, use_container_width=True)
                else:
                    st.caption("No comps yet.")

        else:
            st.info("No listings match this lens. Try widening the filters.")

    # --- TAB: SIGNAL LAB ---
    with tab_lab:
        st.markdown("### Signal Lab 2.0")
        st.caption("Lasso-select comps to surface the average stats behind each cluster.")

        if filtered_df.empty:
            st.info("No listings to analyze yet.")
        else:
            comp_df = filtered_df.copy()
            comp_df["Yield %"] = pd.to_numeric(comp_df["Yield %"], errors="coerce")
            comp_df["Value Delta %"] = pd.to_numeric(comp_df["Value Delta %"], errors="coerce")
            comp_df["Deal Score"] = pd.to_numeric(comp_df["Deal Score"], errors="coerce")
            comp_df["Momentum %"] = pd.to_numeric(comp_df["Momentum %"], errors="coerce")
            comp_df["Liquidity"] = pd.to_numeric(comp_df["Liquidity"], errors="coerce")
            comp_df["Price"] = pd.to_numeric(comp_df["Price"], errors="coerce")
            comp_df = comp_df.dropna(subset=["Yield %", "Value Delta %"])
            comp_df["ID"] = comp_df["ID"].astype(str)

            if comp_df.empty:
                st.info("Not enough signal coverage to chart comps yet.")
            else:
                fig = px.scatter(
                    comp_df,
                    x="Yield %",
                    y="Value Delta %",
                    color="Deal Score",
                    size="Price",
                    hover_name="Title",
                    hover_data={
                        "City": True,
                        "Price": ":,.0f",
                        "Yield %": ":.2f",
                        "Deal Score": ":.2f",
                        "Momentum %": ":.2f",
                        "Liquidity": ":.2f",
                    },
                    custom_data=["ID"],
                    color_continuous_scale=["#37506b", "#2f6f62", "#c1935b"],
                    size_max=28,
                )
                fig.update_layout(
                    height=520,
                    margin=dict(l=10, r=10, t=40, b=10),
                    xaxis_title="Yield %",
                    yaxis_title="Value Delta %",
                    coloraxis_colorbar=dict(title="Deal Score"),
                )
                fig.update_traces(marker=dict(opacity=0.78))

                selection = st.plotly_chart(
                    fig,
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="lasso",
                )
                selected_df = _resolve_plotly_selection(selection, comp_df, id_col="ID")
                stats_df = selected_df if not selected_df.empty else comp_df

                if selected_df.empty:
                    st.caption("Showing lens-wide averages. Lasso a cluster to compare.")
                else:
                    st.caption(f"Selected {len(selected_df)} comps for summary.")

                s1, s2, s3, s4, s5 = st.columns(5)
                s1.metric("Comps", len(stats_df))
                avg_price = stats_df["Price"].mean()
                s2.metric("Avg price", f"{avg_price:,.0f} €" if pd.notna(avg_price) else "n/a")
                avg_yield = stats_df["Yield %"].mean()
                s3.metric("Avg yield", f"{avg_yield:.2f}%" if pd.notna(avg_yield) else "n/a")
                avg_score = stats_df["Deal Score"].mean()
                s4.metric("Avg deal score", f"{avg_score:.2f}" if pd.notna(avg_score) else "n/a")
                avg_liquidity = stats_df["Liquidity"].mean()
                s5.metric(
                    "Avg liquidity", f"{avg_liquidity:.2f}" if pd.notna(avg_liquidity) else "n/a"
                )

                preview_cols = ["Title", "City", "Price", "Yield %", "Deal Score", "Momentum %", "Liquidity"]
                preview = stats_df[preview_cols].head(12)
                st.dataframe(preview, use_container_width=True, height=280)

            st.markdown("#### Market Heatmap")
            heat_df = filtered_df.copy()
            heat_df["Area"] = heat_df["City"].fillna("Unknown")
            heat_df["Momentum %"] = pd.to_numeric(heat_df["Momentum %"], errors="coerce")
            heat_df["Liquidity"] = pd.to_numeric(heat_df["Liquidity"], errors="coerce")
            heat_df["Yield %"] = pd.to_numeric(heat_df["Yield %"], errors="coerce")
            heat_stats = (
                heat_df.groupby("Area")
                .agg(
                    **{
                        "Momentum %": ("Momentum %", "mean"),
                        "Liquidity": ("Liquidity", "mean"),
                        "Deals": ("ID", "count"),
                        "Yield %": ("Yield %", "mean"),
                    }
                )
                .dropna(subset=["Momentum %", "Liquidity"])
            )
            if heat_stats.empty:
                st.info("Not enough area signals to build the heatmap.")
            else:
                heat_stats["Signal"] = _normalize_column(heat_stats["Momentum %"]) * _normalize_column(
                    heat_stats["Liquidity"]
                )
                heat_stats = heat_stats.sort_values("Signal", ascending=False).head(12)
                heat_table = heat_stats[["Momentum %", "Liquidity", "Deals", "Yield %"]]
                styled = (
                    heat_table.style.background_gradient(
                        subset=["Momentum %", "Liquidity", "Yield %"],
                        cmap="YlGnBu",
                        axis=0,
                    )
                    .format(
                        {
                            "Momentum %": "{:.2f}%",
                            "Liquidity": "{:.2f}",
                            "Yield %": "{:.2f}%",
                            "Deals": "{:.0f}",
                        }
                    )
                )
                st.dataframe(styled, use_container_width=True, height=420)
                st.caption("Heatmap uses city-level groupings (neighborhood labels not available).")

# --- Spacer for Fixed Command Center ---
st.markdown("<div style='min-height: 120px;'></div>", unsafe_allow_html=True)
