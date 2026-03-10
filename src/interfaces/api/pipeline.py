from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from sqlalchemy import text

from src.platform.domain.models import DBListing
from src.platform.domain.schema import CanonicalListing, DealAnalysis
import structlog

from src.listings.source_ids import canonicalize_source_id, source_aliases
from src.platform.settings import AppConfig, PipelineConfig, ValuationConfig
from src.platform.db.base import resolve_db_url
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.valuation.services.retrieval import build_retriever
from src.platform.storage import StorageService
from src.valuation.services.valuation import ValuationService
from src.valuation.services.valuation_persister import ValuationPersister
from src.ml.training.train import train_model as train_model_workflow
from src.market.services.transactions import TransactionsIngestService
from src.listings.workflows.unified_crawl import run_backfill
from src.platform.pipeline.state import PipelineStateService
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[3]
_CRAWLER_STATUS_DOC_PATH = _ROOT_DIR / "docs" / "crawler_status.md"
_SOURCE_SUFFIX_RE = re.compile(r"(?:_|-)([a-z]{2})$")
_OBSERVABILITY_DOC_PATH = "docs/manifest/07_observability.md"
_RUNBOOK_DOC_PATH = "docs/manifest/09_runbook.md"
_ARTIFACT_ALIGNMENT_REPORT_PATH = "docs/implementation/reports/artifact_feature_alignment.md"
_ARTIFACT_ALIGNMENT_CHECKLIST_PATH = "docs/implementation/checklists/08_artifact_feature_alignment.md"


def _strip_md(value: str) -> str:
    cleaned = value.replace("`", "").replace("*", "")
    cleaned = cleaned.replace("✅", "").replace("❌", "")
    return " ".join(cleaned.split()).strip()


def _norm_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _parse_crawler_status_doc(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    status_by_name: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue

        cells = [_strip_md(cell.strip()) for cell in line.split("|")[1:-1]]
        if len(cells) < 3:
            continue

        crawler_name = cells[0]
        status_text = cells[2].lower()
        if not crawler_name or crawler_name.lower() == "crawler" or crawler_name.startswith(":---"):
            continue

        if "operational" in status_text:
            status_by_name[_norm_key(crawler_name)] = "operational"
        elif "blocked" in status_text:
            status_by_name[_norm_key(crawler_name)] = "blocked"

    return status_by_name


def _source_candidates(source_id: str, source_name: Optional[str]) -> List[str]:
    candidates: List[str] = []

    if source_name:
        norm_name = _norm_key(source_name)
        if norm_name:
            candidates.append(norm_name)

    norm_id = _norm_key(source_id)
    if norm_id and norm_id not in candidates:
        candidates.append(norm_id)

    suffix_match = _SOURCE_SUFFIX_RE.search(source_id)
    if suffix_match:
        id_without_suffix = _norm_key(source_id[: suffix_match.start()])
        if id_without_suffix and id_without_suffix not in candidates:
            candidates.append(id_without_suffix)

    return candidates


def _runtime_label_from_contract_status(contract_status: str) -> Tuple[str, str]:
    value = str(contract_status or "").strip().lower()
    if value in {"blocked", "policy_blocked"}:
        return "blocked", f"source_contract_{value}"
    if value == "supported":
        return "supported", "source_contract_supported"
    if value:
        return "fallback", f"source_contract_{value}"
    return "fallback", "source_contract_unknown"


def _resolve_crawler_status(source_id: str, source_name: Optional[str], status_by_name: Dict[str, str]) -> str:
    if not status_by_name:
        return "unknown"

    candidates = _source_candidates(source_id, source_name)
    for candidate in candidates:
        if candidate in status_by_name:
            return status_by_name[candidate]

    best_status = "unknown"
    best_len = -1
    for candidate in candidates:
        for report_key, report_status in status_by_name.items():
            if candidate and candidate in report_key:
                if len(report_key) > best_len:
                    best_status = report_status
                    best_len = len(report_key)
    return best_status


def _classify_runtime_label(enabled: bool, crawler_status: str) -> Tuple[str, str]:
    if crawler_status == "blocked":
        return "blocked", "crawler_status_blocked"
    if enabled and crawler_status == "operational":
        return "supported", "enabled_and_operational"
    if enabled:
        return "fallback", "enabled_but_unverified"
    return "fallback", "disabled_or_unverified"


def _repo_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_ROOT_DIR.resolve()))
    except ValueError:
        return str(path.resolve())


class PipelineAPI:
    """
    Public API surface for crawling, market builds, indexing, and valuation.

    Example:
        api = PipelineAPI()
        api.preflight()
        api.crawl_backfill(max_pages=1)
        api.build_market_data()
        api.build_vector_index(listing_type="sale")
        analysis = api.evaluate_listing_id("listing-id", persist=True)
    """

    def __init__(
        self,
        app_config: Optional[AppConfig] = None,
        config: Optional[PipelineConfig] = None,
        valuation_config: Optional[ValuationConfig] = None,
    ) -> None:
        self.app_config = app_config or load_app_config_safe()
        if config is not None and app_config is not None:
            logger.warning("pipeline_config_override", msg="PipelineConfig overrides AppConfig pipeline settings.")
        self.config = config or self.app_config.pipeline
        self._db_url = resolve_db_url(db_url=self.config.db_url, db_path=self.config.db_path)
        self._storage: Optional[StorageService] = None
        self._valuation: Optional[ValuationService] = None
        self._retriever: Optional[CompRetriever] = None
        if valuation_config is not None and app_config is not None:
            logger.warning("valuation_config_override", msg="ValuationConfig overrides AppConfig valuation settings.")
        self._valuation_config = valuation_config or self.app_config.valuation

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
            self._valuation = ValuationService(
                self.storage,
                config=self._valuation_config,
                app_config=self.app_config,
            )
        return self._valuation

    @property
    def retriever(self) -> Any:
        if self._retriever is None:
            self._retriever = build_retriever(
                backend=self._valuation_config.retriever_backend,
                index_path=self.config.index_path,
                metadata_path=self.config.metadata_path,
                lancedb_path=self._valuation_config.retriever_lancedb_path,
                model_name=self._valuation_config.retriever_model_name,
                strict_model_match=True,
                vlm_policy=self._valuation_config.retriever_vlm_policy,
                app_config=self.app_config,
            )
        return self._retriever

    def preflight(self, **kwargs: Any) -> Dict[str, Any]:
        """Run preflight freshness checks and refresh stale artifacts."""
        from src.application.container import get_container

        payload = {
            "source_ids": kwargs.pop("source_ids", kwargs.pop("crawl_source", None)),
            "max_listings": kwargs.pop("max_listings", 0),
            "max_pages": kwargs.pop("max_pages", 1),
            "page_size": kwargs.pop("page_size", 24),
            "skip_crawl": kwargs.pop("skip_crawl", False),
            "skip_market_data": kwargs.pop("skip_market_data", False),
            "skip_index": kwargs.pop("skip_index", False),
            "skip_training": kwargs.pop("skip_training", False),
        }
        return get_container().pipeline.run_preflight(**payload)

    def source_support_summary(self, *, crawler_status_path: Optional[str] = None) -> Dict[str, Any]:
        """Classify source runtime labels as supported/blocked/fallback."""
        doc_path = Path(crawler_status_path) if crawler_status_path else _CRAWLER_STATUS_DOC_PATH
        status_by_name = _parse_crawler_status_doc(doc_path)
        latest_contract_runs: Dict[str, Dict[str, Any]] = {}
        try:
            query = text(
                """
                SELECT source_id, status, metrics, created_at
                FROM source_contract_runs
                ORDER BY created_at DESC
                """
            )
            with self.storage.engine.connect() as conn:
                rows = conn.execute(query).mappings().all()
            for row in rows:
                canonical = canonicalize_source_id(str(row["source_id"] or ""))
                if not canonical or canonical in latest_contract_runs:
                    continue
                metrics = row["metrics"] or {}
                if isinstance(metrics, str):
                    try:
                        metrics = json.loads(metrics)
                    except json.JSONDecodeError:
                        metrics = {"raw_metrics": metrics}
                created_at = row.get("created_at")
                if created_at is not None and not hasattr(created_at, "isoformat"):
                    try:
                        created_at = pd.to_datetime(created_at, format="mixed", errors="coerce")
                    except Exception:
                        created_at = None
                latest_contract_runs[canonical] = {
                    "status": str(row["status"] or ""),
                    "metrics": dict(metrics or {}),
                    "created_at": created_at.isoformat() if created_at is not None else None,
                }
        except Exception:
            latest_contract_runs = {}

        summary = {"supported": 0, "blocked": 0, "fallback": 0}
        sources: List[Dict[str, Any]] = []

        for source in self.app_config.sources.sources:
            canonical_source_id = canonicalize_source_id(source.id)
            latest_contract = latest_contract_runs.get(canonical_source_id)
            if latest_contract is not None:
                crawler_status = str(latest_contract.get("status") or "unknown")
                runtime_label, reason = _runtime_label_from_contract_status(crawler_status)
            else:
                crawler_status = _resolve_crawler_status(source.id, source.name, status_by_name)
                runtime_label, reason = _classify_runtime_label(bool(source.enabled), crawler_status)
            summary[runtime_label] += 1
            sources.append(
                {
                    "id": source.id,
                    "canonical_id": canonical_source_id,
                    "name": source.name or source.id,
                    "countries": list(source.countries),
                    "enabled": bool(source.enabled),
                    "crawler_status": crawler_status,
                    "runtime_label": runtime_label,
                    "reason": reason,
                    "source_aliases": sorted(source_aliases(source.id)),
                    "latest_contract_run": latest_contract,
                }
            )

        return {
            "doc_path": _repo_relative_path(doc_path),
            "summary": summary,
            "sources": sources,
        }

    def assumption_badges(self, *, source_support: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return artifact-backed runtime assumption badges used by API/dashboard status surfaces."""
        summary = source_support.get("summary", {}) if isinstance(source_support, dict) else {}
        if not isinstance(summary, dict):
            summary = {}

        supported = int(summary.get("supported", 0) or 0)
        blocked = int(summary.get("blocked", 0) or 0)
        fallback = int(summary.get("fallback", 0) or 0)
        source_doc = str(source_support.get("doc_path") or "docs/crawler_status.md")

        if blocked > 0 or fallback > 0:
            source_status = "caution"
            source_summary = (
                f"{supported} supported, {blocked} blocked, {fallback} fallback sources; "
                "review crawler caveats before relying on aggregate outputs."
            )
        else:
            source_status = "ok"
            source_summary = (
                f"{supported} supported sources with no blocked/fallback entries in runtime status."
            )

        return [
            {
                "id": "source_coverage",
                "label": "Source coverage caveat",
                "status": source_status,
                "artifact_ids": ["lit-case-shiller-1988"],
                "summary": source_summary,
                "guide_path": source_doc,
            },
            {
                "id": "conditional_coverage",
                "label": "Conformal coverage scope",
                "status": "caution",
                "artifact_ids": ["lit-conformal-tutorial-2021"],
                "summary": (
                    "Conformal intervals are marginal guarantees; monitor segmented coverage "
                    "before treating confidence as certainty."
                ),
                "guide_path": _OBSERVABILITY_DOC_PATH,
            },
            {
                "id": "jackknife_fallback",
                "label": "Fallback interval policy",
                "status": "caution",
                "artifact_ids": ["lit-jackknifeplus-2021"],
                "summary": (
                    "Segmented conformal remains primary; wider bootstrap fallback intervals "
                    "are used for unseen, under-sampled, or under-covered segments."
                ),
                "guide_path": _RUNBOOK_DOC_PATH,
            },
            {
                "id": "decomposition_diagnostics",
                "label": "Land/structure decomposition",
                "status": "gap",
                "artifact_ids": ["lit-deng-gyourko-wu-2012"],
                "summary": "Land/structure decomposition diagnostics are still a planned packet.",
                "guide_path": _ARTIFACT_ALIGNMENT_CHECKLIST_PATH,
            },
        ]

    def pipeline_status(self, *, crawler_status_path: Optional[str] = None) -> Dict[str, Any]:
        """Return pipeline freshness state plus source-support runtime labels."""
        from src.application.container import get_container

        state = get_container().pipeline.pipeline_status()
        source_support = self.source_support_summary(crawler_status_path=crawler_status_path)
        state["source_support"] = source_support
        state["assumption_badges"] = self.assumption_badges(source_support=source_support)
        return state

    def crawl_backfill(
        self,
        *,
        source_ids: Optional[List[str]] = None,
        search_urls: Optional[List[str]] = None,
        search_path: Optional[str] = None,
        listing_urls: Optional[List[str]] = None,
        listing_ids: Optional[List[str]] = None,
        max_listings: int = 0,
        max_pages: int = 1,
        page_size: int = 24,
        run_vlm: bool = True,
        enable_fusion: bool = True,
        enable_augment: bool = True,
        dedupe: bool = True,
        crawler_config: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Crawl listings via the unified crawler backfill."""
        return run_backfill(
            source_ids=source_ids,
            search_urls=search_urls,
            search_path=search_path,
            listing_urls=listing_urls,
            listing_ids=listing_ids,
            max_listings=max_listings,
            max_pages=max_pages,
            page_size=page_size,
            run_vlm=run_vlm,
            enable_fusion=enable_fusion,
            enable_augment=enable_augment,
            dedupe=dedupe,
            crawler_config=crawler_config,
            app_config=self.app_config,
        )

    def build_market_data(self, **kwargs: Any) -> None:
        """Build macro data + market/hedonic indices."""
        from src.application.container import get_container

        get_container().pipeline.run_market_data()

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
        from src.application.container import get_container

        result = get_container().pipeline.run_index(
            listing_type=str(kwargs.pop("listing_type", "all")),
            limit=int(kwargs.pop("limit", 0)),
        )
        return int(result.get("indexed", 0))

    def train_model(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Train the fusion model."""
        db_path = kwargs.pop("db_path", self.config.db_path)
        return train_model_workflow(db_path=db_path, app_config=self.app_config, **kwargs)

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
