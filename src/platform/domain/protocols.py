"""
Service protocols — thin interfaces for swappable implementations.

Each protocol defines the minimum contract a service must satisfy.
Use these for type hints and dependency injection so that:
  - Tests can supply stubs/fakes without touching real infrastructure.
  - Dev/prod can swap implementations (e.g. disable VLM locally).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import numpy as np

from src.platform.domain.schema import CanonicalListing, CompListing, DealAnalysis


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

@runtime_checkable
class ValuationProtocol(Protocol):
    """Interface shared by all valuation service tiers."""

    def evaluate_listing(
        self,
        target: CanonicalListing,
        *,
        persist: bool = False,
        source_status_by_source: Optional[Dict[str, str]] = None,
        source_metrics_by_source: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> DealAnalysis: ...

    def evaluate_listing_id(
        self,
        listing_id: str,
        *,
        persist: bool = False,
        source_status_by_source: Optional[Dict[str, str]] = None,
        source_metrics_by_source: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> DealAnalysis: ...


# ---------------------------------------------------------------------------
# VLM (Vision-Language Model)
# ---------------------------------------------------------------------------

@runtime_checkable
class VLMProtocol(Protocol):
    """Image description / captioning service."""

    def describe_images(
        self,
        image_urls: List[str],
        max_images: Optional[int] = None,
    ) -> str: ...


class NullVLM:
    """No-op VLM for dev/test — returns empty description."""

    def describe_images(
        self,
        image_urls: List[str],
        max_images: Optional[int] = None,
    ) -> str:
        return ""


# ---------------------------------------------------------------------------
# Text / Multimodal Encoding
# ---------------------------------------------------------------------------

@runtime_checkable
class TextEncoderProtocol(Protocol):
    """Dense text embedding."""

    dimension: int

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray: ...

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray: ...


# ---------------------------------------------------------------------------
# Comp Retrieval
# ---------------------------------------------------------------------------

@runtime_checkable
class CompRetrieverProtocol(Protocol):
    """Comparable listing retrieval (vector / geo / hybrid)."""

    def retrieve_comps(
        self,
        target: CanonicalListing,
        k: int = 10,
        max_radius_km: float = 5.0,
        *,
        listing_type: Optional[str] = None,
        max_listed_at: Optional[datetime] = None,
        exclude_duplicate_external: bool = True,
    ) -> List[CompListing]: ...

    def get_metadata(self) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Feature Fusion
# ---------------------------------------------------------------------------

@runtime_checkable
class FeatureFusionProtocol(Protocol):
    """Enrich a listing with VLM / text-analysis features."""

    def fuse(
        self,
        listing: CanonicalListing,
        run_vlm: bool = True,
    ) -> CanonicalListing: ...


class NullFeatureFusion:
    """Pass-through fusion for dev/test."""

    def fuse(
        self,
        listing: CanonicalListing,
        run_vlm: bool = True,
    ) -> CanonicalListing:
        return listing


# ---------------------------------------------------------------------------
# Fusion Model (ML inference)
# ---------------------------------------------------------------------------

@runtime_checkable
class FusionModelProtocol(Protocol):
    """Cross-attention fusion model for valuation."""

    def predict(
        self,
        target_text_embedding: np.ndarray,
        target_tabular_features: np.ndarray,
        target_image_embedding: Optional[np.ndarray],
        comp_text_embeddings: List[np.ndarray],
        comp_tabular_features: List[np.ndarray],
        comp_image_embeddings: List[np.ndarray],
        comp_prices: List[float],
        comp_doms: List[float] | None = None,
        output_mode: str = "price",
    ) -> Any: ...
