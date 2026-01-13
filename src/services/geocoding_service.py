import logging
from typing import Optional, Tuple
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

class GeocodingService:
    def __init__(self, user_agent: str = "property_scanner_bot"):
        self.geolocator = Nominatim(user_agent=user_agent)

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
