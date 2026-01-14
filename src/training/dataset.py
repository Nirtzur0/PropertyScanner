"""
PyTorch Dataset for PropertyFusionModel Training.
Loads listings directly from SQLite database and encodes on-the-fly or uses cached embeddings.
"""
import sqlite3
import ast
import json
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict
from pathlib import Path
import structlog
from PIL import Image
import io

logger = structlog.get_logger()


class PropertyDataset(Dataset):
    """
    Dataset that loads listings directly from SQLite database.
    
    Encodes text using SentenceTransformer (cached after first use).
    Uses VLM descriptions if available in the database (no on-the-fly generation).
    Samples comparables using a two-stage filter:
    1) Geo radius filter
    2) Property type + size compatibility
    """
    def __init__(
        self,
        db_path: str = "data/listings.db",
        num_comps: int = 5,
        cache_embeddings: bool = True,
        text_model: str = "all-MiniLM-L6-v2",
        use_vlm: bool = True,
        min_price: float = 10_000,
        max_price: float = 15_000_000,
        geo_radius_km: float = 5.0,
        size_ratio_tolerance: float = 0.2,
        require_same_property_type: bool = True
    ):
        """
        Args:
            db_path: Path to SQLite database with listings table
            num_comps: Number of comparables to sample per target
            cache_embeddings: Cache text embeddings in memory
            text_model: SentenceTransformer model name
            min_price: Minimum price to include (filter outliers)
            max_price: Maximum price to include (filter outliers)
            geo_radius_km: Geo radius (km) for stage-1 filtering
            size_ratio_tolerance: Allowed +/- ratio for sqm compatibility
            require_same_property_type: Require same property_type for comps
        """
        self.db_path = db_path
        self.num_comps = num_comps
        self.cache_embeddings = cache_embeddings
        self.use_vlm = use_vlm
        self.min_price = min_price
        self.max_price = max_price
        self.geo_radius_km = float(geo_radius_km)
        self.size_ratio_tolerance = float(size_ratio_tolerance)
        self.require_same_property_type = bool(require_same_property_type)
        
        # Load encoder
        from src.services.encoders import TextEncoder, TabularEncoder
        self.text_encoder = TextEncoder(model_name=text_model)
        self.tabular_encoder = TabularEncoder()
        
        # Load all listings from database
        self.listings = self._load_listings()

        # Build geo index + precompute eligible comps
        self._spatial_index: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        self._bucket_size_deg = self._deg_per_km() * max(self.geo_radius_km, 0.01)
        self._build_spatial_index()
        self._comp_candidates: Dict[int, List[int]] = {}
        self._eligible_indices: List[int] = []
        self._build_comp_candidates()
        
        # Cache for embeddings
        self._embedding_cache: Dict[str, np.ndarray] = {}
        
        logger.info("dataset_initialized", 
                   db_path=db_path, 
                   num_listings=len(self.listings),
                   eligible_listings=len(self._eligible_indices),
                   vlm_enabled=use_vlm,
                   price_range=(self.min_price, self.max_price),
                   geo_radius_km=self.geo_radius_km,
                   size_ratio_tolerance=self.size_ratio_tolerance,
                   require_same_property_type=self.require_same_property_type)
        
        # Fit tabular encoder on the data for proper normalization
        self._fit_tabular_encoder()
    
    def _load_listings(self) -> List[Dict[str, Any]]:
        """Load all valid listings from SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        # We query all positive prices first, then filter in python to be safe/flexible
        cursor = conn.execute("""
            SELECT id, source_id, title, description, price, city,
                   bedrooms, bathrooms, surface_area_sqm, floor,
                   lat, lon, image_urls, vlm_description, property_type,
                   listed_at, updated_at, text_sentiment, image_sentiment, has_elevator
            FROM listings
            WHERE price > 0
        """)
        
        raw_listings = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Filter outliers
        valid_listings = []
        dropped_count = 0
        for l in raw_listings:
            p = l.get("price", 0)
            if self.min_price <= p <= self.max_price:
                valid_listings.append(l)
            else:
                dropped_count += 1
                
        if dropped_count > 0:
            logger.warning("outliers_dropped", count=dropped_count, min_price=self.min_price, max_price=self.max_price)
            
        for l in valid_listings:
            l["property_type"] = self._normalize_property_type(l.get("property_type"))
        return valid_listings

    def _normalize_property_type(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if "." in text:
            text = text.split(".")[-1]
        text = text.lower()
        return text or None
    
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
                "price_per_sqm": self._safe_float(listing.get("price")) / max(self._safe_float(listing.get("surface_area_sqm"), 1.0), 1.0),
            }
            feature_dicts.append(features)
        
        self.tabular_encoder.fit(feature_dicts)
        logger.info("tabular_encoder_fitted", num_samples=len(feature_dicts))
    
    def _extract_year_built(self, listing: Dict) -> int:
        """Extract year_built from listing, with fallback estimation."""
        # Try direct field first (if it exists in the DB)
        if listing.get("year_built"):
            return int(listing["year_built"])
        
        # Estimate from listed_at date (assume ~10 years old on average)
        listed_at = listing.get("listed_at")
        if listed_at:
            try:
                from datetime import datetime
                if isinstance(listed_at, str):
                    year = datetime.fromisoformat(listed_at.replace('Z', '+00:00')).year
                else:
                    year = listed_at.year
                return year - 10  # Estimate built 10 years before listing
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
        if target_sqm <= 0:
            return []
        if self.require_same_property_type and not target_type:
            return []

        results: List[Tuple[int, float]] = []
        min_ratio = 1.0 - self.size_ratio_tolerance
        max_ratio = 1.0 + self.size_ratio_tolerance
        for idx, dist_km in candidates:
            cand = self.listings[idx]
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
        for idx, listing in enumerate(self.listings):
            if listing.get("lat") is None or listing.get("lon") is None:
                missing_geo += 1
                continue
            if self._safe_float(listing.get("surface_area_sqm"), default=0.0) <= 0:
                missing_size += 1
                continue

            geo_candidates = self._geo_candidates(idx)
            filtered = self._filter_candidates(idx, geo_candidates)
            if len(filtered) < self.num_comps:
                insufficient += 1
                continue
            filtered.sort(key=lambda item: item[1])
            self._comp_candidates[idx] = [i for i, _ in filtered]
            self._eligible_indices.append(idx)

        logger.info(
            "comp_candidate_build",
            total=len(self.listings),
            eligible=len(self._eligible_indices),
            missing_geo=missing_geo,
            missing_size=missing_size,
            insufficient=insufficient
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
        if self.use_vlm:
             vlm_desc = listing.get("vlm_description") or ""
        
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
    
    def _sample_comps(self, target_idx: int) -> List[int]:
        """Sample comparable indices, excluding the target."""
        candidates = self._comp_candidates.get(target_idx, [])
        return candidates[: self.num_comps]
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        target_idx = self._eligible_indices[idx]
        target = self.listings[target_idx]
        
        # Sample comparables
        comp_indices = self._sample_comps(target_idx)
        comps = [self.listings[i] for i in comp_indices]
        
        # Build tensors
        target_text = torch.from_numpy(self._get_text_embedding(target)).float()
        target_tab = torch.from_numpy(self._get_tabular_features(target)).float()
        target_price = torch.tensor(target["price"], dtype=torch.float32)
        
        comp_text = torch.stack([
            torch.from_numpy(self._get_text_embedding(c)).float() for c in comps
        ])
        comp_tab = torch.stack([
            torch.from_numpy(self._get_tabular_features(c)).float() for c in comps
        ])
        comp_prices = torch.tensor([c["price"] for c in comps], dtype=torch.float32)
        
        return {
            "target_text": target_text,
            "target_tab": target_tab,
            "target_price": target_price,
            "comp_text": comp_text,
            "comp_tab": comp_tab,
            "comp_prices": comp_prices,
            "num_comps": len(comps)
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
        "comp_mask": comp_mask
    }


def create_dataloaders(
    db_path: str = "data/listings.db",
    batch_size: int = 32,
    num_comps: int = 5,
    val_split: float = 0.1,
    num_workers: int = 0,
    use_vlm: bool = True
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
    dataset = PropertyDataset(db_path=db_path, num_comps=num_comps, use_vlm=use_vlm)
    
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
