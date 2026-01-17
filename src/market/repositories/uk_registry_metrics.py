from src.market.repositories.registry_metrics import RegistryMetricsRepository


class UKRegistryMetricsRepository(RegistryMetricsRepository):
    table_name = "uk_registry_metrics"
    provider_id = "uk_land_registry"
