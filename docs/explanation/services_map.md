# Services Map

This page is a visual inventory of service classes and their boundaries.

Companion pages:
- `docs/explanation/system_overview.md`
- `docs/explanation/data_pipeline.md`
- `docs/explanation/scraping_architecture.md`

## Service Landscape

```mermaid
flowchart LR
    subgraph Interfaces
        CLI["CLI"]
        API["PipelineAPI"]
        Dash["Scout dashboard"]
    end

    subgraph Platform
        Storage["StorageService"]
        PipelineState["PipelineStateService"]
        Runs["PipelineRunTracker"]
        AgentMemory["AgentMemoryStore"]
    end

    subgraph Listings
        Snap["SnapshotService"]
        Enrich["EnrichmentService"]
        Geo["GeocodingService"]
        Fusion["FeatureFusionService"]
        Persist["ListingPersistenceService"]
    end

    subgraph Market
        Txn["TransactionsIngestService"]
        Registry["RegistryIngestService"]
        Macro["MacroDataService"]
        Indices["MarketIndexService"]
        Hedonic["HedonicIndexService"]
        Area["AreaIntelligenceService"]
        Analytics["MarketAnalyticsService"]
        ERI["ERISignalsService"]
    end

    subgraph ML
        FusionModel["FusionModelService"]
        TFT["TFTForecastingService"]
    end

    subgraph Valuation
        Forecast["ForecastingService"]
        Val["ValuationService"]
    end

    CLI --> PipelineState
    API --> PipelineState
    Dash --> PipelineState
    PipelineState --> Runs
    AgentMemory --> Storage

    Enrich --> Geo
    Fusion --> Persist --> Storage
    Snap --> Storage

    Txn --> Storage
    Registry --> Storage
    Macro --> Storage
    Indices --> Storage
    Hedonic --> Storage
    Area --> Storage
    ERI --> Area

    Analytics --> Storage
    Forecast --> Storage

    FusionModel --> Val
    Forecast --> Val
    Hedonic --> Val
    Analytics --> Val
    Area --> Val
```

## Valuation Composition

```mermaid
flowchart TB
    Val["ValuationService"] --> Retriever["CompRetriever"]
    Val --> FusionModel["FusionModelService"]
    Val --> Hedonic["HedonicIndexService"]
    Val --> Analytics["MarketAnalyticsService"]
    Val --> Area["AreaIntelligenceService"]
    Val --> Forecast["ForecastingService"]
```

## Service Boundaries

Listings services:
- `SnapshotService`: file-backed HTML snapshots.
- `EnrichmentService`: reverse geocode + geohash generation.
- `GeocodingService`: forward geocoding utility.
- `FeatureFusionService`: merges VLM/text sentiment and enrichments.
- `ListingPersistenceService`: upsert policy for `listings`.

Market services:
- `TransactionsIngestService`: sold price/status updates.
- `RegistryIngestService`: official metrics ingestion.
- `MacroDataService`: macro indicators ingestion/normalization.
- `MarketIndexService`: price/rent index generation.
- `HedonicIndexService`: time-safe hedonic index construction.
- `AreaIntelligenceService`: area sentiment/development signals.
- `MarketAnalyticsService`: liquidity/momentum/catch-up metrics.
- `ERISignalsService`: derived liquidity signals from official metrics.

Valuation and forecasting services:
- `ForecastingService`: forward price/rent/yield projections.
- `ValuationService`: comps, indices, model inference, and adjustments.

ML services:
- `FusionModelService`: multimodal pricing model inference API.
- `TFTForecastingService`: time-series forecasting service.

Platform services:
- `StorageService`: DB session/engine lifecycle.
- `PipelineStateService`: freshness checks for listings/indices/models.
- `PipelineRunTracker`: pipeline run metadata in `pipeline_runs`.
- `AgentMemoryStore`: persisted agent run memory in `agent_runs`.

## Interaction Rules

- Services read/write through repositories and `StorageService`, not ad-hoc direct SQL in workflows.
- Listing enrichment/persistence remains isolated from crawler extraction.
- Valuation is strict: missing load-bearing artifacts are explicit failures.
- Market services derive indicators without mutating listing payload semantics.
