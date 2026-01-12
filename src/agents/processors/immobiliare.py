from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import json
import re
import hashlib
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus, GeoLocation

class ImmobiliareNormalizerAgent(BaseAgent):
    """
    Parses HTML from Immobiliare.it into CanonicalListings.
    Prioritizes JSON-LD and Next.js hydration data.
    """
    def __init__(self):
        super().__init__(name="ImmobiliareNormalizer")

    def _clean_price(self, text: str) -> float:
        # "€ 245.000" -> 245000.0
        cleaned = re.sub(r'[^\d]', '', text)
        return float(cleaned) if cleaned else 0.0

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # --- Data Extraction Strategy ---
        # 1. Try __NEXT_DATA__ (gold mine)
        # 2. Try JSON-LD (standard)
        # 3. Fallback to DOM
        
        json_data = {}
        next_data = {}
        
        # Strategy 1: Next.js Data
        next_script = soup.select_one("#__NEXT_DATA__")
        if next_script:
            try:
                next_data = json.loads(next_script.string)
                # Usually under props -> pageProps -> detailData -> realEstate
                # But strict path checks are fragile, so we'll look loosely or use it for specific fields
            except:
                pass
                
        # Strategy 2: JSON-LD
        # Immobiliare usually has a Schema.org script
        scripts = soup.find_all('script', type='application/ld+json')
        for s in scripts:
            try:
                 d = json.loads(s.string)
                 if d.get("@type") in ["SingleFamilyResidence", "Apartment", "Product", "House"]:
                     json_data = d
                     break
            except:
                pass
        
        # --- Fields ---
        
        # Title
        title = "Unknown Property"
        if json_data.get("name"):
            title = json_data["name"]
        else:
            t_el = soup.select_one("h1.in-title")
            if t_el: title = t_el.get_text(strip=True)
            
        # Price
        price = 0.0
        if json_data.get("offers", {}).get("price"):
            price = float(json_data["offers"]["price"])
        else:
            p_el = soup.select_one("li.nd-list__item.in-feat__item--main") # Old UI
            if not p_el: p_el = soup.select_one(".in-detail__mainFeaturesPrice") # New UI
            if p_el:
                price = self._clean_price(p_el.get_text())

        # Description
        description = ""
        # New UI
        desc_el = soup.select_one("div.in-readMore div.in-readMore__text")
        # Old UI
        if not desc_el: desc_el = soup.select_one("#description div.content")
        
        if desc_el:
            description = desc_el.get_text(separator="\n", strip=True)
        elif json_data.get("description"):
            description = json_data["description"]

        # Features
        bedrooms = None
        bathrooms = None
        sqm = None
        
        # Extract from DOM feature list
        # .in-feat__item (New UI)
        feats = soup.select("li.nd-list__item") # Generic list items in feature block
        if not feats:
             feats = soup.select("dl.in-realEstateFeatures__list dt, dl.in-realEstateFeatures__list dd")
        
        # Try Next.js props first if available for accuracy
        props_re = next_data.get("props", {}).get("pageProps", {}).get("detailData", {}).get("realEstate", {}).get("properties", [])
        if props_re:
             # Iterate complex object if we can, but let's stick to DOM or visible text for robustness
             pass

        # Parse text features
        # usually 3 locali, 1 bagno, 80 m2
        all_text = soup.get_text()
        # Fallback regex on whole text if specific selectors fail (Immobiliare classes change often)
        # Look for specific container first
        feat_container = soup.select_one(".in-feat") or soup.select_one(".in-mainFeatures")
        if feat_container:
            ftxt = feat_container.get_text(separator=" ").lower()
            
            # Surface
            m_sqm = re.search(r'(\d+)\s*(mq|m²)', ftxt)
            if m_sqm:
                sqm = float(m_sqm.group(1))
            
            # Bedrooms (locali)
            m_bed = re.search(r'(\d+)\s*(locali|local|camere)', ftxt)
            if m_bed:
                bedrooms = int(m_bed.group(1))
                
            # Bathrooms
            m_bath = re.search(r'(\d+)\s*(bagni|bagno)', ftxt)
            if m_bath:
                bathrooms = int(m_bath.group(1))
                
            # Floor (Piano)
            # "piano terra", "piano 1", "3 piano"
            floor = None
            if "piano terra" in ftxt or "piano rialzato" in ftxt:
                floor = 0
            else:
                m_floor = re.search(r'(?:piano|p\.)\s*(\d+)', ftxt)
                if m_floor: floor = int(m_floor.group(1))
            
            # Elevator (Ascensore)
            has_elevator = None
            if "ascensore" in ftxt:
                has_elevator = True
                
            # Energy Rating (Classe energetica) or APE
            energy_rating = None
            m_en = re.search(r'(?:classe|energetica|ape)[:\s]+([A-G])\b', ftxt, re.IGNORECASE)
            if m_en:
                energy_rating = m_en.group(1).upper()

        # Images
        image_urls = []
        if json_data.get("image"):
            imgs = json_data["image"]
            if isinstance(imgs, list):
                image_urls = imgs
            elif isinstance(imgs, str):
                image_urls = [imgs]
        
        if not image_urls:
            # Fallback DOM
            imgs = soup.select("img.nd-slideshow__item")
            for img in imgs:
                src = img.get("src")
                if src: image_urls.append(src)
                
        # Geo
        lat = None
        lon = None
        if json_data.get("geo"):
            try:
                lat = float(json_data["geo"].get("latitude", 0))
                lon = float(json_data["geo"].get("longitude", 0))
            except: pass

        # Construct
        unique_string = f"immobiliare_it_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        canonical = CanonicalListing(
            id=unique_hash,
            source_id="immobiliare_it",
            external_id=raw.external_id,
            url=raw.url,
            title=title,
            description=description,
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            floor=floor,
            has_elevator=has_elevator,
            energy_rating=energy_rating,
            surface_area_sqm=sqm,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE
        )

        # Timestamps
        if json_data.get("datePosted"):
            from datetime import datetime
            try:
                # ISO format often used in schema.org: 2023-10-25T10:00:00+02:00
                dt_str = json_data["datePosted"]
                if "T" in dt_str:
                     dt_part = dt_str.split("T")[0]
                     canonical.listed_at = datetime.strptime(dt_part, "%Y-%m-%d")
                else:
                     canonical.listed_at = datetime.strptime(dt_str, "%Y-%m-%d")
            except:
                pass 

        if lat and lon:
            canonical.location = GeoLocation(
                lat=lat,
                lon=lon,
                address_full=title,
                city="Unknown",
                country="IT"
            )
        else:
             # Fallback: Extract city from URL
             # https://www.immobiliare.it/annunci/12345/milano/
             try:
                 url_parts = raw.url.split('/')
                 # Usually .../annunci/ID/CITY/ or .../REGION/CITY/
                 # Let's try to find a known pattern or use part [-2] if it's not the ID
                 city_raw = ""
                 if url_parts[-1] == "": # Trailing slash
                     city_raw = url_parts[-2]
                 else:
                     city_raw = url_parts[-1]
                 
                 if city_raw and not city_raw.isdigit() and len(city_raw) > 2:
                     canonical.location = GeoLocation(
                         lat=0.0,
                         lon=0.0,
                         address_full=title,
                         city=city_raw.capitalize(),
                         country="IT"
                     )
             except:
                 pass

        return canonical

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        raw_listings = input_payload.get("raw_listings", [])
        canonical_listings = []
        errors = []

        for raw in raw_listings:
            try:
                canonical = self._parse_item(raw)
                if canonical:
                    canonical_listings.append(canonical)
            except Exception as e:
                errors.append(f"Immobiliare norm error {raw.external_id}: {e}")

        return AgentResponse(
            status="success" if canonical_listings else "failure",
            data=canonical_listings,
            errors=errors
        )
