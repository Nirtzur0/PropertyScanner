from src.market.repositories.registry_metrics import RegistryMetricsRepository


class ERIMetricsRepository(RegistryMetricsRepository):
    provider_id = "eri_es"
