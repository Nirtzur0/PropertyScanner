"""
PyTorch Dataset for PropertyFusionModel Training.
Loads listings from the listings repository and encodes on-the-fly or uses cached embeddings.
"""
import json
import re
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import structlog
from PIL import Image
import io
from src.services.feature_sanitizer import sanitize_listing_dict, sanitize_year_built
from src.core.config import DEFAULT_DB_PATH, VECTOR_INDEX_PATH, VECTOR_METADATA_PATH
from src.repositories.listings import ListingsRepository

logger = structlog.get_logger()


class PropertyDataset(Dataset):
    """
    Dataset that loads listings via the listings repository.
    
    Encodes text using SentenceTransformer (cached after first use).
    Uses VLM descriptions if available in the database (no on-the-fly generation).
    Samples comparables using a two-stage filter:
    1) Geo radius filter
    2) Property type + size compatibility
    """
    def __init__(
        self,
        db_path: str = str(DEFAULT_DB_PATH),
        num_comps: int = 5,
        cache_embeddings: bool = True,
        text_model: str = "all-MiniLM-L6-v2",
        use_vlm: bool = True,
        listing_type: str = "sale",
        label_source: str = "ask",
        min_price: float = 10_000,
        max_price: float = 15_000_000,
        geo_radius_km: float = 5.0,
        size_ratio_tolerance: float = 0.2,
        require_same_property_type: bool = True,
        time_safe_comps: bool = True,
        normalize_to: str = "latest",
        use_retriever: bool = False,
        retriever_index_path: str = str(VECTOR_INDEX_PATH),
        retriever_metadata_path: str = str(VECTOR_METADATA_PATH),
        retriever_model_name: str = "all-MiniLM-L6-v2",
        retriever_vlm_policy: str = "gated",
        require_hedonic: bool = True
    ):
        """
        Args:
            db_path: Path to database with listings table
            num_comps: Number of comparables to sample per target
            cache_embeddings: Cache text embeddings in memory
            text_model: SentenceTransformer model name
            min_price: Minimum price to include (filter outliers)
            max_price: Maximum price to include (filter outliers)
            geo_radius_km: Geo radius (km) for stage-1 filtering
            size_ratio_tolerance: Allowed +/- ratio for sqm compatibility
            require_same_property_type: Require same property_type for comps
            time_safe_comps: Enforce comp dates <= target date
            normalize_to: "latest", "none", or ISO date for hedonic normalization
            use_retriever: Use FAISS retriever for comps (frozen distribution)
            retriever_*: Retriever config (model/index/metadata/policy)
            require_hedonic: Drop samples if hedonic normalization fails
        """
        self.db_path = db_path
        self.num_comps = num_comps
        self.cache_embeddings = cache_embeddings
        self.use_vlm = use_vlm
        self.listing_type = listing_type
        self.label_source = label_source
        self.min_price = min_price
        self.max_price = max_price
        self.geo_radius_km = float(geo_radius_km)
        self.size_ratio_tolerance = float(size_ratio_tolerance)
        self.require_same_property_type = bool(require_same_property_type)
        self.time_safe_comps = bool(time_safe_comps)
        self.normalize_to = normalize_to
        self.use_retriever = bool(use_retriever)
        self.retriever_index_path = retriever_index_path
        self.retriever_metadata_path = retriever_metadata_path
        self.retriever_model_name = retriever_model_name
        self.retriever_vlm_policy = retriever_vlm_policy
        self.require_hedonic = bool(require_hedonic)
        
        # Load encoder
        from src.services.encoders import TextEncoder, TabularEncoder
        self.text_encoder = TextEncoder(model_name=text_model)
        self.tabular_encoder = TabularEncoder()

        self.hedonic = None
        if self.normalize_to and self.normalize_to != "none":
            from src.services.hedonic_index import HedonicIndexService
            self.hedonic = HedonicIndexService(db_path=self.db_path)

        self.retriever = None
        if self.use_retriever:
            from src.services.retrieval import CompRetriever
            self.retriever = CompRetriever(
                index_path=self.retriever_index_path,
                metadata_path=self.retriever_metadata_path,
                model_name=self.retriever_model_name,
                strict_model_match=True,
                vlm_policy=self.retriever_vlm_policy
            )
        
        # Load all listings from database
        self.listings = self._load_listings()
        self._listing_by_id = {l["id"]: l for l in self.listings}
        self._index_by_id = {l["id"]: i for i, l in enumerate(self.listings)}

        self.reference_date = self._resolve_reference_date()

        # Build geo index + precompute eligible comps
        self._spatial_index: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        self._bucket_size_deg = self._deg_per_km() * max(self.geo_radius_km, 0.01)
        self._build_spatial_index()
        self._comp_candidates: Dict[int, List[Tuple[int, float]]] = {}
        self._eligible_indices: List[int] = []
        self._baseline_cache: Dict[int, float] = {}
        self._target_adj_cache: Dict[int, float] = {}
        self._build_comp_candidates()
        
        # Cache for embeddings
        self._embedding_cache: Dict[str, np.ndarray] = {}
        
        logger.info("dataset_initialized", 
                   db_path=db_path, 
                   num_listings=len(self.listings),
                   eligible_listings=len(self._eligible_indices),
                   vlm_enabled=use_vlm,
                   listing_type=self.listing_type,
                   label_source=self.label_source,
                   price_range=(self.min_price, self.max_price),
                   geo_radius_km=self.geo_radius_km,
                   size_ratio_tolerance=self.size_ratio_tolerance,
                   require_same_property_type=self.require_same_property_type,
                   time_safe_comps=self.time_safe_comps,
                   normalize_to=self.normalize_to,
                   reference_date=self.reference_date.isoformat() if self.reference_date else None,
                   use_retriever=self.use_retriever)
        
        # Fit tabular encoder on the data for proper normalization
        self._fit_tabular_encoder()
    
    def _load_listings(self) -> List[Dict[str, Any]]:
        """Load all valid listings from the listings repository."""
        repo = ListingsRepository(db_path=self.db_path)
        raw_listings = repo.load_listings_for_training(
            listing_type=self.listing_type,
            label_source=self.label_source,
        )
        
        # Filter outliers
        valid_listings = []
        dropped_count = 0
        for l in raw_listings:
            p = l.get("price", 0)
            if self.min_price <= p <= self.max_price:
                valid_listings.append(sanitize_listing_dict(l))
            else:
                dropped_count += 1
                
        if dropped_count > 0:
            logger.warning("outliers_dropped", count=dropped_count, min_price=self.min_price, max_price=self.max_price)

        deduped: Dict[str, Dict[str, Any]] = {}
        duplicates = 0
        for l in valid_listings:
            l["property_type"] = self._normalize_property_type(l.get("property_type"))
            l["obs_date"] = self._listing_observed_date(l)
            l["_dedupe_key"] = self._dedupe_key(l)
            key = l["_dedupe_key"]
            if key in deduped:
                duplicates += 1
                existing = deduped[key]
                if self._prefer_listing(l, existing):
                    deduped[key] = l
            else:
                deduped[key] = l

        if duplicates > 0:
            logger.info("duplicate_listings_dropped", count=duplicates)

        return list(deduped.values())

    def _normalize_property_type(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if "." in text:
            text = text.split(".")[-1]
        text = text.lower()
        return text or None

    def _parse_dt(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo else value
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            return None

    def _listing_observed_date(self, listing: Dict[str, Any]) -> Optional[datetime]:
        sold_at = self._parse_dt(listing.get("sold_at"))
        listed_at = self._parse_dt(listing.get("listed_at"))
        updated_at = self._parse_dt(listing.get("updated_at"))
        if self.label_source == "sold" and sold_at:
            return sold_at
        return listed_at or updated_at or sold_at

    def _dedupe_key(self, listing: Dict[str, Any]) -> str:
        source = listing.get("source_id") or ""
        external = listing.get("external_id")
        if external:
            return f"{source}:{external}"
        url = listing.get("url")
        if url:
            return str(url)
        return str(listing.get("id"))

    def _prefer_listing(self, candidate: Dict[str, Any], existing: Dict[str, Any]) -> bool:
        cand_dt = candidate.get("obs_date") or self._listing_observed_date(candidate)
        exist_dt = existing.get("obs_date") or self._listing_observed_date(existing)
        if cand_dt and exist_dt:
            return cand_dt > exist_dt
        if cand_dt and not exist_dt:
            return True
        if exist_dt and not cand_dt:
            return False
        return False

    def _resolve_reference_date(self) -> Optional[datetime]:
        if not self.normalize_to or self.normalize_to == "none":
            return None
        if self.normalize_to == "latest":
            dates = [l.get("obs_date") for l in self.listings if l.get("obs_date")]
            return max(dates) if dates else None
        # ISO date string
        return self._parse_dt(self.normalize_to)
    
    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
             # Handle special cases if needed (e.g. 'semisotano' -> -1)
             if isinstance(value, str) and 'sota' in value.lower():
                 return -1.0
             return default
    
    def _fit_tabular_encoder(self):
        """Fit tabular encoder on all listings for proper normalization."""
        feature_dicts = []
        for listing in self.listings:
            # NOTE: price is NOT included - it's the target variable
            area = self._safe_float(listing.get("surface_area_sqm"), default=0.0)
            price = self._safe_float(listing.get("price"), default=0.0)
            price_per_sqm = price / area if area > 0 else 0.0
            features = {
                "bedrooms": self._safe_float(listing.get("bedrooms")),
                "bathrooms": self._safe_float(listing.get("bathrooms")),
                "surface_area_sqm": area,
                "year_built": self._safe_float(self._extract_year_built(listing)),
                "floor": self._safe_float(listing.get("floor")),
                "lat": self._safe_float(listing.get("lat")),
                "lon": self._safe_float(listing.get("lon")),
                "text_sentiment": self._safe_float(listing.get("text_sentiment")),
                "image_sentiment": self._safe_float(listing.get("image_sentiment")),
                "has_elevator": 1.0 if listing.get("has_elevator") else 0.0,
                "price_per_sqm": price_per_sqm,
            }
            feature_dicts.append(features)
        
        self.tabular_encoder.fit(feature_dicts)
        logger.info("tabular_encoder_fitted", num_samples=len(feature_dicts))

    def _region_id(self, listing: Dict[str, Any]) -> Optional[str]:
        city = listing.get("city")
        if not city:
            return None
        return str(city).lower().strip()

    def _label_weight(self, listing: Dict[str, Any]) -> float:
        status = str(listing.get("status") or "").lower()
        if status == "sold":
            return 1.0
        if self.label_source == "sold":
            return 0.0
        listed_at = listing.get("obs_date")
        updated_at = self._parse_dt(listing.get("updated_at"))
        if listed_at and updated_at and updated_at > listed_at:
            return 0.7
        return 0.5

    def _time_normalize_price(
        self,
        raw_price: float,
        region_id: Optional[str],
        obs_date: Optional[datetime]
    ) -> Optional[float]:
        if raw_price <= 0:
            return None
        if not self.reference_date or not self.hedonic:
            return float(raw_price)
        if not region_id or not obs_date:
            if self.require_hedonic:
                return None
            return float(raw_price)
        try:
            adj_price, _, meta = self.hedonic.adjust_comp_price(
                raw_price=raw_price,
                region_id=region_id,
                comp_timestamp=obs_date,
                target_timestamp=self.reference_date
            )
            if meta.get("comp_index_fallback") or meta.get("target_index_fallback"):
                if self.require_hedonic:
                    return None
            return float(adj_price)
        except Exception:
            if self.require_hedonic:
                return None
            return float(raw_price)

    def _robust_baseline(self, values: np.ndarray, weights: np.ndarray) -> Optional[float]:
        if len(values) == 0:
            return None
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        if mad <= 0:
            mad = max(median * 0.05, 1.0)
        mask = np.abs(values - median) <= (3.0 * mad)
        if mask.sum() < max(1, min(self.num_comps, len(values))):
            return None
        values = values[mask]
        weights = weights[mask]
        weight_sum = float(weights.sum())
        if weight_sum <= 0:
            weights = np.ones_like(values) / len(values)
        else:
            weights = weights / weight_sum
        order = np.argsort(values)
        cum = np.cumsum(weights[order])
        idx = int(np.searchsorted(cum, 0.5))
        return float(values[order][min(idx, len(values) - 1)])

    def _is_vlm_safe(self, text: str) -> bool:
        if not text:
            return False
        cleaned = str(text).strip()
        if len(cleaned) < 30 or len(cleaned) > 600:
            return False
        lower = cleaned.lower()
        for bad in ("no image", "image not available", "unknown", "n/a", "not provided", "no description"):
            if bad in lower:
                return False
        tokens = [t for t in re.split(r"[^a-z0-9]+", lower) if t]
        if len(tokens) < 5:
            return False
        uniq_ratio = len(set(tokens)) / max(len(tokens), 1)
        return uniq_ratio >= 0.4
    
    def _extract_year_built(self, listing: Dict) -> int:
        """Extract year_built from listing, with fallback estimation."""
        # Try direct field first (if it exists in the DB)
        if listing.get("year_built"):
            year = sanitize_year_built(listing.get("year_built"))
            if year:
                return year
        
        # Estimate from listed_at date (assume ~10 years old on average)
        listed_at = listing.get("listed_at")
        if listed_at:
            try:
                from datetime import datetime
                if isinstance(listed_at, str):
                    year = datetime.fromisoformat(listed_at.replace('Z', '+00:00')).year
                else:
                    year = listed_at.year
                est_year = year - 10  # Estimate built 10 years before listing
                sanitized = sanitize_year_built(est_year)
                if sanitized:
                    return sanitized
            except:
                pass
        
        # Default to 2015 (reasonable modern estimate)
        return 2015

    def _deg_per_km(self) -> float:
        # Approximate conversion at the equator.
        return 1.0 / 110.0

    def _bucket_key(self, lat: float, lon: float) -> Tuple[int, int]:
        from math import floor
        return (
            int(floor(lat / self._bucket_size_deg)),
            int(floor(lon / self._bucket_size_deg)),
        )

    def _build_spatial_index(self) -> None:
        for idx, listing in enumerate(self.listings):
            lat = listing.get("lat")
            lon = listing.get("lon")
            if lat is None or lon is None:
                continue
            self._spatial_index[self._bucket_key(lat, lon)].append(idx)

    def _retriever_candidates(self, target_idx: int) -> List[Tuple[int, float]]:
        target = self.listings[target_idx]
        if not self.retriever:
            return []

        target_date = target.get("obs_date")
        max_date = target_date if self.time_safe_comps else None

        from src.core.domain.schema import CanonicalListing, GeoLocation

        loc = None
        if target.get("lat") is not None and target.get("lon") is not None:
            loc = GeoLocation(
                lat=target.get("lat"),
                lon=target.get("lon"),
                address_full=target.get("title") or "",
                city=target.get("city") or "Unknown",
                country="ES",
            )

        prop_type = target.get("property_type") or "apartment"
        if prop_type not in ("apartment", "house", "land", "commercial", "other"):
            prop_type = "other"

        target_listing = CanonicalListing(
            id=str(target.get("id")),
            source_id=str(target.get("source_id") or "unknown"),
            external_id=str(target.get("external_id") or target.get("id")),
            url=target.get("url") or "http://example.invalid",
            title=target.get("title") or "listing",
            description=target.get("description"),
            price=target.get("price") or 0.0,
            currency="EUR",
            listing_type=target.get("listing_type") or "sale",
            property_type=prop_type,
            bedrooms=target.get("bedrooms"),
            bathrooms=target.get("bathrooms"),
            surface_area_sqm=target.get("surface_area_sqm"),
            floor=target.get("floor"),
            has_elevator=target.get("has_elevator"),
            location=loc,
            image_urls=[],
            vlm_description=target.get("vlm_description"),
            text_sentiment=target.get("text_sentiment"),
            image_sentiment=target.get("image_sentiment"),
            listed_at=target.get("listed_at"),
            updated_at=target.get("updated_at"),
            status=target.get("status") or "active",
        )

        comps = self.retriever.retrieve_comps(
            target=target_listing,
            k=max(self.num_comps, 10),
            max_radius_km=self.geo_radius_km,
            exclude_self=True,
            strict_filters=True,
            listing_type=self.listing_type if self.listing_type != "all" else None,
            max_listed_at=max_date,
            exclude_duplicate_external=True
        )

        target_key = target.get("_dedupe_key")
        results: List[Tuple[int, float]] = []
        for comp in comps:
            comp_row = self._listing_by_id.get(comp.id)
            if not comp_row:
                continue
            if comp_row.get("_dedupe_key") == target_key:
                continue
            if self.time_safe_comps and target_date:
                comp_date = comp_row.get("obs_date")
                if not comp_date or comp_date > target_date:
                    continue
            idx = self._index_by_id.get(comp.id)
            if idx is None:
                continue
            weight = comp.similarity_score or 0.0
            results.append((idx, weight))

        return results

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import radians, sin, cos, sqrt, atan2
        r = 6371.0
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return r * c

    def _geo_candidates(self, target_idx: int) -> List[Tuple[int, float]]:
        target = self.listings[target_idx]
        lat = target.get("lat")
        lon = target.get("lon")
        if lat is None or lon is None:
            return []
        if self.geo_radius_km <= 0:
            return []

        from math import floor, cos, radians
        lat_delta = self.geo_radius_km * self._deg_per_km()
        lon_delta = self.geo_radius_km * (1.0 / (111.0 * max(cos(radians(lat)), 0.1)))

        min_lat = lat - lat_delta
        max_lat = lat + lat_delta
        min_lon = lon - lon_delta
        max_lon = lon + lon_delta

        min_lat_bucket = int(floor(min_lat / self._bucket_size_deg))
        max_lat_bucket = int(floor(max_lat / self._bucket_size_deg))
        min_lon_bucket = int(floor(min_lon / self._bucket_size_deg))
        max_lon_bucket = int(floor(max_lon / self._bucket_size_deg))

        candidates: List[int] = []
        for lat_bucket in range(min_lat_bucket, max_lat_bucket + 1):
            for lon_bucket in range(min_lon_bucket, max_lon_bucket + 1):
                candidates.extend(self._spatial_index.get((lat_bucket, lon_bucket), []))

        results: List[Tuple[int, float]] = []
        for idx in candidates:
            if idx == target_idx:
                continue
            cand = self.listings[idx]
            c_lat = cand.get("lat")
            c_lon = cand.get("lon")
            if c_lat is None or c_lon is None:
                continue
            dist_km = self._haversine_km(lat, lon, c_lat, c_lon)
            if dist_km <= self.geo_radius_km:
                results.append((idx, dist_km))
        return results

    def _filter_candidates(self, target_idx: int, candidates: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        target = self.listings[target_idx]
        target_type = target.get("property_type")
        target_sqm = self._safe_float(target.get("surface_area_sqm"), default=0.0)
        target_date = target.get("obs_date")
        target_key = target.get("_dedupe_key")
        if target_sqm <= 0:
            return []
        if self.require_same_property_type and not target_type:
            return []

        results: List[Tuple[int, float]] = []
        min_ratio = 1.0 - self.size_ratio_tolerance
        max_ratio = 1.0 + self.size_ratio_tolerance
        for idx, dist_km in candidates:
            cand = self.listings[idx]
            if cand.get("_dedupe_key") == target_key:
                continue
            if self.time_safe_comps and target_date:
                cand_date = cand.get("obs_date")
                if not cand_date or cand_date > target_date:
                    continue
            cand_type = cand.get("property_type")
            if self.require_same_property_type:
                if not cand_type or cand_type != target_type:
                    continue
            cand_sqm = self._safe_float(cand.get("surface_area_sqm"), default=0.0)
            if cand_sqm <= 0:
                continue
            ratio = cand_sqm / target_sqm
            if ratio < min_ratio or ratio > max_ratio:
                continue
            results.append((idx, dist_km))
        return results

    def _build_comp_candidates(self) -> None:
        if self.geo_radius_km <= 0:
            logger.error("invalid_geo_radius", geo_radius_km=self.geo_radius_km)
            return

        missing_geo = 0
        missing_size = 0
        insufficient = 0
        missing_hedonic = 0
        baseline_failed = 0
        for idx, listing in enumerate(self.listings):
            if listing.get("lat") is None or listing.get("lon") is None:
                missing_geo += 1
                continue
            if self._safe_float(listing.get("surface_area_sqm"), default=0.0) <= 0:
                missing_size += 1
                continue
            target_date = listing.get("obs_date")
            region_id = self._region_id(listing)
            target_price_adj = self._time_normalize_price(float(listing.get("price", 0)), region_id, target_date)
            if target_price_adj is None or target_price_adj <= 0:
                missing_hedonic += 1
                continue

            if self.use_retriever and self.retriever:
                filtered = self._retriever_candidates(idx)
            else:
                geo_candidates = self._geo_candidates(idx)
                filtered = self._filter_candidates(idx, geo_candidates)

            if len(filtered) < self.num_comps:
                insufficient += 1
                continue
            filtered.sort(key=lambda item: item[1], reverse=self.use_retriever)

            comp_prices_adj = []
            weights = []
            used = []
            for comp_idx, metric in filtered:
                comp = self.listings[comp_idx]
                comp_date = comp.get("obs_date")
                comp_price_adj = self._time_normalize_price(float(comp.get("price", 0)), region_id, comp_date)
                if comp_price_adj is None:
                    continue
                comp_prices_adj.append(comp_price_adj)
                weights.append(metric)
                used.append((comp_idx, metric))
                if len(comp_prices_adj) >= self.num_comps:
                    break

            if len(comp_prices_adj) < self.num_comps:
                baseline_failed += 1
                continue

            weights_arr = np.array(weights, dtype=float)
            if not self.use_retriever:
                weights_arr = 1.0 / (1.0 + np.maximum(weights_arr, 0.0))

            baseline = self._robust_baseline(np.array(comp_prices_adj, dtype=float), weights_arr)
            if baseline is None or baseline <= 0:
                baseline_failed += 1
                continue

            self._comp_candidates[idx] = used
            self._eligible_indices.append(idx)
            self._baseline_cache[idx] = baseline
            self._target_adj_cache[idx] = target_price_adj

        logger.info(
            "comp_candidate_build",
            total=len(self.listings),
            eligible=len(self._eligible_indices),
            missing_geo=missing_geo,
            missing_size=missing_size,
            insufficient=insufficient,
            missing_hedonic=missing_hedonic,
            baseline_failed=baseline_failed
        )

        if not self._eligible_indices:
            raise ValueError("No eligible listings with enough comps. Adjust geo radius or size tolerance.")
    
    def _get_text_embedding(self, listing: Dict) -> np.ndarray:
        """Get text embedding for a listing (cached). Includes VLM description if available."""
        listing_id = listing["id"]
        
        if self.cache_embeddings and listing_id in self._embedding_cache:
            return self._embedding_cache[listing_id]
        
        # Combine text fields
        title = listing.get("title") or ""
        description = listing.get("description") or ""
        
        # Get VLM description (from database)
        vlm_desc = ""
        if self.use_vlm and self.retriever_vlm_policy != "off":
            raw_vlm = listing.get("vlm_description") or ""
            if self._is_vlm_safe(raw_vlm):
                vlm_desc = raw_vlm
        
        # Combine all text
        text = f"{title}. {description} {vlm_desc}".strip()
        
        if not text:
            text = "Property listing"
        
        embedding = self.text_encoder.encode_single(text)
        
        if self.cache_embeddings:
            self._embedding_cache[listing_id] = embedding
        
        return embedding
    
    def _get_tabular_features(self, listing: Dict) -> np.ndarray:
        """Extract normalized tabular features (excluding price - that's the target)."""
        features = {
            "bedrooms": self._safe_float(listing.get("bedrooms")),
            "bathrooms": self._safe_float(listing.get("bathrooms")),
            "surface_area_sqm": self._safe_float(listing.get("surface_area_sqm")),
            "year_built": self._safe_float(self._extract_year_built(listing)),
            "floor": self._safe_float(listing.get("floor")),
            "lat": self._safe_float(listing.get("lat")),
            "lon": self._safe_float(listing.get("lon")),
            "text_sentiment": self._safe_float(listing.get("text_sentiment")),
            "image_sentiment": self._safe_float(listing.get("image_sentiment")),
            "has_elevator": 1.0 if listing.get("has_elevator") else 0.0,
            "price_per_sqm": 0.0,  # Will be computed from comps during inference
        }
        return self.tabular_encoder.encode(features)
    
    def __len__(self) -> int:
        return len(self._eligible_indices)
    
    def _sample_comps(self, target_idx: int) -> List[Tuple[int, float]]:
        """Sample comparable indices, excluding the target."""
        candidates = self._comp_candidates.get(target_idx, [])
        return candidates[: self.num_comps]
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        target_idx = self._eligible_indices[idx]
        target = self.listings[target_idx]
        
        # Sample comparables
        comp_entries = self._sample_comps(target_idx)
        comp_indices = [i for i, _ in comp_entries]
        comp_weights = [w for _, w in comp_entries]
        comps = [self.listings[i] for i in comp_indices]

        # Build tensors
        target_text = torch.from_numpy(self._get_text_embedding(target)).float()
        target_tab = torch.from_numpy(self._get_tabular_features(target)).float()
        target_price_raw = float(target["price"])

        comp_text = torch.stack([torch.from_numpy(self._get_text_embedding(c)).float() for c in comps])
        comp_tab = torch.stack([torch.from_numpy(self._get_tabular_features(c)).float() for c in comps])

        target_date = target.get("obs_date")
        region_id = self._region_id(target)
        target_price_adj = self._target_adj_cache.get(target_idx)
        if target_price_adj is None:
            target_price_adj = self._time_normalize_price(target_price_raw, region_id, target_date)
        if target_price_adj is None or target_price_adj <= 0:
            raise ValueError("invalid_target_price_adjusted")

        comp_prices_adj = []
        for comp in comps:
            comp_date = comp.get("obs_date")
            comp_price_adj = self._time_normalize_price(float(comp["price"]), region_id, comp_date)
            if comp_price_adj is None:
                comp_price_adj = float(comp["price"])
            comp_prices_adj.append(comp_price_adj)

        baseline = self._baseline_cache.get(target_idx)
        if baseline is None:
            weights = np.array(comp_weights, dtype=float)
            if not self.use_retriever:
                weights = 1.0 / (1.0 + np.maximum(weights, 0.0))
            baseline = self._robust_baseline(np.array(comp_prices_adj, dtype=float), weights)
        if baseline is None or baseline <= 0:
            raise ValueError("invalid_comp_baseline")

        target_log = float(np.log(target_price_adj))
        baseline_log = float(np.log(baseline))
        target_residual = target_log - baseline_log
        label_weight = self._label_weight(target)

        comp_prices = torch.tensor(comp_prices_adj, dtype=torch.float32)
        target_price = torch.tensor(target_residual, dtype=torch.float32)
        
        return {
            "target_text": target_text,
            "target_tab": target_tab,
            "target_price": target_price,
            "comp_text": comp_text,
            "comp_tab": comp_tab,
            "comp_prices": comp_prices,
            "num_comps": len(comps),
            "baseline_price": torch.tensor(baseline, dtype=torch.float32),
            "label_weight": torch.tensor(label_weight, dtype=torch.float32),
            "target_price_adj": torch.tensor(target_price_adj, dtype=torch.float32)
        }


def collate_fn(batch: List[Dict]) -> Dict[str, torch.Tensor]:
    """
    Custom collate function to handle variable number of comps.
    Pads to the maximum number of comps in the batch.
    """
    max_comps = max(b["num_comps"] for b in batch)
    batch_size = len(batch)
    
    text_dim = batch[0]["target_text"].shape[0]
    tab_dim = batch[0]["target_tab"].shape[0]
    
    target_text = torch.stack([b["target_text"] for b in batch])
    target_tab = torch.stack([b["target_tab"] for b in batch])
    target_price = torch.stack([b["target_price"] for b in batch])
    baseline_price = torch.stack([b["baseline_price"] for b in batch])
    label_weight = torch.stack([b["label_weight"] for b in batch])
    target_price_adj = torch.stack([b["target_price_adj"] for b in batch])
    
    comp_text = torch.zeros(batch_size, max_comps, text_dim)
    comp_tab = torch.zeros(batch_size, max_comps, tab_dim)
    comp_prices = torch.zeros(batch_size, max_comps)
    comp_mask = torch.zeros(batch_size, max_comps, dtype=torch.bool)
    
    for i, b in enumerate(batch):
        n = b["num_comps"]
        comp_text[i, :n] = b["comp_text"]
        comp_tab[i, :n] = b["comp_tab"]
        comp_prices[i, :n] = b["comp_prices"]
        comp_mask[i, :n] = True
    
    return {
        "target_text": target_text,
        "target_tab": target_tab,
        "target_price": target_price,
        "comp_text": comp_text,
        "comp_tab": comp_tab,
        "comp_prices": comp_prices,
        "comp_mask": comp_mask,
        "baseline_price": baseline_price,
        "label_weight": label_weight,
        "target_price_adj": target_price_adj
    }


def create_dataloaders(
    db_path: str = str(DEFAULT_DB_PATH),
    batch_size: int = 32,
    num_comps: int = 5,
    val_split: float = 0.1,
    num_workers: int = 0,
    use_vlm: bool = True,
    listing_type: str = "sale",
    label_source: str = "ask",
    time_safe_comps: bool = True,
    normalize_to: str = "latest",
    use_retriever: bool = True,
    retriever_index_path: str = str(VECTOR_INDEX_PATH),
    retriever_metadata_path: str = str(VECTOR_METADATA_PATH),
    retriever_model_name: str = "all-MiniLM-L6-v2",
    retriever_vlm_policy: str = "gated"
) -> Tuple[DataLoader, Optional[DataLoader]]:
    """
    Create train and validation dataloaders from the database.
    
    Args:
        db_path: Path to SQLite database
        batch_size: Batch size for training
        num_comps: Number of comparables per sample
        val_split: Fraction of data to use for validation
        num_workers: Number of data loading workers
        use_vlm: Whether to use VLM for image descriptions
    """
    dataset = PropertyDataset(
        db_path=db_path,
        num_comps=num_comps,
        use_vlm=use_vlm,
        listing_type=listing_type,
        label_source=label_source,
        time_safe_comps=time_safe_comps,
        normalize_to=normalize_to,
        use_retriever=use_retriever,
        retriever_index_path=retriever_index_path,
        retriever_metadata_path=retriever_metadata_path,
        retriever_model_name=retriever_model_name,
        retriever_vlm_policy=retriever_vlm_policy
    )
    
    # Split into train/val
    n = len(dataset)
    n_val = int(n * val_split)
    n_train = n - n_val
    
    train_dataset, val_dataset = torch.utils.data.random_split(
        dataset, [n_train, n_val]
    )
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate_fn,
        num_workers=num_workers
    )
    
    val_loader = None
    if n_val > 0:
        val_loader = DataLoader(
            val_dataset,
            batch_size=batch_size,
            shuffle=False,
            collate_fn=collate_fn,
            num_workers=num_workers
        )
    
    return train_loader, val_loader
