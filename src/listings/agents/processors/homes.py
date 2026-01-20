
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import structlog
import re

from urllib.parse import urljoin

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import CanonicalListing, RawListing, GeoLocation

logger = structlog.get_logger(__name__)


class HomesNormalizerAgent(BaseAgent):
    """
    Normalizes Homes.com (US) listings.
    """
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="HomesNormalizer", config=config)

    def normalize(self, html: str, url: str) -> Dict[str, Any]:
        result = {}
        soup = BeautifulSoup(html, "html.parser")

        # Address
        # .property-info-address-main (Street)
        # .property-info-address-citystatezip (City, State, Zip)
        addr_main = soup.select_one(".property-info-address-main")
        addr_csz = soup.select_one(".property-info-address-citystatezip")
        
        street = ""
        city = ""
        state = ""
        zip_code = ""
        
        if addr_main:
            street = addr_main.get_text(strip=True)
            
        if addr_csz:
            csz_text = addr_csz.get_text(strip=True)
            # e.g. "San Francisco, CA 94107"
            # distinct parts usually separated by comma
            parts = csz_text.split(",")
            if len(parts) >= 1:
                city = parts[0].strip()
            if len(parts) >= 2:
                state_zip = parts[1].strip().split(" ")
                if len(state_zip) >= 1:
                    state = state_zip[0].strip()
                if len(state_zip) >= 2:
                    zip_code = state_zip[1].strip()
        
        full_address = f"{street}, {city}, {state} {zip_code}".strip(", ")
        
        result["address_full"] = full_address
        result["city"] = city
        result["zip_code"] = zip_code
        result["country"] = "US"
        result["title"] = full_address or "Unknown Property"

        # Price
        # #price
        price_el = soup.select_one("#price")
        if price_el:
            raw_price = price_el.get_text(strip=True)
            result["price_str"] = raw_price
            clean_price = re.sub(r"[^\d.]", "", raw_price)
            if clean_price:
                try:
                    result["price_amount"] = float(clean_price)
                    result["currency"] = "USD"
                except:
                    pass

        # Specs
        # Beds: .property-info-feature.beds .property-info-feature-detail
        beds_el = soup.select_one(".property-info-feature.beds .property-info-feature-detail")
        if beds_el:
            txt = beds_el.get_text(strip=True)
            if txt.isdigit():
                result["bedrooms"] = float(txt)

        # Baths: .property-info-feature .feature-baths -> parent -> .property-info-feature-detail
        # Easier: Find element containing "Baths"
        for feature in soup.select(".property-info-feature"):
            caption = feature.select_one(".property-info-feature-caption")
            if caption and "Bath" in caption.get_text():
                detail = feature.select_one(".property-info-feature-detail")
                if detail:
                    txt = detail.get_text(strip=True)
                    try:
                        result["bathrooms"] = float(txt)
                    except:
                        pass
        
        # Sqft: .property-info-feature.sqft .property-info-feature-detail
        sqft_el = soup.select_one(".property-info-feature.sqft .property-info-feature-detail")
        if sqft_el:
            txt = sqft_el.get_text(strip=True).replace(",", "")
            if txt.isdigit():
                result["surface_area_sqm"] = float(txt) * 0.092903 # sqft to sqm
                result["surface_area_sqft"] = float(txt)

        # Description
        # #ldp-description-text
        desc_el = soup.select_one("#ldp-description-text")
        if desc_el:
            result["description"] = desc_el.get_text(separator="\n", strip=True)

        # Images
        # #gallery-primary-carousel img
        images = []
        for img in soup.select("#gallery-primary-carousel img"):
            src = img.get("src") or img.get("data-src")
            if src:
                full_src = urljoin(url, src)
                if full_src not in images:
                    images.append(full_src)
        result["images"] = images

        return result

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        raw_listings: List[RawListing] = input_payload.get("raw_listings", [])
        canonical_listings = []
        errors = []

        for raw in raw_listings:
            try:
                if not raw.raw_data or not raw.raw_data.get("html_snippet"):
                    continue
                
                html = raw.raw_data["html_snippet"]
                url = raw.url
                
                data = self.normalize(html, url)
                
                # Construct GeoLocation
                location = GeoLocation(
                    address_full=data.get("address_full", ""),
                    city=data.get("city", "Unknown"),
                    country=data.get("country", "US"),
                    zip_code=data.get("zip_code"),
                )

                # Construct CanonicalListing
                listing_id = raw.external_id or "unknown"
                
                listing = CanonicalListing(
                    id=listing_id,
                    external_id=raw.external_id,
                    source_id=raw.source_id,
                    url=url,
                    title=data.get("title", "Unknown Property"),
                    location=location,
                    price=data.get("price_amount", 0.0),
                    currency=data.get("currency", "USD"),
                    description=data.get("description"),
                    image_urls=data.get("images", []),
                    bedrooms=data.get("bedrooms"),
                    bathrooms=data.get("bathrooms"),
                    surface_area_sqm=data.get("surface_area_sqm"),
                    property_type="house", # Default
                    crawled_at=raw.fetched_at,
                    market_date=raw.fetched_at,
                )
                canonical_listings.append(listing)

            except Exception as e:
                logger.error("homes_normalization_failed", url=raw.url, error=str(e))
                errors.append(str(e))

        return AgentResponse(status="success", data=canonical_listings, errors=errors)
