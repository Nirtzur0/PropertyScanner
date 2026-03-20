from __future__ import annotations

import hashlib
import json
import re
from abc import abstractmethod
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.listings.crawl_contract import detect_block_reason_from_html
from src.platform.agents.base import AgentResponse, BaseAgent
from src.platform.domain.schema import CanonicalListing, Currency, PropertyType, RawListing


class DetailPageNormalizerAgent(BaseAgent):
    def __init__(self, *, name: str) -> None:
        super().__init__(name=name)

    def _parse_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        normalized = text.replace("\xa0", " ")
        if "," in normalized and "." in normalized:
            if normalized.rfind(",") > normalized.rfind("."):
                normalized = normalized.replace(".", "").replace(",", ".")
            else:
                normalized = normalized.replace(",", "")
        else:
            normalized = normalized.replace(",", ".")
        cleaned = re.sub(r"[^0-9.\-]", "", normalized)
        if cleaned.count(".") > 1:
            parts = cleaned.split(".")
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_int(self, value: Any) -> Optional[int]:
        parsed = self._parse_float(value)
        if parsed is None:
            return None
        return int(round(parsed))

    def _parse_date(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                payload = json.loads(script.string)
            except Exception:
                continue
            candidate = self._select_listing_json(payload)
            if candidate:
                return candidate
        return {}

    def _select_listing_json(self, payload: Any) -> Optional[Dict[str, Any]]:
        if isinstance(payload, list):
            for item in payload:
                candidate = self._select_listing_json(item)
                if candidate:
                    return candidate
            return None
        if isinstance(payload, dict):
            graph = payload.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    candidate = self._select_listing_json(item)
                    if candidate:
                        return candidate
            item_type = payload.get("@type")
            if isinstance(item_type, list):
                item_type = item_type[0] if item_type else None
            if isinstance(item_type, str) and item_type.lower() in {
                "singlefamilyresidence",
                "residence",
                "house",
                "apartment",
                "product",
                "realestatelisting",
                "offer",
            }:
                return payload
        return None

    def _extract_json_from_script(self, soup: BeautifulSoup, selector: str) -> Dict[str, Any]:
        node = soup.select_one(selector)
        if node is None or not node.string:
            return {}
        try:
            payload = json.loads(node.string)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _find_nested_dict(self, value: Any, *, required_keys: Iterable[str]) -> Optional[Dict[str, Any]]:
        required = set(required_keys)
        if isinstance(value, dict):
            if required.issubset(value.keys()):
                return value
            for candidate in value.values():
                match = self._find_nested_dict(candidate, required_keys=required)
                if match:
                    return match
        elif isinstance(value, list):
            for item in value:
                match = self._find_nested_dict(item, required_keys=required)
                if match:
                    return match
        return None

    def _text(self, soup: BeautifulSoup, selectors: Iterable[str]) -> Optional[str]:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                text = node.get_text(" ", strip=True)
                if text:
                    return text
        return None

    def _normalize_images(self, images: Any, *, base_url: str) -> List[str]:
        raw_items: List[str] = []
        if isinstance(images, str):
            raw_items = [images]
        elif isinstance(images, list):
            raw_items = [str(item) for item in images if item]
        elif isinstance(images, dict):
            for key in ("url", "contentUrl"):
                if images.get(key):
                    raw_items = [str(images[key])]
                    break

        normalized: List[str] = []
        seen: set[str] = set()
        for item in raw_items:
            url = urljoin(base_url, item)
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            normalized.append(url)
        return normalized

    def _listing_id(self, raw: RawListing) -> str:
        unique_string = f"{raw.source_id}:{raw.external_id}"
        return hashlib.md5(unique_string.encode("utf-8")).hexdigest()

    def _currency(self, value: Any, *, default: Currency) -> Currency:
        text = str(value or "").upper()
        if "USD" in text or "$" in text:
            return Currency.USD
        if "GBP" in text or "£" in text:
            return Currency.GBP
        if "CZK" in text or "KČ" in text:
            return Currency.CZK
        if "PLN" in text or "ZŁ" in text:
            return Currency.PLN
        return default

    def _property_type(self, value: Any, *, default: PropertyType = PropertyType.APARTMENT) -> PropertyType:
        text = str(value or "").lower()
        if "house" in text or "maison" in text or "haus" in text:
            return PropertyType.HOUSE
        if "land" in text or "terrain" in text:
            return PropertyType.LAND
        if "commercial" in text or "bureau" in text or "office" in text:
            return PropertyType.COMMERCIAL
        if "apartment" in text or "flat" in text or "wohnung" in text or "appartement" in text:
            return PropertyType.APARTMENT
        return default

    def _listing_type(self, raw: RawListing, value: Any = None) -> str:
        text = str(value or raw.url or "").lower()
        if any(token in text for token in ("rent", "to-rent", "location", "miete", "alquiler")):
            return "rent"
        return "sale"

    @abstractmethod
    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        raise NotImplementedError

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        raw_listings: List[RawListing] = input_payload.get("raw_listings", [])
        canonical_listings: List[CanonicalListing] = []
        errors: List[str] = []

        for raw in raw_listings:
            html = str((raw.raw_data or {}).get("html_snippet") or "")
            if not html:
                errors.append(f"missing_html:{raw.external_id}")
                continue
            block_reason = detect_block_reason_from_html(html)
            if block_reason:
                errors.append(f"blocked:{block_reason}:{raw.url}")
                continue
            try:
                canonical = self._parse_item(raw)
            except Exception as exc:
                errors.append(f"{self.name}_parse_error:{raw.external_id}:{exc}")
                continue
            if canonical is None:
                errors.append(f"parse_failed:{raw.external_id}")
                continue
            if canonical.analysis_meta is None:
                canonical.analysis_meta = {}
            canonical.analysis_meta.setdefault("normalized_by", self.name)
            canonical_listings.append(canonical)

        if canonical_listings and errors:
            status = "partial"
        elif canonical_listings:
            status = "success"
        elif any(error.startswith("blocked:") for error in errors):
            status = "blocked"
        else:
            status = "failure"

        return AgentResponse(status=status, data=canonical_listings, errors=errors)
