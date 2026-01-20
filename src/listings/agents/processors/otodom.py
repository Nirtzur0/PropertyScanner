
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import structlog
import re
import json

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import CanonicalListing, RawListing, GeoLocation

logger = structlog.get_logger(__name__)


class OtodomNormalizerAgent(BaseAgent):
    """
    Normalizes Otodom.pl listings using JSON-LD and data-cy selectors.
    """
    def __init__(self):
        super().__init__(name="OtodomNormalizer")

    def normalize(self, html: str, url: str) -> Dict[str, Any]:
        result = {}
        soup = BeautifulSoup(html, "html.parser")

        # Try JSON-LD first (usually excellent quality on modern sites)
        json_ld = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                # Sometimes it's a list, sometimes single object
                # Look for @type: Product or Apartment or RealEstateListing
                if isinstance(data, list):
                     for item in data:
                         if isinstance(item, dict) and item.get("@type") in ["Product", "Apartment", "RealEstateListing", "Offer"]:
                             json_ld = item
                             break
                elif isinstance(data, dict):
                     json_ld = data
                
                if json_ld:
                    break
            except:
                continue
        
        if json_ld:
            # Parse from JSON-LD
            result["title"] = json_ld.get("name")
            result["description"] = json_ld.get("description")
            
            offers = json_ld.get("offers")
            if isinstance(offers, dict):
                 price = offers.get("price")
                 currency = offers.get("priceCurrency")
                 if price:
                     try:
                         result["price_amount"] = float(price)
                         result["currency"] = currency
                     except:
                         pass
            
            # Address sometimes deeply nested
            # fallback to HTML for address if JSON is simple
        
        # Fallback / Supplement with HTML selectors

        # Title
        if not result.get("title"):
             t_el = soup.select_one("[data-cy='adPageAdTitle']")
             if t_el:
                 result["title"] = t_el.get_text(strip=True)

        # Price
        if not result.get("price_amount"):
             p_el = soup.select_one("[data-cy='adPageHeaderPrice']")
             if p_el:
                 clean = re.sub(r"[^\d]", "", p_el.get_text(strip=True))
                 if clean:
                     try:
                         result["price_amount"] = float(clean)
                         result["currency"] = "PLN" # Default
                     except:
                         pass

        # Address
        if not result.get("address"):
             a_el = soup.select_one("a[href*='#map']")
             if a_el:
                 result["address"] = a_el.get_text(strip=True)
             else:
                 # Try finding location in title or nearby
                 result["address"] = result.get("title", "")

        # Description
        if not result.get("description"):
             d_el = soup.select_one("[data-cy='adPageAdDescription']")
             if d_el:
                 result["description"] = d_el.get_text(separator="\n", strip=True)

        # Images
        # [data-cy='mosaic-gallery-main-view'] img
        # or JSON-LD "image"
        images = []
        if json_ld and json_ld.get("image"):
             img = json_ld["image"]
             if isinstance(img, list):
                 images.extend(img)
             elif isinstance(img, str):
                 images.append(img)
        
        if not images:
             for img in soup.select("[data-cy^='mosaic-gallery'] img"):
                 src = img.get("src")
                 if src:
                     images.append(src)
        
        result["images"] = list(set(images))

        # Features from Parameters section
        # We need to look for labels "Powierzchnia" and "Liczba pokoi"
        # Since structure varies, search by text label is robust
        # Text "Powierzchnia" -> find parent -> find sibling value?
        
        # Or iterate all divs inside data-cy="ad_table" if it exists?
        # Browser found `[data-testid="table-value-area"]` and `[data-testid="table-value-rooms_num"]`
        
        area_el = soup.select_one('[data-testid="table-value-area"]')
        if area_el:
             txt = area_el.get_text(strip=True)
             match = re.search(r"([\d.,]+)", txt)
             if match:
                 try:
                     result["surface_area_sqm"] = float(match.group(1).replace(",", "."))
                 except:
                     pass
        
        rooms_el = soup.select_one('[data-testid="table-value-rooms_num"]')
        if rooms_el:
             txt = rooms_el.get_text(strip=True)
             if txt.isdigit():
                 result["bedrooms"] = float(txt)

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
                    country="PL",
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
                    currency=data.get("currency", "PLN"),
                    description=data.get("description"),
                    image_urls=data.get("images", []),
                    bedrooms=data.get("bedrooms"),
                    bathrooms=data.get("bathrooms"),
                    surface_area_sqm=data.get("surface_area_sqm"),
                    property_type="apartment", 
                    crawled_at=raw.fetched_at,
                    market_date=raw.fetched_at,
                )
                canonical_listings.append(listing)

            except Exception as e:
                logger.error("otodom_normalization_failed", url=raw.url, error=str(e))
                errors.append(str(e))

        return AgentResponse(status="success", data=canonical_listings, errors=errors)
