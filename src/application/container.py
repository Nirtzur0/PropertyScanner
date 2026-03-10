from __future__ import annotations

from functools import lru_cache

from src.application.analytics import AnalyticsArtifactService
from src.application.jobs import JobService
from src.application.listings import ListingQueryService
from src.application.model_readiness import ModelReadinessService
from src.application.pipeline import PipelineApplicationService
from src.application.reporting import ReportingService
from src.application.sources import SourceCapabilityService
from src.application.valuation import ComparableBaselineValuationService
from src.application.workbench import WorkbenchService
from src.application.workspace import WorkspaceService
from src.core.runtime import RuntimeConfig, load_runtime_config
from src.platform.db.base import resolve_db_url
from src.platform.storage import StorageService


class ServiceContainer:
    def __init__(self, runtime_config: RuntimeConfig) -> None:
        self.runtime_config = runtime_config
        self.storage = StorageService(db_url=resolve_db_url(db_path=runtime_config.paths.db_path))
        self.analytics = AnalyticsArtifactService(runtime_config=runtime_config)
        self.sources = SourceCapabilityService(storage=self.storage, runtime_config=runtime_config)
        self.model_readiness = ModelReadinessService(storage=self.storage, runtime_config=runtime_config)
        self.reporting = ReportingService(storage=self.storage)
        self.listings = ListingQueryService(storage=self.storage)
        self.valuation = ComparableBaselineValuationService(storage=self.storage)
        self.workspace = WorkspaceService(storage=self.storage)
        self.jobs = JobService(storage=self.storage, runtime_config=runtime_config)
        self.workbench = WorkbenchService(
            storage=self.storage,
            valuation_service=self.valuation,
            source_capability_service=self.sources,
            reporting_service=self.reporting,
            job_service=self.jobs,
            workspace_service=self.workspace,
        )
        self.pipeline = PipelineApplicationService(
            storage=self.storage,
            runtime_config=runtime_config,
            source_capability_service=self.sources,
            model_readiness_service=self.model_readiness,
            reporting_service=self.reporting,
            analytics_service=self.analytics,
        )


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return ServiceContainer(load_runtime_config())
