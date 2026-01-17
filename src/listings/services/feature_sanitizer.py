from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from src.platform.domain.schema import CanonicalListing

FEATURE_BOUNDS = {
    "bedrooms": (0, 20),
    "bathrooms": (0, 20),
    "surface_area_sqm": (5.0, 5000.0),
    "plot_area_sqm": (5.0, 200000.0),
    "floor": (-5, 200),
}

PRICE_BOUNDS_SALE = (10_000.0, 15_000_000.0)
PRICE_BOUNDS_RENT = (50.0, 50_000.0)
RENT_BOUNDS = (50.0, 50_000.0)
GROSS_YIELD_BOUNDS = (0.1, 30.0)

LAT_BOUNDS = (-90.0, 90.0)
LON_BOUNDS = (-180.0, 180.0)

YEAR_BUILT_MIN = 1800
YEAR_BUILT_MAX_YEARS_AHEAD = 1


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _sanitize_float_range(value: Any, min_value: float, max_value: float) -> Optional[float]:
    val = _coerce_float(value)
    if val is None:
        return None
    if val < min_value or val > max_value:
        return None
    return val


def _sanitize_int_range(value: Any, min_value: int, max_value: int) -> Optional[int]:
    val = _coerce_int(value)
    if val is None:
        return None
    if val < min_value or val > max_value:
        return None
    return val


def _normalize_listing_type(value: Any) -> str:
    if value is None:
        return "sale"
    text = str(value).strip().lower()
    return text or "sale"


def _price_bounds_for_listing(listing_type: Any) -> Tuple[float, float]:
    if _normalize_listing_type(listing_type) == "rent":
        return PRICE_BOUNDS_RENT
    return PRICE_BOUNDS_SALE


def sanitize_year_built(value: Any) -> Optional[int]:
    max_year = datetime.utcnow().year + YEAR_BUILT_MAX_YEARS_AHEAD
    return _sanitize_int_range(value, YEAR_BUILT_MIN, max_year)


def sanitize_listing_features(listing: CanonicalListing) -> CanonicalListing:
    price_min, price_max = _price_bounds_for_listing(listing.listing_type)
    listing.price = _sanitize_float_range(listing.price, price_min, price_max)
    listing.estimated_rent = _sanitize_float_range(listing.estimated_rent, *RENT_BOUNDS)
    listing.gross_yield = _sanitize_float_range(listing.gross_yield, *GROSS_YIELD_BOUNDS)
    listing.sold_price = _sanitize_float_range(listing.sold_price, *PRICE_BOUNDS_SALE)
    listing.bedrooms = _sanitize_int_range(listing.bedrooms, *FEATURE_BOUNDS["bedrooms"])
    listing.bathrooms = _sanitize_int_range(listing.bathrooms, *FEATURE_BOUNDS["bathrooms"])
    listing.surface_area_sqm = _sanitize_float_range(
        listing.surface_area_sqm, *FEATURE_BOUNDS["surface_area_sqm"]
    )
    listing.plot_area_sqm = _sanitize_float_range(
        listing.plot_area_sqm, *FEATURE_BOUNDS["plot_area_sqm"]
    )
    listing.floor = _sanitize_int_range(listing.floor, *FEATURE_BOUNDS["floor"])

    if listing.location:
        lat = _sanitize_float_range(listing.location.lat, *LAT_BOUNDS)
        lon = _sanitize_float_range(listing.location.lon, *LON_BOUNDS)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            listing.location.lat = None
            listing.location.lon = None
        else:
            listing.location.lat = lat
            listing.location.lon = lon

    return listing


def sanitize_listing_dict(listing: Dict[str, Any]) -> Dict[str, Any]:
    if not listing:
        return listing

    data = dict(listing)
    price_min, price_max = _price_bounds_for_listing(data.get("listing_type"))
    data["price"] = _sanitize_float_range(data.get("price"), price_min, price_max)
    data["estimated_rent"] = _sanitize_float_range(data.get("estimated_rent"), *RENT_BOUNDS)
    data["gross_yield"] = _sanitize_float_range(data.get("gross_yield"), *GROSS_YIELD_BOUNDS)
    data["sold_price"] = _sanitize_float_range(data.get("sold_price"), *PRICE_BOUNDS_SALE)
    data["bedrooms"] = _sanitize_int_range(data.get("bedrooms"), *FEATURE_BOUNDS["bedrooms"])
    data["bathrooms"] = _sanitize_int_range(data.get("bathrooms"), *FEATURE_BOUNDS["bathrooms"])
    data["surface_area_sqm"] = _sanitize_float_range(
        data.get("surface_area_sqm"), *FEATURE_BOUNDS["surface_area_sqm"]
    )
    data["plot_area_sqm"] = _sanitize_float_range(
        data.get("plot_area_sqm"), *FEATURE_BOUNDS["plot_area_sqm"]
    )
    data["floor"] = _sanitize_int_range(data.get("floor"), *FEATURE_BOUNDS["floor"])

    location = data.get("location")
    if isinstance(location, dict):
        location = dict(location)
        lat = _sanitize_float_range(location.get("lat"), *LAT_BOUNDS)
        lon = _sanitize_float_range(location.get("lon"), *LON_BOUNDS)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            location["lat"] = None
            location["lon"] = None
        else:
            location["lat"] = lat
            location["lon"] = lon
        data["location"] = location
    else:
        lat = _sanitize_float_range(data.get("lat"), *LAT_BOUNDS)
        lon = _sanitize_float_range(data.get("lon"), *LON_BOUNDS)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            data["lat"] = None
            data["lon"] = None
        else:
            data["lat"] = lat
            data["lon"] = lon

    return data
