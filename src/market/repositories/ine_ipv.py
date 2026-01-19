from typing import List, Optional, Tuple

import pandas as pd
import re
from sqlalchemy import text

from src.market.repositories.official_metrics import OfficialMetricsRepository


class IneIpvRepository(OfficialMetricsRepository):
    provider_id = "ine_ipv"

    def ensure_schema(self) -> None:
        super().ensure_schema()

    def upsert_records(self, records: List[Tuple[str, str, str, str, float]]) -> int:
        if not records:
            return 0
        payloads = []
        for period, region_id, housing_type, metric, value in records:
            if not period or not region_id or metric is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if pd.isna(numeric):
                continue
            period_text = str(period).strip()
            if not period_text:
                continue
            period_date = self._period_to_date(period_text)
            payloads.append(
                {
                    "id": f"{self.provider_id}|{region_id}|{period_text}|{housing_type}|{metric}",
                    "provider_id": self.provider_id,
                    "region_id": region_id,
                    "period": period_text,
                    "period_date": period_date,
                    "housing_type": housing_type,
                    "metric": metric,
                    "value": numeric,
                }
            )
        return self._upsert_rows(payloads)

    def fetch_latest_metric(
        self,
        region_id: str,
        housing_type: str = "general",
        metric: str = "yoy",
    ) -> Optional[Tuple[str, float]]:
        self.ensure_schema()
        query = text(
            """
            SELECT period, value
            FROM official_metrics
            WHERE provider_id = :provider_id
              AND LOWER(region_id) = :region_id
              AND housing_type = :housing_type
              AND metric = :metric
            ORDER BY period_date DESC, period DESC
            LIMIT 1
            """
        )
        params = {
            "provider_id": self.provider_id,
            "region_id": region_id.lower().strip(),
            "housing_type": housing_type,
            "metric": metric,
        }
        with self.engine.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if not row or row[1] is None:
            return None
        return str(row[0]), float(row[1])

    @staticmethod
    def _period_to_date(period: str) -> Optional[str]:
        text = str(period).strip()
        if not text:
            return None
        match = re.match(r"^(\d{4})-?Q([1-4])$", text)
        if match:
            year = int(match.group(1))
            quarter = int(match.group(2))
            month = (quarter - 1) * 3 + 1
            return f"{year}-{month:02d}-01"
        dt = pd.to_datetime(text, format="mixed", errors="coerce")
        if pd.isna(dt):
            return None
        if isinstance(dt, pd.Timestamp):
            return dt.strftime("%Y-%m-%d")
        return str(dt)
