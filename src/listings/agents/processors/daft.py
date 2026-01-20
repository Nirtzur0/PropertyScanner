
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import structlog
import re

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import CanonicalListing, RawListing, GeoLocation

logger = structlog.get_logger(__name__)


class DaftNormalizerAgent(BaseAgent):
    """
    Normalizes Daft.ie listings using data-testid selectors.
    """
    def __init__(self):
        super().__init__(name="DaftNormalizer")

    def normalize(self, html: str, url: str) -> Dict[str, Any]:
        result = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title / Address
        # h1[data-testid='address']
        title_el = soup.find("h1", {"data-testid": "address"})
        if title_el:
            result["title"] = title_el.get_text(strip=True)
            result["title"] = title_el.get_text(strip=True)
            result["address_full"] = result["title"]
        else:
            # Fallback
            h1 = soup.find("h1")
            if h1:
                result["title"] = h1.get_text(strip=True)

        # Price
        # [data-testid='price']
        price_el = soup.select_one("[data-testid='price']")
        if price_el:
            raw_price = price_el.get_text(strip=True)
            result["price_str"] = raw_price
            # Parse price: €450,000
            clean_price = re.sub(r"[^\d.]", "", raw_price)
            if clean_price:
               try:
                   result["price_amount"] = float(clean_price)
                   result["currency"] = "EUR"
               except:
                   pass

        # Description
        # [data-testid='description']
        desc_el = soup.select_one("[data-testid='description']")
        if desc_el:
            result["description"] = desc_el.get_text(separator="\n", strip=True)

        # Images
        # img[data-testid='main-header-image']
        # img[data-testid*='-header-image']
        images = []
        # Try finding all images that look like gallery images
        for img in soup.select("img[data-testid*='-header-image']"):
            src = img.get("src")
            if src:
                images.append(src)
        
        # Also check standard gallery container
        for img in soup.select("[data-testid='gallery'] img"):
            src = img.get("src")
            if src and src not in images:
                images.append(src)
        
        result["images"] = images

        # Features
        # beds: [data-testid='beds']
        # baths: [data-testid='baths']
        # area: [data-testid='floor-area']
        beds_el = soup.select_one("[data-testid='beds']")
        if beds_el:
            txt = beds_el.get_text(strip=True)
            # "3 Beds"
            match = re.search(r"(\d+)", txt)
            if match:
                result["bedrooms"] = float(match.group(1))

        baths_el = soup.select_one("[data-testid='baths']")
        if baths_el:
            txt = baths_el.get_text(strip=True)
            match = re.search(r"(\d+)", txt)
            if match:
                result["bathrooms"] = float(match.group(1))
        
        area_el = soup.select_one("[data-testid='floor-area']")
        if area_el:
            txt = area_el.get_text(strip=True)
            # "88 m²"
            match = re.search(r"([\d.,]+)", txt)
            if match:
                 try:
                    result["surface_area_sqm"] = float(match.group(1).replace(",", ""))
                 except:
                    pass
        
        # New fallback: check card-info if individual fields missing
        if "bedrooms" not in result or "bathrooms" not in result or "surface_area_sqm" not in result:
             card_info = soup.select_one("[data-testid='card-info']")
             if card_info:
                 spans = card_info.find_all("span")
                 for span in spans:
                     txt = span.get_text(strip=True).lower()
                     if "bed" in txt:
                         match = re.search(r"(\d+)", txt)
                         if match:
                             result["bedrooms"] = float(match.group(1))
                     elif "bath" in txt:
                         match = re.search(r"(\d+)", txt)
                         if match:
                             result["bathrooms"] = float(match.group(1))
                     elif "m²" in txt or "sq. m" in txt:
                         match = re.search(r"([\d.,]+)", txt)
                         if match:
                             try:
                                 result["surface_area_sqm"] = float(match.group(1).replace(",", ""))
                             except:
                                 pass

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
                    address_full=data.get("address_full", ""),
                    city=data.get("city", "Unknown"),
                    country="IE",
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
                    bathrooms=data.get("bathrooms"),
                    surface_area_sqm=data.get("surface_area_sqm"),
                    property_type="apartment", # Default/Guess
                    crawled_at=raw.fetched_at,
                    market_date=raw.fetched_at,
                )
                canonical_listings.append(listing)

            except Exception as e:
                logger.error("daft_normalization_failed", url=raw.url, error=str(e))
                errors.append(str(e))

        return AgentResponse(status="success", data=canonical_listings, errors=errors)
