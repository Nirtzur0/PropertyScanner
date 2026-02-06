
import os
import pytest
from src.market.services.registry_ingest import RegistryIngestService
from src.platform.settings import AppConfig, RegistrySourceConfig
from src.market.repositories.eri_metrics import ERIMetricsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def ine_sample_csv(tmp_path):
    # INE IPV Format Mimic (Simplified)
    # Periodo;Region;Indice
    content = (
        "Periodo;Region;Indice\n"
        "2023T3;Total Nacional;140.5\n"
        "2023T3;Madrid;150.2\n"
        "2023T3;Cataluña;145.8\n"
    )
    file_path = tmp_path / "ine_ipv_sample.csv"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

def test_eri_es_ingest_real_structure(ine_sample_csv, test_db_path):
    """
    Test ERI (Spain) ingestion using a structure mimicking INE IPV data.
    """
    source = RegistrySourceConfig(
        provider_id="eri_es",
        country_code="ES",
        kind="csv",
        csv_paths=[ine_sample_csv],
        has_header=True,
        delimiter=";", # INE often uses semicolon
        region_column="Region",
        date_column="Periodo",
        price_column="Indice", 
    )
    
    config = AppConfig()
    config.registry.sources = [source]
    
    service = RegistryIngestService(db_path=test_db_path, app_config=config)
    
    count = service.run()
    assert count == 3
    
    repo = ERIMetricsRepository(db_url=service.db_url)
    df = repo.load_series("madrid")
    assert not df.empty
    assert df.iloc[0]["price_sqm"] == 150.2
