from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.adapters.http.schemas import (
    BenchmarkJobRequest,
    CompReviewRequest,
    CrawlJobRequest,
    IndexJobRequest,
    MemoRequest,
    PreflightJobRequest,
    SavedSearchRequest,
    UIEventRequest,
    ValuationRequest,
    WatchlistRequest,
)
from src.application.container import get_container
from src.application.workbench import WorkbenchFilters, get_layers
from src.core.runtime import load_runtime_config
from src.platform.observability import trace_span
from src.platform.utils.serialize import model_to_dict


runtime_config = load_runtime_config()
app = FastAPI(title="Property Scanner Local API", version="0.1.0")
api_router = APIRouter(prefix="/api/v1")
_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_VALUATION_FAILURE_MESSAGES = {
    "listing_not_found": "The requested listing was not found.",
    "target_city_required": "This listing cannot be valued yet because the city is missing.",
    "target_surface_area_required": "This listing cannot be valued yet because the surface area is missing.",
    "target_coordinates_required": "This listing cannot be valued yet because the coordinates are missing.",
    "insufficient_comps": "This listing does not have enough comparable sales to produce a supported valuation.",
}


def _source_status_by_source(container) -> dict[str, str]:
    report = _source_audit_report(container)
    return {
        str(item["source_id"]): str(item.get("status") or "experimental")
        for item in report.get("sources", [])
        if item.get("source_id")
    }


def _source_metrics_by_source(container) -> dict[str, dict]:
    report = _source_audit_report(container)
    return {
        str(item["source_id"]): dict(item.get("metrics") or {})
        for item in report.get("sources", [])
        if item.get("source_id")
    }


def _source_audit_report(container) -> dict:
    return container.sources.audit_sources(persist=False).model_dump(mode="json")


def _valuation_failure_response(code: str, request: ValuationRequest) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": code,
            "message": _VALUATION_FAILURE_MESSAGES.get(code, "The valuation could not be completed."),
            "listing_id": request.listing_id,
            "persisted": bool(request.persist),
            "status": "unavailable",
        },
    )


@api_router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": runtime_config.app.name,
        "db_path": Path(runtime_config.paths.db_path).name,
    }


@api_router.get("/pipeline-status")
def pipeline_status() -> dict:
    return get_container().pipeline.pipeline_status()


@api_router.get("/pipeline/trust-summary")
def pipeline_trust_summary() -> dict:
    return get_container().pipeline.pipeline_trust_summary()


@api_router.get("/sources")
def sources() -> dict:
    return get_container().sources.audit_sources().model_dump(mode="json")


@api_router.get("/listings")
def list_listings(
    source_id: str | None = None,
    city: str | None = None,
    listing_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    limit = min(limit, 500)
    return get_container().listings.list_listings(
        source_id=source_id,
        city=city,
        listing_type=listing_type,
        limit=limit,
        offset=offset,
    )


@api_router.get("/listings/{listing_id}")
def get_listing(listing_id: str) -> dict:
    listing = get_container().listings.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing_not_found")
    return listing


@api_router.post("/valuations")
def create_valuation(request: ValuationRequest) -> dict:
    try:
        request.validate_payload()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    container = get_container()
    source_audit_report = _source_audit_report(container)
    source_status_by_source = {
        str(item["source_id"]): str(item.get("status") or "experimental")
        for item in source_audit_report.get("sources", [])
        if item.get("source_id")
    }
    source_metrics_by_source = {
        str(item["source_id"]): dict(item.get("metrics") or {})
        for item in source_audit_report.get("sources", [])
        if item.get("source_id")
    }
    # Use full V3 valuation when available, fall back to baseline
    valuation_svc = container.full_valuation or container.valuation
    try:
        if request.listing_id:
            analysis = valuation_svc.evaluate_listing_id(
                request.listing_id,
                persist=request.persist,
                source_status_by_source=source_status_by_source,
                source_metrics_by_source=source_metrics_by_source,
            )
        else:
            analysis = valuation_svc.evaluate_listing(
                request.listing,
                persist=request.persist,
                source_status_by_source=source_status_by_source,
                source_metrics_by_source=source_metrics_by_source,
            )  # type: ignore[arg-type]
    except ValueError as exc:
        code = str(exc)
        if code in _VALUATION_FAILURE_MESSAGES:
            raise _valuation_failure_response(code, request) from exc
        raise HTTPException(status_code=422, detail={"code": code, "message": code}) from exc
    return model_to_dict(analysis)


@api_router.post("/jobs/preflight")
def submit_preflight_job(request: PreflightJobRequest) -> dict:
    container = get_container()
    payload = request.model_dump(mode="json")
    return container.jobs.submit(
        job_type="preflight",
        payload=payload,
        job_fn=lambda: container.pipeline.run_preflight(**payload),
    )


@api_router.post("/jobs/crawl")
def submit_crawl_job(request: CrawlJobRequest) -> dict:
    container = get_container()
    payload = request.model_dump(mode="json")
    return container.jobs.submit(
        job_type="crawl",
        payload=payload,
        job_fn=lambda: container.pipeline.run_crawl(**payload),
    )


@api_router.post("/jobs/market-data")
def submit_market_data_job() -> dict:
    container = get_container()
    return container.jobs.submit(
        job_type="market_data",
        payload={},
        job_fn=lambda: container.pipeline.run_market_data(),
    )


@api_router.post("/jobs/index")
def submit_index_job(request: IndexJobRequest) -> dict:
    container = get_container()
    payload = request.model_dump(mode="json")
    return container.jobs.submit(
        job_type="index",
        payload=payload,
        job_fn=lambda: container.pipeline.run_index(**payload),
    )


@api_router.post("/jobs/benchmark")
def submit_benchmark_job(request: BenchmarkJobRequest) -> dict:
    container = get_container()
    payload = request.model_dump(mode="json")
    return container.jobs.submit(
        job_type="benchmark",
        payload=payload,
        job_fn=lambda: container.pipeline.run_benchmark(**payload),
    )


@api_router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    container = get_container()
    try:
        return container.jobs.get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.get("/job-runs")
def list_jobs(
    limit: int = 25,
    job_type: str | None = None,
    status: str | None = None,
) -> dict:
    items = get_container().jobs.list_jobs(limit=limit, job_type=job_type, status=status)
    return {"total": len(items), "items": items}


@api_router.get("/benchmarks")
def list_benchmarks(limit: int = 20) -> dict:
    items = get_container().reporting.list_benchmark_runs(limit=limit)
    return {"total": len(items), "items": items}


@api_router.get("/coverage-reports")
def list_coverage_reports(limit: int = 50) -> dict:
    items = get_container().reporting.list_coverage_reports(limit=limit)
    return {"total": len(items), "items": items}


@api_router.get("/data-quality-events")
def list_data_quality_events(limit: int = 100) -> dict:
    limit = min(limit, 500)
    items = get_container().reporting.list_data_quality_events(limit=limit)
    return {"total": len(items), "items": items}


@api_router.post("/ui-events")
def record_ui_event(request: UIEventRequest) -> dict:
    event_id = get_container().reporting.record_ui_event(
        event_name=request.event_name,
        route=request.route,
        subject_type=request.subject_type,
        subject_id=request.subject_id,
        context=request.context,
        occurred_at=request.occurred_at,
    )
    return {"id": event_id, "status": "recorded"}


@api_router.get("/source-contract-runs")
def list_source_contract_runs(limit: int = 50) -> dict:
    items = get_container().reporting.list_source_contract_runs(limit=limit)
    return {"total": len(items), "items": items}


@api_router.get("/watchlists")
def list_watchlists() -> dict:
    items = get_container().workspace.list_watchlists()
    return {"total": len(items), "items": items}


@api_router.post("/watchlists")
def create_watchlist(request: WatchlistRequest) -> dict:
    return get_container().workspace.create_watchlist(**request.model_dump(mode="json"))


@api_router.get("/saved-searches")
def list_saved_searches() -> dict:
    items = get_container().workspace.list_saved_searches()
    return {"total": len(items), "items": items}


@api_router.post("/saved-searches")
def create_saved_search(request: SavedSearchRequest) -> dict:
    return get_container().workspace.create_saved_search(**request.model_dump(mode="json"))


@api_router.get("/memos")
def list_memos() -> dict:
    items = get_container().workspace.list_memos()
    return {"total": len(items), "items": items}


@api_router.post("/memos")
def create_memo(request: MemoRequest) -> dict:
    return get_container().workspace.create_memo(**request.model_dump(mode="json"))


@api_router.get("/memos/{memo_id}")
def get_memo(memo_id: str) -> dict:
    try:
        return get_container().workspace.get_memo(memo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.post("/memos/{memo_id}/export")
def export_memo(memo_id: str) -> dict:
    try:
        return get_container().workspace.export_memo(memo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.get("/comp-reviews")
def list_comp_reviews(listing_id: str | None = None) -> dict:
    items = get_container().workspace.list_comp_reviews(listing_id=listing_id)
    return {"total": len(items), "items": items}


@api_router.get("/comp-reviews/{listing_id}/workspace")
def get_comp_review_workspace(listing_id: str) -> dict:
    try:
        return get_container().comp_review_service.comp_review_workspace(listing_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.post("/comp-reviews")
def create_comp_review(request: CompReviewRequest) -> dict:
    try:
        return get_container().workspace.create_comp_review(**request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get("/command-center/runs")
def list_command_center_runs(limit: int = 20) -> dict:
    items = get_container().workspace.list_command_center_runs(limit=limit)
    return {"total": len(items), "items": items}


@api_router.get("/workbench/explore")
def workbench_explore(
    country: str | None = None,
    city: str | None = None,
    listing_type: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_support: float | None = None,
    source_status: str | None = None,
    search: str | None = None,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
    sort: str = "deal_score_desc",
    limit: int = 150,
    offset: int = 0,
) -> dict:
    limit = min(limit, 500)
    return get_container().explore.explore(
        filters=WorkbenchFilters(
            country=country,
            city=city,
            listing_type=listing_type,
            min_price=min_price,
            max_price=max_price,
            min_support=min_support,
            source_status=source_status,
            search=search,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    )


@api_router.get("/workbench/listings/{listing_id}/context")
def workbench_listing_context(listing_id: str) -> dict:
    try:
        return get_container().listing_context_service.listing_context(listing_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.get("/workbench/layers")
def workbench_layers() -> dict:
    return get_layers(get_container().reporting)


app.include_router(api_router)


@app.get("/", include_in_schema=False)
def frontend_index() -> FileResponse:
    if not _FRONTEND_DIST.exists():
        raise HTTPException(status_code=404, detail="frontend_not_built")
    return FileResponse(_FRONTEND_DIST / "index.html")


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_spa(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not_found")
    if not _FRONTEND_DIST.exists():
        raise HTTPException(status_code=404, detail="frontend_not_built")
    requested = (_FRONTEND_DIST / full_path).resolve()
    if not str(requested).startswith(str(_FRONTEND_DIST.resolve())):
        raise HTTPException(status_code=400, detail="invalid_path")
    if requested.exists() and requested.is_file():
        return FileResponse(requested)
    return FileResponse(_FRONTEND_DIST / "index.html")
