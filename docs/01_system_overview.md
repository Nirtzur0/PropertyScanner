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
        Fusion["FeatureFusionService (optional VLM)"]
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
    end

    subgraph Intelligence
        Retriever["CompRetriever (FAISS + filters)"]
        Model["PropertyFusionModel"]
        Forecast["ForecastingService (regime drift)"]
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
    Retriever --> Val
    Model --> Val
    Val --> Dash
    Val --> CLI
```

## Components in One Line Each
- Acquisition: bulk harvesting via `src/scripts/harvest_batch.py`, optional agent-driven flows via `src/cognitive/graph.py`.
- Processing: normalize, optionally fuse VLM-derived signals, then persist via StorageService.
- Data: SQLite is the system of record; vector index and derived indices are rebuildable artifacts.
- Intelligence: strict comp retrieval (geo + property_type + size), fusion valuation, regime drift projections, rent/yield integration.
- Interface: Streamlit dashboard and CLI scripts (build indices, vector index, backfill valuations, training).
