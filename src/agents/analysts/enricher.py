from typing import Any, Dict, List, Optional
import requests
import structlog
from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.utils.compliance import ComplianceManager
from src.services.enrichment_service import EnrichmentService

class EnrichmentAgent(BaseAgent):
    """
    Enriches listings with Geolocation data using Hybrid Strategy:
    - Forward: Photon API (Address -> Coords)
    - Reverse: Offline EnrichmentService (Coords -> City)
    """
    def __init__(self, compliance: ComplianceManager):
        config = {
            "base_url": "https://photon.komoot.io/api/",
            "period_seconds": 0.5 
        }
        super().__init__(name="EnrichmentAgent", config=config)
        self.compliance = compliance
        self.headers = {
            "User-Agent": "PropertyScanner/1.0"
        }
        # Initialize offline service
        self.offline_service = EnrichmentService()

    def _geocode(self, query: str) -> Optional[GeoLocation]:
        if not query:
            return None
        
        # Photon API
        url = self.config["base_url"]
        
        # Rate Limiting check
        api_domain_url = "https://photon.komoot.io/"
        if not self.compliance.check_and_wait(api_domain_url, rate_limit_seconds=self.config["period_seconds"]):
             self.logger.warning("rate_limit_blocked", url=api_domain_url)
             return None

        params = {
            "q": query,
            "limit": 1
        }
        
        try:
            resp = requests.get(url, params=params, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if features:
                    feat = features[0]
                    props = feat.get("properties", {})
                    coords = feat.get("geometry", {}).get("coordinates", [])
                    
                    if len(coords) == 2:
                        lon, lat = coords # GeoJSON is [lon, lat]
                        
                        # Get city using offline service as fallback or from props
                        city = props.get("city") or props.get("town") or props.get("village")
                        if not city:
                            city = self.offline_service.get_city(lat, lon)

                        return GeoLocation(
                            lat=float(lat),
                            lon=float(lon),
                            address_full=props.get("name", query), # Photon name is often just the POI name
                            city=city or "Unknown",
                            country=props.get("country", "Spain")
                        )
        except Exception as e:
            self.logger.error("geocoding_failed", query=query, error=str(e))
            
        return None

    def _reverse_geocode(self, lat: float, lon: float) -> Optional[GeoLocation]:
        """
        Use offline EnrichmentService for purely reverse geocoding (Coords -> City).
        """
        try:
            city = self.offline_service.get_city(lat, lon)
            if city and city != "Unknown":
                return GeoLocation(
                    lat=lat,
                    lon=lon,
                    address_full="", # We don't get full address from reverse_geocoder, just admin levels
                    city=city,
                    country="Spain" # reverse_geocoder has 'cc' but we can assume context or fetch if needed
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
                    if geo and geo.city != "Unknown":
                        listing.location.city = geo.city
                        enriched_count += 1
                continue
            
            # Case A.1: Has Location object but No Lat/Lon, try Geocoding from Address
            if listing.location and listing.location.address_full:
                 coords = self.offline_service.geocoding_service.geocode_address(listing.location.address_full)
                 if coords:
                     lat, lon = coords
                     listing.location.lat = lat
                     listing.location.lon = lon
                     enriched_count += 1
                     self.logger.info("geocoded_from_address", address=listing.location.address_full, lat=lat, lon=lon)
                     
                     # Chain: Fill City if missing
                     if notOrUnknown(listing.location.city):
                         city = self.offline_service.get_city(lat, lon)
                         if city and city != "Unknown":
                             listing.location.city = city
                             
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
