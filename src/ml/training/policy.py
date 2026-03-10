from __future__ import annotations

from typing import Any, Dict, Optional

from src.application.model_readiness import ModelReadinessService
from src.core.runtime import RuntimeConfig, load_runtime_config
from src.platform.storage import StorageService


class ProductReadinessError(ValueError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def format_product_readiness_error(exc: ProductReadinessError) -> str:
    lines = [exc.message, f"code: {exc.code}"]
    if exc.details:
        for key, value in exc.details.items():
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def sale_training_readiness_for_db(*, db_url: str, runtime_config: RuntimeConfig | None = None) -> Dict[str, Any]:
    config = runtime_config or load_runtime_config()
    storage = StorageService(db_url=db_url)
    service = ModelReadinessService(storage=storage, runtime_config=config)
    return service.sale_training_readiness()


def _normalize_listing_type(listing_type: str) -> str:
    return str(listing_type or "").strip().lower()


def _resolve_sale_label_source(label_source: str) -> str:
    normalized = str(label_source or "auto").strip().lower()
    if normalized == "auto":
        return "sold"
    return normalized


def enforce_fusion_training_policy(
    *,
    db_url: str,
    listing_type: str,
    label_source: str,
    research_only: bool,
    runtime_config: RuntimeConfig | None = None,
) -> Dict[str, Any]:
    del research_only
    normalized_listing_type = _normalize_listing_type(listing_type)
    if normalized_listing_type != "sale":
        return {"ready": True, "reasons": [], "listing_type": normalized_listing_type}

    resolved_label_source = _resolve_sale_label_source(label_source)
    if resolved_label_source != "sold":
        raise ProductReadinessError(
            code="sale_training_requires_closed_labels",
            message="Sale model training requires closed-sale labels. Use '--label-source sold' after ingesting sold transactions.",
            details={
                "listing_type": normalized_listing_type,
                "label_source": label_source,
                "resolved_label_source": resolved_label_source,
            },
        )

    readiness = sale_training_readiness_for_db(db_url=db_url, runtime_config=runtime_config)
    if not readiness["ready"]:
        raise ProductReadinessError(
            code="sale_training_not_ready",
            message="Sale model training is not ready for this database.",
            details=readiness,
        )
    return {**readiness, "resolved_label_source": resolved_label_source}


def enforce_fusion_benchmark_policy(
    *,
    db_url: str,
    listing_type: str,
    label_source: str,
    research_only: bool,
    runtime_config: RuntimeConfig | None = None,
) -> Dict[str, Any]:
    del research_only
    normalized_listing_type = _normalize_listing_type(listing_type)
    if normalized_listing_type != "sale":
        return {"ready": True, "reasons": [], "listing_type": normalized_listing_type}

    resolved_label_source = _resolve_sale_label_source(label_source)
    if resolved_label_source != "sold":
        raise ProductReadinessError(
            code="sale_benchmark_requires_closed_labels",
            message="Sale benchmark requires closed-sale labels. Use '--label-source sold' after ingesting sold transactions.",
            details={
                "listing_type": normalized_listing_type,
                "label_source": label_source,
                "resolved_label_source": resolved_label_source,
            },
        )

    readiness = sale_training_readiness_for_db(db_url=db_url, runtime_config=runtime_config)
    if not readiness["ready"]:
        raise ProductReadinessError(
            code="sale_benchmark_not_ready",
            message="Sale benchmark is not ready for this database.",
            details=readiness,
        )
    return {**readiness, "resolved_label_source": resolved_label_source}
