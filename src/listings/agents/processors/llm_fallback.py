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

        seen_external_ids = {
            item.external_id for item in canonical_listings if getattr(item, "external_id", None)
        }
        fallback_count = 0

        for raw in raw_listings:
            if raw.external_id in seen_external_ids:
                continue
            try:
                candidate = self.llm_service.extract(raw)
                if candidate:
                    canonical_listings.append(candidate)
                    fallback_count += 1
            except Exception as exc:
                errors.append(f"LLM fallback failed {raw.external_id}: {exc}")

        metadata["llm_fallback_count"] = fallback_count
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
