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
                json_data = json.loads(json_ld_script.string)
            except:
                pass
        
        # --- Extraction ---
        
        # Title
        title = "Unknown Property"
        if json_data.get("name"):
            title = json_data["name"]
        else:
            t_el = soup.select_one("a.ad-preview__title")
            if t_el: title = t_el.get_text(strip=True)

        # Price
        price = 0.0
        p_el = soup.select_one("span.ad-preview__price")
        if p_el:
            price = self._clean_price(p_el.get_text())

        # URL
        relative_url = ""
        if json_data.get("url"):
            relative_url = json_data["url"]
        else:
            url_el = soup.select_one("a.ad-preview__title")
            if url_el: relative_url = url_el.get("href")
        
        full_url = f"https://www.pisos.com{relative_url}" if relative_url.startswith("/") else relative_url

        # Components (Bedrooms, Sqm)
        bedrooms = None
        sqm = None
        
        # DOM Parsing for details
        chars = soup.select("p.ad-preview__char")
        for c in chars:
            txt = c.get_text(strip=True)
            if "hab" in txt:
                bedrooms = int(re.sub(r'[^\d]', '', txt) or 0)
            elif "m²" in txt or "m2" in txt:
                sqm = float(re.sub(r'[^\d]', '', txt) or 0)

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
        else:
            # Fallback DOM
            imgs = soup.select("img")
            for img in imgs:
                src = img.get("data-src") or img.get("src")
                if src and "pisos.com" in src or "imghs.net" in src:
                    image_urls.append(src)

        # ID Generation
        # Use provided ID or generate hash
        unique_string = f"pisos_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        # Construct
        canonical = CanonicalListing(
            id=unique_hash,
            source_id="pisos",
            external_id=raw.external_id,
            url=full_url,
            title=title,
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT,
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE
        )
        
        # Hacky: Inject extracted lat/lon into extra_data for enrichment bypass if needed?
        # Actually, if we have lat/lon here, we might want to pass it.
        # But for now, let's let the Enricher handle it or rely on address. 
        # Ideally, we should update CanonicalListing to accept optional lat/lon if known from source.
        # But since CanonicalListing has 'location', let's see. 'location' is a GeoLocation object.
        # Let's populate it partially if we have valid coords.
        from src.core.domain.schema import GeoLocation
        if lat and lon:
            canonical.location = GeoLocation(
                lat=lat, 
                lon=lon, 
                address_full=title, # Placeholder
                city="Unknown", 
                neighborhood="Unknown",
                country="ES" # Required field
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
