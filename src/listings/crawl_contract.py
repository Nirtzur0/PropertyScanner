from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from src.platform.agents.base import AgentResponse


def classify_crawl_status(*, listing_count: int, errors: Sequence[str]) -> str:
    if listing_count > 0 and not errors:
        return "success"
    if listing_count > 0:
        return "partial"

    normalized = [str(error or "") for error in errors if error]
    if any(error.startswith("proxy_required:") for error in normalized):
        return "proxy_required"
    if any(error.startswith("policy_blocked:") for error in normalized):
        return "policy_blocked"
    if any(error.startswith("blocked:") for error in normalized):
        return "blocked"
    if any(error.startswith("fetch_failed:") or error.startswith("browser_task_failed:") for error in normalized):
        return "fetch_failed"
    if any(error == "no_listings_found" for error in normalized):
        return "no_listings_found"
    return "failure"


def primary_block_reason(errors: Sequence[str]) -> str | None:
    for error in errors:
        value = str(error or "")
        if value.startswith("proxy_required:"):
            return value.split(":", 1)[1] if ":" in value else value
        if value.startswith("policy_blocked:"):
            return value.split(":", 2)[1] if ":" in value else value
        if value.startswith("blocked:"):
            return value.split(":", 2)[1] if ":" in value else value
    return None


def field_coverage_metrics(listings: Iterable[Any]) -> Dict[str, float]:
    rows = list(listings)
    total = float(len(rows))
    if total <= 0:
        return {
            "title_coverage_ratio": 0.0,
            "price_coverage_ratio": 0.0,
            "surface_area_coverage_ratio": 0.0,
            "location_coverage_ratio": 0.0,
            "bedrooms_coverage_ratio": 0.0,
            "bathrooms_coverage_ratio": 0.0,
            "image_urls_coverage_ratio": 0.0,
        }

    def ratio(predicate) -> float:
        return round(sum(1 for row in rows if predicate(row)) / total, 6)

    return {
        "title_coverage_ratio": ratio(lambda row: bool(getattr(row, "title", None))),
        "price_coverage_ratio": ratio(lambda row: getattr(row, "price", None) not in (None, 0, 0.0)),
        "surface_area_coverage_ratio": ratio(lambda row: getattr(row, "surface_area_sqm", None) is not None),
        "location_coverage_ratio": ratio(
            lambda row: getattr(row, "location", None) is not None
            and bool(getattr(getattr(row, "location", None), "city", None))
            and bool(getattr(getattr(row, "location", None), "country", None))
        ),
        "bedrooms_coverage_ratio": ratio(lambda row: getattr(row, "bedrooms", None) is not None),
        "bathrooms_coverage_ratio": ratio(lambda row: getattr(row, "bathrooms", None) is not None),
        "image_urls_coverage_ratio": ratio(lambda row: bool(getattr(row, "image_urls", None))),
    }


def invalid_listing_metrics(listings: Iterable[Any]) -> Dict[str, float]:
    rows = list(listings)
    total = float(len(rows))
    if total <= 0:
        return {
            "invalid_price_ratio": 0.0,
            "invalid_surface_area_ratio": 0.0,
        }

    invalid_price = 0
    invalid_surface_area = 0
    for row in rows:
        price = getattr(row, "price", None)
        area = getattr(row, "surface_area_sqm", None)
        if price is None or float(price) < 10000 or float(price) > 15000000:
            invalid_price += 1
        if area is None or float(area) < 5 or float(area) > 5000:
            invalid_surface_area += 1

    return {
        "invalid_price_ratio": round(invalid_price / total, 6),
        "invalid_surface_area_ratio": round(invalid_surface_area / total, 6),
    }


def build_crawl_response(
    *,
    listings: Sequence[Any],
    errors: Sequence[str],
    search_pages_attempted: int = 0,
    search_pages_succeeded: int = 0,
    listing_urls_discovered: int = 0,
    listing_urls_fetched: int | None = None,
    search_fetch_ok: bool | None = None,
    extra_metadata: Dict[str, Any] | None = None,
) -> AgentResponse:
    fetched = len(listings) if listing_urls_fetched is None else int(listing_urls_fetched)
    resolved_search_ok = (
        bool(search_pages_succeeded > 0)
        if search_fetch_ok is None
        else bool(search_fetch_ok)
    )
    metadata = {
        "search_fetch_ok": resolved_search_ok,
        "search_block_reason": primary_block_reason(errors),
        "search_pages_attempted": int(search_pages_attempted),
        "search_pages_succeeded": int(search_pages_succeeded),
        "listing_urls_discovered": int(listing_urls_discovered),
        "listing_urls_fetched": fetched,
        "detail_fetch_success_ratio": round(
            fetched / max(int(listing_urls_discovered), 1),
            6,
        ),
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return AgentResponse(
        status=classify_crawl_status(listing_count=len(listings), errors=errors),
        data=list(listings),
        errors=list(errors),
        metadata=metadata,
    )


def detect_block_reason_from_html(html: str | None) -> str | None:
    if not html:
        return None
    lower = str(html).lower()
    if "captcha-delivery.com" in lower or "js.datadome.co" in lower or "datadome" in lower:
        return "datadome_captcha"
    if "cf-chl-" in lower or "attention required" in lower or "cloudflare" in lower:
        return "cloudflare_challenge"
    if "access denied" in lower:
        return "access_denied"
    if "captcha" in lower:
        return "captcha"
    if "challenge" in lower and "verify" in lower:
        return "challenge_page"
    return None
