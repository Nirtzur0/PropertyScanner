
import os
import pytest
from src.market.services.registry_ingest import RegistryIngestService
from src.platform.settings import AppConfig, RegistrySourceConfig
from src.market.repositories.ine_ipv import IneIpvRepository

@pytest.fixture
def ine_ipv_sample_csv(tmp_path):
    # Mimic INE IPV CSV format (usually columns: Periodo; Comunidades...; Índice)
    content = (
        "Periodo;Region;Indice\n"
        "2023T3;Total Nacional;140.5\n"
        "2023T3;Madrid;150.2\n"
        "2023T2;Madrid;148.1\n"
    )
    file_path = tmp_path / "ine_ipv_sample.csv"
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

def test_ine_ipv_ingest_real(ine_ipv_sample_csv, test_db_path):
    """
    Test dedicated INE IPV ingestion path.
    """
    source = RegistrySourceConfig(
        provider_id="ine_ipv", # Special provider ID triggering specialized logic
        country_code="ES",
        kind="csv",
        csv_paths=[ine_ipv_sample_csv],
        has_header=True,
        delimiter=";",
        region_column="Region",
        date_column="Periodo",
        price_column="Indice"
    )
    
    config = AppConfig()
    config.registry.sources = [source]
    
    service = RegistryIngestService(db_path=test_db_path, app_config=config)
    
    count = service.run()
    assert count == 3
    
    repo = IneIpvRepository(db_url=service.db_url)
    repo.ensure_schema()
    
    val, _ = repo.fetch_latest_metric("madrid", housing_type="general", metric="index")
    # Our mocked ingest logic stores it as "index" type by default
    assert val == "2023Q3"
    
    # Check value fetch manually to be sure
    # fetch_latest_metric returns (period, value)
    period, value = repo.fetch_latest_metric("madrid", metric="index")
    assert value == 150.2
