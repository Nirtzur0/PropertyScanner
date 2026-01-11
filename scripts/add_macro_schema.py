
import sqlite3
import structlog

logger = structlog.get_logger()

def add_macro_table(db_path="data/listings.db"):
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    
    # Macro Indicators Table (Exogenous Variables)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            date DATE PRIMARY KEY,        -- Monthly (YYYY-MM-01)
            
            -- Interest Rates
            euribor_12m FLOAT,            -- Key benchmark
            ecb_deposit_rate FLOAT,       -- ECB main rate
            mortgage_rate_avg FLOAT,      -- Avg commercial mortgage rate
            
            -- Economy
            spain_cpi FLOAT,              -- Inflation (Year-over-Year change)
            unemployment_rate FLOAT,      -- Spain Unemployment
            
            -- Market Benchmarks (Ground Truth)
            idealista_index_madrid FLOAT, -- Scraped benchmark
            idealista_index_national FLOAT,
            
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit()
    conn.close()
    logger.info("schema_upgraded", table="macro_indicators")

if __name__ == "__main__":
    add_macro_table()
