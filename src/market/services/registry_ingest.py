from __future__ import annotations

from datetime import datetime
import os
import re
from typing import List, Optional

import pandas as pd
import structlog

from src.platform.config import DEFAULT_DB_PATH
from src.platform.db.base import resolve_db_url
from src.platform.settings import AppConfig, RegistrySourceConfig
from src.platform.utils.config import load_app_config_safe
from src.market.repositories.eri_metrics import ERIMetricsRepository
from src.market.repositories.it_registry_metrics import ItalyRegistryMetricsRepository
from src.market.repositories.uk_registry_metrics import UKRegistryMetricsRepository
from src.market.repositories.ine_ipv import IneIpvRepository
from src.market.services.registry_canonical import RegistryCanonicalizer

logger = structlog.get_logger(__name__)


class RegistryIngestService:
    """
    Ingests official registry datasets into the canonical registry schema.
    """

    def __init__(
        self,
        db_path: str = str(DEFAULT_DB_PATH),
        db_url: Optional[str] = None,
        app_config: Optional[AppConfig] = None,
    ) -> None:
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.app_config = app_config or load_app_config_safe()
        self.canonicalizer = RegistryCanonicalizer(app_config=self.app_config)
        self._repositories = {
            "eri_es": ERIMetricsRepository(db_url=self.db_url),
            "uk_land_registry": UKRegistryMetricsRepository(db_url=self.db_url),
            "it_omi_registry": ItalyRegistryMetricsRepository(db_url=self.db_url),
            "ine_ipv": IneIpvRepository(db_url=self.db_url),
        }

    def run(self) -> int:
        registry_cfg = getattr(self.app_config, "registry", None)
        if not registry_cfg:
            return 0

        total = 0
        for source in registry_cfg.sources:
            if not source.enabled:
                continue
            try:
                total += self._ingest_source(source)
            except Exception as exc:
                logger.warning(
                    "registry_source_ingest_failed",
                    provider_id=source.provider_id,
                    error=str(exc),
                )
        if total:
            logger.info("registry_sources_ingested", count=total)
        return total

    def _ingest_source(self, source: RegistrySourceConfig) -> int:
        repo = self._repositories.get(source.provider_id)
        if repo is None:
            logger.warning("registry_provider_unknown", provider_id=source.provider_id)
            return 0
        
        # Specialized path for INE IPV due to different schema
        if source.provider_id == "ine_ipv":
            return self._ingest_ine_source(source, repo)

        if source.kind.lower() != "csv":
            logger.warning(
                "registry_source_kind_unsupported",
                provider_id=source.provider_id,
                kind=source.kind,
            )
            return 0

        frames: List[pd.DataFrame] = []
        for path in source.csv_paths or []:
            frames.append(self._load_csv(path, source))
        for url in source.csv_urls or []:
            frames.append(self._load_csv(url, source))
        
        if not frames:
            logger.info("registry_source_no_inputs", provider_id=source.provider_id)
            return 0

        df = pd.concat(frames, ignore_index=True)
        if df.empty:
            return 0

        df = self._normalize_frame(df, source)
        if df.empty:
            return 0

        records = self._to_records(df)
        if not records:
            return 0

        saved = repo.upsert_records(records)
        logger.info("registry_source_saved", provider_id=source.provider_id, count=saved)
        return saved

    def _ingest_ine_source(self, source: RegistrySourceConfig, repo: IneIpvRepository) -> int:
        frames = []
        for path in source.csv_paths or []:
            frames.append(self._load_csv(path, source))
        
        if not frames:
            return 0
            
        df = pd.concat(frames, ignore_index=True)
        if df.empty:
            return 0
            
        # Normalize columns manually for INE
        df = df.copy()
        df.columns = [self._normalize_column(col) for col in df.columns]
        
        region_col = self._normalize_column(source.region_column)
        date_col = self._normalize_column(source.date_column)
        value_col = self._normalize_column(source.price_column) # Map 'value' to price_column config
        
        if not all(c in df.columns for c in [region_col, date_col, value_col]):
            return 0
            
        records = []
        for row in df.to_dict("records"):
            region = row.get(region_col)
            period = row.get(date_col)
            val = row.get(value_col)
            
            if not region or not period or val is None:
                continue
                
            norm_region = region.strip() # INE regions don't always need canonicalization if we trust them, but we should strip.
            # INE Period format is typically "2023T3" or "2023Q3"
            norm_period = str(period).strip().replace("T", "Q")
            
            try:
                numeric_val = float(val)
            except (ValueError, TypeError):
                continue
                
            # Default to "general" type and "yoy" metric if not specified in config
            #Ideally config should support mapping these, but for now we assume Index = Value (metric=index or yoy?)
            # Usually INE IPV table is "Index". 
            # We'll store it as metric="index" if values are ~100+, or "yoy" if small.
            # Let's assume metric="index" by default for IPV.
            records.append((norm_period, norm_region, "general", "index", numeric_val))
            
        saved = repo.upsert_records(records)
        logger.info("registry_ine_saved", count=saved)
        return saved

    def _load_csv(self, location: str, source: RegistrySourceConfig) -> pd.DataFrame:
        logger.info("registry_source_load", provider_id=source.provider_id, location=location)
        
        # Check if location is a URL
        if location.startswith("http://") or location.startswith("https://"):
            return self._download_and_read_csv(location, source)

        if source.has_header:
            return pd.read_csv(location, sep=source.delimiter, encoding=source.encoding)
        
        names = source.column_names if source.column_names else None
        return pd.read_csv(
            location,
            sep=source.delimiter,
            encoding=source.encoding,
            header=None,
            names=names
        )

    def _download_and_read_csv(self, url: str, source: RegistrySourceConfig) -> pd.DataFrame:
        import requests
        import io
        from src.platform.settings import AgentDefaultsConfig

        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        
        logger.info("registry_downloading", url=url)
        try:
            with requests.get(url, headers=headers, stream=True) as r:
                r.raise_for_status()
                # For large files, we might want to save to disk first, 
                # but for simplicity and memory (these are <500MB usually for updates), memory might work.
                # However, UK full dump is huge. The monthly update is small.
                # Let's write to a temp file to be safe.
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    for chunk in r.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                    tmp_path = tmp.name
            
            logger.info("registry_downloaded", path=tmp_path)
            # Now read from the temp file
            df = self._load_csv(tmp_path, source)
            os.unlink(tmp_path) # Clean up
            return df
        except Exception as e:
            logger.error("registry_download_failed", url=url, error=str(e))
            return pd.DataFrame()

    def _normalize_frame(self, df: pd.DataFrame, source: RegistrySourceConfig) -> pd.DataFrame:
        df = df.copy()
        df.columns = [self._normalize_column(col) for col in df.columns]

        region_col = self._normalize_column(source.region_column)
        date_col = self._normalize_column(source.date_column)
        if region_col not in df.columns or date_col not in df.columns:
            missing = []
            if region_col not in df.columns:
                missing.append(source.region_column)
            if date_col not in df.columns:
                missing.append(source.date_column)
            logger.warning(
                "registry_source_missing_columns",
                provider_id=source.provider_id,
                missing=missing,
            )
            return pd.DataFrame()

        df["region_id"] = df[region_col].apply(
            lambda val: self.canonicalizer.canonicalize(
                val,
                country_code=source.country_code,
                provider_id=source.provider_id,
            )
        )
        df["period_date"] = df[date_col].apply(
            lambda val: self._parse_period(val, source.date_format)
        )

        df = df.dropna(subset=["region_id", "period_date"])
        if df.empty:
            return df

        df["region_id"] = df["region_id"].astype(str).str.strip()
        df = df[df["region_id"] != ""]
        if df.empty:
            return df

        df["period_date"] = pd.to_datetime(df["period_date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["period_date"])
        if df.empty:
            return df

        df = self._attach_numeric(df, "txn_count", source.txn_column)
        df = self._attach_numeric(df, "mortgage_count", source.mortgage_column)
        df = self._attach_numeric(df, "price_sqm", source.price_column)
        df = self._attach_numeric(df, "price_sqm_yoy", source.price_yoy_column)
        df = self._attach_numeric(df, "price_sqm_qoq", source.price_qoq_column)

        df = df.sort_values(["region_id", "period_date"]).reset_index(drop=True)
        df = self._derive_changes(df)

        df["period_date"] = df["period_date"].dt.strftime("%Y-%m-%d")
        return df[
            [
                "region_id",
                "period_date",
                "txn_count",
                "mortgage_count",
                "price_sqm",
                "price_sqm_yoy",
                "price_sqm_qoq",
            ]
        ]

    def _attach_numeric(
        self,
        df: pd.DataFrame,
        out_col: str,
        source_col: Optional[str],
    ) -> pd.DataFrame:
        if not source_col:
            df[out_col] = None
            return df
        norm_col = self._normalize_column(source_col)
        if norm_col not in df.columns:
            df[out_col] = None
            return df
        df[out_col] = pd.to_numeric(df[norm_col], errors="coerce")
        return df

    def _derive_changes(self, df: pd.DataFrame) -> pd.DataFrame:
        if "price_sqm" not in df.columns:
            return df
        if df["price_sqm"].isna().all():
            return df

        if "price_sqm_yoy" not in df.columns or df["price_sqm_yoy"].isna().all():
            periods = self._infer_yoy_periods(df)
            df["price_sqm_yoy"] = (
                df.groupby("region_id")["price_sqm"].pct_change(periods=periods)
            )
        if "price_sqm_qoq" not in df.columns or df["price_sqm_qoq"].isna().all():
            df["price_sqm_qoq"] = df.groupby("region_id")["price_sqm"].pct_change(periods=1)
        return df

    def _infer_yoy_periods(self, df: pd.DataFrame) -> int:
        diffs = df.groupby("region_id")["period_date"].diff().dt.days.dropna()
        if diffs.empty:
            return 4
        median_days = diffs.median()
        if median_days >= 60:
            return 4
        return 12

    def _to_records(self, df: pd.DataFrame) -> List[dict]:
        records: List[dict] = []
        for row in df.to_dict("records"):
            region_id = row.get("region_id")
            period_date = row.get("period_date")
            if not region_id or not period_date:
                continue
            records.append(
                {
                    "id": f"{region_id}|{period_date}",
                    "region_id": region_id,
                    "period_date": period_date,
                    "txn_count": row.get("txn_count"),
                    "mortgage_count": row.get("mortgage_count"),
                    "price_sqm": row.get("price_sqm"),
                    "price_sqm_yoy": row.get("price_sqm_yoy"),
                    "price_sqm_qoq": row.get("price_sqm_qoq"),
                }
            )
        return records

    @staticmethod
    def _parse_period(value: object, date_format: Optional[str]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()

        text = str(value).strip()
        if not text:
            return None

        if date_format:
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                return None

        lowered = text.lower()
        if "q" in lowered:
            parts = lowered.replace(" ", "").replace("_", "-")
            match = re.match(r"^(\d{4})-?q([1-4])$", parts)
            if match:
                year = int(match.group(1))
                quarter = int(match.group(2))
                month = quarter * 3
                return datetime(year, month, 1)

        dt = pd.to_datetime(text, format="mixed", errors="coerce")
        if pd.isna(dt):
            return None
        if isinstance(dt, pd.Timestamp):
            return dt.to_pydatetime()
        return dt

    @staticmethod
    def _normalize_column(value: str) -> str:
        return str(value).strip().lower().replace(" ", "_")
