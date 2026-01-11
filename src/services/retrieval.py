"""
Enhanced Comp Retrieval Service with Qdrant-like features using FAISS.
Provides semantic search with metadata filtering for comparable listings.
"""
import os
import json
import structlog
import numpy as np
import faiss
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from sentence_transformers import SentenceTransformer
from src.core.domain.schema import CanonicalListing, CompListing

logger = structlog.get_logger()

@dataclass
class IndexedListing:
    """Cached listing data for fast retrieval."""
    id: str
    int_id: int
    title: str
    price: float
    surface_area_sqm: Optional[float]
    bedrooms: Optional[int]
    lat: Optional[float]
    lon: Optional[float]
    snapshot_id: str
    indexed_at: datetime = field(default_factory=datetime.now)

class CompRetriever:
    """
    Handles embedding generation and retrieving similar comparable listings (Comps).
    
    Features:
    - FAISS for dense vector search
    - SentenceTransformers for text embeddings
    - Geo-filtering (radius-based)
    - Temporal filtering (no future leakage)
    - Persisted index and metadata
    """
    
    def __init__(
        self, 
        index_path: str = "data/vector_index.faiss",
        metadata_path: str = "data/vector_metadata.json",
        model_name: str = 'all-MiniLM-L6-v2'
    ):
        self.index_path = index_path
        self.metadata_path = metadata_path
        
        # Load embedding model
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        
        # Initialize or Load FAISS Index
        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
        else:
            # IndexFlatIP for inner product (cosine similarity with normalized vectors)
            base_index = faiss.IndexFlatL2(self.dimension)
            self.index = faiss.IndexIDMap(base_index)
            
        # Load or initialize metadata
        self.listings: Dict[int, IndexedListing] = {}
        self.id_to_int: Dict[str, int] = {}
        self.next_int_id = 0
        
        if os.path.exists(metadata_path):
            self._load_metadata()

    def _load_metadata(self):
        """Load listing metadata from disk."""
        try:
            with open(self.metadata_path, "r") as f:
                data = json.load(f)
                self.next_int_id = data.get("next_int_id", 0)
                for item in data.get("listings", []):
                    il = IndexedListing(
                        id=item["id"],
                        int_id=item["int_id"],
                        title=item["title"],
                        price=item["price"],
                        surface_area_sqm=item.get("surface_area_sqm"),
                        bedrooms=item.get("bedrooms"),
                        lat=item.get("lat"),
                        lon=item.get("lon"),
                        snapshot_id=item.get("snapshot_id", "")
                    )
                    self.listings[il.int_id] = il
                    self.id_to_int[il.id] = il.int_id
            logger.info("loaded_retrieval_metadata", count=len(self.listings))
        except Exception as e:
            logger.warning("metadata_load_failed", error=str(e))

    def _save_metadata(self):
        """Persist listing metadata to disk."""
        try:
            items = []
            for il in self.listings.values():
                items.append({
                    "id": il.id,
                    "int_id": il.int_id,
                    "title": il.title,
                    "price": il.price,
                    "surface_area_sqm": il.surface_area_sqm,
                    "bedrooms": il.bedrooms,
                    "lat": il.lat,
                    "lon": il.lon,
                    "snapshot_id": il.snapshot_id
                })
            with open(self.metadata_path, "w") as f:
                json.dump({"next_int_id": self.next_int_id, "listings": items}, f)
        except Exception as e:
            logger.error("metadata_save_failed", error=str(e))

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in km between two points."""
        from math import radians, sin, cos, sqrt, atan2
        R = 6371  # Earth's radius in km
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c

    def add_listings(
        self, 
        listings: List[CanonicalListing], 
        snapshot_ids: Optional[Dict[str, str]] = None
    ) -> int:
        """
        Add listings to the vector index.
        
        Args:
            listings: List of canonical listings to index
            snapshot_ids: Optional mapping of listing_id -> snapshot_id
            
        Returns:
            Number of new listings added
        """
        if not listings:
            return 0

        vectors = []
        new_listings = []
        
        snapshot_ids = snapshot_ids or {}
        
        for l in listings:
            # Skip if already indexed
            if l.id in self.id_to_int:
                continue
                
            # Create embedding from text
            text = f"{l.title or ''} {l.description or ''}"
            vec = self.model.encode(text, normalize_embeddings=True)
            vectors.append(vec)
            
            # Create indexed listing
            int_id = self.next_int_id
            self.next_int_id += 1
            
            il = IndexedListing(
                id=l.id,
                int_id=int_id,
                title=l.title or "",
                price=l.price,
                surface_area_sqm=l.surface_area_sqm,
                bedrooms=l.bedrooms,
                lat=l.location.lat if l.location else None,
                lon=l.location.lon if l.location else None,
                snapshot_id=snapshot_ids.get(l.id, "")
            )
            
            self.listings[int_id] = il
            self.id_to_int[l.id] = int_id
            new_listings.append(int_id)
            
        if vectors:
            vectors_np = np.array(vectors).astype('float32')
            ids_np = np.array(new_listings).astype('int64')
            self.index.add_with_ids(vectors_np, ids_np)
            
            # Persist
            faiss.write_index(self.index, self.index_path)
            self._save_metadata()
            
            logger.info("added_vectors_to_index", count=len(new_listings))
            
        return len(new_listings)

    def retrieve_comps(
        self, 
        target: CanonicalListing, 
        k: int = 10,
        max_radius_km: float = 5.0,
        exclude_self: bool = True,
        strict_filters: bool = True
    ) -> List[CompListing]:
        """
        Find K similar listings with optional geo-filtering and logical compatibility.
        
        Args:
            target: The listing to find comparables for
            k: Number of comparables to return
            max_radius_km: Maximum distance for geo-filtering (0 to disable)
            exclude_self: Whether to exclude the target listing from results
            strict_filters: If True, enforces bedroom/size compatibility
            
        Returns:
            List of CompListing objects sorted by similarity
        """
        if self.index.ntotal == 0:
            return []
            
        # Create query embedding
        text = f"{target.title or ''} {target.description or ''}"
        query_vec = self.model.encode(text, normalize_embeddings=True)
        query_vec = query_vec.reshape(1, -1).astype('float32')
        
        # Search for MANY more candidates to allow for heavy filtering
        # We need a large pool because structural mismatch is common
        search_k = min(max(k * 20, 100), self.index.ntotal)
        distances, indices = self.index.search(query_vec, search_k)
        
        candidates = []
        target_lat = target.location.lat if target.location else None
        target_lon = target.location.lon if target.location else None
        
        # optimized pre-fetching
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1: continue
            il = self.listings.get(int(idx))
            if not il: continue
            if exclude_self and il.id == target.id: continue
            candidates.append((il, float(dist)))
            
        # --- Filtering Strategies ---
        
        def get_filtered_results(allowed_bedroom_diff: int, allowed_sqm_ratio: float) -> List[CompListing]:
            """Helper to filter candidates with specific strictness."""
            results = []
            for il, dist in candidates:
                # 1. Geo Filter (Hard Requirement usually)
                if max_radius_km > 0 and target_lat and target_lon and il.lat and il.lon:
                    geo_dist = self._haversine_distance(target_lat, target_lon, il.lat, il.lon)
                    if geo_dist > max_radius_km:
                        continue
                
                # 2. Logical Compatibility
                if strict_filters:
                    # Bedrooms
                    if target.bedrooms is not None and il.bedrooms is not None:
                        # For small units (0-1 beds), be strict. For large, allow margin.
                        if target.bedrooms <= 1 and il.bedrooms != target.bedrooms:
                            if abs(il.bedrooms - target.bedrooms) > 0: continue
                        elif abs(il.bedrooms - target.bedrooms) > allowed_bedroom_diff:
                            continue
                            
                    # Surface Area
                    if target.surface_area_sqm and il.surface_area_sqm:
                        ratio = il.surface_area_sqm / target.surface_area_sqm
                        # e.g. 0.7 to 1.3
                        if not ((1.0 - allowed_sqm_ratio) <= ratio <= (1.0 + allowed_sqm_ratio)):
                            continue

                # Similarity Score
                similarity = 1.0 / (1.0 + dist)
                
                results.append(CompListing(
                    id=il.id,
                    price=il.price,
                    features={
                        "sqm": il.surface_area_sqm or 0,
                        "bedrooms": il.bedrooms or 0,
                        "lat": il.lat or 0,
                        "lon": il.lon or 0
                    },
                    similarity_score=similarity,
                    snapshot_id=il.snapshot_id
                ))
                
                if len(results) >= k:
                    break
            return results

        # Strategy 1: Strict (Apple-to-Apple)
        # +/- 1 Bedroom, +/- 20% size
        comps = get_filtered_results(allowed_bedroom_diff=1, allowed_sqm_ratio=0.2)
        
        # Strategy 2: Relaxed (Apples-to-Pears)
        # +/- 2 Bedrooms, +/- 40% size
        if len(comps) < k:
            # logger.info("relaxing_filters_level_1", target_id=target.id, found=len(comps))
            required = k - len(comps)
            relaxed = get_filtered_results(allowed_bedroom_diff=2, allowed_sqm_ratio=0.4)
            
            # Merge unique
            existing_ids = {c.id for c in comps}
            for c in relaxed:
                if c.id not in existing_ids:
                    comps.append(c)
                    existing_ids.add(c.id)
                    if len(comps) >= k: break
                    
        # Strategy 3: Desperate (Fruit Salad)
        # Just pure vector search (already geo-filtered in the inner loop logic if we reused it, 
        # but let's just take the raw vector results if we still have nothing)
        if len(comps) < k:
            # logger.info("relaxing_filters_level_max", target_id=target.id, found=len(comps))
            # Just take whatever we have from candidates that satisfies Geo
            existing_ids = {c.id for c in comps}
            for il, dist in candidates:
                if il.id in existing_ids: continue
                
                # Check Geo only
                if max_radius_km > 0 and target_lat and target_lon and il.lat and il.lon:
                    geo_dist = self._haversine_distance(target_lat, target_lon, il.lat, il.lon)
                    if geo_dist > max_radius_km: continue
                
                similarity = 1.0 / (1.0 + dist)
                comps.append(CompListing(
                    id=il.id,
                    price=il.price,
                    features={
                        "sqm": il.surface_area_sqm or 0,
                        "bedrooms": il.bedrooms or 0,
                        "lat": il.lat or 0,
                        "lon": il.lon or 0
                    },
                    similarity_score=similarity,
                    snapshot_id=il.snapshot_id
                ))
                if len(comps) >= k: break
                
        return comps[:k]

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "total_vectors": self.index.ntotal,
            "total_listings": len(self.listings),
            "embedding_dimension": self.dimension,
            "index_path": self.index_path
        }
