# System Architecture Overview

Property Scanner is a local-first pipeline that crawls listings, enriches them, and produces valuations, projections, and recommendations with strict data and freshness requirements.

## System Map

```mermaid
flowchart LR
    subgraph Interfaces
        CLI["CLI"]
        Dash["Scout dashboard"]
        API["PipelineAPI"]
    end

    subgraph Agents
        Agent["LangGraph agents"]
    end

    subgraph Orchestration
        Scheduler["Scheduler workflow"]
        Preflight["Preflight workflow"]
    end

    subgraph Listings
        CrawlBackfill["Crawl backfill workflow"]
        Norm["Normalizer agents"]
        Fusion["Feature fusion (VLM + sentiment)"]
        Aug["Listing augmentor"]
        Store["StorageService"]
    end

    subgraph Market
        Transactions["Transactions ingest"]
        MarketData["Market data workflow"]
        Hedonic["HedonicIndexService"]
        Area["AreaIntelligenceService"]
        MarketAnalytics["MarketAnalyticsService"]
        Gov["OfficialSourcesAgent (INE/ERI)"]
    end

    subgraph ML
        Train["Training workflow"]
        Model["PropertyFusionModel (log-residual)"]
    end

    subgraph Valuation
        Index["Vector index workflow"]
        Retriever["CompRetriever"]
        Forecast["ForecastingService"]
        Val["ValuationService"]
    end

    subgraph Data
        ListingsDB[("SQLite: data/listings.db")]
        Seen[("unified_seen_urls.sqlite3")]
        VectorIndex[("vector_index.faiss + metadata")]
        MarketTables[("market/hedonic/macro/area tables")]
        GovData[("ine_ipv + eri_metrics")]
        Runs[("pipeline_runs")]
        ModelArtifacts[("models/fusion_model.pt + fusion_config.json")]
        Calib[("models/calibration_registry.json")]
    end

    CLI --> API
    Dash --> API
    API --> Preflight
    Scheduler --> Preflight
    Agent --> Preflight

    Preflight --> CrawlBackfill
    Preflight --> Transactions
    Preflight --> MarketData
    Preflight --> Index
    Preflight --> Train
    Preflight --> Runs

    CrawlBackfill --> Seen
    CrawlBackfill --> Norm --> Fusion --> Aug --> Store --> ListingsDB
    Transactions --> ListingsDB

    ListingsDB --> MarketData --> MarketTables
    Gov --> GovData --> MarketData
    MarketTables --> Hedonic --> Val
    MarketTables --> Area --> Val
    MarketTables --> MarketAnalytics --> Val

    ListingsDB --> Index --> VectorIndex --> Retriever --> Val
    ListingsDB --> Train
    MarketTables --> Train
    Train --> ModelArtifacts --> Model --> Val
    Calib --> Val
    Forecast --> Val

    Val --> Dash
    Val --> CLI
```

## System components at a glance
- Acquisition: Crawl backfill workflow plus LangGraph for agent-driven discovery and `OfficialSourcesAgent` for government stats.
- Processing: Normalize listings, fuse VLM signals, ingest sold transactions, then persist via StorageService.
- Data: SQLite is the system of record; `pipeline_runs` tracks operational health.
- Intelligence: Time-safe comps with metadata locks, hedonic indices, income-aware valuation, and area intelligence.
- Interfaces: CLI, PipelineAPI, and the Scout Intelligence dashboard.
- Automation: Scheduled preflight keeps data and artifacts fresh without manual runs.

## Module boundaries (what lives where)
- Interfaces: CLI, API, and dashboard entry points.
- Agents: LangGraph tools, the orchestrator, and analyst agents.
- Listings: Crawl/normalize/enrich listings, listing repos, crawl workflows.
- Market: Macro/indices/registry signals, market repos, market workflows.
- Valuation: Retrieval + valuation services, calibration/backfill/indexing workflows.
- ML: Models/encoders and training pipelines.
- Platform: Config/settings, storage + migrations, pipeline state/runs.
- Scripts: Workflow wrappers, crawl harnesses, and debug utilities.
