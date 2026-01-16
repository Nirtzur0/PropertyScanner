import structlog
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.services.retrieval import CompRetriever
from src.services.hedonic_index import HedonicIndexService

logger = structlog.get_logger(__name__)

class RentService:
    """
    Consolidated Rent Service.

    Provides:
    1. Simple heuristic estimation (city-level averages) for fast ingestion/fallback.
    2. Robust comparable-based estimation (using retrieval + hedonic adjustment) for valuation.
    """
    def __init__(
        self,
        db_url: str = "sqlite:///data/listings.db",
        retriever: Optional[CompRetriever] = None,
        hedonic: Optional[HedonicIndexService] = None,
        config: Optional[Any] = None
    ):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)

        self.retriever = retriever
        self.hedonic = hedonic
        self.config = config

        # Cache for simple stats
        self.rental_stats: Dict[str, float] = {}
        self._load_simple_stats()

    # =========================================================================
    # PART 1: Simple Estimation (Heuristic)
    # =========================================================================

    def _load_simple_stats(self):
        """
        Loads rental statistics from the database (City-level Avg Price/Sqm).
        """
        session = self.Session()
        try:
            # Query: Avg rent per sqm per city where listing_type='rent'
            rentals = session.query(DBListing).filter(
                DBListing.listing_type == "rent",
                DBListing.surface_area_sqm > 0,
                DBListing.price > 0
            ).all()

            city_data = {}

            for r in rentals:
                if not r.city: continue
                city = r.city.lower().strip()
                if city not in city_data: city_data[city] = []

                # Basic sanity check
                if r.price > 50 and r.price < 50000 and r.surface_area_sqm > 10:
                    psqm = r.price / r.surface_area_sqm
                    city_data[city].append(psqm)

            # IQR Filtering
            for city, values in city_data.items():
                if len(values) < 3: continue
                q1 = np.percentile(values, 25)
                q3 = np.percentile(values, 75)
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                clean = [v for v in values if lower <= v <= upper]
                if clean:
                    self.rental_stats[city] = sum(clean) / len(clean)

            logger.info("rental_stats_loaded", cities=len(self.rental_stats))
        except Exception as e:
            logger.error("rental_stats_load_failed", error=str(e))
        finally:
            session.close()

    def estimate_simple(self, listing: CanonicalListing) -> Optional[float]:
        """
        Estimates monthly rent using city-level averages.
        Fast, no external dependencies (FAISS/Models).
        """
        if not listing.location or not listing.location.city or not listing.surface_area_sqm:
            return None

        city = listing.location.city.lower().strip()
        avg_sqm = self.rental_stats.get(city)

        if not avg_sqm:
             return None

        estimated_rent = avg_sqm * listing.surface_area_sqm
        return round(estimated_rent, 2)

    def calculate_yield(self, price: float, monthly_rent: float) -> float:
        """Calculate Gross Annual Yield %"""
        if price <= 0: return 0.0
        annual_rent = monthly_rent * 12
        return round((annual_rent / price) * 100, 2)

    # =========================================================================
    # PART 2: Robust Estimation (Comparable-Based)
    # =========================================================================

    def estimate_robust(
        self,
        listing: CanonicalListing,
        valuation_date: datetime,
        tracer: Any = None
    ) -> Tuple[float, float, List[CanonicalListing]]:
        """
        Estimates rent using robust comparable rental listings + hedonic adjustment.
        Requires retriever and hedonic service to be initialized.
        """
        if not self.retriever or not self.hedonic:
            raise RuntimeError("robust_estimation_dependencies_missing")

        if not listing.surface_area_sqm or listing.surface_area_sqm <= 0:
             # Fallback to simple if possible? No, robust implies strictness.
             raise ValueError("missing_surface_area_for_rent")

        region_id = listing.location.city.lower() if listing.location and listing.location.city else "unknown"

        # 1. Retrieve Comps
        # Use config defaults if available
        k = getattr(self.config, "K_model", 30)
        radius = getattr(self.config, "rent_radius_km", 2.0)
        min_comps = getattr(self.config, "min_rent_comps", 5)

        comps, similarity_by_id = self._retrieve_rent_comps(
            listing,
            as_of_date=valuation_date,
            k=k,
            radius=radius,
            min_comps=min_comps
        )

        adjusted_rents = []
        adjusted_weights = []
        comps_used = []

        for comp in comps:
            if not comp.surface_area_sqm or comp.surface_area_sqm <= 0:
                continue
            comp_timestamp = comp.listed_at or comp.updated_at
            if not comp_timestamp:
                continue

            # Adjust Rent Price (Time Adjustment)
            try:
                adj_price, adj_factor = self._adjust_rent_price(
                    raw_price=comp.price,
                    region_id=region_id,
                    comp_timestamp=comp_timestamp,
                    target_timestamp=valuation_date,
                )
            except ValueError:
                # Skip if adjustment fails (e.g. missing index)
                continue

            rent_sqm = adj_price / comp.surface_area_sqm
            weight = similarity_by_id.get(comp.id, 0.0)
            if weight <= 0:
                continue

            adjusted_rents.append(rent_sqm)
            adjusted_weights.append(weight)
            comps_used.append(comp)

        if len(adjusted_rents) < min_comps:
             # If robust fails, maybe we could fallback to simple?
             # For now, raise error as per original logic.
            raise ValueError("insufficient_adjusted_rent_comps")

        # Weighted Median / Mean with Outlier Removal
        values = np.array(adjusted_rents, dtype=float)
        weights = np.array(adjusted_weights, dtype=float)

        # MAD Filter
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        if mad <= 0:
            mad = max(median * 0.05, 0.1)

        mask = np.abs(values - median) <= (3.0 * mad)
        values = values[mask]
        weights = weights[mask]
        comps_used = [c for c, keep in zip(comps_used, mask) if keep]

        if len(values) < min_comps:
            raise ValueError("rent_comp_filter_excessive")

        weights = weights / weights.sum()
        est_rent_sqm = float(np.sum(weights * values))
        variance = float(np.sum(weights * (values - est_rent_sqm) ** 2))
        std_rent_sqm = float(np.sqrt(variance))

        if est_rent_sqm <= 0:
            raise ValueError("invalid_rent_estimate")

        est_rent = est_rent_sqm * listing.surface_area_sqm
        uncertainty = std_rent_sqm / est_rent_sqm

        if tracer:
            tracer.log("rental_valuation", {
                "est_rent": est_rent,
                "comps_count": len(comps_used),
                "avg_sqm": est_rent_sqm
            })

        return est_rent, uncertainty, comps_used

    def _retrieve_rent_comps(
        self,
        listing: CanonicalListing,
        as_of_date: Optional[datetime],
        k: int,
        radius: float,
        min_comps: int
    ) -> Tuple[List[CanonicalListing], Dict[str, float]]:
        """Retrieve and hydrate rental comps."""
        comps = self.retriever.retrieve_comps(
            target=listing,
            k=k,
            max_radius_km=radius,
            listing_type="rent",
            max_listed_at=as_of_date,
            exclude_duplicate_external=True
        )
        if len(comps) < min_comps:
            raise ValueError("insufficient_rent_comps")

        similarity_by_id = {c.id: c.similarity_score for c in comps}
        ids = [c.id for c in comps]

        session = self.Session()
        try:
            rows = (
                session.query(DBListing)
                .filter(DBListing.id.in_(ids))
                .filter(DBListing.listing_type == "rent")
                .all()
            )
        finally:
            session.close()

        by_id = {r.id: r for r in rows}
        hydrated = []
        for comp_id in ids:
            row = by_id.get(comp_id)
            if row:
                hydrated.append(self._db_to_canonical(row))

        if len(hydrated) < min_comps:
            raise ValueError("insufficient_hydrated_rent_comps")

        return hydrated, similarity_by_id

    def _adjust_rent_price(
        self,
        raw_price: float,
        region_id: str,
        comp_timestamp: datetime,
        target_timestamp: datetime,
    ) -> Tuple[float, float]:
        """Adjust rent price using Market Index (Rent Index)."""
        comp_month = comp_timestamp.strftime("%Y-%m")
        target_month = target_timestamp.strftime("%Y-%m")

        # We query the market_indices table directly
        comp_index = self._get_market_index_value(region_id, comp_month, "rent_index_sqm")
        target_index = self._get_market_index_value(region_id, target_month, "rent_index_sqm")

        factor = target_index / comp_index
        if factor <= 0:
            raise ValueError("invalid_rent_adjustment_factor")
        # Sanity bounds
        if factor < 0.5 or factor > 2.0:
             # If index swing is too wild, it's suspicious
            raise ValueError("rent_adjustment_out_of_bounds")

        return raw_price * factor, factor

    def _get_market_index_value(self, region_id: str, month_key: str, column: str) -> float:
        """Helper to get index value from DB."""
        query = text(
            f"""
            SELECT {column}
            FROM market_indices
            WHERE region_id = :region_id AND month_date LIKE :month_key
            ORDER BY month_date DESC
            LIMIT 1
            """
        )

        with self.engine.connect() as conn:
            row = conn.execute(
                query,
                {"region_id": region_id, "month_key": f"{month_key}%"}
            ).fetchone()

        if not row or row[0] is None:
             # Try fallback to "all" region if specific city missing?
             # For now, strict.
            raise ValueError(f"missing_market_index for {region_id} {month_key}")

        value = float(row[0])
        if value <= 0:
            raise ValueError("invalid_market_index")

        return value

    def _db_to_canonical(self, db_item: DBListing) -> CanonicalListing:
        """Convert DBListing to CanonicalListing (Hydration helper)."""
        loc = None
        if db_item.city or db_item.lat or db_item.lon:
            loc = GeoLocation(
                lat=db_item.lat,
                lon=db_item.lon,
                address_full=db_item.address_full or db_item.title,
                city=db_item.city or "Unknown",
                country="ES",
            )

        # Helper helpers
        def _to_int(v):
             try: return int(float(v)) if v is not None else None
             except: return None
        def _to_float(v):
             try: return float(v) if v is not None else None
             except: return None
        def _norm_prop(v):
             if not v: return "apartment"
             s = str(v).strip()
             return s.split(".")[-1].lower() if "." in s else s.lower()

        return CanonicalListing(
            id=db_item.id,
            source_id=db_item.source_id,
            external_id=db_item.external_id,
            url=str(db_item.url),
            title=db_item.title,
            description=db_item.description,
            price=db_item.price,
            currency=db_item.currency,
            listing_type=getattr(db_item, "listing_type", "sale") or "sale",
            property_type=_norm_prop(db_item.property_type),
            bedrooms=_to_int(db_item.bedrooms),
            bathrooms=_to_int(db_item.bathrooms),
            surface_area_sqm=_to_float(db_item.surface_area_sqm),
            floor=_to_int(db_item.floor),
            has_elevator=db_item.has_elevator,
            location=loc,
            image_urls=db_item.image_urls or [],
            vlm_description=db_item.vlm_description,
            text_sentiment=db_item.text_sentiment,
            image_sentiment=db_item.image_sentiment,
            analysis_meta=db_item.analysis_meta,
            listed_at=db_item.listed_at,
            updated_at=db_item.updated_at,
            status=db_item.status,
            tags=db_item.tags or [],
        )
