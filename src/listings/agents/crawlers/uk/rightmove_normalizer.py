import json
import re
import logging
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class RightmoveNormalizer:
    """
    Extracts structured property data from Rightmove HTML.
    Target: window.PAGE_MODEL or window.__PRELOADED_STATE__
    """

    def normalize(self, html_content: str, url: str = "") -> Dict[str, Any]:
        data: Dict[str, Any] = {}

        # Strategy 1: PAGE_MODEL
        # Look for window.PAGE_MODEL = { ... }
        pm_match = re.search(r'window\.PAGE_MODEL\s*=\s*({.*?});', html_content, re.DOTALL)
        if pm_match:
            try:
                json_str = pm_match.group(1)
                pm_data = json.loads(json_str)
                self._extract_from_page_model(pm_data, data)
            except Exception as e:
                logger.warning(f"Error parsing PAGE_MODEL in Rightmove: {e}")

        # Strategy 2: Schema.org (rare on Rightmove but possible)
        # ... logic if needed ...

        data["source_url"] = url
        return data

    def _extract_from_page_model(self, pm: Dict[str, Any], data: Dict[str, Any]) -> None:
        # Standard structure: propertyData -> property
        p_data = pm.get("propertyData", {})
        prop = p_data.get("property", {})
        
        if not prop:
            return

        # Price
        price_obj = p_data.get("prices", {}).get("primaryPrice", {})
        if not price_obj:
            # Maybe inside property?
            price_obj = prop.get("price", {})
            
        if "amount" in price_obj:
            data["price"] = price_obj["amount"]
        if "currencyCode" in price_obj:
            data["currency"] = price_obj["currencyCode"]
        
        # Details
        if "bedrooms" in prop:
             data["bedrooms"] = prop["bedrooms"]
        if "bathrooms" in prop:
             data["bathrooms"] = prop["bathrooms"]
             
        # Address
        if "address" in p_data:
             addr = p_data["address"]
             if "displayAddress" in addr:
                 data["address"] = addr["displayAddress"]
        elif "address" in prop:
             # handle prop address object
             pass

        # Images
        if "images" in p_data:
             imgs = p_data["images"]
             urls = [img.get("url") for img in imgs if "url" in img]
             if urls:
                 data["images"] = urls

        # Description
        if "description" in p_data:
             data["description"] = p_data["description"]
