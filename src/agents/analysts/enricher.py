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

    def _reverse_geocode(self, lat: float, lon: float) -> Optional[GeoLocation]:
        url = "https://nominatim.openstreetmap.org/reverse"
        
        # Rate Limiting check
        api_domain_url = "https://nominatim.openstreetmap.org/"
        if not self.compliance.check_and_wait(api_domain_url, rate_limit_seconds=self.config["period_seconds"]):
             self.logger.warning("rate_limit_blocked", url=api_domain_url)
             return None

        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "zoom": 10
        }
        
        try:
            resp = requests.get(url, params=params, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data and "address" in data:
                    addr = data["address"]
                    # Priority for city-level labels
                    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or addr.get("county") or "Unknown"
                    
                    return GeoLocation(
                        lat=lat, # Keep original precise coords
                        lon=lon,
                        address_full=data.get("display_name", ""),
                        city=city,
                        country=addr.get("country", "Spain")
                    )
        except Exception as e:
            self.logger.error("reverse_geocoding_failed", error=str(e))
            
        return None

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """
        Input: {'listings': List[CanonicalListing]}
        Output: List[CanonicalListing] (modified in-place)
        """
        listings: List[CanonicalListing] = input_payload.get("listings", [])
        enriched_count = 0
        
        for listing in listings:
            # Case A: Has Lat/Lon but no City (or Unknown)
            if listing.location and listing.location.lat != 0:
                if notOrUnknown(listing.location.city):
                    geo = self._reverse_geocode(listing.location.lat, listing.location.lon)
                    if geo:
                        listing.location.city = geo.city
                        if notOrUnknown(listing.location.address_full):
                            listing.location.address_full = geo.address_full
                        enriched_count += 1
                continue
                
            # Case B: No Lat/Lon, try Geocoding from Title
            query = listing.title
            remove_prefixes = ["Piso en ", "Ático en ", "Chalet en ", "Estudio en ", "Venta de piso en "]
            for p in remove_prefixes:
                query = query.replace(p, "")
            
            geo = self._geocode(query)
            if geo:
                listing.location = geo
                enriched_count += 1
                
        return AgentResponse(status="success", data=listings, metadata={"enriched_count": enriched_count})

def notOrUnknown(s: Optional[str]) -> bool:
    return not s or s.lower() == "unknown"
