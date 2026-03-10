from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import json
import re
import hashlib
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus, GeoLocation
from datetime import datetime
from src.listings.source_ids import canonicalize_source_id

class ImovirtualNormalizerAgent(BaseAgent):
    """
    Parses HTML snippets from Imovirtual (Portugal) into CanonicalListings.
    """
    def __init__(self):
        super().__init__(name="ImovirtualNormalizer")

    def _clean_price(self, text: str) -> float:
        # "245 000 €" -> 245000.0
        cleaned = re.sub(r'[^\d]', '', text)
        return float(cleaned) if cleaned else 0.0

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Strategy: Try JSON-LD first
        json_data = {}
        scripts = soup.find_all('script', type='application/ld+json')
        for s in scripts:
            try:
                data = json.loads(s.string)
                
                # Handle @graph in JSON-LD
                if isinstance(data, dict) and "@graph" in data:
                    data = data["@graph"]

                if isinstance(data, list):
                    for item in data:
                         types = item.get("@type")
                         if isinstance(types, str): types = [types]
                         # print(f"DEBUG: Checking item types: {types}")
                         if any(t in ["SingleFamilyResidence", "Apartment", "House", "Residence", "Product"] for t in types):
                             json_data = item
                             # print(f"DEBUG: Found JSON-LD match: {json_data.keys()}")
                             break
                else:
                    types = data.get("@type")
                    if isinstance(types, str): types = [types]
                    # print(f"DEBUG: Checking object types: {types}")
                    if any(t in ["SingleFamilyResidence", "Apartment", "House", "Residence", "Product"] for t in types):
                        json_data = data
                        # print(f"DEBUG: Found JSON-LD match: {json_data.keys()}")
            except Exception as e:
                # print(f"DEBUG: JSON-LD parse error: {e}")
                continue
            if json_data: break
            
        # Title
        title = "Unknown Property"
        if json_data.get("name"):
            title = json_data["name"]
        else:
            t_el = soup.select_one("h1.css-15g2mhc") or soup.select_one("h1")
            if t_el: title = t_el.get_text(strip=True)

        # Price
        price = 0.0
        if json_data.get("offers", {}).get("price"):
            price = float(json_data["offers"]["price"])
        else:
            p_el = soup.select_one("strong[data-cy='ad-price']") or soup.select_one(".css-1wxc2al")
            if p_el:
                price = self._clean_price(p_el.get_text())

        # URL
        full_url = raw.url

        # Features
        bedrooms = None
        sqm = None
        bathrooms = None
        
        # Parse from feature list
        # Look for "T2", "3 quartos", "120 m²"
        
        # Try JSON-LD description for regex or specific fields if available (Imovirtual JSON-LD is sometimes sparse on details)
        
        # DOM Strategy
        # Features are often in a grid or list
        # "Área bruta: 120 m²", "Quartos: 3", "Casas de Banho: 2"
        
        feature_items = soup.select("div[data-cy='table-label-value']") # Common class in OLX-based sites like Imovirtual?
        # Or look for specific attributes
        
        # 2024 Imovirtual Design:
        # Often uses classes like css-1s3v2r3
        # Best to iterate all text nodes that look like key-value
        
        all_text = soup.get_text(" ", strip=True)
        
        # Bedrooms
        # "T2" -> 2
        m = re.search(r'\bT(\d+)\b', title) 
        if m:
            bedrooms = int(m.group(1))
        
        if not bedrooms:
            # "3 quartos"
            m = re.search(r'(\d+)\s*quarto', all_text, re.IGNORECASE)
            if m: bedrooms = int(m.group(1))

        # SQM
        # "120 m²"
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', all_text, re.IGNORECASE)
        if m:
            sqm_str = m.group(1).replace('.', '').replace(',', '.')
            sqm = float(sqm_str)

        # Bathrooms
        m = re.search(r'(\d+)\s*casa(?:s)?\s*de\s*banho', all_text, re.IGNORECASE)
        if m: bathrooms = int(m.group(1))
        
        # Images
        image_urls = []
        if json_data.get("image"):
            imgs = json_data["image"]
            if isinstance(imgs, list):
                image_urls = [i for i in imgs if isinstance(i, str)]
            elif isinstance(imgs, str):
                image_urls = [imgs]
        
        if not image_urls:
            # DOM fallback
            # Look for img tags in gallery
            imgs = soup.select("img")
            for img in imgs:
                src = img.get("src") or img.get("data-src")
                if src and "image" in src and "http" in src:
                    image_urls.append(src)

        # Location
        city = "Unknown"
        lat = None
        lon = None
        
        if json_data.get("geo"):
            try:
                lat = float(json_data["geo"].get("latitude", 0))
                lon = float(json_data["geo"].get("longitude", 0))
            except: pass
            
        # Address
        if json_data.get("address"):
             addr = json_data["address"]
             if isinstance(addr, dict):
                 city = addr.get("addressLocality", city)

        # ID
        unique_string = f"imovirtual_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        canonical = CanonicalListing(
            id=unique_hash,
            source_id=canonicalize_source_id(raw.source_id),
            external_id=raw.external_id,
            url=full_url,
            title=title,
            description=BeautifulSoup(json_data.get("description", ""), "html.parser").get_text(separator=" ", strip=True),
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT, # Default
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            bathrooms=bathrooms,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE,
            listed_at=raw.fetched_at,
            crawled_at=raw.fetched_at,
            market_date=raw.fetched_at,
        )
        
        if lat and lon:
            canonical.location = GeoLocation(
                lat=lat, lon=lon,
                address_full=title,
                city=city,
                country="PT",
                zip_code=None
            )
        else:
             canonical.location = GeoLocation(
                lat=None, lon=None,
                address_full=title,
                city=city,
                country="PT"
            )
            
        return canonical

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        raw_listings: List[RawListing] = input_payload.get("raw_listings", [])
        canonical_listings = []
        errors = []

        for raw in raw_listings:
            try:
                canonical = self._parse_item(raw)
                if canonical:
                    canonical_listings.append(canonical)
            except Exception as e:
                errors.append(f"Failed to normalize {raw.external_id}: {str(e)}")
        
        status = "success" if canonical_listings else ("failure" if errors else "success")
        return AgentResponse(status=status, data=canonical_listings, errors=errors)
