"""
Batch Data Collector for Training Pipeline.
Scrapes property listings from Pisos.com to build training dataset.
Target: 1500+ listings to properly train 92k param model.
"""
import time
import structlog
from src.core.config import DEFAULT_DB_PATH
from src.services.feature_sanitizer import sanitize_listing_dict
from src.services.storage import StorageService
from src.services.listing_augmenter import ListingAugmentor
from src.core.domain.schema import CanonicalListing
from typing import List, Dict

from src.agents.crawlers.pisos import PisosCrawlerAgent
from src.agents.processors.pisos import PisosNormalizerAgent
from src.utils.compliance import ComplianceManager

logger = structlog.get_logger()

# Spanish cities with their Pisos.com search URLs
# Each URL returns ~30-50 listings per page - expanded for 2000+ listings
CITY_URLS = [
    # Madrid - multiple price ranges and areas
    "https://www.pisos.com/venta/pisos-madrid/",
    "https://www.pisos.com/venta/pisos-madrid/featurestag-amueblado/",
    "https://www.pisos.com/venta/pisos-madrid/0-200000_euros/",
    "https://www.pisos.com/venta/pisos-madrid/200000-400000_euros/",
    "https://www.pisos.com/venta/pisos-madrid/400000-600000_euros/",
    "https://www.pisos.com/venta/pisos-madrid/600000-1000000_euros/",
    "https://www.pisos.com/venta/pisos-madrid/1000000-2000000_euros/",
    "https://www.pisos.com/venta/casas-madrid/",
    # Barcelona - expanded
    "https://www.pisos.com/venta/pisos-barcelona/",
    "https://www.pisos.com/venta/pisos-barcelona/0-200000_euros/",
    "https://www.pisos.com/venta/pisos-barcelona/200000-400000_euros/",
    "https://www.pisos.com/venta/pisos-barcelona/400000-800000_euros/",
    "https://www.pisos.com/venta/pisos-barcelona/800000-1500000_euros/",
    "https://www.pisos.com/venta/casas-barcelona/",
    # Valencia - expanded
    "https://www.pisos.com/venta/pisos-valencia/",
    "https://www.pisos.com/venta/pisos-valencia/0-150000_euros/",
    "https://www.pisos.com/venta/pisos-valencia/150000-300000_euros/",
    "https://www.pisos.com/venta/pisos-valencia/300000-500000_euros/",
    "https://www.pisos.com/venta/casas-valencia/",
    # Sevilla - expanded
    "https://www.pisos.com/venta/pisos-sevilla/",
    "https://www.pisos.com/venta/pisos-sevilla/0-150000_euros/",
    "https://www.pisos.com/venta/pisos-sevilla/150000-300000_euros/",
    "https://www.pisos.com/venta/pisos-sevilla/300000-500000_euros/",
    "https://www.pisos.com/venta/casas-sevilla/",
    # Malaga - expanded
    "https://www.pisos.com/venta/pisos-malaga/",
    "https://www.pisos.com/venta/pisos-malaga/0-200000_euros/",
    "https://www.pisos.com/venta/pisos-malaga/200000-500000_euros/",
    "https://www.pisos.com/venta/pisos-malaga/500000-1000000_euros/",
    "https://www.pisos.com/venta/casas-malaga/",
    # Bilbao
    "https://www.pisos.com/venta/pisos-bilbao/",
    "https://www.pisos.com/venta/pisos-bilbao/0-200000_euros/",
    "https://www.pisos.com/venta/pisos-bilbao/200000-400000_euros/",
    "https://www.pisos.com/venta/casas-bilbao/",
    # Zaragoza
    "https://www.pisos.com/venta/pisos-zaragoza/",
    "https://www.pisos.com/venta/pisos-zaragoza/0-150000_euros/",
    "https://www.pisos.com/venta/pisos-zaragoza/150000-300000_euros/",
    "https://www.pisos.com/venta/casas-zaragoza/",
    # Alicante
    "https://www.pisos.com/venta/pisos-alicante/",
    "https://www.pisos.com/venta/pisos-alicante/0-150000_euros/",
    "https://www.pisos.com/venta/pisos-alicante/150000-300000_euros/",
    "https://www.pisos.com/venta/casas-alicante/",
    # Murcia
    "https://www.pisos.com/venta/pisos-murcia/",
    "https://www.pisos.com/venta/pisos-murcia/0-150000_euros/",
    "https://www.pisos.com/venta/casas-murcia/",
    # Palma de Mallorca
    "https://www.pisos.com/venta/pisos-palma_de_mallorca/",
    "https://www.pisos.com/venta/pisos-palma_de_mallorca/0-300000_euros/",
    "https://www.pisos.com/venta/pisos-palma_de_mallorca/300000-600000_euros/",
    # Las Palmas
    "https://www.pisos.com/venta/pisos-las_palmas_de_gran_canaria/",
    "https://www.pisos.com/venta/pisos-las_palmas_de_gran_canaria/0-200000_euros/",
    # Cordoba
    "https://www.pisos.com/venta/pisos-cordoba/",
    "https://www.pisos.com/venta/pisos-cordoba/0-150000_euros/",
    # Granada
    "https://www.pisos.com/venta/pisos-granada/",
    "https://www.pisos.com/venta/pisos-granada/0-150000_euros/",
    # San Sebastian
    "https://www.pisos.com/venta/pisos-san_sebastian/",
    "https://www.pisos.com/venta/pisos-san_sebastian/0-400000_euros/",
    # Santander
    "https://www.pisos.com/venta/pisos-santander/",
    "https://www.pisos.com/venta/pisos-santander/0-200000_euros/",
    # Valladolid
    "https://www.pisos.com/venta/pisos-valladolid/",
    "https://www.pisos.com/venta/pisos-valladolid/0-150000_euros/",
]


def save_listings_to_db(listings: List[Dict], db_path: str = str(DEFAULT_DB_PATH)):
    """Save normalized listings to SQLite database."""
    db_path_str = str(db_path)
    db_url = db_path_str if db_path_str.startswith("sqlite:") else f"sqlite:///{db_path_str}"
    storage = StorageService(db_url=db_url)
    augmenter = ListingAugmentor(db_url=db_url)

    canonical_listings: List[CanonicalListing] = []
    for listing in listings:
        try:
            listing = sanitize_listing_dict(listing)
            if isinstance(listing, CanonicalListing):
                canonical = listing
            else:
                canonical = CanonicalListing(**listing)
            canonical_listings.append(canonical)
        except Exception as e:
            logger.warning("canonicalize_failed", error=str(e), listing_id=listing.get("id", "unknown"))

    canonical_listings = augmenter.augment_listings(canonical_listings)
    return storage.save_listings(canonical_listings)


def collect_data(target_count: int = 1500, db_path: str = str(DEFAULT_DB_PATH)):
    """
    Collect property listings until target_count is reached.
    
    Args:
        target_count: Minimum number of listings to collect
        db_path: Path to SQLite database
    """
    config = {"source": "pisos", "max_pages": 3}
    compliance = ComplianceManager(user_agent="PropertyScanner/1.0 Training Data Collection")
    
    crawler = PisosCrawlerAgent(config, compliance)
    normalizer = PisosNormalizerAgent()
    
    total_collected = 0
    
    logger.info("collection_started", target=target_count, num_urls=len(CITY_URLS))
    
    for url in CITY_URLS:
        if total_collected >= target_count:
            break
            
        logger.info("crawling_url", url=url[:60])
        
        try:
            # Crawl
            response = crawler.run({"start_url": url})
            
            if response.status != "success" or not response.data:
                logger.warning("crawl_failed", url=url[:60], errors=response.errors)
                continue
            
            raw_listings = response.data
            logger.info("raw_listings_fetched", count=len(raw_listings))
            
            # Normalize
            norm_response = normalizer.run({"raw_listings": raw_listings})
            
            if norm_response.status != "success" or not norm_response.data:
                logger.warning("normalize_failed", errors=norm_response.errors)
                continue
            
            canonical_listings = norm_response.data
            
            # Convert to dict format for DB
            listing_dicts = []
            for listing in canonical_listings:
                if hasattr(listing, "model_dump"):
                    listing_dicts.append(listing.model_dump())
                elif hasattr(listing, "dict"):
                    listing_dicts.append(listing.dict())
                else:
                    listing_dicts.append(listing)
            
            # Save to DB
            inserted = save_listings_to_db(listing_dicts, db_path)
            total_collected += inserted
            
            logger.info("batch_saved", 
                       inserted=inserted, 
                       total=total_collected,
                       progress=f"{total_collected}/{target_count}")
            
            # Rate limiting
            time.sleep(3)
            
        except Exception as e:
            logger.error("collection_error", url=url[:60], error=str(e))
            time.sleep(5)
    
    logger.info("collection_complete", total=total_collected)
    return total_collected


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Collect training data from Pisos.com")
    parser.add_argument("--target", type=int, default=1500, help="Target number of listings")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Database path")
    
    args = parser.parse_args()
    
    total = collect_data(target_count=args.target, db_path=args.db)
    print(f"\nCollection complete! Total listings: {total}")
