from src.market.repositories.registry_metrics import RegistryMetricsRepository


class ItalyRegistryMetricsRepository(RegistryMetricsRepository):
    table_name = "it_registry_metrics"
    provider_id = "it_omi_registry"
