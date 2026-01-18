from __future__ import annotations
import html
import json
import re
import pandas as pd
from typing import Any, List, Optional, Union, Dict

def format_budget_range(min_value: float, max_value: float) -> str:
    """Formats a budget range (e.g., '€200k–€400k')."""
    def _shorten(value: float) -> str:
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}m"
        return f"{value / 1_000:.0f}k"

    return f"€{_shorten(min_value)}–€{_shorten(max_value)}"

def normalize_text(value: object) -> str:
    """Normalizes text by stripping whitespace and replacing nulls with empty string."""
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

def humanize_token(value: object) -> str:
    """Converts snake_case or slug-style tokens to human readable lowercase string."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("_", " ").replace("-", " ").replace("/", " ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()

def clean_label(value: object) -> str:
    """Humanizes a token and filters out 'unknown', 'none', 'n/a'."""
    text = humanize_token(value)
    if not text:
        return ""
    if text in {"unknown", "none", "n/a", "null"}:
        return ""
    return text

def format_list(value: object, max_items: int = 4) -> List[str]:
    """Formats a list of items into a list of strings, filtering empty/unknown values."""
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    results: List[str] = []
    for item in items:
        label = clean_label(item)
        if not label:
            continue
        if label in results:
            continue
        results.append(label)
        if len(results) >= max_items:
            break
    return results

def ensure_sentence(text: str) -> str:
    """Ensures text ends with punctuation."""
    text = normalize_text(text)
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text

def try_parse_json(value: object) -> Optional[Union[dict, list]]:
    """Robustly attempts to parse a string as JSON."""
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
        # Try to find JSON blob in text
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            snippet = match.group(1)
            try:
                return json.loads(snippet)
            except Exception:
                return None
    return None

def truncate_text(value: object, limit: int = 140) -> str:
    """Truncates text to limit, respecting word boundaries if possible."""
    text = normalize_text(value)
    if not text:
        return ""
    if len(text) <= limit:
        return text
    cutoff = max(0, limit - 3)
    return text[:cutoff].rstrip() + "..."

def escape_html(value: object) -> str:
    """Escapes HTML characters."""
    return html.escape(normalize_text(value))

def append_unique(items: List[str], text: object, limit: int = 5) -> None:
    """Appends text to items if not already present and limit not reached."""
    if len(items) >= limit:
        return
    cleaned = normalize_text(text)
    if not cleaned:
        return
    if cleaned in items:
        return
    items.append(cleaned)

def safe_num(value: Any, default: Any = None) -> Any:
    """Safely converts value to float, returning default on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


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
