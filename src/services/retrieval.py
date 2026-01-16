"""
Enhanced Comp Retrieval Service with Qdrant-like features using FAISS.
Provides semantic search with metadata filtering for comparable listings.
"""
import os
import json
import re
import structlog
import numpy as np
import faiss
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from sentence_transformers import SentenceTransformer
from src.core.config import VECTOR_INDEX_PATH, VECTOR_METADATA_PATH
from src.core.domain.schema import CanonicalListing, CompListing

logger = structlog.get_logger()

METADATA_VERSION = 2

@dataclass
class IndexedListing:
    """Cached listing data for fast retrieval."""
    id: str
    int_id: int
    title: str
    price: float
    listing_type: str # "sale" or "rent"
    snapshot_id: str
    external_id: Optional[str] = None
    source_id: Optional[str] = None
    url: Optional[str] = None
    property_type: Optional[str] = None
    surface_area_sqm: Optional[float] = None
    bedrooms: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    listed_at: Optional[str] = None
    updated_at: Optional[str] = None
    status: Optional[str] = None
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
        index_path: str = str(VECTOR_INDEX_PATH),
        metadata_path: str = str(VECTOR_METADATA_PATH),
        model_name: str = 'all-MiniLM-L6-v2',
        strict_model_match: bool = False,
        vlm_policy: str = "gated"
    ):
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.model_name = model_name
        self.strict_model_match = strict_model_match
        self.vlm_policy = vlm_policy

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
        self.metadata_version = 0
        self.metadata_model_name = None
        self.metadata_index_fingerprint = None
        self.metadata_vlm_policy = None
        
        if os.path.exists(metadata_path):
            self._load_metadata()
        elif self.strict_model_match:
            raise FileNotFoundError("retrieval_metadata_missing")

    def _load_metadata(self):
        """Load listing metadata from disk."""
        try:
            with open(self.metadata_path, "r") as f:
                data = json.load(f)
                self.metadata_version = data.get("version", 0)
                self.metadata_model_name = data.get("model_name")
                self.metadata_index_fingerprint = data.get("index_fingerprint")
                self.metadata_vlm_policy = data.get("vlm_policy")

                if self.metadata_version < METADATA_VERSION and self.strict_model_match:
                    raise ValueError("retrieval_metadata_version_mismatch")

                if self.metadata_model_name and self.metadata_model_name != self.model_name:
                    msg = "retrieval_model_mismatch"
                    if self.strict_model_match:
                        raise ValueError(msg)
                    logger.warning(msg, expected=self.model_name, found=self.metadata_model_name)
                elif not self.metadata_model_name and self.strict_model_match:
                    raise ValueError("retrieval_model_missing")

                if self.metadata_vlm_policy and self.metadata_vlm_policy != self.vlm_policy:
                    msg = "retrieval_vlm_policy_mismatch"
                    if self.strict_model_match:
                        raise ValueError(msg)
                    logger.warning(msg, expected=self.vlm_policy, found=self.metadata_vlm_policy)

                self.next_int_id = data.get("next_int_id", 0)
                for item in data.get("listings", []):
                    il = IndexedListing(
                        id=item["id"],
                        int_id=item["int_id"],
                        external_id=item.get("external_id"),
                        source_id=item.get("source_id"),
                        url=item.get("url"),
                        title=item["title"],
                        price=item["price"],
                        listing_type=item.get("listing_type", "sale"),
                        property_type=item.get("property_type"),
                        surface_area_sqm=item.get("surface_area_sqm"),
                        bedrooms=item.get("bedrooms"),
                        lat=item.get("lat"),
                        lon=item.get("lon"),
                        snapshot_id=item.get("snapshot_id", ""),
                        listed_at=item.get("listed_at"),
                        updated_at=item.get("updated_at"),
                        status=item.get("status")
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
                    "external_id": il.external_id,
                    "source_id": il.source_id,
                    "url": il.url,
                    "title": il.title,
                    "price": il.price,
                    "listing_type": il.listing_type,
                    "property_type": il.property_type,
                    "surface_area_sqm": il.surface_area_sqm,
                    "bedrooms": il.bedrooms,
                    "lat": il.lat,
                    "lon": il.lon,
                    "snapshot_id": il.snapshot_id,
                    "listed_at": il.listed_at,
                    "updated_at": il.updated_at,
                    "status": il.status
                })
            with open(self.metadata_path, "w") as f:
                json.dump({
                    "version": METADATA_VERSION,
                    "model_name": self.model_name,
                    "vlm_policy": self.vlm_policy,
                    "index_fingerprint": self._index_fingerprint(),
                    "created_at": datetime.now().isoformat(),
                    "next_int_id": self.next_int_id,
                    "listings": items
                }, f)
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

    def _index_fingerprint(self) -> Dict[str, Any]:
        if not os.path.exists(self.index_path):
            return {}
        stat = os.stat(self.index_path)
        return {"size": stat.st_size, "mtime": int(stat.st_mtime)}

    def _parse_dt(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _is_vlm_safe(self, text: str) -> bool:
        if not text:
            return False
        cleaned = text.strip()
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

    def _build_text(self, title: str, description: str, vlm_description: Optional[str]) -> str:
        parts = [title or "", description or ""]
        if self.vlm_policy != "off":
            if self._is_vlm_safe(vlm_description or ""):
                parts.append(vlm_description or "")
        return " ".join(p for p in parts if p).strip()

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
        metadata_dirty = False
        
        snapshot_ids = snapshot_ids or {}
        
        for l in listings:
            # Skip if already indexed, but refresh missing timestamps
            if l.id in self.id_to_int:
                int_id = self.id_to_int[l.id]
                il = self.listings.get(int_id)
                if il:
                    listed_at = l.listed_at.isoformat() if getattr(l, "listed_at", None) else None
                    updated_at = l.updated_at.isoformat() if getattr(l, "updated_at", None) else None
                    if listed_at and not il.listed_at:
                        il.listed_at = listed_at
                        metadata_dirty = True
                    if updated_at and not il.updated_at:
                        il.updated_at = updated_at
                        metadata_dirty = True
                continue
                
            # Create embedding from text
            text = self._build_text(l.title or "", l.description or "", getattr(l, "vlm_description", None))
            vec = self.model.encode(text, normalize_embeddings=True, show_progress_bar=False)
            vectors.append(vec)
            
            # Create indexed listing
            int_id = self.next_int_id
            self.next_int_id += 1
            
            il = IndexedListing(
                id=l.id,
                int_id=int_id,
                external_id=getattr(l, "external_id", None),
                source_id=getattr(l, "source_id", None),
                url=str(getattr(l, "url", "")) if getattr(l, "url", None) else None,
                title=l.title or "",
                price=l.price,
                listing_type=l.listing_type if hasattr(l, "listing_type") and l.listing_type else "sale",
                property_type=(l.property_type.value if hasattr(l, "property_type") and hasattr(l.property_type, "value") else str(getattr(l, "property_type", "") or "")).lower() or None,
                surface_area_sqm=l.surface_area_sqm,
                bedrooms=l.bedrooms,
                lat=l.location.lat if l.location else None,
                lon=l.location.lon if l.location else None,
                snapshot_id=snapshot_ids.get(l.id, ""),
                listed_at=l.listed_at.isoformat() if getattr(l, "listed_at", None) else None,
                updated_at=l.updated_at.isoformat() if getattr(l, "updated_at", None) else None,
                status=str(getattr(l, "status", None)) if getattr(l, "status", None) else None
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
        elif metadata_dirty:
            self._save_metadata()
            logger.info("updated_index_metadata", count=len(self.listings))

        return len(new_listings)

    def retrieve_comps(
        self, 
        target: CanonicalListing, 
        k: int = 10,
        max_radius_km: float = 5.0,
        exclude_self: bool = True,
        strict_filters: bool = True,
        listing_type: Optional[str] = None,
        max_listed_at: Optional[datetime] = None,
        exclude_duplicate_external: bool = True
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
        try:
            index_total = int(getattr(self.index, "ntotal", 0) or 0)
        except (TypeError, ValueError):
            index_total = 0
        if index_total <= 0:
            return []

        if max_radius_km > 0:
            if not target.location or target.location.lat is None or target.location.lon is None:
                raise ValueError("missing_target_geolocation")

        target_property_type = None
        if hasattr(target, "property_type") and target.property_type:
            target_property_type = str(target.property_type)
            if "." in target_property_type:
                target_property_type = target_property_type.split(".")[-1]
            target_property_type = target_property_type.lower().strip()

        if strict_filters:
            if not target_property_type:
                raise ValueError("missing_target_property_type")
            if not target.surface_area_sqm or target.surface_area_sqm <= 0:
                raise ValueError("missing_target_surface_area")
            
        # Create query embedding
        text = self._build_text(target.title or "", target.description or "", getattr(target, "vlm_description", None))
        query_vec = self.model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        query_vec = query_vec.reshape(1, -1).astype('float32')
        
        # Search for MANY more candidates to allow for heavy filtering
        # We need a large pool because structural mismatch is common
        search_k = min(max(k * 20, 100), index_total)
        search_output = self.index.search(query_vec, search_k)
        if not isinstance(search_output, (list, tuple)) or len(search_output) != 2:
            logger.warning("retriever_search_invalid", output_type=str(type(search_output)))
            return []
        distances, indices = search_output
        if distances is None or indices is None:
            logger.warning("retriever_search_empty")
            return []
        try:
            if len(distances) == 0 or len(indices) == 0:
                return []
        except TypeError:
            logger.warning("retriever_search_uniterable")
            return []
        
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
            
        # --- Strict Two-Stage Filtering ---
        # Stage 1: Geo + listing_type
        # Stage 2: Property type + size (and bedrooms if available)

        results = []
        allowed_bedroom_diff = 1
        allowed_sqm_ratio = 0.2

        target_external_id = getattr(target, "external_id", None)
        target_url = str(getattr(target, "url", "")) if getattr(target, "url", None) else None

        for il, dist in candidates:
            if listing_type and il.listing_type != listing_type:
                continue
            if exclude_duplicate_external and target_external_id and il.external_id == target_external_id:
                continue
            if target_url and il.url and il.url == target_url:
                continue

            if max_listed_at:
                comp_dt = self._parse_dt(il.listed_at) or self._parse_dt(il.updated_at)
                if comp_dt is None:
                    continue
                as_of = max_listed_at
                if comp_dt.tzinfo is not None:
                    comp_dt = comp_dt.replace(tzinfo=None)
                if as_of.tzinfo is not None:
                    as_of = as_of.replace(tzinfo=None)
                if comp_dt > as_of:
                    continue

            if target_property_type and il.property_type and il.property_type != target_property_type:
                continue

            if max_radius_km > 0:
                if il.lat is None or il.lon is None:
                    continue
                geo_dist = self._haversine_distance(target_lat, target_lon, il.lat, il.lon)
                if geo_dist > max_radius_km:
                    continue

            if strict_filters:
                if target.bedrooms is not None:
                    if il.bedrooms is None:
                        continue
                    if target.bedrooms <= 1 and il.bedrooms != target.bedrooms:
                        continue
                    if target.bedrooms > 1 and abs(il.bedrooms - target.bedrooms) > allowed_bedroom_diff:
                        continue

                if target.surface_area_sqm:
                    if not il.surface_area_sqm:
                        continue
                    ratio = il.surface_area_sqm / target.surface_area_sqm
                    if not ((1.0 - allowed_sqm_ratio) <= ratio <= (1.0 + allowed_sqm_ratio)):
                        continue

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

        if strict_filters and len(results) < k:
            relaxed_ids = {c.id for c in results}
            for il, dist in candidates:
                if il.id in relaxed_ids:
                    continue
                if listing_type and il.listing_type != listing_type:
                    continue
                if exclude_duplicate_external and target_external_id and il.external_id == target_external_id:
                    continue
                if target_url and il.url and il.url == target_url:
                    continue

                if max_listed_at:
                    comp_dt = self._parse_dt(il.listed_at) or self._parse_dt(il.updated_at)
                    if comp_dt is None:
                        continue
                    as_of = max_listed_at
                    if comp_dt.tzinfo is not None:
                        comp_dt = comp_dt.replace(tzinfo=None)
                    if as_of.tzinfo is not None:
                        as_of = as_of.replace(tzinfo=None)
                    if comp_dt > as_of:
                        continue

                if max_radius_km > 0:
                    if il.lat is None or il.lon is None:
                        continue
                    geo_dist = self._haversine_distance(target_lat, target_lon, il.lat, il.lon)
                    if geo_dist > max_radius_km:
                        continue

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

        return results[:k]

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "total_vectors": self.index.ntotal,
            "total_listings": len(self.listings),
            "embedding_dimension": self.dimension,
            "index_path": self.index_path
        }
