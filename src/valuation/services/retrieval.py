"""
Comp retriever utilities with LanceDB-backed semantic search and metadata filtering.
"""
import os
import json
import re
import structlog
import numpy as np
try:
    import lancedb
    import pyarrow as pa
except ImportError:  # pragma: no cover - optional dependency
    lancedb = None
    pa = None
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from sentence_transformers import SentenceTransformer
from src.platform.config import VECTOR_INDEX_PATH, VECTOR_METADATA_PATH
from src.platform.domain.schema import CanonicalListing, CompListing
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe
from src.platform.utils.time import utcnow

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
    indexed_at: datetime = field(default_factory=utcnow)

class CompRetriever:
    """
    Handles embedding generation and retrieving similar comparable listings (Comps).
    
    Features:
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
        device = os.environ.get("PROPERTY_SCANNER_TEXT_DEVICE")
        if device:
            self.model = SentenceTransformer(model_name, device=device)
        else:
            self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        self.index = None
            
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
                    "created_at": utcnow().isoformat(),
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

    def get_metadata(self) -> Dict[str, Any]:
        """Expose retriever metadata for reproducible training/inference alignment."""
        fingerprint = self.metadata_index_fingerprint or self._index_fingerprint()
        return {
            "version": self.metadata_version,
            "model_name": self.metadata_model_name or self.model_name,
            "vlm_policy": self.metadata_vlm_policy or self.vlm_policy,
            "index_fingerprint": fingerprint,
            "metadata_path": self.metadata_path,
            "index_path": self.index_path,
        }

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
        raise NotImplementedError("retriever_add_listings_unsupported")

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
        if self.index is None:
            return []
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
        total_vectors = 0
        if self.index is not None:
            try:
                total_vectors = int(getattr(self.index, "ntotal", 0) or 0)
            except (TypeError, ValueError):
                total_vectors = 0
        return {
            "total_vectors": total_vectors,
            "total_listings": len(self.listings),
            "embedding_dimension": self.dimension,
            "index_path": self.index_path
        }


class LanceDBRetriever(CompRetriever):
    """
    LanceDB-backed retriever with the same comp filtering logic as the legacy retriever.
    """

    table_name = "comp_listings"

    def __init__(
        self,
        *,
        lancedb_path: str,
        metadata_path: str,
        model_name: str = "all-MiniLM-L6-v2",
        strict_model_match: bool = False,
        vlm_policy: str = "gated",
    ):
        if lancedb is None or pa is None:
            raise ImportError("lancedb_missing")

        self.index_path = lancedb_path
        self.metadata_path = metadata_path
        self.model_name = model_name
        self.strict_model_match = strict_model_match
        self.vlm_policy = vlm_policy

        device = os.environ.get("PROPERTY_SCANNER_TEXT_DEVICE")
        if device:
            self.model = SentenceTransformer(model_name, device=device)
        else:
            self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()

        self.db = lancedb.connect(lancedb_path)
        self.table = self._load_table()

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

    def _load_table(self):
        existing = self.db.table_names()
        if self.table_name in existing:
            return self.db.open_table(self.table_name)

        vector_type = pa.list_(pa.float32(), list_size=self.dimension)
        schema = pa.schema(
            [
                ("id", pa.string()),
                ("int_id", pa.int64()),
                ("vector", vector_type),
                ("title", pa.string()),
                ("price", pa.float64()),
                ("listing_type", pa.string()),
                ("snapshot_id", pa.string()),
                ("external_id", pa.string()),
                ("source_id", pa.string()),
                ("url", pa.string()),
                ("property_type", pa.string()),
                ("surface_area_sqm", pa.float64()),
                ("bedrooms", pa.int64()),
                ("lat", pa.float64()),
                ("lon", pa.float64()),
                ("listed_at", pa.string()),
                ("updated_at", pa.string()),
                ("status", pa.string()),
            ]
        )
        return self.db.create_table(self.table_name, schema=schema)

    def _row_to_indexed(self, row: Dict[str, Any]) -> IndexedListing:
        return IndexedListing(
            id=row.get("id", ""),
            int_id=int(row.get("int_id", -1)),
            external_id=row.get("external_id"),
            source_id=row.get("source_id"),
            url=row.get("url"),
            title=row.get("title", ""),
            price=row.get("price", 0.0),
            listing_type=row.get("listing_type", "sale"),
            property_type=row.get("property_type"),
            surface_area_sqm=row.get("surface_area_sqm"),
            bedrooms=row.get("bedrooms"),
            lat=row.get("lat"),
            lon=row.get("lon"),
            snapshot_id=row.get("snapshot_id", ""),
            listed_at=row.get("listed_at"),
            updated_at=row.get("updated_at"),
            status=row.get("status"),
        )

    def add_listings(
        self,
        listings: List[CanonicalListing],
        snapshot_ids: Optional[Dict[str, str]] = None,
    ) -> int:
        if not listings:
            return 0

        snapshot_ids = snapshot_ids or {}
        records = []
        metadata_dirty = False

        for l in listings:
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

            text = self._build_text(l.title or "", l.description or "", getattr(l, "vlm_description", None))
            vec = self.model.encode(text, normalize_embeddings=True, show_progress_bar=False)

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
                status=str(getattr(l, "status", None)) if getattr(l, "status", None) else None,
            )

            self.listings[int_id] = il
            self.id_to_int[l.id] = int_id

            record = {
                "id": il.id,
                "int_id": il.int_id,
                "vector": vec.astype("float32").tolist(),
                "title": il.title,
                "price": il.price,
                "listing_type": il.listing_type,
                "snapshot_id": il.snapshot_id,
                "external_id": il.external_id,
                "source_id": il.source_id,
                "url": il.url,
                "property_type": il.property_type,
                "surface_area_sqm": il.surface_area_sqm,
                "bedrooms": il.bedrooms,
                "lat": il.lat,
                "lon": il.lon,
                "listed_at": il.listed_at,
                "updated_at": il.updated_at,
                "status": il.status,
            }
            records.append(record)

        if records:
            self.table.add(records)
            self._save_metadata()
            logger.info("added_vectors_to_lancedb", count=len(records))
        elif metadata_dirty:
            self._save_metadata()
            logger.info("updated_lancedb_metadata", count=len(self.listings))

        return len(records)

    def retrieve_comps(
        self,
        target: CanonicalListing,
        k: int = 10,
        max_radius_km: float = 5.0,
        exclude_self: bool = True,
        strict_filters: bool = True,
        listing_type: Optional[str] = None,
        max_listed_at: Optional[datetime] = None,
        exclude_duplicate_external: bool = True,
    ) -> List[CompListing]:
        if not self.listings:
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

        text = self._build_text(target.title or "", target.description or "", getattr(target, "vlm_description", None))
        query_vec = self.model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        query_vec = query_vec.astype("float32").tolist()

        index_total = len(self.listings)
        search_k = min(max(k * 20, 100), index_total)

        search_results = self.table.search(query_vec, vector_column_name="vector").limit(search_k).to_list()
        candidates = []
        for row in search_results:
            int_id = row.get("int_id")
            il = self.listings.get(int_id) if int_id is not None else None
            if il is None:
                il = self._row_to_indexed(row)
            dist = row.get("_distance")
            if dist is None:
                dist = row.get("_score")
            if dist is None:
                continue
            if exclude_self and il.id == target.id:
                continue
            candidates.append((il, float(dist)))

        results = []
        allowed_bedroom_diff = 1
        allowed_sqm_ratio = 0.2

        target_lat = target.location.lat if target.location else None
        target_lon = target.location.lon if target.location else None
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

            if il.price is None or il.price <= 0:
                continue

            similarity = 1.0 / (1.0 + dist)
            results.append(
                CompListing(
                    id=il.id,
                    price=il.price,
                    features={
                        "sqm": il.surface_area_sqm or 0,
                        "bedrooms": il.bedrooms or 0,
                        "lat": il.lat or 0,
                        "lon": il.lon or 0,
                    },
                    similarity_score=similarity,
                    snapshot_id=il.snapshot_id,
                )
            )

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

                if il.price is None or il.price <= 0:
                    continue

                similarity = 1.0 / (1.0 + dist)
                results.append(
                    CompListing(
                        id=il.id,
                        price=il.price,
                        features={
                            "sqm": il.surface_area_sqm or 0,
                            "bedrooms": il.bedrooms or 0,
                            "lat": il.lat or 0,
                            "lon": il.lon or 0,
                        },
                        similarity_score=similarity,
                        snapshot_id=il.snapshot_id,
                    )
                )

                if len(results) >= k:
                    break

        return results[:k]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_vectors": len(self.listings),
            "total_listings": len(self.listings),
            "embedding_dimension": self.dimension,
            "index_path": self.index_path,
        }


def build_retriever(
    *,
    backend: Optional[str] = None,
    index_path: Optional[str] = None,
    metadata_path: Optional[str] = None,
    lancedb_path: Optional[str] = None,
    model_name: Optional[str] = None,
    strict_model_match: bool = False,
    vlm_policy: Optional[str] = None,
    app_config: Optional[AppConfig] = None,
):
    app_config = app_config or load_app_config_safe()
    if backend is None:
        backend = app_config.valuation.retriever_backend
    backend = str(backend).strip().lower()
    if backend != "lancedb":
        raise ValueError("retriever_backend_lancedb_only")

    if model_name is None:
        model_name = app_config.valuation.retriever_model_name
    if vlm_policy is None:
        vlm_policy = app_config.valuation.retriever_vlm_policy
    if metadata_path is None:
        metadata_path = app_config.valuation.retriever_metadata_path

    if lancedb_path is None:
        lancedb_path = app_config.valuation.retriever_lancedb_path
    return LanceDBRetriever(
        lancedb_path=str(lancedb_path),
        metadata_path=str(metadata_path),
        model_name=model_name,
        strict_model_match=strict_model_match,
        vlm_policy=vlm_policy,
    )
