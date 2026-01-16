
import sqlite3
import structlog
from src.core.config import DEFAULT_DB_PATH

logger = structlog.get_logger(__name__)

def run_migrations(db_path=str(DEFAULT_DB_PATH)):
    """
    Applies all schema changes in order. Idempotent check should be improved in production (using version table).
    """
    logger.info("migration_start")
    conn = sqlite3.connect(db_path, timeout=60.0)
    
    # 1. Market Indices
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_indices (
            id TEXT PRIMARY KEY, -- "region_id|month"
            region_id TEXT, -- "city:madrid" or "gh6:ezjmgu"
            month_date DATE,
            price_index_sqm FLOAT,
            rent_index_sqm FLOAT,
            inventory_count INT,
            new_listings_count INT,
            sold_count INT,
            absorption_rate FLOAT,
            median_dom INT,
            price_cut_share FLOAT,
            volatility_3m FLOAT,
            updated_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_market_indices_region_date ON market_indices (region_id, month_date)")
    
    # 2. Macro Indicators
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            date DATE PRIMARY KEY,        -- Monthly (YYYY-MM-01)
            euribor_12m FLOAT,            -- Key benchmark
            ecb_deposit_rate FLOAT,       -- ECB main rate
            mortgage_rate_avg FLOAT,      -- Avg commercial mortgage rate
            spain_cpi FLOAT,              -- Inflation
            unemployment_rate FLOAT,      -- Spain Unemployment
            idealista_index_madrid FLOAT, -- Scraped benchmark
            idealista_index_national FLOAT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 3. Macro Scenarios (LLM)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            source_url TEXT,
            scenario_name TEXT, -- "base", "optimistic", "pessimistic"
            euribor_12m_forecast FLOAT,
            inflation_forecast FLOAT,
            gdp_growth_forecast FLOAT,
            confidence_text TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 4. Geohash
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN geohash VARCHAR")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_listings_geohash ON listings (geohash)")
        logger.info("migration_geohash_added")
    except Exception:
        pass

    # 4b. Listing type (sale vs rent) for downstream indices/forecasting
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN listing_type TEXT DEFAULT 'sale'")
        logger.info("migration_listing_type_added")
        try:
            # Best-effort backfill from URL patterns.
            conn.execute(
                """
                UPDATE listings
                SET listing_type = 'rent'
                WHERE (
                    listing_type IS NULL OR listing_type = '' OR listing_type = 'sale'
                ) AND (
                    url LIKE '%/alquiler/%' OR url LIKE '%/rent/%' OR url LIKE '%/rental/%'
                )
                """
            )
        except Exception:
            pass
    except Exception:
        pass

    # 4c. Location metadata (zip, country)
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN zip_code TEXT")
        logger.info("migration_zip_code_added")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE listings ADD COLUMN country TEXT")
        logger.info("migration_country_added")
    except Exception:
        pass

    # 4d. Plot area + image embeddings
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN plot_area_sqm FLOAT")
        logger.info("migration_plot_area_added")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE listings ADD COLUMN image_embeddings JSON")
        logger.info("migration_image_embeddings_added")
    except Exception:
        pass
    
    # 5. Hedonic Indices (SOTA V3)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hedonic_indices (
            id TEXT PRIMARY KEY,
            region_id TEXT,
            month_date DATE,
            hedonic_index_sqm FLOAT,
            raw_median_sqm FLOAT,
            r_squared FLOAT,
            n_observations INT,
            coefficients TEXT,
            updated_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_hedonic_region_date ON hedonic_indices (region_id, month_date)")

    # 5b. Area Intelligence (used by forecasting)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS area_intelligence (
            area_id TEXT PRIMARY KEY,
            last_updated DATETIME,
            sentiment_score FLOAT,
            future_development_score FLOAT,
            news_summary TEXT,
            top_keywords TEXT,
            source_urls TEXT
        )
    """)

    # 6. ERI (Registral) Metrics
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eri_metrics (
            id TEXT PRIMARY KEY, -- "region_id|period_date"
            region_id TEXT,
            period_date DATE,
            txn_count INT,
            mortgage_count INT,
            price_sqm FLOAT,
            price_sqm_yoy FLOAT,
            price_sqm_qoq FLOAT,
            updated_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_eri_region_date ON eri_metrics (region_id, period_date)")
    
    # 7. Update macro_scenarios schema for SOTA V3 (cite-or-drop)
    try:
        conn.execute("ALTER TABLE macro_scenarios ADD COLUMN source_id TEXT")
        conn.execute("ALTER TABLE macro_scenarios ADD COLUMN horizon_year INT")
        conn.execute("ALTER TABLE macro_scenarios ADD COLUMN retrieved_at DATETIME")
    except Exception:
        pass
        
    conn.commit()
    conn.close()
    logger.info("migration_complete")

if __name__ == "__main__":
    run_migrations()
