
import sqlite3
import structlog

logger = structlog.get_logger()

def upgrade_schema(db_path="data/listings.db"):
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    
    # 1. Market Indices Table (The Core Time Series)
    # Granularity: Monthly per Region
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_indices (
            id TEXT PRIMARY KEY,          -- Format: "region_id|YYYY-MM"
            region_id TEXT NOT NULL,      -- e.g. "madrid_centro" or "geohash_xyz"
            month_date DATE NOT NULL,     -- First day of the month (e.g. 2024-01-01)
            
            -- Price Metrics
            price_index_sqm FLOAT,        -- Median Price/m2 (The target)
            rent_index_sqm FLOAT,         -- Median Rent/m2
            
            -- Supply/Demand
            inventory_count INT,          -- Active listings at month end
            new_listings_count INT,       -- Added this month
            sold_count INT,               -- Removed/Sold this month
            absorption_rate FLOAT,        -- sold / inventory
            
            -- Liquidity / Health
            median_dom INT,               -- Days on Market
            price_cut_share FLOAT,        -- % of listings with price cuts
            volatility_3m FLOAT,          -- Standard deviation of price over last 3m
            
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Index for fast time-series retrieval
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_market_indices_region_date ON market_indices (region_id, month_date);")
    
    conn.commit()
    conn.close()
    logger.info("schema_upgraded", table="market_indices")

if __name__ == "__main__":
    upgrade_schema()
