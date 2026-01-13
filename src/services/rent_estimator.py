
from typing import Dict, List, Optional
import structlog
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing

logger = structlog.get_logger()

class RentEstimator:
    def __init__(self, db_url="sqlite:///data/listings.db"):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.rental_stats: Dict[str, float] = {} # city -> avg_price_sqm
        self._load_stats()
        
    def _load_stats(self):
        """
        Loads rental statistics from the database.
        Calculates average price/sqm for rental listings per city.
        """
        session = self.Session()
        try:
            # Query: Avg rent per sqm per city where listing_type='rent'
            rentals = session.query(DBListing).filter(
                DBListing.listing_type == "rent",
                DBListing.surface_area_sqm > 0,
                DBListing.price > 0
            ).all()

            # Collect all price_sqm values per city to process outliers
            city_data = {} # city -> list of price_sqm
            
            for r in rentals:
                if not r.city: continue
                city = r.city.lower().strip()
                if city not in city_data: city_data[city] = []
                
                # Basic sanity check (e.g. rent > 50 EUR and < 50k EUR)
                if r.price > 50 and r.price < 50000 and r.surface_area_sqm > 10:
                    psqm = r.price / r.surface_area_sqm
                    city_data[city].append(psqm)
            
            # Process statistics with IQR filtering
            import numpy as np
            
            for city, values in city_data.items():
                if len(values) < 3: # Need minimum samples
                    continue
                    
                # Calculate IQR
                q1 = np.percentile(values, 25)
                q3 = np.percentile(values, 75)
                iqr = q3 - q1
                
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                
                # Filter
                clean_values = [v for v in values if lower_bound <= v <= upper_bound]
                
                if clean_values:
                    # Avg of clean values
                    self.rental_stats[city] = sum(clean_values) / len(clean_values)
                    
            logger.info("Rental stats loaded", cities=len(self.rental_stats))
            
        except Exception as e:
            logger.error("Failed to load rental stats", error=str(e))
        finally:
            session.close()

    def estimate_rent(self, listing: CanonicalListing) -> Optional[float]:
        """
        Estimates monthly rent for a sales listing.
        """
        if not listing.location or not listing.location.city or not listing.surface_area_sqm:
            return None
            
        city = listing.location.city.lower().strip()
        avg_sqm = self.rental_stats.get(city)
        
        # Fallback to "madrid" if specific city not found?
        if not avg_sqm:
             # Try broader matching or just return None for now
             # Could fallback to total average
             return None
             
        estimated_rent = avg_sqm * listing.surface_area_sqm
        return round(estimated_rent, 2)
        
    def calculate_yield(self, price: float, monthly_rent: float) -> float:
        """
        Gross Annual Yield %
        """
        if price <= 0: return 0.0
        annual_rent = monthly_rent * 12
        return round((annual_rent / price) * 100, 2)
