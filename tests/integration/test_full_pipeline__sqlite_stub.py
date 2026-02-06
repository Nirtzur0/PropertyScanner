from __future__ import annotations

import sqlite3
from datetime import datetime

import pandas as pd
import pytest

from src.market.services.hedonic_index import HedonicIndexService
from src.market.services.market_indices import MarketIndexService
from src.valuation.services.forecasting import ForecastingService


@pytest.fixture
def pipeline_db_path(tmp_path) -> str:
    db_path = tmp_path / "pipeline.db"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE listings (
                id VARCHAR PRIMARY KEY,
                price FLOAT,
                surface_area_sqm FLOAT,
                city VARCHAR,
                geohash VARCHAR,
                listed_at DATETIME,
                updated_at DATETIME,
                status VARCHAR,
                listing_type VARCHAR,
                image_urls TEXT,
                vlm_description TEXT,
                bedrooms INT,
                bathrooms INT,
                has_elevator INT,
                floor INT
            )
            """
        )
        conn.execute(
            """
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
            """
        )
        conn.execute(
            "CREATE INDEX ix_market_indices_region_date ON market_indices (region_id, month_date)"
        )

        conn.execute(
            """
            CREATE TABLE macro_indicators (
                date DATE PRIMARY KEY,
                euribor_12m FLOAT,
                ecb_deposit_rate FLOAT,
                spain_cpi FLOAT,
                idealista_index_madrid FLOAT,
                idealista_index_national FLOAT
            )
            """
        )

        listings = [
            ("L1", 300000, 100, "madrid", "ezjmgu", "2024-01-01", "2024-01-15", "active", "sale", "[]", "desc", 2, 1, 1, 2),
            ("L2", 310000, 100, "madrid", "ezjmgu", "2024-02-01", "2024-02-15", "active", "sale", "[]", "desc", 2, 1, 1, 3),
            ("L3", 320000, 100, "madrid", "ezjmgu", "2024-03-01", "2024-03-15", "active", "sale", "[]", "desc", 2, 1, 1, 4),
            ("L4", 150000, 50, "madrid", "ezjmgu", "2024-01-01", "2024-01-15", "active", "sale", "[]", "desc", 1, 1, 0, 1),
            ("R1", 1500, 50, "madrid", "ezjmgu", "2024-01-01", "2024-01-15", "active", "rent", "[]", "desc", 1, 1, 0, 1),
        ]
        conn.executemany(
            """
            INSERT INTO listings (
                id, price, surface_area_sqm, city, geohash, listed_at, updated_at, status, listing_type,
                image_urls, vlm_description, bedrooms, bathrooms, has_elevator, floor
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            listings,
        )

        macros = [
            ("2024-01-01", 3.6, 3.5, 3.0, 2000, 1800),
            ("2024-02-01", 3.6, 3.5, 3.0, 2010, 1810),
            ("2024-03-01", 3.5, 3.5, 2.9, 2020, 1820),
        ]
        conn.executemany("INSERT INTO macro_indicators VALUES (?,?,?,?,?,?)", macros)

        conn.commit()
    finally:
        conn.close()

    return str(db_path)


@pytest.mark.integration
def test_market_indices__seeded_listings__creates_rows(pipeline_db_path):
    # Arrange
    service = MarketIndexService(db_path=pipeline_db_path)

    # Act
    service.recompute_indices(region_type="city")

    # Assert
    conn = sqlite3.connect(pipeline_db_path)
    try:
        indices = pd.read_sql("SELECT * FROM market_indices WHERE region_id='madrid'", conn)
    finally:
        conn.close()

    assert len(indices) >= 1


@pytest.mark.integration
def test_hedonic_index__seeded_listings__does_not_crash(pipeline_db_path):
    # Arrange
    service = HedonicIndexService(db_path=pipeline_db_path)

    # Act
    df = service.compute_index(region_name="madrid")

    # Assert
    # On minimal synthetic data, regression may be skipped, but the call should be safe.
    assert isinstance(df, pd.DataFrame)


@pytest.mark.integration
def test_forecasting_service__with_indices__returns_horizons(pipeline_db_path):
    # Arrange
    idx_svc = MarketIndexService(db_path=pipeline_db_path)
    idx_svc.recompute_indices(region_type="city")

    svc = ForecastingService(db_path=pipeline_db_path)

    # Act
    projections = svc.forecast_property(
        region_id="madrid",
        current_value=300000,
        horizons_months=[3, 6],
    )
    rent_projections = svc.forecast_rent(
        region_id="madrid",
        current_monthly_rent=1500,
        horizons_months=[3, 6],
    )

    # Assert
    assert len(projections) == 2
    assert len(rent_projections) == 2
