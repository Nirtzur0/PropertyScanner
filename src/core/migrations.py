
import sqlite3
import structlog
import pygeohash as pgh

logger = structlog.get_logger(__name__)

def run_migrations(db_path="data/listings.db"):
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
    
    # 6. Update macro_scenarios schema for SOTA V3 (cite-or-drop)
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
