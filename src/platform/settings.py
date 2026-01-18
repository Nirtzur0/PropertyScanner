from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.platform.config import (
    CALIBRATION_PATH,
    CONFIG_DIR,
    DATA_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_DB_URL,
    FUSION_CONFIG_PATH,
    FUSION_MODEL_PATH,
    MODELS_DIR,
    SNAPSHOTS_DIR,
    TFT_MODEL_PATH,
    TRANSACTIONS_PATH,
    VECTOR_INDEX_PATH,
    VECTOR_METADATA_PATH,
)


class BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PathsConfig(BaseConfigModel):
    data_dir: Path = Field(default=DATA_DIR)
    models_dir: Path = Field(default=MODELS_DIR)
    config_dir: Path = Field(default=CONFIG_DIR)
    snapshots_dir: Path = Field(default=SNAPSHOTS_DIR)

    default_db_path: Path = Field(default=DEFAULT_DB_PATH)
    default_db_url: str = Field(default=DEFAULT_DB_URL)

    vector_index_path: Path = Field(default=VECTOR_INDEX_PATH)
    vector_metadata_path: Path = Field(default=VECTOR_METADATA_PATH)

    fusion_model_path: Path = Field(default=FUSION_MODEL_PATH)
    fusion_config_path: Path = Field(default=FUSION_CONFIG_PATH)
    calibration_path: Path = Field(default=CALIBRATION_PATH)
    tft_model_path: Path = Field(default=TFT_MODEL_PATH)

    transactions_path: Path = Field(default=TRANSACTIONS_PATH)


class RateLimitConfig(BaseConfigModel):
    requests: int = 1
    period_seconds: float = 10.0


class ComplianceConfig(BaseConfigModel):
    robots_txt_url: Optional[str] = ""
    allowed_paths: List[str] = Field(default_factory=list)
    disallowed_paths: List[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    id: str
    name: Optional[str] = None
    base_url: Optional[str] = None
    type: str = "html"
    enabled: bool = True
    countries: List[str] = Field(default_factory=list)

    search_path_template: Optional[str] = None
    search_url_template: Optional[str] = None
    listing_url_template: Optional[str] = None

    user_agent: Optional[str] = None
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)


class SourcesConfig(BaseConfigModel):
    sources: List[SourceConfig] = Field(default_factory=list)


class RegistrySourceConfig(BaseConfigModel):
    provider_id: str
    country_code: str
    enabled: bool = True
    kind: str = "csv"
    csv_paths: List[str] = Field(default_factory=list)
    csv_urls: List[str] = Field(default_factory=list)
    delimiter: str = ","
    encoding: str = "utf-8"
    date_format: Optional[str] = None
    region_column: str = "region"
    date_column: str = "period_date"
    txn_column: Optional[str] = "txn_count"
    mortgage_column: Optional[str] = "mortgage_count"
    price_column: Optional[str] = "price_sqm"
    price_yoy_column: Optional[str] = None
    price_qoq_column: Optional[str] = None
    has_header: bool = True
    column_names: List[str] = Field(default_factory=list)


class RegistryConfig(BaseConfigModel):
    sources: List[RegistrySourceConfig] = Field(default_factory=list)
    include_country_prefix: bool = False
    region_aliases: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    provider_region_aliases: Dict[str, Dict[str, str]] = Field(default_factory=dict)


class AgentDefaultsConfig(BaseConfigModel):
    timeout_seconds: int = 300
    retries: int = 3
    uastring: str = "PropertyScanner/1.0 (bot@example.com)"


class DiscoveryAgentConfig(BaseConfigModel):
    search_depth: int = 2


class CrawlerAgentConfig(BaseConfigModel):
    download_delay: float = 2.0
    user_agent_rotation: bool = False
    headless: bool = True


class EnrichmentProvidersConfig(BaseConfigModel):
    geocoding: str = "nominatim"
    demographics: str = "census_bureau"


class EnrichmentAgentConfig(BaseConfigModel):
    providers: EnrichmentProvidersConfig = Field(default_factory=EnrichmentProvidersConfig)


class AgentsConfig(BaseConfigModel):
    defaults: AgentDefaultsConfig = Field(default_factory=AgentDefaultsConfig)
    discovery: DiscoveryAgentConfig = Field(default_factory=DiscoveryAgentConfig)
    crawler: CrawlerAgentConfig = Field(default_factory=CrawlerAgentConfig)
    enrichment: EnrichmentAgentConfig = Field(default_factory=EnrichmentAgentConfig)


class ScoringWeightsConfig(BaseConfigModel):
    price_undervaluation: float = 0.5
    rent_yield: float = 0.3
    location_score: float = 0.2


class ScoringThresholdsConfig(BaseConfigModel):
    min_deal_score: float = 0.7
    max_uncertainty_interval: float = 0.2


class RiskPenaltiesConfig(BaseConfigModel):
    missing_sqft: float = -0.1
    foreclosure_risk: float = -0.2


class ScoringConfig(BaseConfigModel):
    weights: ScoringWeightsConfig = Field(default_factory=ScoringWeightsConfig)
    thresholds: ScoringThresholdsConfig = Field(default_factory=ScoringThresholdsConfig)
    risk_penalties: RiskPenaltiesConfig = Field(default_factory=RiskPenaltiesConfig)


class PipelineConfig(BaseConfigModel):
    db_path: str = str(DEFAULT_DB_PATH)
    db_url: Optional[str] = None
    index_path: str = str(VECTOR_INDEX_PATH)
    metadata_path: str = str(VECTOR_METADATA_PATH)


class QualityGateConfig(BaseConfigModel):
    max_invalid_ratio: float = 0.1
    min_samples: int = 20


class ValuationConfig(BaseConfigModel):
    K_candidates: int = 100
    K_model: int = 10
    max_distance_km: float = 10.0
    max_age_months: int = 24
    min_comps_for_fusion: int = 5
    min_comps_for_baseline: int = 5
    min_rent_comps: int = 5
    rent_radius_km: float = 2.0
    retriever_model_name: str = "all-MiniLM-L6-v2"
    retriever_index_path: str = str(VECTOR_INDEX_PATH)
    retriever_metadata_path: str = str(VECTOR_METADATA_PATH)
    retriever_vlm_policy: str = "gated"

    eri_lag_days: int = 45
    eri_disagreement_threshold: float = 0.08
    eri_uncertainty_multiplier: float = 1.25

    horizons_months: List[int] = Field(default_factory=lambda: [12, 36, 60])

    forecast_mode: str = "analytic"
    forecast_index_source: str = "market"
    tft_model_path: str = str(TFT_MODEL_PATH)

    conformal_alpha: float = 0.1
    conformal_window: int = 50
    calibration_path: str = str(CALIBRATION_PATH)
    bootstrap_min_uncertainty_pct: float = 0.08

    income_value_weight_max: float = 0.35
    income_value_weight_min: float = 0.0
    income_value_max_adjustment_pct: float = 0.35
    area_sentiment_weight: float = 0.06
    area_development_weight: float = 0.04
    area_adjustment_cap: float = 0.08
    rent_fallback_uncertainty: float = 0.35
    fallback_yield_pct: float = 4.0


class TFTConfig(BaseConfigModel):
    hidden_size: int = 64
    attention_heads: int = 4
    dropout: float = 0.1
    num_encoder_layers: int = 2
    quantiles: List[float] = Field(default_factory=lambda: [0.1, 0.5, 0.9])
    context_length: int = 12
    prediction_horizons: List[int] = Field(default_factory=lambda: [3, 6, 12, 36, 60])


class DescriptionAnalystConfig(BaseConfigModel):
    model_name: str = "llama3:latest"
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = 60
    min_description_length: int = 50


class VLMConfig(BaseConfigModel):
    model: str = "llava"
    max_images: int = 2
    debug_max_images: int = 4
    timeout_seconds: int = 60


class ImageSelectorConfig(BaseConfigModel):
    max_candidates: int = 12
    max_bytes: int = 7_000_000
    min_side: int = 220
    min_pixels: int = 200 * 200
    duplicate_threshold: int = 6
    use_clip: bool = True
    clip_weight: float = 0.35


class AppConfig(BaseConfigModel):
    paths: PathsConfig = Field(default_factory=PathsConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    valuation: ValuationConfig = Field(default_factory=ValuationConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    quality_gate: QualityGateConfig = Field(default_factory=QualityGateConfig)
    tft: TFTConfig = Field(default_factory=TFTConfig)
    description_analyst: DescriptionAnalystConfig = Field(default_factory=DescriptionAnalystConfig)
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    image_selector: ImageSelectorConfig = Field(default_factory=ImageSelectorConfig)
