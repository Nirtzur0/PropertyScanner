from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus, GeoLocation
from src.services.geocoding_service import GeocodingService
import hashlib
import re

class IdealistaNormalizerAgent(BaseAgent):
    """
    Parses HTML snippets from Idealista into CanonicalListings.
    """
    def __init__(self):
        super().__init__(name="IdealistaNormalizer")
        self.geocoding_service = GeocodingService()

    def _clean_price(self, text: str) -> float:
        # "245.000 €" -> 245000.0
        cleaned = re.sub(r'[^\d]', '', text)
        return float(cleaned) if cleaned else 0.0

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None

        unique_hash = hashlib.md5(f"{raw.source_id}:{raw.external_id}".encode()).hexdigest()
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # --- 1. Identify Page Type ---
        # If it has "adCommentsLanguage", it's likely a DETAIL page.
        is_detail_page = bool(soup.select_one("div.adCommentsLanguage") or soup.select_one("#main-image-container"))

        # --- 2. title ---
        if is_detail_page:
            t_el = soup.select_one("h1.main-info__title") or soup.select_one("span.main-info__title-main")
            title = t_el.get_text(strip=True) if t_el else "Unknown Property"
        else:
            t_el = soup.select_one("a.item-link")
            title = t_el.get_text(strip=True) if t_el else "Unknown Property"
        
        # --- 3. Price ---
        if is_detail_page:
            p_el = soup.select_one("span.info-data-price") or soup.select_one("span.txt-bold")
        else:
            p_el = soup.select_one("span.item-price")
            
        price = 0.0
        if p_el:
            price = self._clean_price(p_el.get_text())

        # --- 4. Description (The Gold Mine) ---
        description = ""
        if is_detail_page:
            # Try newer selector
            desc_container = soup.select_one("div.adCommentsLanguage")
            if not desc_container:
                 desc_container = soup.select_one("div.comment")
            
            if desc_container:
                # Get text with newlines
                description = desc_container.get_text(separator="\n", strip=True)
                
            # Expand "Read more" if it was just hidden in HTML?
            # Usually Idealista puts the full text in HTML but hides it with CSS.
        
        # --- 5. Features (Bedrooms, Bathrooms, Sqm, Floor, Elevator, Energy) ---
        bedrooms = None
        bathrooms = None
        sqm = None
        floor = None
        has_elevator = None
        energy_rating = None
        
        feature_texts = []
        
        if is_detail_page:
             # Look for "Basic features" list
             # <ul> <li class="details-property-feature-one">...</li> </ul>
             features_list = soup.select("div.details-property-feature-one ul > li")
             feature_texts = [f.get_text(strip=True).lower() for f in features_list]
        else:
            # Fallback to search card parsing
            feature_texts = [s.get_text(strip=True).lower() for s in soup.select("span.item-detail")]
            
        for txt in feature_texts:
            # Sqm
            if "m²" in txt:
                 sqm_match = re.search(r'(\d+)', txt.replace('.', ''))
                 if sqm_match: sqm = float(sqm_match.group(1))
            elif "construido" in txt and "año" not in txt and "19" not in txt and "20" not in txt:
                 # Fallback but risky if it's year
                 sqm_match = re.search(r'(\d+)', txt.replace('.', ''))
                 if sqm_match and float(sqm_match.group(1)) < 1800: # Sanity check vs year
                    sqm = float(sqm_match.group(1))
            
            # Bedrooms
            elif "hab" in txt or "bedroom" in txt:
                 bed_match = re.search(r'(\d+)', txt)
                 if bed_match: bedrooms = int(bed_match.group(1))
            
            # Bathrooms
            elif "baño" in txt or "bath" in txt:
                 bath_match = re.search(r'(\d+)', txt)
                 if bath_match: bathrooms = int(bath_match.group(1))

            # Floor
            elif "planta" in txt or "bajo" in txt:
                # "Planta 3ª exterior" -> 3
                # "Bajo exterior" -> 0
                if "bajo" in txt:
                    floor = 0
                else:
                    floor_match = re.search(r'planta (\d+)', txt)
                    if floor_match: floor = int(floor_match.group(1))
            
            # Elevator
            if "ascensor" in txt:
                if "sin" in txt: has_elevator = False
                elif "con" in txt: has_elevator = True
            
            # Energy Rating
            if "certifi" in txt or "energé" in txt:
                # "Certificación energética: E"
                # "Certificado energético: en trámite"
                if "trámite" in txt:
                    energy_rating = "pending"
                else:
                    # Find single uppercase letter
                    rating_match = re.search(r':\s*([A-G])', txt, re.IGNORECASE)
                    if rating_match:
                        energy_rating = rating_match.group(1).upper()

        # --- 6. Images ---
        image_urls = []
        
        # Check for JSON data (Deep extraction)
        # Idealista often puts gallery in a JS variable "fullScreenGalleryPics"
        scripts = soup.find_all("script")
        for s in scripts:
            if s.string and "fullScreenGalleryPics" in s.string:
                try:
                    # Regex extract the generic list structure
                    # fullScreenGalleryPics: [...json...]
                    match = re.search(r'fullScreenGalleryPics\s*:\s*(\[.*?\]),', s.string, re.DOTALL)
                    if match:
                        # This is a JS object, not strict JSON (keys might not be quoted)
                        # But typically the URLs are strings.
                        # Simple regex for URLs ending in .jpg
                        urls = re.findall(r'(https?://[^"\']+\.jpg)', match.group(1))
                        image_urls.extend(urls)
                except:
                   pass
        
        if not image_urls:
            # DOM Fallback
            imgs = soup.select("img")
            for img in imgs:
                src = img.get("data-src") or img.get("src")
                if src and "http" in src and "idealista" in src and "logo" not in src:
                    image_urls.append(src)
        
        # Deduplicate
        image_urls = list(set(image_urls))
        
        # --- 7. Location / City Extraction ---
        # Idealista URLs: https://www.idealista.com/inmueble/12345/
        # Or search: https://www.idealista.com/venta-viviendas/madrid-madrid/
        
        city = "Unknown"
        
        # Method A: From Title (e.g. "Piso en Calle de Atocha, Madrid")
        # Usually "Type in Address, City"
        if "," in title:
            parts = title.split(",")
            if len(parts) >= 2:
                potential_city = parts[-1].strip()
                # Sanity check length
                if len(potential_city) < 30: 
                    city = potential_city

        # Method B: From URL if Detail Page context
        # Ideally we'd need the search URL context, but we might only have listing URL
        # Listing URLs don't always have city. 
        # But if we have a "Location" section in features?
        
        # Populate GeoLocation
        lat, lon = 0.0, 0.0
        if title != "Unknown Property":
            coords = self.geocoding_service.geocode_address(title)
            if coords:
                lat, lon = coords

        canonical = CanonicalListing(
            id=unique_hash,
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=title,
            description=description, 
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT, 
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            surface_area_sqm=sqm,
            floor=floor,
            has_elevator=has_elevator,
            energy_rating=energy_rating,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE,
            location=GeoLocation(
                lat=lat,
                lon=lon,
                address_full=title,
                city=city,
                country="ES"
            )
        )

        return canonical

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """
        Input: {'raw_listings': List[RawListing]}
        Output: List[CanonicalListing]
        """
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
        
        if canonical_listings:
             status = "success"
        elif errors:
             status = "failure"
        else:
             status = "success"
        
        return AgentResponse(
            status=status,
            data=canonical_listings,
            errors=errors
        )
