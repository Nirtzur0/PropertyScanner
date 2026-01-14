import reverse_geocoder as rg
import pandas as pd
import logging
import geolib.geohash
from src.core.domain.models import DBListing
from src.services.geocoding_service import GeocodingService

logger = logging.getLogger(__name__)

class EnrichmentService:
    """
    Service to enrich listings with additional data.
    Currently focuses on city information based on latitude and longitude using offline reverse geocoding.
    Designed to be part of the main data ingestion/storage flow.
    """
    
    def __init__(self):
        # Trigger loading of the data on init to avoid latency later
        # passing a dummy coordinate to force load
        try:
            rg.search((0, 0), mode=1)
            logger.info("EnrichmentService initialized: reverse_geocoder data loaded.")
        except Exception as e:
            logger.error(f"Failed to initialize reverse_geocoder: {e}")
            
        self.geocoding_service = GeocodingService()

    def get_city(self, lat: float, lon: float) -> str:
        """
        Get the city name for a given latitude and longitude.
        Returns 'Unknown' if valid coordinates are not provided or lookup fails.
        """
        if not lat or not lon or (lat == 0 and lon == 0):
            return "Unknown"
            
        try:
            results = rg.search((lat, lon), mode=1)
            if results:
                # rg returns a list of OrderedDicts. We want the 'name' (city) or 'admin1'/'admin2' fallback
                # Sometimes 'name' is just a neighborhood or very obscure
                city_name = results[0].get('name', '')
                admin1 = results[0].get('admin1', '')
                
                # Filter out generic country names if they somehow appear or very generic placeholders
                if city_name.lower() in ["spain", "españa", "unknown"]:
                    if admin1: return admin1
                    return "Unknown"
                    
                return city_name
        except Exception as e:
            logger.warning(f"Error resolving city for {lat}, {lon}: {e}")
            
        return "Unknown"

    def enrich_db_listing(self, listing: DBListing) -> bool:
        """
        Enriches a DBListing object in-place before persistence.
        Returns True if enriched (data was missing and is now found), False otherwise.
        """
        enriched = False
        
        # 1. Geocoding (if lat/lon missing)
        if not listing.lat or not listing.lon or (listing.lat == 0 and listing.lon == 0):
            # Try to geocode from address
            if listing.address_full:
                coords = self.geocoding_service.geocode_address(listing.address_full)
                if coords:
                    listing.lat, listing.lon = coords
                    enriched = True
                    logger.info(f"Geocoded address '{listing.address_full}' to ({listing.lat}, {listing.lon})")
            
            # Fallback: Try from Title if address failed
            if (not listing.lat or not listing.lon) and listing.title:
                 # Simple heuristic: remove common prefixes
                query = listing.title
                remove_prefixes = ["Piso en ", "Ático en ", "Chalet en ", "Estudio en ", "Venta de piso en "]
                for p in remove_prefixes:
                    query = query.replace(p, "")
                
                # Avoid geocoding very short queries or generic ones if possible, but GeocodingService handles most
                coords = self.geocoding_service.geocode_address(query)
                if coords:
                    listing.lat, listing.lon = coords
                    enriched = True
                    logger.info(f"Geocoded title '{query}' to ({listing.lat}, {listing.lon})")

        # 2. City Enrichment
        # Only enrich if (lat/lon exist) AND (city is missing OR 'Unknown')
        if listing.lat and listing.lon:
            if not listing.city or listing.city == "Unknown":
                city = self.get_city(listing.lat, listing.lon)
                if city and city != "Unknown":
                    listing.city = city
                    enriched = True
        
        # 3. Geohash Generation
        if listing.lat and listing.lon and not listing.geohash:
            try:
                # geolib.geohash.encode(lat, lon, precision)
                listing.geohash = geolib.geohash.encode(listing.lat, listing.lon, 9)
                enriched = True
            except Exception as e:
                logger.warning(f"Failed to generate geohash for {listing.lat}, {listing.lon}: {e}")

        return enriched

    def enrich_dataframe(self, df: pd.DataFrame, lat_col: str = 'lat', lon_col: str = 'lon', city_col: str = 'City') -> pd.DataFrame:
        """
        Enriches a pandas DataFrame with a city column if missing.
        Useful for ad-hoc analysis or repairing old data.
        """
        if df.empty or lat_col not in df.columns or lon_col not in df.columns:
            return df

        def get_city_wrapper(row):
            if city_col in row and row[city_col] and row[city_col] != "Unknown":
                return row[city_col]
            return self.get_city(row[lat_col], row[lon_col])

        df[city_col] = df.apply(get_city_wrapper, axis=1)
        return df
