from __future__ import annotations

from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from src.listings.agents.processors.detail_parser import DetailPageNormalizerAgent
from src.platform.domain.schema import CanonicalListing, Currency, GeoLocation, ListingStatus, PropertyType, RawListing


class RealtorNormalizerAgent(DetailPageNormalizerAgent):
    def __init__(self) -> None:
        super().__init__(name="RealtorNormalizer")

    def _extract_hydration(self, soup: BeautifulSoup) -> Dict[str, Any]:
        next_data = self._extract_json_from_script(soup, "#__NEXT_DATA__")
        if next_data:
            listing = self._find_nested_dict(
                next_data,
                required_keys=("list_price", "location"),
            )
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

        price = self._parse_float(offers.get("price")) or self._parse_float(hydration.get("list_price")) or 0.0
        if price <= 0:
            return None

        address = json_ld.get("address") or {}
        location_data = hydration.get("location") or {}
        coordinates = hydration.get("coordinates") or {}
        city = (
            address.get("addressLocality")
            or location_data.get("city")
            or self._text(soup, ["[data-testid='city']", ".ldp-address"])
            or "Unknown"
        )
        country = address.get("addressCountry") or "US"
        full_address = (
            self._text(soup, ["[data-testid='address']", ".ldp-address"])
            or json_ld.get("name")
            or raw.url
        )

        lat = self._parse_float((json_ld.get("geo") or {}).get("latitude")) or self._parse_float(
            coordinates.get("lat")
        )
        lon = self._parse_float((json_ld.get("geo") or {}).get("longitude")) or self._parse_float(
            coordinates.get("lon")
        )

        title = json_ld.get("name") or hydration.get("description", {}).get("name") or full_address
        description = (
            json_ld.get("description")
            or hydration.get("description", {}).get("text")
            or self._text(soup, ["[data-testid='description']", "#ldp-detail-description"])
        )

        bedrooms = self._parse_int(json_ld.get("numberOfRooms")) or self._parse_int(hydration.get("beds"))
        bathrooms = self._parse_int(json_ld.get("numberOfBathroomsTotal")) or self._parse_int(
            hydration.get("baths")
        )

        floor_size = json_ld.get("floorSize") or {}
        area = self._parse_float(floor_size.get("value")) or self._parse_float(hydration.get("sqft"))
        if area and area > 1000:
            area = area * 0.092903

        images = self._normalize_images(
            json_ld.get("image") or hydration.get("photos") or [],
            base_url=raw.url,
        )
        if not images:
            images = self._normalize_images(
                [node.get("src") or node.get("data-src") for node in soup.select("img") if node.get("src") or node.get("data-src")],
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
            property_type=self._property_type(json_ld.get("@type") or hydration.get("prop_type"), default=PropertyType.HOUSE),
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            surface_area_sqm=area,
            image_urls=images,
            location=GeoLocation(
                lat=lat,
                lon=lon,
                address_full=full_address,
                city=city,
                country=country,
            ),
            status=ListingStatus.ACTIVE,
            analysis_meta={
                "structured_data": bool(json_ld),
                "hydration_data": bool(hydration),
            },
        )
