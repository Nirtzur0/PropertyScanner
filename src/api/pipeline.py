from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.config import DEFAULT_DB_PATH, VECTOR_INDEX_PATH, VECTOR_METADATA_PATH
from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing, DealAnalysis
from src.repositories.base import resolve_db_url
from src.services.listing_adapter import db_listing_to_canonical
from src.services.retrieval import CompRetriever
from src.services.storage import StorageService
from src.services.valuation import ValuationConfig, ValuationService
from src.services.valuation_persister import ValuationPersister
from src.training.train import train_model as train_model_workflow
from src.services.transactions import TransactionsIngestService
from src.workflows.harvest import Harvester, DEFAULT_TARGET_COUNT
from src.workflows.indexing import build_vector_index as build_vector_index_workflow
from src.workflows.market_data import build_market_data as build_market_data_workflow
from src.workflows.preflight import run_preflight as run_preflight_workflow


@dataclass(frozen=True)
class PipelineConfig:
    """Configuration for the public pipeline API."""

    db_path: str = str(DEFAULT_DB_PATH)
    db_url: Optional[str] = None
    index_path: str = str(VECTOR_INDEX_PATH)
    metadata_path: str = str(VECTOR_METADATA_PATH)


class PipelineAPI:
    """
    Public API surface for harvesting, market builds, indexing, and valuation.

    Example:
        api = PipelineAPI()
        api.preflight()
        api.harvest(mode="sale", target_count=1000)
        api.build_market_data()
        api.build_vector_index(listing_type="sale")
        analysis = api.evaluate_listing_id("listing-id", persist=True)
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        valuation_config: Optional[ValuationConfig] = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._db_url = resolve_db_url(db_url=self.config.db_url, db_path=self.config.db_path)
        self._storage: Optional[StorageService] = None
        self._valuation: Optional[ValuationService] = None
        self._retriever: Optional[CompRetriever] = None
        self._valuation_config = valuation_config

    @property
    def db_url(self) -> str:
        return self._db_url

    @property
    def storage(self) -> StorageService:
        if self._storage is None:
            self._storage = StorageService(db_url=self._db_url)
        return self._storage

    @property
    def valuation(self) -> ValuationService:
        if self._valuation is None:
            self._valuation = ValuationService(self.storage, config=self._valuation_config)
        return self._valuation

    @property
    def retriever(self) -> CompRetriever:
        if self._retriever is None:
            self._retriever = CompRetriever(
                index_path=self.config.index_path,
                metadata_path=self.config.metadata_path,
                strict_model_match=True,
            )
        return self._retriever

    def preflight(self, **kwargs: Any) -> Dict[str, Any]:
        """Run preflight freshness checks and refresh stale artifacts."""
        db_path = kwargs.pop("db_path", self.config.db_path)
        return run_preflight_workflow(db_path=db_path, **kwargs)

    def harvest(
        self,
        *,
        mode: str = "sale",
        target_count: int = 0,
        start_urls: Optional[List[str]] = None,
        run_vlm: bool = True,
    ) -> None:
        """Harvest listings via the workflow harvester."""
        Harvester(
            mode=mode,
            target_count=target_count or DEFAULT_TARGET_COUNT,
            start_urls=start_urls,
            run_vlm=run_vlm,
        ).run()

    def build_market_data(self, **kwargs: Any) -> None:
        """Build macro data + market/hedonic indices."""
        db_path = kwargs.pop("db_path", self.config.db_path)
        build_market_data_workflow(db_path=db_path, **kwargs)

    def ingest_transactions(
        self,
        path: str,
        *,
        listing_type: str = "sale",
        source_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingest sold/transaction data and map onto listings."""
        service = TransactionsIngestService(db_path=self.config.db_path, db_url=self.config.db_url)
        return service.ingest_file(
            path,
            default_listing_type=listing_type,
            default_source_id=source_id,
        )

    def build_vector_index(self, **kwargs: Any) -> int:
        """Build the vector index for comps."""
        db_url = kwargs.pop("db_url", self._db_url)
        index_path = kwargs.pop("index_path", self.config.index_path)
        metadata_path = kwargs.pop("metadata_path", self.config.metadata_path)
        return build_vector_index_workflow(
            db_url=db_url,
            index_path=index_path,
            metadata_path=metadata_path,
            **kwargs,
        )

    def train_model(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Train the fusion model."""
        db_path = kwargs.pop("db_path", self.config.db_path)
        return train_model_workflow(db_path=db_path, **kwargs)

    def load_listing(self, listing_id: str) -> CanonicalListing:
        """Load a canonical listing by ID from storage."""
        session = self.storage.get_session()
        try:
            db_item = session.query(DBListing).filter(DBListing.id == listing_id).first()
            if not db_item:
                raise ValueError("listing_not_found")
            return db_listing_to_canonical(db_item)
        finally:
            session.close()

    def evaluate_listing(
        self,
        listing: Union[CanonicalListing, DBListing, Dict[str, Any]],
        *,
        comps: Optional[List[CanonicalListing]] = None,
        persist: bool = False,
    ) -> DealAnalysis:
        """Evaluate a listing using the valuation service."""
        if isinstance(listing, CanonicalListing):
            target = listing
        elif isinstance(listing, DBListing):
            target = db_listing_to_canonical(listing)
        else:
            target = CanonicalListing(**listing)

        analysis = self.valuation.evaluate_deal(target, comps=comps)

        if persist:
            session = self.storage.get_session()
            try:
                persister = ValuationPersister(session)
                persister.save_valuation(target.id, analysis)
            finally:
                session.close()

        return analysis

    def evaluate_listing_id(
        self,
        listing_id: str,
        *,
        comps: Optional[List[CanonicalListing]] = None,
        persist: bool = False,
    ) -> DealAnalysis:
        """Evaluate a listing from storage by ID."""
        listing = self.load_listing(listing_id)
        return self.evaluate_listing(listing, comps=comps, persist=persist)


@lru_cache(maxsize=1)
def get_pipeline_api() -> PipelineAPI:
    """Return a cached PipelineAPI instance with default config."""
    return PipelineAPI()
