import os
import structlog
import numpy as np
import faiss
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
from src.core.domain.schema import CanonicalListing, CompListing

logger = structlog.get_logger()

class CompRetriever:
    """
    Handles embedding generation and retrieving similar comparable listings (Comps).
    Uses FAISS for vector search and SentenceTransformers for text embeddings.
    """
    def __init__(self, index_path: str = "data/vector_index.faiss"):
        self.index_path = index_path
        # Load small model for MVP speed
        self.model = SentenceTransformer('all-MiniLM-L6-v2') 
        self.dimension = 384
        
        # Initialize or Load FAISS Index
        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
        else:
            # IDMap allows us to store integer IDs mapped to vectors
            self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))
            
        # For MVP, we need a mapping from Integer ID (FAISS) -> Listing ID (String)
        # In a real system (Qdrant), this is built-in.
        self.id_map: Dict[int, str] = {} 
        self.listing_cache: Dict[str, CanonicalListing] = {}
        self.next_int_id = 0

    def add_listings(self, listings: List[CanonicalListing]):
        if not listings:
            return

        vectors = []
        ids = []
        
        for l in listings:
            text = f"{l.title} {l.description or ''}"
            vec = self.model.encode(text)
            vectors.append(vec)
            
            # Map ID
            # In MVP, we just auto-increment.
            # In production, we'd hash or persist this map robustly.
            int_id = self.next_int_id
            self.id_map[int_id] = l.id
            self.listing_cache[l.id] = l # Poor man's cache
            ids.append(int_id)
            self.next_int_id += 1
            
        if vectors:
            vectors_np = np.array(vectors).astype('float32')
            ids_np = np.array(ids).astype('int64')
            self.index.add_with_ids(vectors_np, ids_np)
            faiss.write_index(self.index, self.index_path)
            logger.info("added_vectors_to_index", count=len(vectors))

    def retrieve_comps(self, target: CanonicalListing, k: int = 5) -> List[CompListing]:
        """
        Finds K similar listings.
        """
        if self.index.ntotal == 0:
            return []
            
        text = f"{target.title} {target.description or ''}"
        query_vec = self.model.encode(text).reshape(1, -1).astype('float32')
        
        # Search
        distances, indices = self.index.search(query_vec, k)
        
        comps = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1: continue # Not found
            
            listing_id = self.id_map.get(idx)
            if not listing_id or listing_id == target.id:
                continue # Skip self match
                
            comp_obj = self.listing_cache.get(listing_id)
            if comp_obj:
                # Similarity: Convert L2 distance to rough 0..1 score
                similarity = 1.0 / (1.0 + dist)
                
                comps.append(CompListing(
                    id=comp_obj.id,
                    price=comp_obj.price,
                    features={
                        "sqm": comp_obj.surface_area_sqm or 0,
                        "bedrooms": comp_obj.bedrooms or 0
                    },
                    similarity_score=float(similarity),
                    snapshot_id="TODO_LINK_TO_SNAPSHOT"
                ))
                
        return comps
