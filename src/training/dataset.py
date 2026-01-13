"""
PyTorch Dataset for PropertyFusionModel Training.
Loads listings directly from SQLite database and encodes on-the-fly or uses cached embeddings.
"""
import sqlite3
import random
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
    Samples comparables from the same city for contextual learning.
    """
    def __init__(
        self,
        db_path: str = "data/listings.db",
        num_comps: int = 5,
        same_city_only: bool = True,
        min_comps_fallback: int = 3,
        cache_embeddings: bool = True,
        text_model: str = "all-MiniLM-L6-v2",
        use_vlm: bool = True
    ):
        """
        Args:
            db_path: Path to SQLite database with listings table
            num_comps: Number of comparables to sample per target
            same_city_only: If True, sample comps from same city only
            min_comps_fallback: Minimum comps required; if not met, sample from all
            cache_embeddings: Cache text embeddings in memory
            text_model: SentenceTransformer model name
        """
        self.db_path = db_path
        self.num_comps = num_comps
        self.same_city_only = same_city_only
        self.min_comps_fallback = min_comps_fallback
        self.cache_embeddings = cache_embeddings
        self.use_vlm = use_vlm
        
        # Load encoder
        from src.services.encoders import TextEncoder, TabularEncoder
        self.text_encoder = TextEncoder(model_name=text_model)
        self.tabular_encoder = TabularEncoder()
        
        # Load all listings from database
        self.listings = self._load_listings()
        
        # Build city index for efficient comp sampling
        self.city_index: Dict[str, List[int]] = defaultdict(list)
        for i, listing in enumerate(self.listings):
            city = listing.get("city") or "unknown"
            self.city_index[city].append(i)
        
        self.all_indices = list(range(len(self.listings)))
        
        # Cache for embeddings
        self._embedding_cache: Dict[str, np.ndarray] = {}
        
        logger.info("dataset_initialized", 
                   db_path=db_path, 
                   num_listings=len(self.listings),
                   num_cities=len(self.city_index),
                   vlm_enabled=use_vlm)
        
        # Fit tabular encoder on the data for proper normalization
        self._fit_tabular_encoder()
    
    def _load_listings(self) -> List[Dict[str, Any]]:
        """Load all valid listings from SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT id, source_id, title, description, price, city,
                   bedrooms, bathrooms, surface_area_sqm, floor,
                   lat, lon, image_urls, vlm_description,
                   listed_at, updated_at, sentiment_score, has_elevator
            FROM listings
            WHERE price > 0
        """)
        
        listings = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return listings
    
    def _fit_tabular_encoder(self):
        """Fit tabular encoder on all listings for proper normalization."""
        feature_dicts = []
        for listing in self.listings:
            # NOTE: price is NOT included - it's the target variable
            features = {
                "bedrooms": listing.get("bedrooms") or 0,
                "bathrooms": listing.get("bathrooms") or 0,
                "surface_area_sqm": listing.get("surface_area_sqm") or 0,
                "year_built": self._extract_year_built(listing),
                "floor": listing.get("floor") or 0,
                "lat": listing.get("lat") or 0,
                "lon": listing.get("lon") or 0,
                "sentiment_score": listing.get("sentiment_score") or 0.0,
                "has_elevator": 1.0 if listing.get("has_elevator") else 0.0,
                "price_per_sqm": (listing.get("price") or 0) / max(listing.get("surface_area_sqm") or 1, 1),
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
            "bedrooms": listing.get("bedrooms") or 0,
            "bathrooms": listing.get("bathrooms") or 0,
            "surface_area_sqm": listing.get("surface_area_sqm") or 0,
            "year_built": self._extract_year_built(listing),
            "floor": listing.get("floor") or 0,
            "lat": listing.get("lat") or 0,
            "lon": listing.get("lon") or 0,
            "sentiment_score": listing.get("sentiment_score") or 0.0,
            "has_elevator": 1.0 if listing.get("has_elevator") else 0.0,
            "price_per_sqm": 0,  # Will be computed from comps during inference
        }
        return self.tabular_encoder.encode(features)
    
    def __len__(self) -> int:
        return len(self.listings)
    
    def _sample_comps(self, target_idx: int, target_city: str) -> List[int]:
        """Sample comparable indices, excluding the target."""
        if self.same_city_only:
            candidates = [i for i in self.city_index.get(target_city, []) if i != target_idx]
        else:
            candidates = [i for i in self.all_indices if i != target_idx]
        
        # Fallback if not enough candidates
        if len(candidates) < self.min_comps_fallback:
            candidates = [i for i in self.all_indices if i != target_idx]
        
        k = min(self.num_comps, len(candidates))
        if k == 0:
            return [target_idx]  # Edge case
        
        return random.sample(candidates, k)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        target = self.listings[idx]
        target_city = target.get("city") or "unknown"
        
        # Sample comparables
        comp_indices = self._sample_comps(idx, target_city)
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
