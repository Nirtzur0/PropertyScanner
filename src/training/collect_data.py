"""
Batch Data Collector for Training Pipeline.
Scrapes property listings from Pisos.com to build training dataset.
Target: 1500+ listings to properly train 92k param model.
"""
import sqlite3
import time
import structlog
import json
from datetime import datetime
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


def save_listings_to_db(listings: List[Dict], db_path: str = "data/listings.db"):
    """Save normalized listings to SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Ensure table exists with correct schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            source_id TEXT,
            title TEXT,
            description TEXT,
            price REAL,
            city TEXT,
            bedrooms INTEGER,
            bathrooms INTEGER,
            surface_area_sqm REAL,
            floor INTEGER,
            lat REAL,
            lon REAL,
            image_urls TEXT,
            vlm_description TEXT,
            listed_at TEXT,
            updated_at TEXT
        )
    """)
    
    inserted = 0
    for listing in listings:
        try:
            # Extract city from nested location object
            location = listing.get("location") or {}
            city = location.get("city", "Unknown") if isinstance(location, dict) else "Unknown"
            lat = location.get("lat", 0) if isinstance(location, dict) else 0
            lon = location.get("lon", 0) if isinstance(location, dict) else 0
            
            # Handle image_urls - could be list of HttpUrl objects
            image_urls = listing.get("image_urls", [])
            if image_urls and hasattr(image_urls[0], '__str__'):
                image_urls = [str(u) for u in image_urls]
            
            listing_id = listing.get("id") or listing.get("external_id") or f"gen_{inserted}"
            external_id = listing.get("external_id") or listing_id
            url = listing.get("url", "")
            if hasattr(url, '__str__') and not isinstance(url, str):
                url = str(url)
            
            cursor.execute("""
                INSERT OR REPLACE INTO listings 
                (id, source_id, external_id, url, title, description, price, city, bedrooms, bathrooms,
                 surface_area_sqm, floor, lat, lon, image_urls, listed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing_id,
                listing.get("source_id", "pisos"),
                external_id,
                url,
                listing.get("title", ""),
                listing.get("description", ""),
                listing.get("price", 0),
                city,
                listing.get("bedrooms"),
                listing.get("bathrooms"),
                listing.get("surface_area_sqm"),
                listing.get("floor"),
                lat,
                lon,
                json.dumps(image_urls),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            inserted += 1
        except Exception as e:
            logger.warning("insert_failed", error=str(e), listing_id=listing.get("id", "unknown"))
    
    conn.commit()
    conn.close()
    return inserted


def collect_data(target_count: int = 1500, db_path: str = "data/listings.db"):
    """
    Collect property listings until target_count is reached.
    
    Args:
        target_count: Minimum number of listings to collect
        db_path: Path to SQLite database
    """
    config = {"source": "pisos_es", "max_pages": 3}
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
    parser.add_argument("--db", default="data/listings.db", help="Database path")
    
    args = parser.parse_args()
    
    total = collect_data(target_count=args.target, db_path=args.db)
    print(f"\nCollection complete! Total listings: {total}")
