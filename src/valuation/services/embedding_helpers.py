"""
Embedding and feature helpers for valuation — building text, tabular, and image
representations for the fusion model.

Extracted from :class:`ValuationService` to keep the orchestrator focused on
pipeline flow rather than feature engineering.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.listings.services.feature_sanitizer import sanitize_listing_features
from src.platform.domain.schema import CanonicalListing


def is_vlm_safe(text: Optional[str]) -> bool:
    """Check whether a VLM description is trustworthy enough to embed."""
    if not text:
        return False
    cleaned = str(text).strip()
    if len(cleaned) < 30 or len(cleaned) > 600:
        return False
    lower = cleaned.lower()
    for bad in (
        "no image",
        "image not available",
        "unknown",
        "n/a",
        "not provided",
        "no description",
    ):
        if bad in lower:
            return False
    tokens = [t for t in re.split(r"[^a-z0-9]+", lower) if t]
    if len(tokens) < 5:
        return False
    uniq_ratio = len(set(tokens)) / max(len(tokens), 1)
    return uniq_ratio >= 0.4


def build_text_for_embedding(
    listing: CanonicalListing,
    include_vlm: bool,
    vlm_policy: str = "gated",
) -> str:
    """Concatenate title, description, and (optionally) VLM text."""
    text_parts = [listing.title]
    if listing.description:
        text_parts.append(listing.description)
    if include_vlm and listing.vlm_description and vlm_policy != "off":
        if is_vlm_safe(listing.vlm_description):
            text_parts.append(listing.vlm_description)
    return " ".join(part for part in text_parts if part)


def build_tabular_features(listing: CanonicalListing) -> Dict[str, float]:
    """Extract a flat feature dict from a listing for the fusion model."""
    return {
        "bedrooms": listing.bedrooms or 0,
        "bathrooms": listing.bathrooms or 0,
        "surface_area_sqm": listing.surface_area_sqm or 0,
        "year_built": 0,
        "floor": listing.floor or 0,
        "lat": listing.location.lat if listing.location else 0,
        "lon": listing.location.lon if listing.location else 0,
        "price_per_sqm": 0.0,
        "text_sentiment": listing.text_sentiment or 0.5,
        "image_sentiment": listing.image_sentiment or 0.5,
        "has_elevator": 1.0 if listing.has_elevator else 0.0,
    }


def get_image_embedding(listing: CanonicalListing) -> Optional[np.ndarray]:
    """Return the first cached image embedding or None."""
    if listing.image_embeddings and len(listing.image_embeddings) > 0:
        try:
            return np.array(listing.image_embeddings[0], dtype="float32")
        except Exception:
            return None
    return None


def get_embeddings(
    listing: CanonicalListing,
    encoder,
    include_vlm: bool = True,
    vlm_policy: str = "gated",
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    """Return ``(text_embedding, tabular_features, image_embedding)``."""
    sanitize_listing_features(listing)
    text = build_text_for_embedding(listing, include_vlm=include_vlm, vlm_policy=vlm_policy)
    text_emb = encoder.text_encoder.encode_single(text)
    tab_vec = encoder.tabular_encoder.encode(build_tabular_features(listing))
    img_emb = get_image_embedding(listing)
    return text_emb, tab_vec, img_emb


def robust_comp_baseline(
    prices: List[float],
    weights: Optional[List[float]] = None,
    min_comps: int = 5,
) -> float:
    """MAD-trimmed weighted median of comp prices."""
    if not prices:
        raise ValueError("missing_comp_prices")
    values = np.array(prices, dtype=float)
    if np.any(values <= 0):
        values = values[values > 0]
    if len(values) == 0:
        raise ValueError("invalid_comp_prices")

    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad <= 0:
        mad = max(median * 0.05, 1.0)

    mask = np.abs(values - median) <= (3.0 * mad)
    values = values[mask]
    if len(values) < min_comps:
        raise ValueError("insufficient_baseline_comps")

    if weights is None:
        weights_arr = np.ones_like(values) / len(values)
    else:
        weights_arr = np.array(weights, dtype=float)
        weights_arr = weights_arr[mask] if len(weights_arr) >= len(mask) else weights_arr
        if weights_arr.sum() <= 0:
            weights_arr = np.ones_like(values) / len(values)
        else:
            weights_arr = weights_arr / weights_arr.sum()

    order = np.argsort(values)
    cum = np.cumsum(weights_arr[order])
    idx = int(np.searchsorted(cum, 0.5))
    return float(values[order][min(idx, len(values) - 1)])
