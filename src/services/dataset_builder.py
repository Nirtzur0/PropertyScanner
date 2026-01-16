import os
import glob
import pandas as pd
import structlog
from datetime import datetime
from typing import List, Optional
from src.core.domain.schema import RawListing, CanonicalListing
from src.core.config import SNAPSHOTS_DIR
from src.agents.processors.normalizer import IdealistaNormalizerAgent

logger = structlog.get_logger()

class DatasetBuilder:
    """
    Replays historical snapshots to build training datasets.
    """
    def __init__(self, snapshot_dir: str = str(SNAPSHOTS_DIR)):
        self.snapshot_dir = snapshot_dir
        self.normalizer = IdealistaNormalizerAgent()

    def build_dataset(self, source_id: str = "idealista_local_test") -> pd.DataFrame:
        """
        Scans snapshots for the given source, normalizes them, and returns a DataFrame.
        """
        search_pattern = os.path.join(self.snapshot_dir, source_id, "**", "*.html")
        files = glob.glob(search_pattern, recursive=True)
        
        logger.info("dataset_build_started", source=source_id, found_snapshots=len(files))
        
        data_records = []
        
        for filepath in files:
            try:
                # Parse metadata from path/filename
                # Path: .../{source_id}/{date}/{external_id}_{hash}.html
                parts = filepath.split(os.sep)
                # date_str = parts[-2]
                filename = parts[-1] 
                external_id = filename.split("_")[0]
                
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # Reconstruct RawListing
                # URL is lost in snapshot filename, but we construct a fake one or optional
                # For basic normalization, URL often not strictly needed if content is there.
                raw = RawListing(
                    source_id=source_id,
                    external_id=external_id,
                    url=f"http://replay/{external_id}",
                    fetched_at=datetime.fromtimestamp(os.path.getmtime(filepath)),
                    raw_data={"html_snippet": content},
                    html_snapshot_path=filepath
                )
                
                # Normalize
                norm_resp = self.normalizer.run({"raw_listings": [raw]})
                if norm_resp.data:
                    canonical: CanonicalListing = norm_resp.data[0]
                    # Convert to flat dict for ML
                    record = canonical.model_dump()
                    # Flatten location if present
                    if canonical.location:
                         record["lat"] = canonical.location.lat
                         record["lon"] = canonical.location.lon
                         record["address"] = canonical.location.address_full
                    
                    data_records.append(record)
                    
            except Exception as e:
                logger.error("replay_failed", file=filepath, error=str(e))
                continue
                
        df = pd.DataFrame(data_records)
        logger.info("dataset_build_completed", rows=len(df))
        return df

    def save_dataset(self, df: pd.DataFrame, output_path: str = "data/training/training_set.csv"):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("dataset_saved", path=output_path)
