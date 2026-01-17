import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import (
    CanonicalListing,
    Currency,
    GeoLocation,
    ListingStatus,
    PropertyType,
    RawListing,
)


class ZooplaNormalizerAgent(BaseAgent):
    """
    Parses HTML snippets from Zoopla into CanonicalListings.
    Prefers JSON-LD when present.
    """

    def __init__(self) -> None:
        super().__init__(name="ZooplaNormalizer")

    def _parse_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^\d.]", "", str(value))
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _parse_date(self, value: Any) -> Optional[datetime]:
        if not value:
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
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
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
            if "@graph" in payload and isinstance(payload["@graph"], list):
                for item in payload["@graph"]:
                    candidate = self._select_listing_json(item)
                    if candidate:
                        return candidate
                return None
            item_type = payload.get("@type")
            if isinstance(item_type, list):
                item_type = item_type[0]
            if isinstance(item_type, str):
                item_type = item_type.lower()
            if item_type in {
                "singlefamilyresidence",
                "residence",
                "house",
                "apartment",
                "product",
                "realestatelisting",
            }:
                return payload
        return None

    def _map_property_type(self, value: Optional[str], title: str) -> PropertyType:
        raw_value = value
        if isinstance(raw_value, list):
            raw_value = raw_value[0] if raw_value else ""
        raw = str(raw_value or "").lower()
        title_lower = title.lower()
        if "house" in raw or "house" in title_lower:
            return PropertyType.HOUSE
        if "apartment" in raw or "flat" in title_lower:
            return PropertyType.APARTMENT
        if "land" in raw or "land" in title_lower:
            return PropertyType.LAND
        if "commercial" in raw or "commercial" in title_lower:
            return PropertyType.COMMERCIAL
        return PropertyType.APARTMENT

    def _infer_listing_type(self, url: str) -> str:
        url_lower = url.lower()
        if "to-rent" in url_lower or "/rent" in url_lower or "/rental" in url_lower:
            return "rent"
        return "sale"

    def _area_to_sqm(self, value: Any, unit_code: Optional[str]) -> Optional[float]:
        raw_val = self._parse_float(value)
        if raw_val is None:
            return None
        code = (unit_code or "").upper()
        if code in {"FTK", "FT2", "SQF", "SQFT"}:
            return float(raw_val * 0.092903)
        return float(raw_val)

    def _map_currency(self, code: Any) -> Currency:
        text = str(code or "").upper()
        if text == "USD":
            return Currency.USD
        if text == "EUR":
            return Currency.EUR
        return Currency.GBP

    def _compose_address(self, address: Dict[str, Any], fallback: str) -> str:
        parts = [
            address.get("streetAddress"),
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("postalCode"),
        ]
        cleaned = [str(p).strip() for p in parts if p]
        return ", ".join(cleaned) if cleaned else fallback

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        data = self._extract_json_ld(soup)

        title = data.get("name") or ""
        if not title:
            title_el = soup.find("h1") or soup.select_one("meta[property='og:title']")
            title = title_el.get_text(strip=True) if title_el else "Unknown Property"
        description = data.get("description") or ""
        if not description:
            meta_desc = soup.select_one("meta[name='description']")
            if meta_desc:
                description = meta_desc.get("content", "") or ""

        offers = data.get("offers") or {}
        if isinstance(offers, list) and offers:
            offers = offers[0]
        price = self._parse_float(offers.get("price")) or 0.0
        currency = offers.get("priceCurrency") or "GBP"

        bedrooms = self._parse_float(data.get("numberOfRooms"))
        if bedrooms is not None:
            bedrooms = int(bedrooms)
        bathrooms = self._parse_float(data.get("numberOfBathroomsTotal"))
        if bathrooms is not None:
            bathrooms = int(bathrooms)

        floor_size = data.get("floorSize") or {}
        sqm = self._area_to_sqm(floor_size.get("value"), floor_size.get("unitCode"))

        if bedrooms is None:
            match = re.search(r"(\d+)\s*bed", title.lower())
            if match:
                bedrooms = int(match.group(1))
        if bathrooms is None:
            match = re.search(r"(\d+)\s*bath", description.lower())
            if match:
                bathrooms = int(match.group(1))

        image_urls = []
        images = data.get("image")
        if isinstance(images, list):
            image_urls = [str(i) for i in images if i]
        elif isinstance(images, str):
            image_urls = [images]
        if not image_urls:
            og_img = soup.select_one("meta[property='og:image']")
            if og_img and og_img.get("content"):
                image_urls = [og_img.get("content")]

        address = data.get("address") or {}
        if isinstance(address, str):
            address = {"streetAddress": address}
        city = address.get("addressLocality") or address.get("addressRegion") or "Unknown"
        country = address.get("addressCountry") or "GB"
        address_full = self._compose_address(address, title)

        lat = None
        lon = None
        geo = data.get("geo") or {}
        if geo:
            lat = self._parse_float(geo.get("latitude"))
            lon = self._parse_float(geo.get("longitude"))

        location = None
        if address_full or city or (lat is not None and lon is not None):
            location = GeoLocation(
                lat=lat,
                lon=lon,
                address_full=address_full or title,
                city=city or "Unknown",
                country=country,
                zip_code=address.get("postalCode"),
            )

        unique_hash = hashlib.md5(f"{raw.source_id}:{raw.external_id}".encode()).hexdigest()

        listing = CanonicalListing(
            id=unique_hash,
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=title or "Unknown Property",
            description=description or None,
            price=price,
            currency=self._map_currency(currency),
            listing_type=self._infer_listing_type(str(raw.url)),
            property_type=self._map_property_type(data.get("@type"), title),
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            surface_area_sqm=sqm,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE,
            location=location,
        )

        posted = data.get("datePosted") or data.get("datePublished")
        listing.listed_at = self._parse_date(posted)
        return listing

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        raw_listings = input_payload.get("raw_listings", [])
        canonical_listings = []
        errors = []

        for raw in raw_listings:
            try:
                canonical = self._parse_item(raw)
                if canonical:
                    canonical_listings.append(canonical)
            except Exception as exc:
                errors.append(f"zoopla_norm_error:{getattr(raw, 'external_id', 'unknown')}:{exc}")

        status = "success" if canonical_listings else "failure"
        return AgentResponse(status=status, data=canonical_listings, errors=errors)
