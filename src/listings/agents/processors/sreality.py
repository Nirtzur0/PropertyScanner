
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import structlog
import re

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import CanonicalListing, RawListing, GeoLocation

logger = structlog.get_logger(__name__)


class SrealityNormalizerAgent(BaseAgent):
    """
    Normalizes Sreality.cz listings.
    """
    def __init__(self):
        super().__init__(name="SrealityNormalizer")

    def normalize(self, html: str, url: str) -> Dict[str, Any]:
        result = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title
        title_el = soup.select_one("[data-e2e='detail-heading']")
        if not title_el:
            title_el = soup.find("h1")
            
        if title_el:
             result["title"] = title_el.get_text(strip=True)

        # Price
        # Look for text containing CZK or Kč
        price_text = None
        for el in soup.find_all(["p", "span", "div", "strong"]):
            txt = el.get_text(strip=True)
            if ("CZK" in txt or "Kč" in txt) and len(txt) < 30:
                 price_text = txt
                 break
        
        if price_text:
             clean = re.sub(r"[^\d]", "", price_text)
             if clean:
                 try:
                     result["price_amount"] = float(clean)
                     result["currency"] = "CZK"
                 except:
                     pass

        # Location/Address
        # Heuristic: title often contains address in Sreality
        # "Prodej bytu 2+1 53 m² Donatellova, Praha - Strašnice"
        # We can try to split by newline if present
        if result.get("title"):
             parts = result["title"].split("\n")
             if len(parts) > 1:
                 result["address"] = parts[-1].strip()
             else:
                 # Try to find address in title by looking for comma?
                 # Fallback to title
                 result["address"] = result["title"]
        else:
             result["address"] = ""

        # Description
        desc_el = soup.select_one("[data-e2e='detail-description']")
        if desc_el:
            result["description"] = desc_el.get_text(separator="\n", strip=True)
        else:
            # Fallback
            longest_p = None
            max_len = 0
            for p in soup.find_all("p"):
                 txt = p.get_text(strip=True)
                 if len(txt) > max_len:
                     max_len = len(txt)
                     longest_p = txt
            if longest_p and max_len > 100:
                result["description"] = longest_p

        # Features (DL parsing)
        dl = soup.select_one("dl")
        if dl:
             # Heuristic: iterate children or find_all
             keys = [dt.get_text(strip=True).rstrip(":") for dt in dl.find_all("dt")]
             vals = [dd.get_text(strip=True) for dd in dl.find_all("dd")]
             features = dict(zip(keys, vals))
             
             if "Plocha" in features:
                 # "Užitná plocha 53 m²"
                 match = re.search(r"(\d+)", features["Plocha"])
                 if match:
                     try:
                         result["surface_area_sqm"] = float(match.group(1))
                     except: pass

        # Images
        images = []
        for img in soup.find_all("img"):
             src = img.get("src")
             # Allow sreality.cz, sdn.cz (image server), or generic for now if synthesized
             if src and ("sreality.cz" in src or "sdn.cz" in src or "img" in src):
                  if src.startswith("http"):
                      images.append(src)
        
        result["images"] = list(set(images))

        # Features
        # Try to parse title for bedrooms: "3+1", "2+kk"
        if result.get("title"):
             t = result["title"]
             # Match N+something
             match = re.search(r"(\d+)\+(kk|1|\d)", t)
             if match:
                 try:
                     result["bedrooms"] = float(match.group(1))
                 except:
                     pass
        
        # Usable area
        # Often in text like "65 m2" or "65 m²"
        # Search whole text for this pattern near "Usable area"
        text_content = soup.get_text(" ", strip=True)
        area_match = re.search(r"(\d+)\s*m[²2]", text_content)
        if area_match:
             try:
                 result["surface_area_sqm"] = float(area_match.group(1))
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
                    address_full=data.get("address", ""),
                    city=data.get("city", "Unknown"),
                    country="CZ",
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
                    currency=data.get("currency", "CZK"),
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
                logger.error("sreality_normalization_failed", url=raw.url, error=str(e))
                errors.append(str(e))

        return AgentResponse(status="success", data=canonical_listings, errors=errors)
