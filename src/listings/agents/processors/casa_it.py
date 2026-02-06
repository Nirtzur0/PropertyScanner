from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import json
import re
import hashlib
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus, GeoLocation
from datetime import datetime
from src.platform.utils.time import utcnow

class CasaItNormalizerAgent(BaseAgent):
    """
    Parses HTML from Casa.it into CanonicalListings.
    """
    def __init__(self):
        super().__init__(name="CasaItNormalizer")

    def _clean_price(self, text: str) -> float:
        # "€ 245.000" -> 245000.0
        cleaned = re.sub(r'[^\d]', '', text)
        return float(cleaned) if cleaned else 0.0

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Strategy: Data Layer / JSON-LD / DOM
        json_data = {}
        
        # Try JSON-LD
        scripts = soup.find_all('script', type='application/ld+json')
        for s in scripts:
            try:
                data = json.loads(s.string)
                if isinstance(data, list):
                   for d in data:
                       if d.get("@type") in ["Place", "Residence", "Apartment", "SingleFamilyResidence", "Product"]:
                           json_data = d
                           break
                elif data.get("@type") in ["Place", "Residence", "Apartment", "SingleFamilyResidence", "Product"]:
                    json_data = data
            except:
                continue
            if json_data: break
            
        # Title
        title = "Unknown Property"
        if json_data.get("name"):
            title = json_data["name"]
        else:
            t_el = soup.select_one("h1")
            if t_el: title = t_el.get_text(strip=True)

        # Price
        price = 0.0
        # Try finding price in DOM
        # casa.it often uses .price or similar
        p_el = soup.select_one(".price") or soup.select_one("div[class*='price']")
        if p_el:
            price = self._clean_price(p_el.get_text())

        # URL
        full_url = raw.url
        
        # Features
        bedrooms = None
        sqm = None
        bathrooms = None
        floor = None
        
        # Grid/List of features
        all_text = soup.get_text(" ", strip=True)
        
        # Regex heuristics for Italian
        # "120 mq"
        m = re.search(r'(\d+)\s*mq', all_text, re.IGNORECASE)
        if m: sqm = float(m.group(1))
        
        # "3 locali" (rooms, loosely used for bedrooms sometimes, but distinct)
        # "3 camere" (bedrooms)
        m = re.search(r'(\d+)\s*camer[ae]', all_text, re.IGNORECASE)
        if m: bedrooms = int(m.group(1))
        elif not bedrooms:
             # Fallback to locali if camere not found, though imprecise
             m = re.search(r'(\d+)\s*locali', all_text, re.IGNORECASE)
             if m: bedrooms = int(m.group(1)) # Approximate
        
        # "2 bagni"
        m = re.search(r'(\d+)\s*bagn[oi]', all_text, re.IGNORECASE)
        if m: bathrooms = int(m.group(1))

        # "Piano 3"
        m = re.search(r'piano\s*(\d+)', all_text, re.IGNORECASE)
        if m: floor = int(m.group(1))

        # Images
        image_urls = []
        if json_data.get("image"):
            imgs = json_data["image"]
            if isinstance(imgs, list):
                image_urls = [i for i in imgs if isinstance(i, str)]
            elif isinstance(imgs, str):
                image_urls = [imgs]
        
        if not image_urls:
            # DOM Search
            imgs = soup.select("img.gallery-image") # Hypothetical class
            for img in imgs:
                src = img.get("src")
                if src and "http" in src: image_urls.append(src)
                
            if not image_urls:
                # Broad search
                imgs = soup.select("img[class*='photo'], img[class*='image']")
                for img in imgs:
                     src = img.get("src")
                     if src and "http" in src and "icon" not in src:
                         image_urls.append(src)

        # ID
        unique_string = f"casait_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()
        
        # Description
        description = json_data.get("description", "")
        if not description:
            desc_el = soup.select_one(".description")
            if desc_el: description = desc_el.get_text(strip=True)

        canonical = CanonicalListing(
            id=unique_hash,
            source_id="casa_it",
            external_id=raw.external_id,
            url=full_url,
            title=title,
            description=description,
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT,
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            bathrooms=bathrooms,
            floor=floor,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE,
            listed_at=utcnow()
        )
        
        # Location (Italy)
        # Try to parse city from title or URL or breadcrumbs
        city = "Unknown"
        if "milano" in full_url.lower() or "milano" in title.lower():
            city = "Milano"
        # ... rudimentary
        
        canonical.location = GeoLocation(
            lat=None, lon=None,
            address_full=title,
            city=city,
            country="IT"
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
