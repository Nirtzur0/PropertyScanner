
import os
import pytest
from src.market.services.registry_ingest import RegistryIngestService
from src.platform.settings import AppConfig, RegistrySourceConfig
from src.market.repositories.it_registry_metrics import ItalyRegistryMetricsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def omi_sample_csv(tmp_path):
    # OMI Format Mimic (Simplified)
    # Anno;Semestre;Provincia;Comunale;Zone;Descr;Min;Max
    content = (
        "year,semester,province,city,zone,desc,min,max\n"
        "2023,1,MI,MILANO,B1,CENTRO,5000,7000\n"
        "2023,1,MI,MILANO,D2,PERIFERIA,2000,3000\n"
    )
    file_path = tmp_path / "omi_sample.csv"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

@pytest.fixture
def omi_sample_config(omi_sample_csv):
    """
    Needs a wrapper to convert year/semester to period_date for the generic ingestor,
    OR we rely on the ingestor's flexible date parsing if we format it right.
    Generic ingestor expects a single date column.
    We'll construct a CSV where we pre-merge year/sem into a period column for testing.
    """
    pass

@pytest.fixture
def omi_sample_csv_clean(tmp_path):
    # Pre-processed OMI format for generic ingest (Aggregated by City)
    content = (
        "period,city,price_avg\n"
        "2023-01-01,MILANO,6000\n"
    )
    file_path = tmp_path / "omi_clean.csv"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

def test_it_omi_ingest_real_structure(omi_sample_csv_clean, test_db_path):
    source = RegistrySourceConfig(
        provider_id="it_omi_registry",
        country_code="IT",
        kind="csv",
        csv_paths=[omi_sample_csv_clean],
        has_header=True,
        region_column="city",
        date_column="period",
        price_column="price_avg",
    )
    
    config = AppConfig()
    config.registry.sources = [source]
    
    service = RegistryIngestService(db_path=test_db_path, app_config=config)
    
    count = service.run()
    assert count == 1
    
    repo = ItalyRegistryMetricsRepository(db_url=service.db_url)
    df = repo.load_series("milano")
    assert not df.empty
    assert df.iloc[0]["price_sqm"] == 6000
