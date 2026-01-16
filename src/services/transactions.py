import csv
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import structlog
from sqlalchemy import func

from src.core.config import DEFAULT_DB_PATH
from src.core.domain.models import DBListing
from src.repositories.base import resolve_db_url
from src.repositories.ine_ipv import IneIpvRepository
from src.services.eri_signals import ERISignalsService
from src.services.storage import StorageService

logger = structlog.get_logger(__name__)


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_listing_type(value: Optional[str], fallback: str = "sale") -> str:
    if not value:
        return fallback
    text = str(value).strip().lower()
    if text not in {"sale", "rent"}:
        return fallback
    return text


def _first_value(record: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for key in keys:
        value = record.get(key)
        if value:
            return str(value).strip()
    return None


def _normalize_address(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).lower().strip()
    if not text:
        return None
    text = re.sub(r"\bc/\s*", "calle ", text)
    replacements = [
        (r"\bavda\.?\b", "avenida"),
        (r"\bav\.?\b", "avenida"),
        (r"\bcl\.?\b", "calle"),
        (r"\bpl\.?\b", "plaza"),
        (r"\bpza\.?\b", "plaza"),
        (r"\bpso\.?\b", "paseo"),
        (r"\bctra\.?\b", "carretera"),
        (r"\bcarret\.?\b", "carretera"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _address_tokens(value: Optional[str]) -> List[str]:
    if not value:
        return []
    stop = {
        "calle",
        "avenida",
        "paseo",
        "plaza",
        "carretera",
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "y",
    }
    tokens = [t for t in value.split(" ") if t]
    return [t for t in tokens if t not in stop]


def _address_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    tokens_a = _address_tokens(a)
    tokens_b = _address_tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    overlap = len(set_a & set_b) / max(1, len(set_a | set_b))
    seq = SequenceMatcher(None, a, b).ratio()
    score = 0.6 * overlap + 0.4 * seq
    nums_a = {t for t in tokens_a if t.isdigit()}
    nums_b = {t for t in tokens_b if t.isdigit()}
    if nums_a and nums_b and nums_a.isdisjoint(nums_b):
        score *= 0.75
    return score


def _load_records(path: Path) -> Iterable[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
        return

    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


class TransactionsIngestService:
    """
    Ingest sold/transaction data and map it onto listings as ground-truth labels.
    """

    def __init__(self, *, db_path: str = str(DEFAULT_DB_PATH), db_url: Optional[str] = None) -> None:
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.storage = StorageService(db_url=self.db_url)
        self.eri_signals = ERISignalsService(db_url=self.db_url)
        self.ine_repo = IneIpvRepository(db_url=self.db_url)
        self._market_change_cache: Dict[str, Optional[float]] = {}

    def ingest_file(
        self,
        path: str,
        *,
        default_listing_type: str = "sale",
        default_source_id: Optional[str] = None,
        enable_fuzzy_address_match: bool = True,
        address_min_similarity: float = 0.82,
        max_address_candidates: int = 200,
        max_price_deviation_pct: float = 0.30,
        max_date_deviation_days: int = 730,
        max_date_early_days: int = 45,
        use_official_market_adjustment: bool = True,
    ) -> Dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"transactions_file_not_found:{file_path}")

        processed = 0
        matched = 0
        updated = 0
        unmatched = 0
        skipped = 0
        fuzzy_matched = 0
        price_guard_skipped = 0
        date_guard_skipped = 0

        session = self.storage.get_session()
        try:
            for record in _load_records(file_path):
                processed += 1

                listing_id = record.get("listing_id") or record.get("id")
                source_id = record.get("source_id") or default_source_id
                external_id = record.get("external_id")
                url = record.get("url")

                sold_price = (
                    _parse_float(record.get("sold_price"))
                    or _parse_float(record.get("transaction_price"))
                    or _parse_float(record.get("price_sold"))
                    or _parse_float(record.get("closing_price"))
                    or _parse_float(record.get("price"))
                )
                if not sold_price or sold_price <= 0:
                    skipped += 1
                    continue

                sold_at = (
                    _parse_datetime(record.get("sold_at"))
                    or _parse_datetime(record.get("transaction_date"))
                    or _parse_datetime(record.get("closed_at"))
                    or _parse_datetime(record.get("close_date"))
                    or _parse_datetime(record.get("date"))
                )
                listing_type = _normalize_listing_type(record.get("listing_type"), default_listing_type)

                listing = None
                if listing_id:
                    listing = session.query(DBListing).filter(DBListing.id == listing_id).first()
                if listing is None and source_id and external_id:
                    listing = (
                        session.query(DBListing)
                        .filter(DBListing.source_id == source_id, DBListing.external_id == external_id)
                        .first()
                    )
                if listing is None and url:
                    listing = session.query(DBListing).filter(DBListing.url == url).first()

                if listing is None and enable_fuzzy_address_match:
                    listing, _match_score = self._match_by_address(
                        session=session,
                        record=record,
                        min_similarity=address_min_similarity,
                        max_candidates=max_address_candidates,
                    )
                    if listing is not None:
                        fuzzy_matched += 1

                if listing is None:
                    unmatched += 1
                    continue

                if not self._passes_price_guard(
                    listing,
                    sold_price,
                    sold_at,
                    max_price_deviation_pct=max_price_deviation_pct,
                    use_official_market_adjustment=use_official_market_adjustment,
                ):
                    price_guard_skipped += 1
                    continue

                if not self._passes_date_guard(
                    listing,
                    sold_at,
                    max_date_deviation_days=max_date_deviation_days,
                    max_date_early_days=max_date_early_days,
                ):
                    date_guard_skipped += 1
                    continue

                matched += 1
                listing.sold_price = sold_price
                if sold_at:
                    listing.sold_at = sold_at
                listing.status = "sold"
                listing.listing_type = listing_type
                if record.get("city") and not listing.city:
                    listing.city = str(record.get("city")).strip()
                address_value = _first_value(
                    record,
                    [
                        "address",
                        "address_full",
                        "street_address",
                        "full_address",
                        "direccion",
                        "direccion_completa",
                        "direccion_full",
                    ],
                )
                if address_value and not listing.address_full:
                    listing.address_full = address_value

                updated += 1

            session.commit()
        finally:
            session.close()

        summary = {
            "processed": processed,
            "matched": matched,
            "updated": updated,
            "unmatched": unmatched,
            "skipped": skipped,
            "fuzzy_matched": fuzzy_matched,
            "price_guard_skipped": price_guard_skipped,
            "date_guard_skipped": date_guard_skipped,
        }
        logger.info("transactions_ingest_summary", **summary)
        return summary

    def _match_by_address(
        self,
        *,
        session,
        record: Dict[str, Any],
        min_similarity: float,
        max_candidates: int,
    ) -> Tuple[Optional[DBListing], float]:
        address = _first_value(
            record,
            [
                "address",
                "address_full",
                "street_address",
                "full_address",
                "direccion",
                "direccion_completa",
                "direccion_full",
            ],
        )
        if not address:
            return None, 0.0
        address_norm = _normalize_address(address)
        if not address_norm or len(address_norm) < 6:
            return None, 0.0

        city = _first_value(
            record,
            ["city", "municipality", "municipio", "locality", "localidad", "town"],
        )
        zip_code = _first_value(record, ["zip", "zip_code", "postal_code", "postcode", "codigo_postal"])
        if zip_code:
            zip_code = re.sub(r"\s+", "", zip_code)

        query = session.query(DBListing).filter(DBListing.address_full.isnot(None))
        if city:
            city_norm = city.lower().strip()
            query = query.filter(func.lower(DBListing.city) == city_norm)
        if zip_code:
            query = query.filter(DBListing.zip_code == zip_code)

        candidates = query.limit(max_candidates).all()
        if not candidates:
            return None, 0.0

        best = None
        best_score = 0.0
        for cand in candidates:
            cand_norm = _normalize_address(cand.address_full)
            score = _address_similarity(address_norm, cand_norm)
            if score > best_score:
                best_score = score
                best = cand

        if best is None or best_score < min_similarity:
            return None, best_score
        return best, best_score

    def _listing_reference_date(self, listing: DBListing) -> Optional[datetime]:
        return listing.listed_at or listing.updated_at or listing.fetched_at

    def _passes_date_guard(
        self,
        listing: DBListing,
        sold_at: Optional[datetime],
        *,
        max_date_deviation_days: int,
        max_date_early_days: int,
    ) -> bool:
        if not sold_at:
            return True
        listing_date = self._listing_reference_date(listing)
        if not listing_date:
            return True
        delta_days = (sold_at - listing_date).days
        if delta_days < -abs(max_date_early_days):
            return False
        if abs(delta_days) > max_date_deviation_days:
            return False
        return True

    def _passes_price_guard(
        self,
        listing: DBListing,
        sold_price: float,
        sold_at: Optional[datetime],
        *,
        max_price_deviation_pct: float,
        use_official_market_adjustment: bool,
    ) -> bool:
        if listing.listing_type and str(listing.listing_type).lower() == "rent":
            return True
        ask_price = listing.price
        if not ask_price or ask_price <= 0:
            return True
        max_delta = max(0.0, float(max_price_deviation_pct))
        if use_official_market_adjustment:
            max_delta = self._adjust_max_delta_for_market(
                listing,
                sold_at,
                base_delta=max_delta,
            )
        max_delta = min(max_delta, 0.6)
        diff_pct = abs(sold_price - ask_price) / ask_price
        return diff_pct <= max_delta

    def _adjust_max_delta_for_market(
        self,
        listing: DBListing,
        sold_at: Optional[datetime],
        *,
        base_delta: float,
    ) -> float:
        listing_date = self._listing_reference_date(listing)
        if not listing_date or not sold_at:
            return base_delta
        region_id = (listing.city or "").lower().strip()
        if not region_id:
            return base_delta
        price_change = self._market_price_change(region_id, sold_at)
        if price_change is None:
            return base_delta
        years = abs((sold_at - listing_date).days) / 365.0
        if years <= 0:
            return base_delta
        return base_delta + min(0.2, abs(price_change) * years)

    def _market_price_change(self, region_id: str, as_of_date: datetime) -> Optional[float]:
        region_key = region_id.lower().strip()
        if region_key in self._market_change_cache:
            return self._market_change_cache[region_key]

        change = None
        try:
            signals = self.eri_signals.get_signals(region_key, as_of_date, allow_proxy=False)
            if signals:
                change = _parse_float(signals.get("registral_price_sqm_change"))
        except Exception:
            change = None

        if change is None:
            for region in (region_key, "national", "total nacional"):
                record = self.ine_repo.fetch_latest_metric(region, housing_type="general", metric="yoy")
                if record:
                    _, value = record
                    change = value
                    break

        self._market_change_cache[region_key] = change
        return change
