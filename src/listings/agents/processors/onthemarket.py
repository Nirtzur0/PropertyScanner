from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import json
import re
import hashlib
from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import RawListing, CanonicalListing, PropertyType, Currency, ListingStatus, GeoLocation
from datetime import datetime

class OnTheMarketNormalizerAgent(BaseAgent):
    """
    Parses HTML snippets from OnTheMarket (UK) into CanonicalListings.
    """
    def __init__(self):
        super().__init__(name="OnTheMarketNormalizer")

    def _clean_price(self, text: str) -> float:
        # "£275,000" -> 275000.0
        cleaned = re.sub(r'[^\d.]', '', text)
        return float(cleaned) if cleaned else 0.0

    def _parse_item(self, raw: RawListing) -> Optional[CanonicalListing]:
        html = raw.raw_data.get("html_snippet", "")
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Strategy 1: DataLayer (Very reliable on OTM)
        dl_data = {}
        # window.dataLayer.push({"parent-locations":...})
        dl_pattern = re.compile(r'window\.dataLayer\.push\s*\((.*?)\);', re.DOTALL)
        # Scan all scripts
        for script in soup.find_all('script'):
            if script.string and 'window.dataLayer' in script.string:
                match = dl_pattern.search(script.string)
                if match:
                    try:
                        # Ideally parse as JSON, but it might be JS object
                        # It looks like valid JSON int the snapshot: {"key": "value"}
                        dl_data = json.loads(match.group(1))
                        break
                    except:
                        pass
        
        # Strategy 2: JSON-LD (not implemented yet; kept for future extension)

        # Title
        title = "Unknown Property"
        t_el = soup.find('h1')
        if t_el:
            title = t_el.get_text(strip=True)
        elif soup.title:
            title = soup.title.get_text(strip=True)
            
        # Price
        price = 0.0
        if dl_data.get("price"):
            # "275,000"
            price = self._clean_price(str(dl_data["price"]))
        
        if price == 0.0:
            # Fallback regex on title or meta
            # "£275,000"
            m = re.search(r'£([\d,]+)', title)
            if m:
                price = self._clean_price(m.group(1))

        # URL
        full_url = raw.url
        if not full_url and dl_data.get("property-id"):
            full_url = f"https://www.onthemarket.com/details/{dl_data['property-id']}/"

        # Description
        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = str(meta_desc.get("content") or "").strip()

        # Features
        bedrooms = None
        bathrooms = None
        sqm = None
        
        # OTM often puts bed count in title/meta description ("3 bed", "3 bedroom").
        bed_text = f"{title} {description}".lower()
        m = re.search(r'(\d+)\s*bed(?:room)?', bed_text)
        if m:
            try:
                bedrooms = int(m.group(1))
            except Exception:
                bedrooms = bedrooms
                 
        # Parse for area. Prefer sqm when present, otherwise convert sqft -> sqm.
        all_text = soup.get_text(" ", strip=True)
        if sqm is None:
            # "54 sq m", "54 sqm", "54 m2", "54 m²"
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:sq\s*m|sqm|m2|m²)\b", all_text, re.IGNORECASE)
            if m:
                try:
                    sqm = float(m.group(1))
                except Exception:
                    sqm = None
        if sqm is None:
            # "581 sq ft"
            m = re.search(r"(\d+(?:\.\d+)?)\s*sq\s*ft\b", all_text, re.IGNORECASE)
            if m:
                try:
                    sqft = float(m.group(1))
                    sqm = round(sqft * 0.092903, 2)
                except Exception:
                    sqm = None

        # Images
        image_urls = []
        # og:image
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            image_urls.append(og_img["content"])
            
        # Swiper images or gallery
        # Look for <img src="..."> in gallery containers
        # Or look for JSON data with images
        
        # Location
        city = "London" # Default for now if not found, or extract from address
        postcode = dl_data.get("postcode")
        
        if dl_data.get("addressline_2"): # sometimes city
             pass
             
        # Address from title often: "High Street, New Malden, KT3 4"
        address_parts = title.split(',')
        if len(address_parts) > 1:
            city = address_parts[-2].strip() # Heuristic

        # Coordinates from script?
        # Often in Next.js data `__NEXT_DATA__`
        # But let's skip complex parsing for now unless needed.

        # ID
        pid = dl_data.get("property-id") or raw.external_id
        unique_string = f"onthemarket_{pid}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()

        canonical = CanonicalListing(
            id=unique_hash,
            source_id=raw.source_id,
            external_id=str(pid),
            url=full_url,
            title=title,
            description=description or title,
            price=price,
            currency=Currency.GBP,
            property_type=PropertyType.APARTMENT if "apartment" in title.lower() or "flat" in title.lower() else PropertyType.HOUSE,
            bedrooms=bedrooms,
            surface_area_sqm=sqm,
            bathrooms=bathrooms,
            image_urls=image_urls,
            status=ListingStatus.ACTIVE,
            listed_at=raw.fetched_at,
            crawled_at=raw.fetched_at,
            market_date=raw.fetched_at,
        )
        
        if postcode:
            canonical.location = GeoLocation(
                lat=None, lon=None,
                address_full=title,
                city=city,
                zip_code=postcode,
                country="GB"
            )
        else:
             canonical.location = GeoLocation(
                lat=None, lon=None,
                address_full=title,
                city=city,
                country="GB"
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
