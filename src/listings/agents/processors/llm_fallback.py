from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing, CanonicalListing
from src.listings.services.llm_normalizer import LLMNormalizerService


class LLMFallbackNormalizer(BaseAgent):
    def __init__(self, base_normalizer: BaseAgent, llm_service: LLMNormalizerService) -> None:
        super().__init__(name=f"{base_normalizer.name}+LLMFallback")
        self.base_normalizer = base_normalizer
        self.llm_service = llm_service

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        raw_listings: List[RawListing] = input_payload.get("raw_listings", [])
        base_response = self.base_normalizer.run(input_payload)

        canonical_listings: List[CanonicalListing] = list(base_response.data or [])
        errors: List[str] = list(base_response.errors or [])
        metadata: Dict[str, Any] = dict(base_response.metadata or {})

        # Map existing listings by external_id for easy lookup
        base_map = {
            item.external_id: item
            for item in canonical_listings
            if getattr(item, "external_id", None)
        }
        
        fallback_count = 0
        enriched_count = 0

        for raw in raw_listings:
            existing = base_map.get(raw.external_id)
            
            # Decide if we should skip LLM. 
            # Ideally, we verify if existing has "enough" data.
            # But per user request, we want to "fill in" details.
            # We will try to extract and merge.
            
            try:
                candidate = self.llm_service.extract(raw)
                if candidate:
                    if existing:
                        self._merge_listings(existing, candidate)
                        enriched_count += 1
                    else:
                        canonical_listings.append(candidate)
                        fallback_count += 1
            except Exception as exc:
                errors.append(f"LLM extraction failed {raw.external_id}: {exc}")

        metadata["llm_fallback_count"] = fallback_count
        metadata["llm_enriched_count"] = enriched_count
        
        if errors and canonical_listings:
            status = "partial"
        elif errors:
            status = "failure"
        else:
            status = "success"

        return AgentResponse(
            status=status,
            data=canonical_listings,
            metadata=metadata,
            errors=errors,
        )

    def _merge_listings(self, target: CanonicalListing, source: CanonicalListing) -> None:
        """
        Merge source (LLM) into target (Deterministic).
        Target fields take precedence if they are truthy/present.
        """
        # Iterate over fields to fill in missing ones
        # We manually check common fields or use introspection
        
        # Simple fields
        if not target.description and source.description:
            target.description = source.description
            
        if not target.bedrooms and source.bedrooms:
            target.bedrooms = source.bedrooms
            
        if not target.bathrooms and source.bathrooms:
            target.bathrooms = source.bathrooms
            
        if not target.surface_area_sqm and source.surface_area_sqm:
            target.surface_area_sqm = source.surface_area_sqm
            
        if not target.floor and source.floor:
            target.floor = source.floor
            
        if target.has_elevator is None and source.has_elevator is not None:
            target.has_elevator = source.has_elevator
            
        # Address enrichment
        if target.location and source.location:
             if not target.location.address_full and source.location.address_full:
                 target.location.address_full = source.location.address_full
             if not target.location.city and source.location.city:
                 target.location.city = source.location.city
            
        # Images: If target has none, use source. If target has some, keep target (usually higher quality/deterministic)
        if not target.image_urls and source.image_urls:
            target.image_urls = source.image_urls
            
        # Analysis meta
        target.analysis_meta["llm_enriched"] = True
        target.analysis_meta["llm_model"] = source.analysis_meta.get("llm_model")
