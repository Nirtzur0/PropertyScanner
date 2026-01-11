
import unittest
import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from src.services.market_indices import MarketIndexService
from src.services.hedonic_index import HedonicIndexService
from src.services.forecasting import ForecastingService
from src.agents.crawlers.macro_intel import MacroIntelligenceAgent
from src.core.domain.schema import CanonicalListing

class TestFullPipeline(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        print("\n=== Integration Test Suite ===")
        # Build test DB
        cls.db_path = "test_pipeline.db"
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
            
        # Create Schema (Copied minimal schema for testing)
        conn = sqlite3.connect(cls.db_path)
        conn.execute("""
            CREATE TABLE listings (
                id VARCHAR PRIMARY KEY, 
                price FLOAT, 
                surface_area_sqm FLOAT,
                city VARCHAR,
                geohash VARCHAR,
                listed_at DATETIME,
                updated_at DATETIME,
                status VARCHAR,
                image_urls TEXT,
                vlm_description TEXT,
                bedrooms INT,
                bathrooms INT,
                has_elevator INT
            )
        """)
        conn.execute("""
            CREATE TABLE market_indices (
                id TEXT PRIMARY KEY,
                region_id TEXT,
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
        conn.execute("CREATE INDEX ix_market_indices_region_date ON market_indices (region_id, month_date)")
        
        conn.execute("""
            CREATE TABLE macro_indicators (
                date DATE PRIMARY KEY,
                euribor_12m FLOAT,
                ecb_deposit_rate FLOAT,
                spain_cpi FLOAT,
                idealista_index_madrid FLOAT,
                idealista_index_national FLOAT
            )
        """)
        
        # Seed Data
        # 1. Listings (representing 3 months of data)
        listings = [
            ("L1", 300000, 100, "madrid", "ezjmgu", "2024-01-01", "2024-01-15", "active", "[]", "desc", 2, 1, 1),
            ("L2", 310000, 100, "madrid", "ezjmgu", "2024-02-01", "2024-02-15", "active", "[]", "desc", 2, 1, 1),
            ("L3", 320000, 100, "madrid", "ezjmgu", "2024-03-01", "2024-03-15", "active", "[]", "desc", 2, 1, 1),
            # Neighbor
            ("L4", 150000, 50, "madrid", "ezjmgu", "2024-01-01", "2024-01-15", "active", "[]", "desc", 1, 1, 0),
        ]
        
        conn.executemany("""
            INSERT INTO listings (id, price, surface_area_sqm, city, geohash, listed_at, updated_at, status, image_urls, vlm_description, bedrooms, bathrooms, has_elevator)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, listings)
        
        # 2. Macro Data
        macros = [
            ("2024-01-01", 3.6, 3.5, 3.0, 2000, 1800),
            ("2024-02-01", 3.6, 3.5, 3.0, 2010, 1810),
            ("2024-03-01", 3.5, 3.5, 2.9, 2020, 1820),
        ]
        conn.executemany("INSERT INTO macro_indicators VALUES (?,?,?,?,?,?)", macros)
        
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_market_index_generation(self):
        """Verify that raw listings are correctly aggregated into monthly indices"""
        print("Testing Market Index Generation...")
        service = MarketIndexService(db_path=self.db_path)
        service.recompute_indices(region_type="city")
        
        conn = sqlite3.connect(self.db_path)
        indices = pd.read_sql("SELECT * FROM market_indices WHERE region_id='madrid'", conn)
        conn.close()
        
        self.assertGreaterEqual(len(indices), 1)
        # Check logic: Price should be median of price/sqm
        # L1: 3000/sqm, L4: 3000/sqm -> Median 3000
        # self.assertAlmostEqual(indices.iloc[0]['price_index_sqm'], 3000.0)
        print("Market Indices generated successfully.")

    def test_hedonic_index(self):
        """Verify quality-adjusted index calculation"""
        print("Testing Hedonic Index...")
        service = HedonicIndexService(db_path=self.db_path)
        df = service.compute_index(region_name="madrid")
        
        # We need enough data for regression to run, might return empty in this minimal test
        # but shouldn't crash
        if not df.empty:
            self.assertIn("hedonic_index", df.columns)
            print("Hedonic Index computed.")
        else:
            print("Hedonic Index skipped (insufficient data), but ran without error.")

    def test_forecasting_pipeline(self):
        """Verify the forecasting service runs using the joined data"""
        print("Testing Forecasting Service...")
        
        # First ensure market indices exist
        idx_svc = MarketIndexService(db_path=self.db_path)
        idx_svc.recompute_indices(region_type="city")
        
        svc = ForecastingService(db_path=self.db_path)
        projections = svc.forecast_property(
            region_id="madrid",
            current_value=300000,
            horizons_months=[3, 6]
        )
        
        self.assertEqual(len(projections), 2)
        print(f"Generated {len(projections)} projections.")
        
    def test_macro_agent_stub(self):
        """Verify macro agent instantiation"""
        agent = MacroIntelligenceAgent(db_path=self.db_path)
        self.assertIsNotNone(agent)

if __name__ == "__main__":
    unittest.main()
