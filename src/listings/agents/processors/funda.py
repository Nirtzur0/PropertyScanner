from typing import Any, Dict, List, Optional
import json
import re
from bs4 import BeautifulSoup
import structlog
from urllib.parse import urljoin

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import CanonicalListing, RawListing, GeoLocation

logger = structlog.get_logger(__name__)

class FundaNormalizerAgent(BaseAgent):
    """
    Dedicated normalizer for Funda (NL).
    """
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="FundaNormalizer", config=config)

    def normalize(self, html: str, url: str) -> Dict[str, Any]:
        result = {}
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. Try extracting from JSON-LD
        json_ld_data = {}
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                # Sometimes it's a list, sometimes dict
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") in ["Appartement", "House", "Product", "PostalAddress", "Offer"]:
                             json_ld_data.update(item)
                elif isinstance(data, dict):
                     json_ld_data.update(data)
            except:
                continue
                
        # Basic fields from JSON-LD
        if json_ld_data:
            result["title"] = json_ld_data.get("name")
            result["description"] = json_ld_data.get("description")
            
            # Price
            if "offers" in json_ld_data:
                offers = json_ld_data["offers"]
                if isinstance(offers, dict):
                    result["price_amount"] = float(offers.get("price", 0))
                    result["currency"] = offers.get("priceCurrency", "EUR")
            
            # Address
            addr = json_ld_data.get("address", {})
            if isinstance(addr, dict):
                result["street"] = addr.get("streetAddress", "")
                result["city"] = addr.get("addressLocality", "")
                result["province"] = addr.get("addressRegion", "")
                result["zip_code"] = addr.get("postalCode", "")
            
            # Images
            photos = json_ld_data.get("photo", [])
            images = []
            if isinstance(photos, list):
                for p in photos:
                    if isinstance(p, dict) and p.get("contentUrl"):
                        images.append(p.get("contentUrl"))
            elif json_ld_data.get("image"):
                 images.append(json_ld_data["image"])
            
            result["image_urls"] = images

        # 2. Parse HTML Description List (dl/dt/dd) for specs
        # This is more reliable for bedrooms, area, etc.
        specs = {}
        for dt in soup.find_all("dt"):
            key = dt.get_text(strip=True).lower()
            dd = dt.find_next_sibling("dd")
            if dd:
                val = dd.get_text(strip=True)
                specs[key] = val
        
        # Map specs to result
        # Bedrooms / Rooms
        # e.g. "Aantal kamers" -> "4 kamers (2 slaapkamers)"
        # e.g. "Aantal slaapkamers" -> "2" (sometimes explicit)
        if "aantal kamers" in specs:
            val = specs["aantal kamers"]
            # Try to extract bedrooms count inside parens if available: "4 kamers (2 slaapkamers)"
            slaap_match = re.search(r"\((\d+)\s*slaapkamer", val, re.IGNORECASE)
            if slaap_match:
                result["bedrooms"] = int(slaap_match.group(1))
            else:
                # fall back to just parsing number of rooms
                match = re.search(r"(\d+)", val)
                if match:
                    # Note: this is total rooms, but better than nothing
                    # We store it, but maybe not as bedrooms if ambiguous?
                    # Let's verify if there is an explicit 'aantal slaapkamers'
                    pass
        
        if "aantal slaapkamers" in specs:
             # Explicit override
             try:
                 result["bedrooms"] = float(specs["aantal slaapkamers"])
             except:
                 pass

        # Living Area
        # "wonen" or "gebruiksoppervlakte wonen" -> "65 m²"
        living_area_val = None
        if "wonen" in specs:
            living_area_val = specs["wonen"]
        elif "gebruiksoppervlakte wonen" in specs:
             living_area_val = specs["gebruiksoppervlakte wonen"]
             
        if living_area_val:
            match = re.search(r"(\d+(?:\.\d+)*)\s*m²", living_area_val)
            if match:
                 # remove dots in european numbers 1.000 -> 1000
                 num = match.group(1).replace(".", "")
                 result["surface_area_sqm"] = float(num)

        # Bathrooms
        # "Aantal badkamers" -> "1 badkamer" or "1 badkamer en 1 apart toilet"
        if "aantal badkamers" in specs:
            val = specs["aantal badkamers"]
            match = re.search(r"(\d+)", val)
            if match:
                result["bathrooms"] = int(match.group(1))

        # Build Year
        if "bouwjaar" in specs:
            result["build_year"] = specs["bouwjaar"] # store metadata?
            
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
                street = data.get("street", "")
                city = data.get("city", "")
                province = data.get("province", "")
                
                full_address = f"{street}, {city}, {province}".strip(", ")
                
                location = GeoLocation(
                    address_full=full_address,
                    city=city,
                    country="NL",
                    zip_code=data.get("zip_code")
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
                    currency=data.get("currency", "EUR"),
                    description=data.get("description"),
                    image_urls=data.get("image_urls", []),
                    bedrooms=data.get("bedrooms"),
                    surface_area_sqm=data.get("surface_area_sqm"),
                    bathrooms=data.get("bathrooms"),
                    property_type="apartment", # Default or parse
                    crawled_at=raw.fetched_at,
                    market_date=raw.fetched_at,
                )
                canonical_listings.append(listing)

            except Exception as e:
                logger.error("funda_normalization_failed", url=raw.url, error=str(e))
                errors.append(str(e))

        return AgentResponse(status="success", data=canonical_listings, errors=errors)
