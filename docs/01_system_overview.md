# System Architecture Overview

Property Scanner is a local-first pipeline that harvests listings, enriches them, and produces valuations, projections, and recommendations with strict data requirements.

## System Map

```mermaid
flowchart LR
    subgraph Acquisition
        HB["harvest_batch.py"]
        AG["LangGraph agent workflow"]
    end

    subgraph Processing
        Norm["Normalizer agents"]
        Fusion["FeatureFusionService (VLM + sentiment clamp)"]
        Store["StorageService (enrich + analyze)"]
        BuildIndex["build_vector_index.py"]
        BuildMarket["build_market_data.py"]
    end

    subgraph Data
        Listings[("SQLite: data/listings.db")]
        Seen[("SQLite: harvest_seen_urls.sqlite3")]
        State["JSON: harvest_state_*.json"]
        VectorIndex[("FAISS: vector_index.faiss + metadata")]
        Indices[("market/hedonic/macro/area tables")]
        ERI[("eri_metrics (optional)")]
        Calib[("models/calibration_registry.json")]
    end

    subgraph Intelligence
        Retriever["CompRetriever (FAISS + time-safe filters)"]
        Market["MarketAnalyticsService (liquidity + ERI)"]
        Model["PropertyFusionModel"]
        Forecast["ForecastingService (analytic/TFT)"]
        Calibrator["Stratified Calibrators"]
        Val["ValuationService (fusion + rent + yield)"]
    end

    subgraph Interface
        CLI["Scripts / CLI"]
        Dash["Streamlit dashboard"]
    end

    HB --> Seen
    HB --> State
    HB --> Norm
    AG --> Norm
    Norm --> Fusion --> Store --> Listings
    Listings --> BuildIndex --> VectorIndex --> Retriever
    Listings --> BuildMarket --> Indices --> Forecast --> Val
    Listings --> Market
    ERI --> Market --> Val
    Calib --> Calibrator --> Val
    Retriever --> Val
    Model --> Val
    Val --> Dash
    Val --> CLI
```

## Components in One Line Each
- Acquisition: bulk harvesting via `src/scripts/harvest_batch.py`, optional agent-driven flows via `src/cognitive/graph.py`.
- Processing: normalize, fuse VLM-derived signals, clamp sentiment, then persist via StorageService.
- Data: SQLite is the system of record; vector index/metadata, market indices, and (optional) ERI metrics are rebuildable artifacts.
- Intelligence: time-safe comp retrieval with frozen retriever metadata, fusion valuation on log-residuals over a robust comp baseline, calibrated uncertainty, and analytic/TFT projections.
- Interface: Streamlit dashboard and CLI scripts (build indices, vector index, backfill valuations, training).

## Module Boundaries (Contract)
- Agents (`src/agents/**`): crawling, normalization, and enrichment of raw source data into `CanonicalListing`.
- Services (`src/services/**`): storage, encoding, retrieval, valuation, forecasting, and model artifacts; no direct crawling.
- Scripts/CLI (`src/scripts/**`, `src/cli.py`): orchestration glue and user-facing entrypoints.
