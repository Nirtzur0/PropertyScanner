from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func

from src.application.jobs import JobService
from src.application.reporting import ReportingService
from src.application.serving import evaluate_serving_eligibility, evaluate_valuation_readiness
from src.application.sources import SourceCapabilityService
from src.application.valuation import ComparableBaselineValuationService
from src.application.workspace import WorkspaceService
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.platform.domain.models import CompReview, DBListing, Memo, Watchlist
from src.platform.storage import StorageService
from src.platform.utils.serialize import model_to_dict
from src.valuation.services.valuation_persister import ValuationPersister


@dataclass(frozen=True)
class WorkbenchFilters:
    country: Optional[str] = None
    city: Optional[str] = None
    listing_type: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_support: Optional[float] = None
    source_status: Optional[str] = None
    search: Optional[str] = None
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon: Optional[float] = None
    max_lon: Optional[float] = None
    sort: str = "deal_score_desc"
    limit: int = 150
    offset: int = 0


class WorkbenchService:
    def __init__(
        self,
        *,
        storage: StorageService,
        valuation_service: ComparableBaselineValuationService,
        source_capability_service: SourceCapabilityService,
        reporting_service: ReportingService,
        job_service: JobService,
        workspace_service: WorkspaceService,
    ) -> None:
        self.storage = storage
        self.valuation_service = valuation_service
        self.source_capability_service = source_capability_service
        self.reporting_service = reporting_service
        self.job_service = job_service
        self.workspace_service = workspace_service

    @staticmethod
    def _clip(value: Optional[float], low: float = 0.05, high: float = 0.99) -> Optional[float]:
        if value is None:
            return None
        return max(low, min(high, float(value)))

    @staticmethod
    def _source_status_map(source_reports: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return {str(item["source_id"]): item for item in source_reports if item.get("source_id")}

    @staticmethod
    def _watchlist_index(watchlists: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        indexed: Dict[str, List[Dict[str, Any]]] = {}
        for watchlist in watchlists:
            for listing_id in watchlist.get("listing_ids") or []:
                indexed.setdefault(str(listing_id), []).append(watchlist)
        return indexed

    def _memo_index(self) -> Dict[str, List[Dict[str, Any]]]:
        indexed: Dict[str, List[Dict[str, Any]]] = {}
        for memo in self.workspace_service.list_memos():
            listing_id = memo.get("listing_id")
            if listing_id:
                indexed.setdefault(str(listing_id), []).append(memo)
        return indexed

    def _comp_review_index(self) -> Dict[str, List[Dict[str, Any]]]:
        session = self.storage.get_session()
        try:
            rows = session.query(CompReview).order_by(CompReview.updated_at.desc()).all()
            indexed: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                indexed.setdefault(str(row.listing_id), []).append(
                    {
                        "id": row.id,
                        "status": row.status,
                        "selected_comp_ids": list(row.selected_comp_ids or []),
                        "rejected_comp_ids": list(row.rejected_comp_ids or []),
                        "overrides": dict(row.overrides or {}),
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                )
            return indexed
        finally:
            session.close()

    def _query_rows(self, filters: WorkbenchFilters) -> tuple[int, List[DBListing]]:
        session = self.storage.get_session()
        try:
            query = session.query(DBListing)
            if filters.country:
                query = query.filter(DBListing.country == filters.country)
            if filters.city:
                query = query.filter(DBListing.city == filters.city)
            if filters.listing_type:
                query = query.filter(DBListing.listing_type == filters.listing_type)
            if filters.min_price is not None:
                query = query.filter(DBListing.price >= filters.min_price)
            if filters.max_price is not None:
                query = query.filter(DBListing.price <= filters.max_price)
            if filters.search:
                like = f"%{filters.search.strip().lower()}%"
                query = query.filter(
                    func.lower(DBListing.title).like(like)
                    | func.lower(func.coalesce(DBListing.description, "")).like(like)
                )
            if filters.min_lat is not None:
                query = query.filter(DBListing.lat >= filters.min_lat)
            if filters.max_lat is not None:
                query = query.filter(DBListing.lat <= filters.max_lat)
            if filters.min_lon is not None:
                query = query.filter(DBListing.lon >= filters.min_lon)
            if filters.max_lon is not None:
                query = query.filter(DBListing.lon <= filters.max_lon)

            total = query.count()
            rows = (
                query.order_by(DBListing.updated_at.desc())
                .offset(max(filters.offset, 0))
                .limit(max(1, min(filters.limit, 300)))
                .all()
            )
            return total, rows
        finally:
            session.close()

    def _valuation_payload(self, row: DBListing, persister: ValuationPersister) -> Dict[str, Any]:
        readiness = evaluate_valuation_readiness(row)
        cached = persister.get_latest_valuation(row.id, max_age_days=None)
        if cached is not None:
            support = self._clip(float(cached.confidence_score or 0.0))
            evidence = dict(cached.evidence or {})
            projections = list(evidence.get("projections") or [])
            price_range_low = float(cached.price_range_low or 0.0) if cached.price_range_low is not None else None
            price_range_high = float(cached.price_range_high or 0.0) if cached.price_range_high is not None else None
            fair_value = float(cached.fair_value)
            value_delta_pct = None
            if row.price and row.price > 0:
                value_delta_pct = (fair_value - float(row.price)) / float(row.price)
            projected_value = projections[0].get("predicted_value") if projections else None
            return {
                "valuation_status": "available",
                "fair_value": fair_value,
                "deal_score": support,
                "support": support,
                "value_delta_pct": value_delta_pct,
                "yield_pct": evidence.get("signals", {}).get("market_yield"),
                "price_range_low": price_range_low,
                "price_range_high": price_range_high,
                "uncertainty_pct": None,
                "reason": None,
                "projected_value_12m": projected_value,
                "valuation_ready": readiness.ready,
            }

        if not readiness.ready:
            return {
                "valuation_status": "missing_required_fields",
                "fair_value": None,
                "deal_score": None,
                "support": None,
                "value_delta_pct": None,
                "yield_pct": None,
                "price_range_low": None,
                "price_range_high": None,
                "uncertainty_pct": None,
                "reason": readiness.reason,
                "projected_value_12m": None,
                "valuation_ready": False,
            }

        target = db_listing_to_canonical(row)
        try:
            candidates = self.valuation_service._candidate_rows(target, k=3)
        except ValueError as exc:
            return {
                "valuation_status": "missing_required_fields",
                "fair_value": None,
                "deal_score": None,
                "support": None,
                "value_delta_pct": None,
                "yield_pct": None,
                "price_range_low": None,
                "price_range_high": None,
                "uncertainty_pct": None,
                "reason": str(exc),
                "projected_value_12m": None,
                "valuation_ready": False,
            }
        if len(candidates) < 3:
            return {
                "valuation_status": "insufficient_comps",
                "fair_value": None,
                "deal_score": None,
                "support": None,
                "value_delta_pct": None,
                "yield_pct": None,
                "price_range_low": None,
                "price_range_high": None,
                "uncertainty_pct": None,
                "reason": "insufficient_comps",
                "projected_value_12m": None,
                "valuation_ready": True,
            }
        return {
            "valuation_status": "not_evaluated",
            "fair_value": None,
            "deal_score": None,
            "support": None,
            "value_delta_pct": None,
            "yield_pct": None,
            "price_range_low": None,
            "price_range_high": None,
            "uncertainty_pct": None,
            "reason": "manual_valuation_required",
            "projected_value_12m": None,
            "valuation_ready": True,
        }

    @staticmethod
    def _next_action(
        *,
        source_status: str,
        support: Optional[float],
        valuation_status: str,
        has_comp_review: bool,
        has_memo: bool,
    ) -> str:
        if valuation_status == "not_evaluated":
            return "Run valuation"
        if valuation_status != "available":
            return "Resolve data gap"
        if has_comp_review:
            return "Open comp review"
        if source_status in {"degraded", "blocked"}:
            return "Manual review"
        if has_memo:
            return "Open memo"
        if support is not None and support < 0.75:
            return "Review support"
        return "Open dossier"

    @staticmethod
    def _marker_color(source_status: str, support: Optional[float], valuation_status: str) -> str:
        if valuation_status != "available":
            return "#9a5a46"
        if source_status == "blocked":
            return "#8b4332"
        if source_status == "degraded":
            return "#b9812c"
        if support is not None and support >= 0.85:
            return "#2d7c82"
        if support is not None and support >= 0.7:
            return "#c56b37"
        return "#7a7d66"

    @staticmethod
    def _marker_size(value_delta_pct: Optional[float], deal_score: Optional[float]) -> float:
        base = 22.0
        if value_delta_pct is not None:
            base += min(max(value_delta_pct, -0.05), 0.25) * 160.0
        if deal_score is not None:
            base += max(0.0, deal_score - 0.5) * 40.0
        return max(18.0, min(base, 64.0))

    @staticmethod
    def _format_price(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"EUR {value:,.0f}"

    def explore(self, *, filters: WorkbenchFilters) -> Dict[str, Any]:
        total, rows = self._query_rows(filters)
        source_summary = self.source_capability_service.audit_sources(persist=False).model_dump(mode="json")
        source_map = self._source_status_map(source_summary["sources"])
        watchlists = self.workspace_service.list_watchlists()
        watchlist_index = self._watchlist_index(watchlists)
        memo_index = self._memo_index()
        comp_review_index = self._comp_review_index()
        jobs = self.job_service.list_jobs(limit=8)
        alerts = self.reporting_service.list_data_quality_events(limit=8)
        saved_searches = self.workspace_service.list_saved_searches()

        session = self.storage.get_session()
        persister = ValuationPersister(session)
        try:
            markers: List[Dict[str, Any]] = []
            table_rows: List[Dict[str, Any]] = []
            support_values: List[float] = []
            for row in rows:
                source_report = source_map.get(str(row.source_id), {})
                source_status = str(source_report.get("status") or "experimental")
                serving = evaluate_serving_eligibility(row, source_status=source_status)
                if not serving.eligible:
                    continue

                valuation = self._valuation_payload(row, persister)
                support = valuation["support"]
                if support is not None:
                    support_values.append(float(support))
                watchlisted = str(row.id) in watchlist_index
                memo_state = "drafted" if str(row.id) in memo_index else "none"
                comp_review_state = "ready" if str(row.id) in comp_review_index else "none"
                next_action = self._next_action(
                    source_status=source_status,
                    support=support,
                    valuation_status=str(valuation["valuation_status"]),
                    has_comp_review=str(row.id) in comp_review_index,
                    has_memo=str(row.id) in memo_index,
                )
                marker = {
                    "id": row.id,
                    "title": row.title,
                    "lat": float(row.lat),
                    "lon": float(row.lon),
                    "city": row.city,
                    "country": row.country,
                    "ask_price": float(row.price) if row.price is not None else None,
                    "fair_value": valuation["fair_value"],
                    "deal_score": valuation["deal_score"],
                    "support": support,
                    "value_delta_pct": valuation["value_delta_pct"],
                    "yield_pct": valuation["yield_pct"],
                    "source_status": source_status,
                    "watchlisted": watchlisted,
                    "memo_state": memo_state,
                    "comp_review_state": comp_review_state,
                    "valuation_status": valuation["valuation_status"],
                    "valuation_reason": valuation["reason"],
                    "valuation_ready": valuation["valuation_ready"],
                    "serving_eligible": True,
                    "serving_reason": None,
                    "next_action": next_action,
                    "marker_color": self._marker_color(source_status, support, str(valuation["valuation_status"])),
                    "marker_size": self._marker_size(valuation["value_delta_pct"], valuation["deal_score"]),
                    "label": self._format_price(float(row.price) if row.price is not None else None),
                    "bedrooms": row.bedrooms,
                    "surface_area_sqm": row.surface_area_sqm,
                }
                markers.append(marker)
                table_rows.append(
                    {
                        "id": row.id,
                        "title": row.title,
                        "city": row.city,
                        "country": row.country,
                        "ask_price": marker["ask_price"],
                        "fair_value": marker["fair_value"],
                        "deal_score": marker["deal_score"],
                        "support": marker["support"],
                        "source_status": marker["source_status"],
                        "valuation_status": marker["valuation_status"],
                        "valuation_ready": marker["valuation_ready"],
                        "serving_eligible": marker["serving_eligible"],
                        "serving_reason": marker["serving_reason"],
                        "watchlisted": marker["watchlisted"],
                        "memo_state": marker["memo_state"],
                        "comp_review_state": marker["comp_review_state"],
                        "next_action": marker["next_action"],
                    }
                )
        finally:
            session.close()

        if filters.source_status:
            markers = [item for item in markers if item["source_status"] == filters.source_status]
            table_rows = [item for item in table_rows if item["source_status"] == filters.source_status]
        if filters.min_support is not None:
            markers = [item for item in markers if item["support"] is not None and item["support"] >= filters.min_support]
            table_rows = [item for item in table_rows if item["support"] is not None and item["support"] >= filters.min_support]

        sort_key = filters.sort or "deal_score_desc"
        reverse = sort_key.endswith("_desc")
        sort_field = {
            "deal_score_desc": "deal_score",
            "support_desc": "support",
            "value_delta_desc": "value_delta_pct",
            "price_asc": "ask_price",
            "price_desc": "ask_price",
        }.get(sort_key, "deal_score")
        markers.sort(key=lambda item: (item.get(sort_field) is None, item.get(sort_field)), reverse=reverse)
        table_rows.sort(key=lambda item: (item.get(sort_field) is None, item.get(sort_field)), reverse=reverse)

        support_median = median(support_values) if support_values else None
        return {
            "filters": {
                "country": filters.country,
                "city": filters.city,
                "listing_type": filters.listing_type,
                "min_price": filters.min_price,
                "max_price": filters.max_price,
                "min_support": filters.min_support,
                "source_status": filters.source_status,
                "search": filters.search,
                "sort": sort_key,
            },
            "stats": {
                "tracked": total,
                "visible": len(markers),
                "watchlist_hits": sum(1 for marker in markers if marker["watchlisted"]),
                "support_median": support_median,
                "unavailable_count": sum(1 for marker in markers if marker["valuation_status"] != "available"),
                "available_count": sum(1 for marker in markers if marker["valuation_status"] == "available"),
                "valuation_ready_count": sum(1 for marker in markers if marker["valuation_ready"]),
                "degraded_source_count": sum(1 for marker in markers if marker["source_status"] == "degraded"),
            },
            "markers": markers,
            "table_rows": table_rows[:60],
            "alerts": alerts,
            "saved_searches": saved_searches[:8],
            "watchlists": watchlists[:8],
            "jobs": jobs,
            "source_summary": source_summary["summary"],
        }

    def listing_context(self, listing_id: str) -> Dict[str, Any]:
        session = self.storage.get_session()
        persister = ValuationPersister(session)
        try:
            row = session.query(DBListing).filter(DBListing.id == listing_id).first()
            if row is None:
                raise ValueError("listing_not_found")
            valuation = self._valuation_payload(row, persister)
            source_summary = self.source_capability_service.audit_sources(persist=False).model_dump(mode="json")
            source_map = self._source_status_map(source_summary["sources"])
            source_status = source_map.get(str(row.source_id), {})
            serving = evaluate_serving_eligibility(row, source_status=str(source_status.get("status") or "experimental"))
            watchlists = [item for item in self.workspace_service.list_watchlists() if listing_id in (item.get("listing_ids") or [])]
            memos = [item for item in self.workspace_service.list_memos() if item.get("listing_id") == listing_id]
            comp_reviews = self.workspace_service.list_comp_reviews(listing_id=listing_id)
            recent_quality = [
                event
                for event in self.reporting_service.list_data_quality_events(limit=25)
                if event.get("source_id") == row.source_id or event.get("listing_id") == listing_id
            ][:8]
            next_action = self._next_action(
                source_status=str(source_status.get("status") or "experimental"),
                support=valuation["support"],
                valuation_status=str(valuation["valuation_status"]),
                has_comp_review=bool(comp_reviews),
                has_memo=bool(memos),
            )
            return {
                "listing": model_to_dict(db_listing_to_canonical(row)),
                "valuation": valuation,
                "source_status": source_status,
                "serving_eligible": serving.eligible,
                "serving_reason": serving.reason,
                "valuation_ready": valuation["valuation_ready"],
                "can_run_valuation": bool(serving.eligible and valuation["valuation_ready"] and valuation["valuation_status"] != "available"),
                "watchlists": watchlists,
                "memos": memos,
                "comp_reviews": comp_reviews,
                "quality_events": recent_quality,
                "next_action": next_action,
            }
        finally:
            session.close()

    def layers(self) -> Dict[str, Any]:
        return {
            "base_map": {
                "provider": "MapLibre + CARTO",
                "style": "voyager",
            },
            "defaults": ["value_opportunity", "support", "source_health", "watchlists"],
            "overlays": [
                {
                    "id": "value_opportunity",
                    "label": "Value opportunity",
                    "description": "Marker size follows value delta and deal score.",
                    "default": True,
                    "blocked": False,
                },
                {
                    "id": "support",
                    "label": "Support / confidence",
                    "description": "Marker color and legend reflect support bands and unavailable states.",
                    "default": True,
                    "blocked": False,
                },
                {
                    "id": "yield",
                    "label": "Yield",
                    "description": "Highlights listings with rental yield support where available.",
                    "default": False,
                    "blocked": False,
                },
                {
                    "id": "source_health",
                    "label": "Source health",
                    "description": "Highlights degraded and blocked source states.",
                    "default": True,
                    "blocked": False,
                },
                {
                    "id": "watchlists",
                    "label": "Watchlist hits",
                    "description": "Adds watchlist rings and saved-lens context.",
                    "default": True,
                    "blocked": False,
                },
                {
                    "id": "comp_density",
                    "label": "Comp density",
                    "description": "Shows heat/grid aggregation for dense zoomed-out exploration.",
                    "default": False,
                    "blocked": False,
                },
                {
                    "id": "benchmark_gate",
                    "label": "Benchmark gate",
                    "description": "Operational alert overlay for model/benchmark readiness.",
                    "default": False,
                    "blocked": len(self.reporting_service.list_benchmark_runs(limit=1)) == 0,
                    "blocked_reason": "benchmark_runs_empty",
                },
            ],
        }
