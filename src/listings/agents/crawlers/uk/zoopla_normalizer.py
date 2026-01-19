import json
import logging
from typing import Any, Dict, Optional, List
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class ZooplaNormalizer:
    """
    Extracts structured property data from Zoopla HTML using JSON-LD and Fallbacks.
    """

    def normalize(self, html_content: str, url: str = "") -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        soup = BeautifulSoup(html_content, "html.parser")

        # Strategy 1: JSON-LD (Schema.org)
        # Zoopla often puts data effectively in two places:
        # 1. A global 'SearchResultsPage' graph
        # 2. A 'Product' or 'RealEstateAgent' listing
        
        try:
            json_lds = soup.find_all("script", {"type": "application/ld+json"})
            for script in json_lds:
                if not script.string:
                    continue
                try:
                    js = json.loads(script.string)
                    self._parse_json_ld(js, data)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning(f"Error parsing JSON-LD in Zoopla: {e}")

        # Strategy 2: Fallbacks (CSS Selectors) if critical data missing
        if not data.get("price"):
            price_el = soup.select_one('[data-testid="price"]')
            if price_el:
                data["price"] = price_el.get_text(strip=True)

        if not data.get("address"):
             address_el = soup.select_one('[data-testid="address-label"]')
             if address_el:
                 data["address"] = address_el.get_text(strip=True)

        data["source_url"] = url
        return data

    def _parse_json_ld(self, js: Any, data: Dict[str, Any]) -> None:
        if isinstance(js, list):
            for item in js:
                self._parse_json_ld(item, data)
            return
        
        if not isinstance(js, dict):
            return

        formatted_type = js.get("@type", "")
        
        # Check for Graph
        if "@graph" in js:
             self._parse_json_ld(js["@graph"], data)
             return

        # Handle SearchResultsPage which contains the main entity
        if formatted_type == "SearchResultsPage":
            pass # Falling through to check keys below

        # Recursion for nested structures (ItemList, etc.)
        for key in ["mainEntity", "itemListElement", "containsPlace", "@graph", "item"]:
            if key in js:
                self._parse_json_ld(js[key], data)

        # Handle Single Listing (often inside itemListElement of a search page, or standalone)
        # Note: On a detail page, we might find "RealEstateListing" or "Product" or "Residence"
        # In the sample, we saw 'offers' inside an item.
        
        # Check for offers (Pricing)
        if "offers" in js:
            offers = js["offers"]
            if isinstance(offers, dict):
                price = offers.get("price")
                currency = offers.get("priceCurrency")
                if price:
                    data["price"] = price
                if currency:
                    data["currency"] = currency
        
        # Check for Property Details
        if "name" in js and not data.get("title"):
             data["title"] = js["name"]
        
        if "description" in js and not data.get("description"):
             data["description"] = js["description"]

        if "image" in js and not data.get("images"):
             imgs = js["image"]
             if isinstance(imgs, str):
                 data["images"] = [imgs]
             elif isinstance(imgs, list):
                 data["images"] = [i for i in imgs if isinstance(i, str)]
             elif isinstance(imgs, dict) and "url" in imgs:
                 data["images"] = [imgs["url"]]

        if "url" in js and not data.get("listing_url"):
            data["listing_url"] = js["url"]
        
        if "address" in js and not data.get("address"):
            addr = js["address"]
            if isinstance(addr, str):
                data["address"] = addr
            elif isinstance(addr, dict):
                parts = []
                if addr.get("streetAddress"): parts.append(addr["streetAddress"])
                if addr.get("addressLocality"): parts.append(addr["addressLocality"])
                if addr.get("postalCode"): parts.append(addr["postalCode"])
                data["address"] = ", ".join(parts)

