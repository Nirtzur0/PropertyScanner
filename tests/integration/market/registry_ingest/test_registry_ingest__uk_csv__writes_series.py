import pytest
import pandas as pd
from src.market.services.registry_ingest import RegistryIngestService
from src.platform.settings import AppConfig, RegistrySourceConfig
from src.market.repositories.uk_registry_metrics import UKRegistryMetricsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def uk_sample_csv(tmp_path):
    # UK Registry Metrics expects aggregated data (e.g. Price Paid Data aggregated by city/month)
    # columns: city, date, price, count
    content = (
        "city,transfer_date,price,count\n"
        "BRISTOL,2023-08-01,185000,10\n"
        "LONDON,2023-08-01,350000,25\n"
    )
    file_path = tmp_path / "uk_ppd_sample.csv"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

def test_registry_ingest__uk_land_registry_csv__writes_canonical_series(uk_sample_csv, tmp_path):
    # Arrange
    db_path = tmp_path / "uk_registry.db"
    source = RegistrySourceConfig(
        provider_id="uk_land_registry",
        country_code="GB",
        kind="csv",
        csv_paths=[uk_sample_csv],
        has_header=True,
        region_column="city",
        date_column="transfer_date",
        price_column="price", 
        txn_column="count",
        date_format="%Y-%m-%d"
    )
    
    config = AppConfig()
    config.registry.sources = [source]
    
    # Act
    service = RegistryIngestService(db_path=str(db_path), app_config=config)
    
    count = service.run()

    # Assert
    assert count == 2
    
    repo = UKRegistryMetricsRepository(db_url=service.db_url)
    repo.ensure_schema()
    
    df_bristol = repo.load_series("bristol") 
    assert not df_bristol.empty
    row = df_bristol.iloc[0]
    assert row["price_sqm"] == 185000.0
    assert row["txn_count"] == 10
