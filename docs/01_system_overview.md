# System Architecture Overview

Property Scanner is a local-first pipeline that harvests listings, enriches them, and produces valuations, projections, and recommendations with strict data and freshness requirements.

## System Map

```mermaid
flowchart LR
    subgraph Acquisition
        Harvest["src/listings/workflows/harvest.py"]
        Agent["LangGraph agent"]
        Gov["OfficialSourcesAgent (INE/ERI)"]
    end

    subgraph Processing
        Norm["Normalizer agents"]
        Fusion["FeatureFusionService (VLM + sentiment)"]
        Aug["ListingAugmentor (rent + city fixes)"]
        Store["StorageService (persistence only)"]
        BuildIndex["src/valuation/workflows/indexing.py"]
        BuildMarket["src/market/workflows/market_data.py"]
        Transactions["src/market/workflows/transactions.py"]
        Preflight["src/platform/workflows/preflight.py"]
    end

    subgraph Data
        Listings[("SQLite: data/listings.db")]
        Seen[("SQLite: harvest_seen_urls.sqlite3")]
        State["JSON: harvest_state_*.json"]
        VectorIndex[("FAISS: vector_index.faiss + metadata")]
        Indices[("market/hedonic/macro/area tables")]
        GovData[("ine_ipv + eri_metrics")]
        Runs[("pipeline_runs")]
        Calib[("models/calibration_registry.json")]
    end

    subgraph Intelligence
        Retriever["CompRetriever (FAISS + time-safe filters)"]
        Market["MarketAnalyticsService"]
        Model["PropertyFusionModel"]
        Forecast["ForecastingService (analytic/TFT)"]
        Hedonic["HedonicIndexService"]
        Area["AreaIntelligenceService"]
        Val["ValuationService (comp + income + area blend)"]
    end

    subgraph Interface
        CLI["src/interfaces/cli.py"]
        Dash["Scout Intelligence (Streamlit)"]
        Scheduler["src/platform/workflows/scheduler.py"]
    end

    Harvest --> Seen
    Harvest --> State
    Harvest --> Norm
    Agent --> Norm
    Gov --> GovData
    Norm --> Fusion --> Aug --> Store --> Listings
    Transactions --> Listings

    Listings --> BuildIndex --> VectorIndex --> Retriever
    Listings --> BuildMarket --> Indices
    GovData --> BuildMarket --> Indices
    GovData --> Hedonic --> Val
    Indices --> Market --> Val
    Indices --> Area --> Val
    Retriever --> Val
    Model --> Val

    Preflight --> Harvest
    Preflight --> Transactions
    Preflight --> BuildMarket
    Preflight --> BuildIndex
    Preflight --> Runs
    Scheduler --> Preflight

    Val --> Dash
    Val --> CLI
```

## Components in One Line Each
- Acquisition: `src/listings/workflows/harvest.py`, plus LangGraph for agent-driven discovery and `OfficialSourcesAgent` for government stats.
- Processing: normalize, fuse VLM signals, ingest sold transactions, then persist via StorageService.
- Data: SQLite is the system of record; `pipeline_runs` records operational health.
- Intelligence: time-safe comps, hedonic indices, income-aware valuation, and area intelligence.
- Interface: CLI and the Scout Intelligence dashboard.
- Automation: scheduled preflight keeps data and artifacts fresh without manual runs.

## Module Boundaries (Contract)
- `src/interfaces/**`: CLI, API, and dashboard entry points.
- `src/agentic/**`: LangGraph tools, cognitive orchestrator, and analyst agents.
- `src/listings/**`: crawl/normalize/enrich listings, listing repos, harvest workflows.
- `src/market/**`: macro/indices/registry signals, market repos, market workflows.
- `src/valuation/**`: retrieval + valuation services, calibration/backfill/indexing workflows.
- `src/ml/**`: models/encoders and training pipelines.
- `src/platform/**`: config/settings, storage + migrations, pipeline state/runs.
- `scripts/workflows/**`: thin wrappers for workflow entry points.
