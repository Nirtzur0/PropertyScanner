import logging
from typing import Dict, Optional, Tuple
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

class GeocodingService:
    def __init__(self, user_agent: str = "property_scanner_bot"):
        import ssl
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        self.geolocator = Nominatim(user_agent=user_agent, ssl_context=ctx)

    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Geocodes an address string to (lat, lon).
        Returns None if not found or error.
        """
        try:
            location = self.geolocator.geocode(address, timeout=5)
            if location:
                return (location.latitude, location.longitude)
            else:
                return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(f"Geocoding service error for address '{address}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error geocoding '{address}': {e}")
            return None

    def geocode_details(self, address: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Geocodes an address and returns basic details including country code.
        """
        try:
            location = self.geolocator.geocode(address, timeout=5, addressdetails=True)
            if not location:
                return None

            raw = location.raw or {}
            address_data = raw.get("address", {}) if isinstance(raw, dict) else {}
            country_code = address_data.get("country_code")
            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "country": address_data.get("country"),
                "country_code": country_code.upper() if country_code else None,
            }
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(f"Geocoding service error for address '{address}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error geocoding '{address}': {e}")
            return None
