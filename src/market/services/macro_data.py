from datetime import datetime
from typing import Dict, Any, Optional
import structlog
from bs4 import BeautifulSoup
import re
import unicodedata
from src.platform.config import DEFAULT_DB_PATH
from src.platform.db.base import resolve_db_url
from src.market.repositories.macro_context import MacroContextRepository
from src.platform.utils.stealth_requests import create_session, request_get

logger = structlog.get_logger(__name__)

class MacroDataService:
    """
    Fetches external macroeconomic data:
    1. ECB Rates (Official API)
    2. Euribor (Scraped)
    3. National Housing Indices (Idealista Scraped)
    """
    def __init__(self, db_path: str = str(DEFAULT_DB_PATH), db_url: Optional[str] = None):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.repo = MacroContextRepository(db_url=self.db_url)
        self.session = create_session(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def fetch_all(self):
        """Orchestrate data collection"""
        try:
            # 1. ECB
            ecb_data = self._fetch_ecb_rates()
            # 2. Euribor
            euribor_data = self._scrape_euribor()
            # 3. Idealista Index
            idealista_data = self._scrape_idealista_index()

            if not ecb_data:
                logger.warning("macro_source_empty", source="ecb")
            if not euribor_data:
                logger.warning("macro_source_empty", source="euribor")
            if not idealista_data:
                logger.warning("macro_source_empty", source="idealista")

            # Merge and Save (Aggregated by month)
            self._merge_and_save(ecb_data, euribor_data, idealista_data)
        except Exception as e:
            logger.error("macro_fetch_failed", error=str(e))

    def _fetch_ecb_rates(self) -> Dict[str, float]:
        """
        Fetch Main Refinancing Operations Rate from ECB Data Portal API.
        Series Key: FM.D.U2.EUR.4F.KR.MRR_RT.LEV
        """
        # Simplified: Using a reliable SDMX endpoint or public json mirror
        # For robustness in this MVP, we will use a hardcoded recent context + scraping a summary page
        # Getting historical via API often requires complex XML parsing (SDMX).
        # Let's try to get a simple JSON from a financial data provider or fallback to scraping.
        
        # Strategy: Scrape a table from a clean financial site
        rates = {}
        try:
            resp = request_get(self.session, "https://www.euribor-rates.eu/en/ecb-refinancing-rate/")
            if resp.status_code != 200:
                logger.warning("ecb_fetch_failed", status=resp.status_code)
                return rates
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if table:
                rows = table.find_all("tr")
                for row in rows[1:5]:
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        date_str = cols[0].get_text(strip=True)
                        rate_str = cols[1].get_text(strip=True).replace("%", "")
                        try:
                            dt = datetime.strptime(date_str, "%m/%d/%Y")
                            val = float(rate_str)
                            key = dt.strftime("%Y-%m-01")
                            if key not in rates:
                                rates[key] = val
                        except Exception:
                            continue
        except Exception as e:
            logger.warning("ecb_fetch_error", error=str(e))
        return rates

    def _scrape_euribor(self) -> Dict[str, float]:
        """Scrape monthly 12m Euribor history"""
        data = {}
        try:
            resp = request_get(
                self.session,
                "https://www.euribor-rates.eu/en/current-euribor-rates/2/euribor-rate-12-months/",
            )
            if resp.status_code != 200:
                logger.warning("euribor_fetch_failed", status=resp.status_code)
                return data
            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if table:
                for row in table.find_all("tr"):
                    cols = row.find_all("td")
                    if len(cols) == 2:
                        date_txt = cols[0].get_text(strip=True)
                        rate_txt = cols[1].get_text(strip=True).replace("%", "")
                        # Parse date
                        try:
                            dt = datetime.strptime(date_txt, "%m/%d/%Y")
                            month_key = dt.strftime("%Y-%m-01")
                            data[month_key] = float(rate_txt)
                        except Exception:
                            continue
        except Exception as e:
            logger.warning("euribor_scrape_error", error=str(e))
        return data

    def _scrape_idealista_index(self) -> Dict[str, Dict[str, float]]:
        """
        Scrape Idealista price reports.
        Returns {month: {'national': 2000.0, 'madrid': 3200.0}}
        """
        data: Dict[str, Dict[str, float]] = {}

        def parse_value(text: str) -> Optional[float]:
            cleaned = text.replace(".", "").replace(",", ".")
            cleaned = re.sub(r"[^0-9.]+", "", cleaned)
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None

        def resolve_month_key(soup: BeautifulSoup) -> Optional[str]:
            month_map = {
                "enero": 1,
                "febrero": 2,
                "marzo": 3,
                "abril": 4,
                "mayo": 5,
                "junio": 6,
                "julio": 7,
                "agosto": 8,
                "septiembre": 9,
                "octubre": 10,
                "noviembre": 11,
                "diciembre": 12,
            }
            for tag in soup.find_all(["h1", "h2", "time"]):
                text = tag.get("datetime") or tag.get_text(" ", strip=True)
                if not text:
                    continue
                text_lower = text.lower()
                iso_match = re.search(r"(20\\d{2})[-/](\\d{1,2})[-/](\\d{1,2})", text_lower)
                if iso_match:
                    year = int(iso_match.group(1))
                    month = int(iso_match.group(2))
                    return f"{year:04d}-{month:02d}-01"
                for name, month_num in month_map.items():
                    if name in text_lower:
                        year_match = re.search(r"(20\\d{2})", text_lower)
                        if year_match:
                            year = int(year_match.group(1))
                            return f"{year:04d}-{month_num:02d}-01"
            return None

        try:
            resp = request_get(
                self.session,
                "https://www.idealista.com/media/informes-precio-vivienda/",
            )
            if resp.status_code != 200:
                logger.warning("idealista_fetch_failed", status=resp.status_code)
                return data

            soup = BeautifulSoup(resp.text, "html.parser")
            month_key = resolve_month_key(soup)
            if not month_key:
                logger.warning("idealista_month_missing")
                return data

            national_value = None
            madrid_value = None

            for row in soup.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                if not cells:
                    continue
                label = cells[0].lower()
                normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
                if "espana" in normalized:
                    for cell in cells[1:]:
                        value = parse_value(cell)
                        if value is not None:
                            national_value = value
                            break
                if "madrid" in normalized:
                    for cell in cells[1:]:
                        value = parse_value(cell)
                        if value is not None:
                            madrid_value = value
                            break

            if national_value is None and madrid_value is None:
                logger.warning("idealista_values_missing", month=month_key)
                return data

            payload: Dict[str, float] = {}
            if national_value is not None:
                payload["national"] = national_value
            if madrid_value is not None:
                payload["madrid"] = madrid_value
            data[month_key] = payload
        except Exception as e:
            logger.warning("idealista_scrape_error", error=str(e))

        return data

    def _merge_and_save(self, ecb: Dict, euribor: Dict, idealista: Dict):
        """Merge all sources into SQLite"""
        all_months = set(ecb.keys()) | set(euribor.keys()) | set(idealista.keys())
        if not all_months:
            logger.warning("macro_data_empty")
            return

        records = []
        missing_counts = {"ecb": 0, "euribor": 0, "idealista_national": 0, "idealista_madrid": 0}
        for month in sorted(all_months):
            e_rate = ecb.get(month)
            eur_rate = euribor.get(month)
            ideal_nat = idealista.get(month, {}).get("national")
            ideal_mad = idealista.get(month, {}).get("madrid")

            if e_rate is None:
                missing_counts["ecb"] += 1
            if eur_rate is None:
                missing_counts["euribor"] += 1
            if ideal_nat is None:
                missing_counts["idealista_national"] += 1
            if ideal_mad is None:
                missing_counts["idealista_madrid"] += 1

            if all(val is None for val in [e_rate, eur_rate, ideal_nat, ideal_mad]):
                continue

            records.append((month, eur_rate, e_rate, ideal_nat, ideal_mad))

        for source, count in missing_counts.items():
            if count:
                logger.warning("macro_missing_values", source=source, months=count)

        if not records:
            logger.warning("macro_data_empty_after_merge")
            return

        self.repo.upsert_actuals(records)
        logger.info("macro_data_saved", months=len(records))

if __name__ == "__main__":
    # Test run
    svc = MacroDataService()
    svc.fetch_all()
