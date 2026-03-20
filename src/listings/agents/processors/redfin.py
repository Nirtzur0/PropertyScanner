from __future__ import annotations

from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from src.listings.agents.processors.detail_parser import DetailPageNormalizerAgent
from src.platform.domain.schema import CanonicalListing, Currency, GeoLocation, ListingStatus, PropertyType, RawListing


class RedfinNormalizerAgent(DetailPageNormalizerAgent):
    def __init__(self) -> None:
        super().__init__(name="RedfinNormalizer")

    def _extract_hydration(self, soup: BeautifulSoup) -> Dict[str, Any]:
        next_data = self._extract_json_from_script(soup, "#__NEXT_DATA__")
        if next_data:
            listing = self._find_nested_dict(next_data, required_keys=("price", "addressInfo"))
            if listing:
                return listing
        return {}

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = str(raw.raw_data.get("html_snippet") or "")
        soup = BeautifulSoup(html, "html.parser")
        json_ld = self._extract_json_ld(soup)
        hydration = self._extract_hydration(soup)

        offers = json_ld.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        price = self._parse_float(offers.get("price")) or self._parse_float(hydration.get("price")) or 0.0
        if price <= 0:
            return None

        address_info = hydration.get("addressInfo") or {}
        address = json_ld.get("address") or {}
        street = address.get("streetAddress") or address_info.get("streetLine") or ""
        city = address.get("addressLocality") or address_info.get("city") or "Unknown"
        region = address.get("addressRegion") or address_info.get("state") or ""
        postal_code = address.get("postalCode") or address_info.get("zip") or None
        country = address.get("addressCountry") or "US"
        address_parts = [street, city, region, postal_code]
        full_address = ", ".join(str(part).strip() for part in address_parts if part)

        geo = json_ld.get("geo") or {}
        lat = self._parse_float(geo.get("latitude")) or self._parse_float(hydration.get("latLong", {}).get("latitude"))
        lon = self._parse_float(geo.get("longitude")) or self._parse_float(hydration.get("latLong", {}).get("longitude"))

        description = json_ld.get("description") or self._text(soup, ["[data-rf-test-id='abp-description']", "#marketing-remarks-scroll"])
        title = json_ld.get("name") or self._text(soup, ["h1", "[data-rf-test-id='abp-address']"]) or full_address or raw.url

        bedrooms = self._parse_int(json_ld.get("numberOfRooms")) or self._parse_int(hydration.get("beds"))
        bathrooms = self._parse_int(json_ld.get("numberOfBathroomsTotal")) or self._parse_int(hydration.get("baths"))
        floor_size = json_ld.get("floorSize") or {}
        area = self._parse_float(floor_size.get("value")) or self._parse_float(hydration.get("sqFt", {}).get("value"))
        if area and area > 1000:
            area = area * 0.092903

        images = self._normalize_images(
            json_ld.get("image") or hydration.get("photos") or [],
            base_url=raw.url,
        )
        if not images:
            images = self._normalize_images(
                [node.get("src") or node.get("data-rf-src") for node in soup.select("img") if node.get("src") or node.get("data-rf-src")],
                base_url=raw.url,
            )

        return CanonicalListing(
            id=self._listing_id(raw),
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=title,
            description=description,
            price=price,
            currency=self._currency(offers.get("priceCurrency") or "USD", default=Currency.USD),
            listing_type=self._listing_type(raw, hydration.get("listing_type")),
            property_type=self._property_type(json_ld.get("@type") or hydration.get("propertyType"), default=PropertyType.HOUSE),
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            surface_area_sqm=area,
            image_urls=images,
            location=GeoLocation(
                lat=lat,
                lon=lon,
                address_full=full_address or title,
                city=city,
                zip_code=postal_code,
                country=country,
            ),
            status=ListingStatus.ACTIVE,
            analysis_meta={
                "structured_data": bool(json_ld),
                "hydration_data": bool(hydration),
            },
        )
