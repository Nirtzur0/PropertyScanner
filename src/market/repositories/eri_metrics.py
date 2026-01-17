from src.market.repositories.registry_metrics import RegistryMetricsRepository


class ERIMetricsRepository(RegistryMetricsRepository):
    table_name = "eri_metrics"
    provider_id = "eri_es"
