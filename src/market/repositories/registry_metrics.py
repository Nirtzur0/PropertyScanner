from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from src.market.repositories.official_metrics import OfficialMetricsRepository


class RegistryMetricsRepository(OfficialMetricsRepository):
    provider_id: str = ""
    registry_metrics = (
        "txn_count",
        "mortgage_count",
        "price_sqm",
        "price_sqm_yoy",
        "price_sqm_qoq",
    )

    def __init__(
        self,
        *,
        provider_id: Optional[str] = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        if provider_id:
            self.provider_id = provider_id

    def _require_provider(self) -> None:
        if not self.provider_id:
            raise ValueError("registry_provider_id_missing")

    def ensure_schema(self) -> None:
        super().ensure_schema()

    def upsert_records(self, records: List[Dict[str, object]]) -> int:
        if not records:
            return 0
        self._require_provider()
        payloads: List[Dict[str, object]] = []
        saved_records = 0
        for record in records:
            region_id = record.get("region_id")
            period_date = self._normalize_period_date(record.get("period_date"))
            if not region_id or not period_date:
                continue
            period = str(period_date)
            record_saved = False
            for metric in self.registry_metrics:
                value = record.get(metric)
                if value is None or pd.isna(value):
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                record_saved = True
                payloads.append(
                    {
                        "id": f"{self.provider_id}|{region_id}|{period}|{metric}",
                        "provider_id": self.provider_id,
                        "region_id": region_id,
                        "period": period,
                        "period_date": period_date,
                        "housing_type": None,
                        "metric": metric,
                        "value": numeric,
                    }
                )
            if record_saved:
                saved_records += 1
        self._upsert_rows(payloads)
        return saved_records

    @staticmethod
    def _normalize_period_date(value: object) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d")
        text = str(value).strip()
        if not text:
            return None
        dt = pd.to_datetime(text, format="mixed", errors="coerce")
        if pd.isna(dt):
            return text
        if isinstance(dt, pd.Timestamp):
            return dt.strftime("%Y-%m-%d")
        return text

    def load_series(self, region_id: str) -> pd.DataFrame:
        self._require_provider()
        query = text(
            """
            SELECT
                period_date,
                metric,
                value
            FROM official_metrics
            WHERE provider_id = :provider_id
              AND LOWER(region_id) = :region_id
            ORDER BY period_date ASC
            """
        )
        df = pd.read_sql(
            query,
            self.engine,
            params={
                "provider_id": self.provider_id,
                "region_id": region_id.lower().strip(),
            },
        )
        if df.empty:
            return df
        df["period_date"] = pd.to_datetime(df["period_date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["period_date"])
        if df.empty:
            return df
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        wide = df.pivot_table(index="period_date", columns="metric", values="value", aggfunc="last")
        wide = wide.reset_index()
        wide.columns.name = None
        for metric in self.registry_metrics:
            if metric not in wide.columns:
                wide[metric] = None
        wide = wide[["period_date"] + list(self.registry_metrics)]
        return wide.sort_values("period_date").reset_index(drop=True)

    def fetch_latest_period_date(self, region_id: str) -> Optional[pd.Timestamp]:
        self._require_provider()
        query = text(
            """
            SELECT MAX(period_date) as period_date
            FROM official_metrics
            WHERE provider_id = :provider_id
              AND LOWER(region_id) = :region_id
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                query,
                {
                    "provider_id": self.provider_id,
                    "region_id": region_id.lower().strip(),
                },
            ).fetchone()
        if not row or row[0] is None:
            return None
        dt = pd.to_datetime(row[0], format="mixed", errors="coerce")
        if pd.isna(dt):
            return None
        return dt
