"""
Enhanced Snapshot Storage Service.
Provides immutable storage for raw listing data (HTML/JSON) with metadata for reproducibility.
"""
import os
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
import structlog
from src.platform.config import SNAPSHOTS_DIR
from pydantic import BaseModel
from src.platform.utils.time import utcnow

logger = structlog.get_logger()

class SnapshotMetadata(BaseModel):
    """Metadata for a stored snapshot."""
    snapshot_id: str
    source_id: str
    external_id: str
    listing_url: str
    content_hash: str
    size_bytes: int
    created_at: datetime
    file_path: str

class SnapshotService:
    """
    Manages the storage of raw data snapshots (HTML/JSON) for reproducibility.
    
    Key Features:
    - Content-addressable storage (hash-based filenames)
    - Structured metadata (JSON sidecar files)
    - Organized by source and date for easy retrieval/cleanup
    """
    def __init__(self, base_dir: str = str(SNAPSHOTS_DIR)):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._metadata_cache: Dict[str, SnapshotMetadata] = {}

    def save_snapshot(
        self, 
        content: str, 
        source_id: str, 
        external_id: str, 
        listing_url: str = "",
        extension: str = "html"
    ) -> Optional[SnapshotMetadata]:
        """
        Saves the content to a file and returns a SnapshotMetadata object.
        
        Storage Structure:
            data/snapshots/{source_id}/{YYYYMMDD}/{content_hash}.{ext}
            data/snapshots/{source_id}/{YYYYMMDD}/{content_hash}.meta.json
        """
        try:
            # Create subdirs
            date_prefix = utcnow().strftime("%Y%m%d")
            save_dir = os.path.join(self.base_dir, source_id, date_prefix)
            os.makedirs(save_dir, exist_ok=True)
            
            # Content Hash for uniqueness/integrity (full hash for ID)
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            snapshot_id = f"{source_id}:{external_id}:{content_hash[:16]}"
            
            # Files
            content_filename = f"{content_hash[:16]}.{extension}"
            meta_filename = f"{content_hash[:16]}.meta.json"
            content_filepath = os.path.join(save_dir, content_filename)
            meta_filepath = os.path.join(save_dir, meta_filename)
            
            # Write content
            with open(content_filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            # Create metadata
            meta = SnapshotMetadata(
                snapshot_id=snapshot_id,
                source_id=source_id,
                external_id=external_id,
                listing_url=listing_url,
                content_hash=content_hash,
                size_bytes=len(content.encode('utf-8')),
                created_at=utcnow(),
                file_path=content_filepath
            )
            
            # Write metadata sidecar
            with open(meta_filepath, "w", encoding="utf-8") as f:
                json.dump(meta.model_dump(mode='json'), f, default=str)
            
            # Cache
            self._metadata_cache[snapshot_id] = meta
                
            logger.debug("snapshot_saved", snapshot_id=snapshot_id, path=content_filepath)
            return meta
            
        except Exception as e:
            logger.error("snapshot_save_failed", error=str(e), source=source_id, id=external_id)
            return None

    def load_snapshot(self, snapshot_id: str) -> Optional[str]:
        """Load raw content by snapshot_id."""
        meta = self._metadata_cache.get(snapshot_id)
        if meta and os.path.exists(meta.file_path):
            with open(meta.file_path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def get_metadata(self, snapshot_id: str) -> Optional[SnapshotMetadata]:
        """Get metadata for a snapshot."""
        return self._metadata_cache.get(snapshot_id)

    def list_snapshots(self, source_id: str = None, date_prefix: str = None) -> list:
        """List snapshots filtered by source and/or date."""
        results = []
        search_dir = self.base_dir
        
        if source_id:
            search_dir = os.path.join(search_dir, source_id)
            if date_prefix:
                search_dir = os.path.join(search_dir, date_prefix)
        
        if not os.path.exists(search_dir):
            return results
            
        for root, _, files in os.walk(search_dir):
            for f in files:
                if f.endswith('.meta.json'):
                    meta_path = os.path.join(root, f)
                    with open(meta_path, "r") as mf:
                        data = json.load(mf)
                        results.append(SnapshotMetadata(**data))
        return results
