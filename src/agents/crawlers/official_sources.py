"""
Official Sources Agent

Fetches "ground truth" market data from official Spanish government sources:
1. INE (Instituto Nacional de Estadística): Housing Price Index (IPV).
2. ERI (Estadística Registral Inmobiliaria): Registered transaction stats (College of Registrars).

These sources provide the authoritative "macro" signal to anchor our "micro" listing observations.
"""

import requests
import pandas as pd
import structlog
from datetime import datetime
from typing import Optional, List, Dict
from src.core.config import DEFAULT_DB_PATH
from src.repositories.eri_metrics import ERIMetricsRepository
from src.repositories.ine_ipv import IneIpvRepository

logger = structlog.get_logger(__name__)

class OfficialSourcesAgent:
    def __init__(self, db_path: str = str(DEFAULT_DB_PATH)):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PropertyScanner/1.0 (Research; contact@example.com)"
        })
        self.ine_repo = IneIpvRepository(db_path=db_path)
        self.eri_repo = ERIMetricsRepository(db_path=db_path)

    def run(self):
        """Main execution flow."""
        logger.info("official_sources_start")
        
        # 1. Fetch INE IPV
        try:
            self.fetch_ine_ipv()
        except Exception as e:
            logger.error("ine_ipv_fetch_failed", error=str(e))

        # 2. Fetch ERI
        try:
            # For demo/MVP, we try to fetch the latest available quarters
            current_year = datetime.now().year
            self.fetch_eri_stats(year=current_year)
            self.fetch_eri_stats(year=current_year - 1)
        except Exception as e:
             logger.error("eri_fetch_failed", error=str(e))
             
        logger.info("official_sources_finished")

    def fetch_ine_ipv(self, table_id: str = "25171"):
        """
        Fetch Housing Price Index (IPV) from INE API.
        Table 25171: IPV by Autonomous Community and type.
        """
        url = f"https://servicios.ine.es/wstempus/js/es/DATOS_TABLA/{table_id}?nult=20" # Last 20 periods
        logger.info("fetching_ine_ipv", url=url)
        
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        records = []
        for entry in data:
            # INE structure: "Nombre" contains metadata, "Data" contains time series
            # Example Name: "Total Nacional. Índice general. Variación anual."
            name = entry.get("Nombre", "")
            
            # Simple parsing of region and type
            region = "National"
            if "Total Nacional" not in name:
                # Keep it simple for now, can implement robust region mapping later
                region = name.split(".")[0] 
            
            dtype = "general"
            if "Vivienda nueva" in name: dtype = "new"
            elif "segunda mano" in name: dtype = "used"
            
            metric = "index"
            if "Variación anual" in name: metric = "yoy"
            elif "Variación trimestral" in name: metric = "qoq"
            
            for d in entry.get("Data", []):
                # Anyo: 2024, FK_Periodo: 1 (Q1), 2 (Q2)... check INE docs for period codes
                # Usually period codes for quarters are 19, 20, 21, 22 or similar.
                # Actually INE 'Periodo' text is usually "Trimestre 1/2024"
                p_text = d.get("Anyo", "") # This sometimes just year
                
                # Use date_epoch for reliable date
                ts = d.get("Fecha", 0) / 1000 # ms to seconds
                date_str = datetime.fromtimestamp(ts).strftime("%Y-Q%q")
                # Fix Quarter calc
                dt = datetime.fromtimestamp(ts)
                quarter = (dt.month - 1) // 3 + 1
                period_str = f"{dt.year}-Q{quarter}"
                
                val = d.get("Valor")
                if val is not None:
                     records.append((period_str, region, dtype, metric, val))

        # Pivot/Save logic would go here. For now, we store raw-ish
        self._save_ine_ipv(records)

    def fetch_eri_stats(self, year: int):
        """
        Fetch ERI (Registral) stats from open data CSVs.
        Using a flexible URL pattern based on user provided examples.
        """
        # Note: This URL pattern is hypothetical based on user inputs. 
        # In a real scenario, we might need a dynamic scraper for the catalog.
        # We try quarters 1-4
        base_urls = [
             f"https://opendata.euskadi.eus/contenidos/estadistica/ovv_registral{str(year)[-2:]}/opendata/ER.{{quarter}}.{year}.csv",
             # Add other known regional/national endpoints here
        ]
        
        for q in range(1, 5):
            for pattern in base_urls:
                url = pattern.format(quarter=q)
                try:
                    logger.info("fetching_eri_csv", url=url)
                    df = pd.read_csv(url, sep=";", encoding="latin1") # Common Spanish format
                    
                    if not df.empty:
                        self._process_eri_csv(df, year, q)
                        break # Found it
                except Exception as e:
                    # 404 is expected for future quarters
                    pass

    def _process_eri_csv(self, df: pd.DataFrame, year: int, quarter: int):
        """
        Normalize and save ERI CSV data.
        """
        # Normalize columns (handling Spanish headers)
        # Example headers: "Territorio", "N_Transacciones", "Precio_m2", "Hipotecas"
        df.columns = [c.strip().lower() for c in df.columns]
        
        records = []
        period_date = f"{year}-{quarter*3:02d}-01" # End of quarter approx
        
        for _, row in df.iterrows():
            # Map region
            region_raw = str(row.get("territorio", "unknown"))
            # Skip totals or headers if mixed
            
            # Extract metrics
            txn = pd.to_numeric(row.get("n_transacciones", 0), errors="coerce") or 0
            price = pd.to_numeric(row.get("precio_m2", 0), errors="coerce") or 0
            mortgages = pd.to_numeric(row.get("hipotecas", 0), errors="coerce") or 0
            
            if txn > 0 or price > 0:
                records.append({
                    "region_id": region_raw,
                    "period_date": period_date,
                    "txn_count": int(txn),
                    "mortgage_count": int(mortgages),
                    "price_sqm": float(price)
                })
                
        self._save_eri_metrics(records)

    def _save_ine_ipv(self, records: List[tuple]):
        if not records:
            return
        saved = self.ine_repo.upsert_records(records)
        logger.info("ine_ipv_saved", count=saved)

    def _save_eri_metrics(self, records: List[Dict]):
        if not records:
            return
        payloads = []
        for record in records:
            payloads.append(
                {
                    "id": f"{record['region_id']}|{record['period_date']}",
                    "region_id": record["region_id"],
                    "period_date": record["period_date"],
                    "txn_count": record["txn_count"],
                    "mortgage_count": record["mortgage_count"],
                    "price_sqm": record["price_sqm"],
                }
            )
        saved = self.eri_repo.upsert_records(payloads)
        logger.info("eri_metrics_saved", count=saved)

if __name__ == "__main__":
    OfficialSourcesAgent().run()
