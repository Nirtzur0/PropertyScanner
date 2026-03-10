from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import json
import re
import hashlib
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus, GeoLocation

class PisosNormalizerAgent(BaseAgent):
    """
    Parses HTML snippets from Pisos.com into CanonicalListings.
    Uses JSON-LD if available, falls back to DOM selectors.
    """
    MIN_PRICE = 10_000.0
    MAX_PRICE = 50_000_000.0
    MIN_SURFACE_AREA = 10.0
    MAX_SURFACE_AREA = 1_000.0

    def __init__(self):
        super().__init__(name="PisosNormalizer")

    def _parse_eu_float(self, text: str) -> float:
        raw = re.sub(r"[^0-9.,]", "", str(text or ""))
        if not raw:
            return 0.0

        if "," in raw and "." in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif "," in raw:
            raw = raw.replace(",", ".")
        elif "." in raw:
            parts = raw.split(".")
            last = parts[-1]
            if last.isdigit() and len(last) in (1, 2) and all(p.isdigit() for p in parts[:-1] if p):
                raw = "".join(parts[:-1]) + "." + last
            else:
                raw = raw.replace(".", "")

        try:
            return float(raw)
        except Exception:
            return 0.0

    def _normalize_price(self, value: float) -> float:
        if self.MIN_PRICE <= float(value) <= self.MAX_PRICE:
            return float(value)
        return 0.0

    def _normalize_surface_area(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        value = float(value)
        if self.MIN_SURFACE_AREA <= value <= self.MAX_SURFACE_AREA:
            return value
        return None

    def _clean_price(self, text: str) -> float:
        normalized = " ".join(str(text or "").split())
        match = re.search(r"(\d[\d.\s]*(?:,\d+)?)\s*(?:€|eur)\b", normalized, re.IGNORECASE)
        if match:
            return self._normalize_price(self._parse_eu_float(match.group(1)))

        fallback = re.search(r"\b(\d[\d.\s]*(?:,\d+)?)\b", normalized)
        if fallback:
            return self._normalize_price(self._parse_eu_float(fallback.group(1)))
        return 0.0

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
        
        # Strategy 1: Summary list (e.g. "2 habs.", "78 m²")
        chars = soup.select("ul.features-summary li")
        
        for c in chars:
            txt = c.get_text(strip=True)
            txt_lower = txt.lower()
            if "hab" in txt_lower or "dorm" in txt_lower:
                bedrooms = int(re.sub(r'[^\d]', '', txt) or 0)
            elif ("m²" in txt_lower or "m2" in txt_lower) and not (
                "€/m" in txt_lower
                or "eur/m" in txt_lower
                or (" /m" in txt_lower and ("€" in txt_lower or "eur" in txt_lower))
                or ("/m" in txt_lower and ("€" in txt_lower or "eur" in txt_lower))
            ):
                sqm = self._normalize_surface_area(self._parse_eu_float(txt))

        # JSON-LD floorSize (if present)
        if not sqm and json_data.get("floorSize"):
            try:
                floor_size = json_data["floorSize"]
                if isinstance(floor_size, dict):
                    sqm_val = floor_size.get("value") or floor_size.get("maxValue") or floor_size.get("minValue")
                    if sqm_val is not None:
                        sqm = self._normalize_surface_area(self._parse_eu_float(str(sqm_val)))
                elif isinstance(floor_size, (int, float, str)):
                    sqm = self._normalize_surface_area(self._parse_eu_float(str(floor_size)))
            except Exception:
                pass
                
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
                         sqm = self._normalize_surface_area(self._parse_eu_float(v_txt))
        
        # Process chars list (from Search page fallback if still missing)
        if not bedrooms and not sqm:
            if not chars:
                chars = soup.select("p.ad-preview__char")
                
            for c in chars:
                txt = c.get_text(strip=True).lower()
                if "hab" in txt or "dorm" in txt:
                    bedrooms = int(re.sub(r'[^\d]', '', txt) or 0)
                elif ("m²" in txt or "m2" in txt) and not (
                    "€/m" in txt
                    or "eur/m" in txt
                    or (" /m" in txt and ("€" in txt or "eur" in txt))
                    or ("/m" in txt and ("€" in txt or "eur" in txt))
                ):
                    sqm = self._normalize_surface_area(self._parse_eu_float(txt))
        
        # --- NEW: Extended Features (Bathrooms, Floor, Elevator) ---
        bathrooms = None
        floor = None
        has_elevator = None
        energy_rating = None

        all_features_text = soup.select(
            "div.features__value, li.features__list-item, p.ad-preview__char, ul.features-summary li"
        )
        full_feat_text = " ".join(
            el.get_text(separator=" ", strip=True).lower() for el in all_features_text
        )
        
        # 1. Parse bathrooms from chars list if present (e.g. "2 baños")
        if not bathrooms:
            for c in chars:
                txt = c.get_text(strip=True).lower()
                if "baño" in txt or "bano" in txt:
                    bathrooms = int(re.sub(r'[^\d]', '', txt) or 0)

        # 2. Parse from Feature Blocks (Generic) if still missing
        if not bathrooms:
            # "2 baños"
            m = re.search(r'(\d+)\s*ba(?:ñ|n)o', full_feat_text)
            if m:
                bathrooms = int(m.group(1))

        if floor is None:
            # "Planta 3ª", "Bajo", "3er piso"
            if "bajo" in full_feat_text:
                floor = 0
            else:
                m = re.search(r'planta\s*(\d+)', full_feat_text)
                if m:
                    floor = int(m.group(1))

        if has_elevator is None:
            if "con ascensor" in full_feat_text:
                has_elevator = True
            elif "sin ascensor" in full_feat_text:
                has_elevator = False
            # Often just "Ascensor" listed means true
            elif "ascensor" in full_feat_text:
                has_elevator = True

        # Energy Rating
        # "Certificado energético", "Eficiencia energética: E"
        m = re.search(r'(?:energétic[oa]|calificación|letra)[:\s]+([A-G])\b', full_feat_text, re.IGNORECASE)
        if m:
            energy_rating = m.group(1).upper()
        elif "trámite" in full_feat_text and ("energ" in full_feat_text):
            energy_rating = "pending"

        
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
                # Common pattern in pisos.com: img with class "ad-preview__image" or inside swiper
                imgs = soup.select("img.ad-preview__image, div.swiper-slide img, img.carousel-item-img")
                for img in imgs:
                    src = img.get("data-src") or img.get("src")
                    if src and ("pisos.com" in src or "imghs.net" in src) and "logo" not in src:
                        image_urls.append(src)
                
                # Fallback: grab ANY large image
                if not image_urls:
                    all_imgs = soup.find_all("img")
                    for img in all_imgs:
                         src = img.get("src") or img.get("data-src")
                         if src and src.startswith("http"):
                             # Filter small icons
                             if "icon" not in src and "logo" not in src and ".svg" not in src:
                                 image_urls.append(src)

        # Address / City Extraction
        city = "Unknown"
        
        # 1. Try JSON-LD Address
        if json_data.get("address"):
            addr = json_data["address"]
            if isinstance(addr, dict):
                city = addr.get("addressLocality", city)
        
        # 2. Try Breadcrumbs (Very reliable)
        if city == "Unknown":
            breadcrumbs = soup.select(
                "div.bread-crumbs ul li a, ul.breadcrumbs li a, nav.breadcrumb a, ol.breadcrumb li a, .breadcrumb a"
            )
            if breadcrumbs:
                # Usually: Home > Sale > Province > City > Zone
                # We try to grab the City (index -2 or -3 usually?)
                # Or just grab the text of the one containing "Pisos en..."
                candidates = []
                for b in breadcrumbs:
                    txt = b.get_text(strip=True)
                    if not txt or txt in ["pisos.com", "Venta", "Alquiler", "Inicio", "Home"]:
                        continue
                    clean_city = (
                        txt.replace("Pisos en ", "")
                        .replace("Casas en ", "")
                        .strip()
                    )
                    if clean_city:
                        candidates.append(clean_city)

                # Prefer the actual city over neighborhood/zone crumbs.
                if candidates:
                    candidates_norm = [c.strip() for c in candidates if c.strip()]
                    common_cities = {
                        "madrid",
                        "barcelona",
                        "valencia",
                        "sevilla",
                        "zaragoza",
                        "malaga",
                        "alicante",
                        "bilbao",
                    }
                    chosen = None
                    for c in candidates_norm:
                        if c.lower() in common_cities:
                            chosen = c
                            break
                    city = chosen or candidates_norm[0]
        
        # 3. Fallback to URL extraction if still Unknown
        if city == "Unknown":
            # URL structure often: .../piso-city_neighborhood...
            # e.g. pisos.com/comprar/piso-puerta_de_madrid_el_juncal28802...
            try:
                parts = full_url.split("/")
                # usually last part, or second to last
                slug = parts[-1] if parts[-1] else parts[-2]
                if "-" in slug:
                    # simplistic parse: "piso-puerta_de_madrid..."
                    # We can assume the text *before* huge number is city-ish
                    # But it's hard. Let's just try to grab common cities (Madrid, Barcelona) if present
                    slug_lower = slug.lower()
                    common_cities = ["madrid", "barcelona", "valencia", "sevilla", "zaragoza", "malaga", "alicante", "bilbao"]
                    for c in common_cities:
                        if c in slug_lower:
                            city = c.capitalize()
                            break
            except:
                pass
        
        # 3. Fallback: Check Title
        if city == "Unknown" and title:
             # "Piso en venta en Madrid"
             # Very naive, but better than nothing
             # We rely heavily on enrichment later anyway
             pass

        # Elevator scan in description if missing
        if has_elevator is None and description:
            desc_lower = description.lower()
            if "con ascensor" in desc_lower or "tiene ascensor" in desc_lower or "dispone de ascensor" in desc_lower:
                has_elevator = True
            elif "sin ascensor" in desc_lower:
                has_elevator = False
            elif "ascensor" in desc_lower:
                # Ambiguous, but if mentioned often positive feature
                has_elevator = True

        # Force Location Object creation even if Lat/Lon missing, to allow enrichment
        if city == "Unknown": 
             # Try regex for coordinates if missing from JSON-LD
             pass

        # Coordinate Regex Fallback
        if not lat or not lon:
            # mapData = { ... "latitude": 40.4... }
            # or "lat": 40.4
            try:
                # Search for latitude pattern
                lat_match = re.search(r'["\']?latitude["\']?\s*:\s*([-\d.]+)', html)
                lon_match = re.search(r'["\']?longitude["\']?\s*:\s*([-\d.]+)', html)
                
                if not lat_match:
                     lat_match = re.search(r'["\']?lat["\']?\s*:\s*([-\d.]+)', html)
                if not lon_match:
                     lon_match = re.search(r'["\']?lng["\']?\s*:\s*([-\d.]+)', html)

                # NEW: Check for data-params="latitude=..." style
                if not lat_match:
                     lat_match = re.search(r'latitude=([-\d.]+)', html)
                if not lon_match:
                     lon_match = re.search(r'longitude=([-\d.]+)', html)
                     
                if lat_match and lon_match:
                    lat = float(lat_match.group(1))
                    lon = float(lon_match.group(1))
            except:
                pass


        # ID Generation
        unique_string = f"pisos_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        # Construct
        canonical = CanonicalListing(
            id=unique_hash,
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=full_url,
            title=title,
            description=description,
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT,
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            image_urls=image_urls,
            
            # New Extended Fields
            bathrooms=bathrooms,
            floor=floor,
            has_elevator=has_elevator,
            # energy_rating removed
            
            status=ListingStatus.ACTIVE,
            crawled_at=raw.fetched_at,
            market_date=raw.fetched_at
        )
        
        if lat and lon:
            canonical.location = GeoLocation(
                lat=lat, 
                lon=lon, 
                address_full=title, 
                city=city, 
                country="ES",
                zip_code=None
            )
        else:
            # Create location object even if incomplete, to ensure it exists for enrichment
            canonical.location = GeoLocation(
                lat=None,
                lon=None,
                address_full=title,
                city=city, # Might be "Unknown"
                country="ES"
            )

        # Final fallback for sqm: scan full text for "NN m2"/"NN m²".
        # We keep it conservative to avoid capturing prices/years.
        if canonical.surface_area_sqm is None or canonical.surface_area_sqm <= 0:
            try:
                candidate_blocks = [
                    description,
                    soup.find("meta", attrs={"name": "description"}).get("content", "") if soup.find("meta", attrs={"name": "description"}) else "",
                ]
                for block in candidate_blocks:
                    if not block:
                        continue
                    m = re.search(r"(?<![\d.,])(\d{2,4}(?:[.,]\d+)?)\s*(?:m2|m²)\b", block.lower())
                    if not m:
                        continue
                    parsed_area = self._normalize_surface_area(self._parse_eu_float(m.group(1)))
                    if parsed_area is not None:
                        canonical.surface_area_sqm = parsed_area
                        break
            except Exception:
                pass

        # Timestamps (Source)
        if json_data.get("datePosted"):
            from datetime import datetime
            try:
                # e.g. "2023-11-15T00:00:00"
                dt_str = json_data["datePosted"]
                if "T" in dt_str:
                     dt_part = dt_str.split("T")[0]
                     canonical.listed_at = datetime.strptime(dt_part, "%Y-%m-%d")
                else:
                     canonical.listed_at = datetime.strptime(dt_str, "%Y-%m-%d")
            except:
                pass

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
