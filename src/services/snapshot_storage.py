import os
import hashlib
from datetime import datetime
import structlog

logger = structlog.get_logger()

class SnapshotService:
    """
    Manages the storage of raw data snapshots (HTML/JSON) for reproducibility.
    """
    def __init__(self, base_dir: str = "data/snapshots"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def save_snapshot(self, content: str, source_id: str, external_id: str, extension: str = "html") -> str:
        """
        Saves the content to a file and returns the relative path.
        Structure: data/snapshots/{source_id}/{date_prefix}/{external_id}_{hash}.{ext}
        """
        try:
            # Create subdirs
            date_prefix = datetime.now().strftime("%Y%m%d")
            save_dir = os.path.join(self.base_dir, source_id, date_prefix)
            os.makedirs(save_dir, exist_ok=True)
            
            # Content Hash for uniqueness/integrity
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
            
            filename = f"{external_id}_{content_hash}.{extension}"
            filepath = os.path.join(save_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
                
            logger.info("snapshot_saved", path=filepath)
            return filepath
            
        except Exception as e:
            logger.error("snapshot_save_failed", error=str(e), source=source_id, id=external_id)
            return None
