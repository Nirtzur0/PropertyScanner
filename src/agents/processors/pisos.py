from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import json
import re
import hashlib
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus

class PisosNormalizerAgent(BaseAgent):
    """
    Parses HTML snippets from Pisos.com into CanonicalListings.
    Uses JSON-LD if available, falls back to DOM selectors.
    """
    def __init__(self):
        super().__init__(name="PisosNormalizer")

    def _clean_price(self, text: str) -> float:
        # "245.000 €" -> 245000.0
        cleaned = re.sub(r'[^\d]', '', text)
        return float(cleaned) if cleaned else 0.0

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Strategy A: Try JSON-LD first (cleaner)
        json_ld_script = soup.find('script', type='application/ld+json')
        json_data = {}
        if json_ld_script:
            try:
                # Iterate all scripts as sometimes multiple are present
                scripts = soup.find_all('script', type='application/ld+json')
                for s in scripts:
                    data = json.loads(s.string)
                    # Look for Residence type
                    if data.get("@type") in ["SingleFamilyResidence", "Apartment", "House", "Residence"]:
                        json_data = data
                        break
            except:
                pass
        
        # --- Extraction ---
        
        # Title
        title = "Unknown Property"
        if json_data.get("name"):
            title = json_data["name"]
        else:
            # Detail page: often just <h1> inside .details__block
            t_el = soup.select_one("div.details__block h1") or soup.select_one("h1") or soup.select_one("a.ad-preview__title")
            if t_el: title = t_el.get_text(strip=True)

        # Price
        price = 0.0
        p_el = soup.select_one("div.price") or soup.select_one("span.ad-preview__price")
        # Detail page often has price in specialized container
        if not p_el: 
            p_el = soup.select_one(".priceBox-price") # Common class
        if p_el:
            price = self._clean_price(p_el.get_text())

        # URL
        full_url = raw.url

        # Components (Bedrooms, Sqm)
        bedrooms = None
        sqm = None
        
        def parse_eu_float(t):
             # Remove thousands separator (.), replace decimal separator (,) with (.)
             # "1.200,50" -> "1200.50"
             clean = t.replace('.', '') 
             clean = clean.replace(',', '.')
             # Remove non-numeric except dot
             clean = re.sub(r'[^\d.]', '', clean)
             return float(clean) if clean else 0.0

        # Strategy 1: Summary list (e.g. "2 habs.", "78 m²")
        chars = soup.select("ul.features-summary li")
        
        for c in chars:
            txt = c.get_text(strip=True)
            txt_lower = txt.lower()
            if "hab" in txt_lower or "dorm" in txt_lower:
                bedrooms = int(re.sub(r'[^\d]', '', txt) or 0)
            elif "m²" in txt_lower or "m2" in txt_lower:
                sqm = parse_eu_float(txt)
                
        # DOM Parsing for details
        # Strategy 2: Detailed features block (fallback if chars didn't work or found nothing)
        if not bedrooms and not sqm:
             # Iterate feature blocks
             feature_blocks = soup.select("div.features__feature")
             for fb in feature_blocks:
                 label = fb.select_one(".features__label")
                 val = fb.select_one(".features__value")
                 if label and val:
                     l_txt = label.get_text(strip=True).lower()
                     v_txt = val.get_text(strip=True)
                     if "habitaciones" in l_txt:
                         bedrooms = int(re.sub(r'[^\d]', '', v_txt) or 0)
                     elif "superficie" in l_txt:
                         sqm = parse_eu_float(v_txt)
        
        # Process chars list (from Search page fallback if still missing)
        if not bedrooms and not sqm:
            if not chars:
                chars = soup.select("p.ad-preview__char")
                
            for c in chars:
                txt = c.get_text(strip=True).lower()
                if "hab" in txt or "dorm" in txt:
                    bedrooms = int(re.sub(r'[^\d]', '', txt) or 0)
                elif "m²" in txt or "m2" in txt:
                    sqm = parse_eu_float(txt)
        
        # Description Extraction (New!)
        description = ""
        # 1. Try description container
        desc_el = soup.select_one("div.description__content")
        if desc_el:
            description = desc_el.get_text(strip=True, separator=" ")
        # 2. Try meta tag
        if not description:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                description = meta_desc.get("content", "")
        # 3. JSON-LD fallback (usually just title repeated, but check)
        if not description and json_data.get("description"):
            # Avoid using title as description unless it's long
            if len(json_data["description"]) > len(title) + 10:
                description = json_data["description"]

        # Lat/Lon extraction from JSON-LD
        lat = None
        lon = None
        if json_data.get("geo"):
            try:
                lat = float(json_data["geo"].get("latitude", 0))
                lon = float(json_data["geo"].get("longitude", 0))
            except:
                pass
        
        # Images
        image_urls = []
        if json_data.get("image"):
            if isinstance(json_data["image"], str):
                image_urls.append(json_data["image"])
            elif isinstance(json_data["image"], list):
                image_urls.extend(json_data["image"])
        
        # Detail page image gallery fallback
        if not image_urls:
            # Look for gallery (often in a JS object or specific huge-images)
            # Try finding gallery images
            gallery_imgs = soup.select("img.main-image") # Example
            for img in gallery_imgs:
                src = img.get("src")
                if src: image_urls.append(src)
                
            # If not found, try all images in known CDN
            if not image_urls:
                imgs = soup.select("img")
                for img in imgs:
                    src = img.get("data-src") or img.get("src")
                    if src and ("pisos.com" in src or "imghs.net" in src) and not "logo" in src:
                        # Filter out thumbnails if possible by size/naming
                        image_urls.append(src)

        # ID Generation
        unique_string = f"pisos_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        # Construct
        canonical = CanonicalListing(
            id=unique_hash,
            source_id="pisos",
            external_id=raw.external_id,
            url=full_url,
            title=title,
            description=description, # Now populated
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT,
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE
        )
        
        if lat and lon:
            from src.core.domain.schema import GeoLocation
            canonical.location = GeoLocation(
                lat=lat, 
                lon=lon, 
                address_full=title, 
                city="Unknown", 
                neighborhood="Unknown",
                country="ES" 
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
