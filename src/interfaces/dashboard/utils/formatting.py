from __future__ import annotations
import html
import json
import re
import pandas as pd
from typing import Any, List, Optional, Union

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
