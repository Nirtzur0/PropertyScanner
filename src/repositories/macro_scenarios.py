from typing import Dict, List
import hashlib

from sqlalchemy import inspect, text

from src.repositories.base import RepositoryBase


class MacroScenariosRepository(RepositoryBase):
    def ensure_schema(self) -> None:
        if not self.has_table("macro_scenarios"):
            query = text(
                """
                CREATE TABLE IF NOT EXISTS macro_scenarios (
                    id TEXT PRIMARY KEY,
                    date DATE,
                    source_id TEXT,
                    source_url TEXT,
                    scenario_name TEXT,
                    horizon_year INT,
                    euribor_12m_forecast FLOAT,
                    inflation_forecast FLOAT,
                    gdp_growth_forecast FLOAT,
                    confidence_text TEXT,
                    retrieved_at DATETIME
                )
                """
            )
            with self.engine.begin() as conn:
                conn.execute(query)

        # Ensure columns exist for newer schema.
        for column, ddl in (
            ("source_id", "ALTER TABLE macro_scenarios ADD COLUMN source_id TEXT"),
            ("horizon_year", "ALTER TABLE macro_scenarios ADD COLUMN horizon_year INT"),
            ("retrieved_at", "ALTER TABLE macro_scenarios ADD COLUMN retrieved_at DATETIME"),
            ("fetched_at", "ALTER TABLE macro_scenarios ADD COLUMN fetched_at DATETIME"),
        ):
            if not self.has_column("macro_scenarios", column):
                try:
                    with self.engine.begin() as conn:
                        conn.execute(text(ddl))
                except Exception:
                    pass

    def _id_is_integer(self) -> bool:
        inspector = inspect(self.engine)
        try:
            cols = inspector.get_columns("macro_scenarios")
        except Exception:
            return False
        for col in cols:
            if col.get("name") != "id":
                continue
            col_type = str(col.get("type", "")).lower()
            return "int" in col_type
        return False

    def _stable_int_id(self, key: str) -> int:
        digest = hashlib.md5(key.encode("utf-8")).hexdigest()
        return int(digest[:12], 16)

    def upsert_records(self, records: List[Dict[str, object]]) -> int:
        if not records:
            return 0
        self.ensure_schema()

        id_is_integer = self._id_is_integer()
        has_retrieved_at = self.has_column("macro_scenarios", "retrieved_at")
        has_fetched_at = self.has_column("macro_scenarios", "fetched_at")
        has_source_id = self.has_column("macro_scenarios", "source_id")
        has_horizon = self.has_column("macro_scenarios", "horizon_year")

        columns = [
            "id",
            "date",
            "source_url",
            "scenario_name",
            "euribor_12m_forecast",
            "inflation_forecast",
            "gdp_growth_forecast",
            "confidence_text",
        ]
        if has_source_id:
            columns.append("source_id")
        if has_horizon:
            columns.append("horizon_year")
        if has_retrieved_at:
            columns.append("retrieved_at")
        elif has_fetched_at:
            columns.append("fetched_at")

        placeholders = ", ".join([f":{col}" for col in columns])
        query = text(
            f"""
            INSERT OR REPLACE INTO macro_scenarios
            ({", ".join(columns)})
            VALUES ({placeholders})
            """
        )

        payloads: List[Dict[str, object]] = []
        for record in records:
            source_id = record.get("source_id") or ""
            scenario_name = record.get("scenario_name") or ""
            horizon_year = record.get("horizon_year") or ""
            record_id = f"{source_id}|{scenario_name}|{horizon_year}"
            id_value = self._stable_int_id(record_id) if id_is_integer else record_id

            payload = {
                "id": id_value,
                "date": record.get("date"),
                "source_url": record.get("source_url"),
                "scenario_name": scenario_name,
                "euribor_12m_forecast": record.get("euribor_12m_forecast"),
                "inflation_forecast": record.get("inflation_forecast"),
                "gdp_growth_forecast": record.get("gdp_growth_forecast"),
                "confidence_text": record.get("confidence_text"),
            }
            if has_source_id:
                payload["source_id"] = source_id
            if has_horizon:
                payload["horizon_year"] = record.get("horizon_year")
            if has_retrieved_at:
                payload["retrieved_at"] = record.get("retrieved_at")
            elif has_fetched_at:
                payload["fetched_at"] = record.get("retrieved_at")

            payloads.append(payload)

        with self.engine.begin() as conn:
            result = conn.execute(query, payloads)
        return int(result.rowcount or 0)
