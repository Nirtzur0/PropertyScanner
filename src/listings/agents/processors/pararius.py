
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import structlog
import re

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import CanonicalListing, RawListing, GeoLocation

logger = structlog.get_logger(__name__)


class ParariusNormalizerAgent(BaseAgent):
    """
    Normalizes Pararius.nl listings.
    """
    def __init__(self):
        super().__init__(name="ParariusNormalizer")

    def normalize(self, html: str, url: str) -> Dict[str, Any]:
        result = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title / Address
        # h1.listing-detail-summary__title
        title_el = soup.select_one("h1.listing-detail-summary__title")
        if title_el:
            result["title"] = title_el.get_text(strip=True)
        
        # Location
        # div.listing-detail-summary__location
        loc_el = soup.select_one("div.listing-detail-summary__location")
        if loc_el:
            result["address"] = loc_el.get_text(strip=True)
            if not result.get("title"):
                result["title"] = result["address"]

        # Price
        # span.listing-detail-summary__price-main
        price_el = soup.select_one("span.listing-detail-summary__price-main")
        if price_el:
            raw_price = price_el.get_text(strip=True)
            result["price_str"] = raw_price
            # e.g. € 1.500 per month
            clean_price = re.sub(r"[^\d]", "", raw_price)
            if clean_price:
               try:
                   result["price_amount"] = float(clean_price)
                   result["currency"] = "EUR"
               except:
                   pass

        # Description
        # div.listing-detail-description__content
        desc_el = soup.select_one("div.listing-detail-description__content")
        if desc_el:
            result["description"] = desc_el.get_text(separator="\n", strip=True)

        # Images
        # wc-carrousel img
        images = []
        # Since wc-carrousel might be a web component, the images might be in shadow DOM or plain inside
        # Our BS4 parser sees light DOM. Usually they fall back to normal img tags or sources inside.
        # Research found: wc-carrousel img
        for img in soup.select("wc-carrousel img"):
            src = img.get("src") or img.get("data-src")
            if src and src.startswith("http") and src not in images:
                images.append(src)
        
        # Fallback to checking picture sources if wc-carrousel is empty
        if not images:
             for pic in soup.select("picture source"):
                 srcset = pic.get("srcset")
                 if srcset:
                     parts = srcset.split(",")
                     if parts:
                         src = parts[-1].strip().split(" ")[0]
                         if src.startswith("http"):
                             images.append(src)

        result["images"] = images

        # Features
        # Bedrooms: dd.listing-features__description--number_of_bedrooms
        beds_el = soup.select_one("dd.listing-features__description--number_of_bedrooms")
        if beds_el:
            txt = beds_el.get_text(strip=True)
            if txt.isdigit():
                 result["bedrooms"] = float(txt)
        
        # Area: dd.listing-features__description--surface_area
        area_el = soup.select_one("dd.listing-features__description--surface_area")
        if area_el:
            txt = area_el.get_text(strip=True) # "65 m²"
            match = re.search(r"(\d+)", txt)
            if match:
                result["surface_area_sqm"] = float(match.group(1))

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
                
                # Construct CanonicalListing
                listing_id = raw.external_id or "unknown"
                
                
                # Construct GeoLocation
                location = GeoLocation(
                    address_full=data.get("address", ""),
                    city=data.get("city", "Unknown"),
                    country="NL",
                    zip_code=data.get("zip_code"),
                )

                listing = CanonicalListing(
                    id=listing_id,
                    external_id=raw.external_id,
                    source_id=raw.source_id,
                    url=url,
                    title=data.get("title", "Unknown Property"),
                    location=location,
                    price=data.get("price_amount", 0.0),
                    currency=data.get("currency", "EUR"),
                    description=data.get("description"),
                    image_urls=data.get("images", []),
                    bedrooms=data.get("bedrooms"),
                    bathrooms=data.get("bathrooms"), # Added bathrooms if available in normalize
                    surface_area_sqm=data.get("surface_area_sqm"),
                    property_type="apartment", 
                    crawled_at=raw.fetched_at,
                    market_date=raw.fetched_at,
                )
                canonical_listings.append(listing)

            except Exception as e:
                logger.error("pararius_normalization_failed", url=raw.url, error=str(e))
                errors.append(str(e))

        return AgentResponse(status="success", data=canonical_listings, errors=errors)
