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
def omi_sample_csv_clean(tmp_path):
    # Pre-processed OMI format for generic ingest (Aggregated by City)
    content = (
        "period,city,price_avg\n"
        "2023-01-01,MILANO,6000\n"
    )
    file_path = tmp_path / "omi_clean.csv"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

def test_registry_ingest__it_omi_csv__writes_canonical_series(omi_sample_csv_clean, tmp_path):
    # Arrange
    db_path = tmp_path / "it_omi.db"
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
    
    # Act
    service = RegistryIngestService(db_path=str(db_path), app_config=config)
    
    count = service.run()

    # Assert
    assert count == 1
    
    repo = ItalyRegistryMetricsRepository(db_url=service.db_url)
    df = repo.load_series("milano")
    assert not df.empty
    assert df.iloc[0]["price_sqm"] == 6000
