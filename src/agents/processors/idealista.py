from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus
import hashlib
import re

class IdealistaNormalizerAgent(BaseAgent):
    """
    Parses HTML snippets from Idealista into CanonicalListings.
    """
    def __init__(self):
        super().__init__(name="IdealistaNormalizer")

    def _clean_price(self, text: str) -> float:
        # "245.000 €" -> 245000.0
        cleaned = re.sub(r'[^\d]', '', text)
        return float(cleaned) if cleaned else 0.0

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None
            
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
        
        # --- 5. Features (Bedrooms, Sqm) ---
        bedrooms = None
        sqm = None
        
        if is_detail_page:
             # Look for "Basic features" list
             # <ul> <li class="details-property-feature-one">...</li> </ul>
             features_list = soup.select("div.details-property-feature-one ul > li")
             for f in features_list:
                 txt = f.get_text(strip=True).lower()
                 if "hab" in txt or "bedroom" in txt:
                      bedrooms = int(re.sub(r'[^\d]', '', txt) or 0)
                 elif "m²" in txt or "construido" in txt:
                      # "120 m² construidos"
                      sqm = float(re.sub(r'[^\d]', '', txt) or 0)
        else:
            # Fallback to search card parsing
            details = [s.get_text(strip=True) for s in soup.select("span.item-detail")]
            for d in details:
                cleaned = re.sub(r'[^\d]', '', d)
                if not cleaned: continue
                if "hab" in d: bedrooms = int(cleaned)
                elif "m²" in d: sqm = float(cleaned)

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
        
        # --- 7. ID Generation ---
        unique_string = f"{raw.source_id}_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        return CanonicalListing(
            id=unique_hash,
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=title,
            description=description, # Populated!
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT, 
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE
        )

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
             status = "success" # Empty input
        
        # NOTE: The article suggests parsing hidden JSON (e.g. `utag_data`).
        # If we had the full PAGE HTML, we would regex for "var utag_data = {...}".
        # Currently, 'RawListing' only contains the item snippet (<article>...</article>).
        # So we stick to DOM parsing for now.
        
        return AgentResponse(
            status=status,
            data=canonical_listings,
            errors=errors
        )
