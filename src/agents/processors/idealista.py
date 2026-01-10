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
        
        # --- 1. Basic Metadata (Search Page) ---
        # The raw input is currently the "article.item" snippet from the search page.
        # Ideally, we should fetch the DETAILS page for full info, but for now we parse the search card.
        
        # Title
        title_el = soup.select_one("a.item-link")
        title = title_el.get_text(strip=True) if title_el else "Unknown Property"
        
        # Price
        price_el = soup.select_one("span.item-price")
        # Handle "350.000€" -> 350000.0
        price = self._clean_price(price_el.get_text()) if price_el else 0.0
        
        # Details
        # <span class="item-detail">3 hab.</span> <span class="item-detail">90 m²</span>
        details = [s.get_text(strip=True) for s in soup.select("span.item-detail")]
        
        bedrooms = None
        sqm = None
        
        for d in details:
            cleaned = re.sub(r'[^\d]', '', d)
            if not cleaned: continue
            
            if "hab" in d:
                bedrooms = int(cleaned)
            elif "m²" in d:
                sqm = float(cleaned)

        # --- 2. Images ---
        # Idealista search cards use lazy loading or simple img tags.
        # The "fullScreenGalleryPics" regex is for the DETAIL PAGE.
        # For the search card, we look for: <img src="..."> or picture sources.
        
        image_urls = []
        # Try to find visible images in the card
        imgs = soup.select("img")
        for img in imgs:
            src = img.get("data-src") or img.get("src")
            # Filter out tiny icons or placeholders
            if src and "http" in src and "idealista" in src:
               image_urls.append(src)
        
        # --- 3. ID Generation ---
        unique_string = f"{raw.source_id}_{raw.external_id}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        return CanonicalListing(
            id=unique_hash,
            source_id=raw.source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=title,
            price=price,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT, 
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            image_urls=image_urls, # Now populated
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
