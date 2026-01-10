from typing import Any, Dict, List, Optional
import requests
import structlog
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.utils.compliance import ComplianceManager

class EnrichmentAgent(BaseAgent):
    """
    Enriches listings with Geolocation data using Nominatim (OpenStreetMap).
    """
    def __init__(self, compliance: ComplianceManager):
        config = {
            "base_url": "https://nominatim.openstreetmap.org/search",
            "period_seconds": 1.1 # Strict 1 request per second limit for Nominatim
        }
        super().__init__(name="EnrichmentAgent", config=config)
        self.compliance = compliance
        self.headers = {
            "User-Agent": "PropertyScanner/1.0 (bot@example.com)"
        }

    def _geocode(self, query: str) -> Optional[GeoLocation]:
        if not query:
            return None
        
        url = self.config["base_url"]
        
        # Rate Limiting check
        # We treat the API domain as the rate limit key
        api_domain_url = "https://nominatim.openstreetmap.org/"
        if not self.compliance.check_and_wait(api_domain_url, rate_limit_seconds=self.config["period_seconds"]):
             self.logger.warning("rate_limit_blocked", url=api_domain_url)
             return None

        params = {
            "q": query,
            "format": "json",
            "limit": 1
        }
        
        try:
            resp = requests.get(url, params=params, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    item = data[0]
                    return GeoLocation(
                        lat=float(item.get("lat")),
                        lon=float(item.get("lon")),
                        address_full=item.get("display_name", ""),
                        city="", # Simplify for now
                        country="Spain" # Assume Spain for Idealista MVP
                    )
        except Exception as e:
            self.logger.error("geocoding_failed", query=query, error=str(e))
            
        return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """
        Input: {'listings': List[CanonicalListing]}
        Output: List[CanonicalListing] (modified in-place or new list)
        """
        listings: List[CanonicalListing] = input_payload.get("listings", [])
        enriched_count = 0
        
        for listing in listings:
            # Skip if already has location
            if listing.location and listing.location.lat:
                continue
                
            # Construct query from Title or fallback
            # Idealista title: "Piso en Calle de Atocha, Madrid"
            # We can use regex to extract the likely address part, or just try the whole string.
            # "Piso en " is noise.
            query = listing.title
            remove_prefixes = ["Piso en ", "Ático en ", "Chalet en ", "Estudio en "]
            for p in remove_prefixes:
                query = query.replace(p, "")
            
            geo = self._geocode(query)
            if geo:
                listing.location = geo
                enriched_count += 1
                
        return AgentResponse(status="success", data=listings, metadata={"enriched_count": enriched_count})
