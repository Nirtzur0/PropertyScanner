from __future__ import annotations

from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from src.listings.agents.processors.detail_parser import DetailPageNormalizerAgent
from src.platform.domain.schema import CanonicalListing, Currency, GeoLocation, ListingStatus, PropertyType, RawListing


class SeLogerNormalizerAgent(DetailPageNormalizerAgent):
    def __init__(self) -> None:
        super().__init__(name="SeLogerNormalizer")

    def _extract_hydration(self, soup: BeautifulSoup) -> Dict[str, Any]:
        next_data = self._extract_json_from_script(soup, "#__NEXT_DATA__")
        if next_data:
            listing = self._find_nested_dict(next_data, required_keys=("pricing", "location"))
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

        pricing = hydration.get("pricing") or {}
        location_data = hydration.get("location") or {}

        price = self._parse_float(offers.get("price")) or self._parse_float(pricing.get("price")) or 0.0
        if price <= 0:
            return None

        address = json_ld.get("address") or {}
        city = address.get("addressLocality") or location_data.get("city") or "Unknown"
        country = address.get("addressCountry") or "FR"
        full_address = (
            self._text(soup, ["[data-testid='sl-title-bar-address']", "h1"])
            or json_ld.get("name")
            or raw.url
        )
        geo = json_ld.get("geo") or {}
        lat = self._parse_float(geo.get("latitude")) or self._parse_float(location_data.get("latitude"))
        lon = self._parse_float(geo.get("longitude")) or self._parse_float(location_data.get("longitude"))

        title = json_ld.get("name") or hydration.get("title") or full_address
        description = (
            json_ld.get("description")
            or hydration.get("description")
            or self._text(soup, ["[data-testid='sl-description']", ".Description"])
        )

        bedrooms = self._parse_int(json_ld.get("numberOfRooms")) or self._parse_int(hydration.get("bedrooms"))
        bathrooms = self._parse_int(json_ld.get("numberOfBathroomsTotal")) or self._parse_int(
            hydration.get("bathrooms")
        )
        floor_size = json_ld.get("floorSize") or {}
        area = self._parse_float(floor_size.get("value")) or self._parse_float(hydration.get("livingArea"))

        images = self._normalize_images(json_ld.get("image") or hydration.get("photos") or [], base_url=raw.url)
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
            currency=self._currency(offers.get("priceCurrency") or "EUR", default=Currency.EUR),
            listing_type=self._listing_type(raw, hydration.get("listingType")),
            property_type=self._property_type(json_ld.get("@type") or hydration.get("propertyType"), default=PropertyType.APARTMENT),
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
