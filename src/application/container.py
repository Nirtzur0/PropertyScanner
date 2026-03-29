"""
Composition root — assembles the full service graph via constructor injection.

Each service receives its dependencies explicitly through ``__init__``.
No service reaches into the container or uses global state.

Usage::

    container = get_container()          # cached singleton
    container = build_container(config)  # explicit construction
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from src.application.analytics import AnalyticsArtifactService
from src.application.jobs import JobService
from src.application.listings import ListingQueryService
from src.application.model_readiness import ModelReadinessService
from src.application.pipeline import PipelineApplicationService
from src.application.reporting import ReportingService
from src.application.sources import SourceCapabilityService
from src.application.valuation import ComparableBaselineValuationService
from src.application.workbench import CompReviewService, ExploreService, ListingContextService
from src.application.workspace import WorkspaceService
from src.core.runtime import RuntimeConfig, load_runtime_config
from src.platform.db.base import resolve_db_url
from src.platform.domain.protocols import ValuationProtocol
from src.platform.storage import StorageService

logger = logging.getLogger(__name__)


def _try_load_full_valuation(
    storage: StorageService, runtime_config: RuntimeConfig
) -> Optional[ValuationProtocol]:
    """Attempt to load the SOTA V3 ValuationService.

    Returns None if artifacts are missing. Requires the fusion model file
    to exist on disk — without it, V3 predictions are meaningless.
    """
    try:
        from pathlib import Path

        from src.platform.utils.config import load_app_config_safe

        app_config = load_app_config_safe()
        if app_config is None:
            return None

        # V3 requires a trained fusion model. Don't load if it's absent.
        fusion_path = Path(str(app_config.paths.fusion_model_path))
        if not fusion_path.exists():
            logger.debug("V3 valuation skipped: fusion model not found at %s", fusion_path)
            return None

        from src.valuation.services.valuation import ValuationService

        service = ValuationService(
            storage,
            app_config=app_config,
            db_path=str(runtime_config.paths.db_path),
        )
        logger.info("Full V3 valuation service loaded successfully")
        return service
    except Exception as exc:
        logger.debug("V3 valuation unavailable (falling back to baseline): %s", exc)
        return None


class ServiceContainer:
    """Immutable service graph built once at startup.

    Every service is created via constructor injection — no service
    reaches back into the container.  This makes the dependency graph
    explicit, testable, and free of import-time side-effects.
    """

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        *,
        storage: Optional[StorageService] = None,
        full_valuation: Optional[ValuationProtocol] = _try_load_full_valuation,  # sentinel: callable → auto-load
    ) -> None:
        self.runtime_config = runtime_config

        # --- Infrastructure layer ---
        self.storage = storage or StorageService(
            db_url=resolve_db_url(db_path=runtime_config.paths.db_path)
        )

        # --- Cross-cutting services ---
        self.analytics = AnalyticsArtifactService(runtime_config=runtime_config)
        self.sources = SourceCapabilityService(storage=self.storage, runtime_config=runtime_config)
        self.model_readiness = ModelReadinessService(storage=self.storage, runtime_config=runtime_config)
        self.reporting = ReportingService(storage=self.storage)
        self.listings = ListingQueryService(storage=self.storage)

        # --- Valuation tier ---
        self.valuation = ComparableBaselineValuationService(storage=self.storage)
        if callable(full_valuation):
            self.full_valuation: Optional[ValuationProtocol] = full_valuation(
                self.storage, runtime_config
            )
        else:
            self.full_valuation = full_valuation

        # --- Workspace / library ---
        self.workspace = WorkspaceService(
            storage=self.storage,
            source_capability_service=self.sources,
        )
        self.jobs = JobService(storage=self.storage, runtime_config=runtime_config)

        # --- Workbench (UI-facing) ---
        self.explore = ExploreService(
            storage=self.storage,
            valuation_service=self.valuation,
            source_capability_service=self.sources,
            workspace_service=self.workspace,
        )
        self.listing_context_service = ListingContextService(
            storage=self.storage,
            valuation_service=self.valuation,
            source_capability_service=self.sources,
            workspace_service=self.workspace,
            reporting_service=self.reporting,
        )
        self.comp_review_service = CompReviewService(
            storage=self.storage,
            valuation_service=self.valuation,
            source_capability_service=self.sources,
            workspace_service=self.workspace,
        )

        # --- Pipeline orchestration ---
        self.pipeline = PipelineApplicationService(
            storage=self.storage,
            runtime_config=runtime_config,
            source_capability_service=self.sources,
            model_readiness_service=self.model_readiness,
            reporting_service=self.reporting,
            analytics_service=self.analytics,
        )


def build_container(
    runtime_config: RuntimeConfig,
    *,
    storage: Optional[StorageService] = None,
    full_valuation: Optional[ValuationProtocol] = _try_load_full_valuation,
) -> ServiceContainer:
    """Build a fresh container (useful for tests that need custom wiring)."""
    return ServiceContainer(
        runtime_config,
        storage=storage,
        full_valuation=full_valuation,
    )


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    """Return the cached application-wide container singleton."""
    return build_container(load_runtime_config())
