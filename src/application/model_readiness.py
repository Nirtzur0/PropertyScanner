from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text

from src.core.runtime import RuntimeConfig
from src.platform.storage import StorageService


class ModelReadinessService:
    def __init__(self, *, storage: StorageService, runtime_config: RuntimeConfig) -> None:
        self.storage = storage
        self.runtime_config = runtime_config

    def sale_training_readiness(self) -> Dict[str, Any]:
        thresholds = self.runtime_config.model_readiness
        query = text(
            """
            SELECT
                SUM(CASE WHEN listing_type = 'sale' THEN 1 ELSE 0 END) AS sale_rows,
                SUM(CASE WHEN listing_type = 'sale' AND sold_price IS NOT NULL AND sold_price > 0 THEN 1 ELSE 0 END) AS closed_label_rows
            FROM listings
            """
        )
        with self.storage.engine.connect() as conn:
            row = conn.execute(query).mappings().one()
        sale_rows = int(row["sale_rows"] or 0)
        closed_label_rows = int(row["closed_label_rows"] or 0)
        ratio = float(closed_label_rows) / float(sale_rows) if sale_rows > 0 else 0.0
        ready = (
            closed_label_rows >= thresholds.sale_min_closed_labels
            and ratio >= thresholds.sale_min_closed_ratio
        )
        reasons = []
        if closed_label_rows < thresholds.sale_min_closed_labels:
            reasons.append("closed_label_floor_not_met")
        if ratio < thresholds.sale_min_closed_ratio:
            reasons.append("closed_label_ratio_not_met")
        return {
            "ready": ready,
            "sale_rows": sale_rows,
            "closed_label_rows": closed_label_rows,
            "closed_label_ratio": round(ratio, 6),
            "reasons": reasons,
        }
