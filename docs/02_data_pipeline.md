# Data and Training Pipeline

This document summarizes how listings flow through the system, how derived artifacts are produced, and how quality gates keep the lake clean.

## 0. Start here: preflight

Preflight is the simplest way to run the pipeline. It checks freshness and only runs what is stale.

```mermaid
flowchart LR
    CLI["CLI"] --> Preflight["Preflight workflow"]
    Dash["Dashboard"] --> Preflight
    Scheduler["Scheduler workflow"] --> Preflight
    Preflight --> Harvest["Harvest workflow"]
    Preflight --> Transactions["Transactions ingest"]
    Preflight --> MarketData["Market data workflow"]
    Preflight --> Index["Vector index workflow"]
    Preflight --> Train["Training workflow"]
    Preflight --> Runs[("pipeline_runs")]
```

- `python3 -m src.interfaces.cli dashboard` triggers preflight unless `--skip-preflight` is passed.
- `python3 -m src.interfaces.cli schedule` runs preflight on an interval or cron schedule (canonical automation entry point).
- Preflight uses `PipelineStateService` to compare listing freshness against market data, index files, and model artifacts.
- Preflight ingests transactions from config defaults unless `--skip-transactions` is set; `--transactions-path` overrides the default. Transactions run before market data and training.

## 1. Ingestion: harvesting with quality gates

```mermaid
flowchart LR
    Portal["Source portals"] --> Harvest["Harvest workflow"]
    Harvest --> Seen[("harvest_seen_urls.sqlite3")]
    Harvest --> State["harvest_state_*.json"]
    Harvest --> Gate["ListingQualityGate"]
    Gate --> Norm["Normalizer agents"]
    Norm --> Fusion["Feature fusion"]
    Fusion --> Aug["Listing augmentor"]
    Aug --> Store["StorageService"]
    Store --> DB[("SQLite: data/listings.db")]
    Gate --> Runs[("pipeline_runs")]
```

- URL de-dupe and resume are handled by `SeenUrlStore` and `HarvestState`.
- Listings are validated before persistence. If the invalid ratio exceeds the threshold, the harvest stops.

## 1.5 Transactions: sold/registry ingest

```
python3 -m src.interfaces.cli transactions -- --path data/transactions.csv
```

- The transactions workflow ingests sold price and sold date updates.
- Records are matched by `listing_id`, `(source_id, external_id)`, or `url`.
- `status`, `sold_price`, and `sold_at` are updated so downstream training and valuation use ground-truth sales.

## 2. Derived data and caches

```mermaid
flowchart LR
    Listings[("listings")] --> MarketData["Market data workflow"]
    MarketData --> MarketTables["market_indices / hedonic_indices / macro_indicators / area_intelligence"]

    Gov["OfficialSourcesAgent"] --> GovData["ine_ipv + eri_metrics"] --> MarketData

    Listings --> Index["Vector index workflow"]
    Index --> VectorIndex["vector_index.faiss + vector_metadata.json"]

    Listings --> Train["Training workflow"]
    MarketTables --> Train
    Train --> ModelArtifacts["models/fusion_model.pt + fusion_config.json"]

    Listings --> Backfill["Backfill workflow"]
    VectorIndex --> Backfill
    ModelArtifacts --> Backfill
    Backfill --> Val["valuations table"]

    CalibSamples["calibration_samples.jsonl"] --> CalibUpdate["Calibration workflow"]
    CalibUpdate --> Calib["models/calibration_registry.json"]
```

Recommended manual order:
1) Harvest + normalize + store
2) Ingest transactions (sold/registry data)
3) Build market data (macro + indices)
4) Build vector index
5) Train fusion model
6) Backfill valuations
7) Update calibration registry

## 3. Quality gates and run logs

- **ListingQualityGate** rejects listings missing price, surface area, or title.
- If invalid ratio exceeds the configured threshold, the pipeline stops.
- Every workflow run is recorded in `pipeline_runs` with metadata, including sample failures.

## 4. Data assets on disk

| Artifact | Purpose | Produced by | Notes |
| --- | --- | --- | --- |
| `data/listings.db` (listings) | Primary dataset | `StorageService` | System of record |
| `data/listings.db` (market/hedonic) | Derived indices | Market data workflow | Market + hedonic indices |
| `data/listings.db` (ine_ipv) | Official stats | `OfficialSourcesAgent` | Benchmark anchors |
| `data/listings.db` (eri_metrics) | Registral stats | `OfficialSourcesAgent` | Liquidity signals |
| `data/listings.db` (pipeline_runs) | Operational logs | `PipelineRunTracker` | Run metadata |
| `data/vector_index.faiss` | Dense comp index | Indexing workflow | Required for comps |
| `data/vector_metadata.json` | Comp metadata | Indexing workflow | Encoder + policy lock |
| `data/harvest_seen_urls.sqlite3` | URL de-dupe | `SeenUrlStore` | Safe to delete to re-crawl |
| `data/harvest_state_*.json` | Resume state | `HarvestState` | Safe to delete to restart |
| `data/harvest_urls_*.json` | URL checkpoint | Harvester | Optional safety net |
| `models/fusion_model.pt` | Trained fusion model | Training workflow | Required for valuation |
| `models/fusion_config.json` | Fusion model config | Training workflow | Required for valuation |
| `models/comp_cache.json` | Comp cache (optional) | Training workflow | Persisted comps when using retriever |
| `models/calibration_registry.json` | Conformal calibrators | Calibration workflow | Optional |

## 5. Multimodal training at a glance

```mermaid
sequenceDiagram
    participant DB as listings.db
    participant Indices as "Market indices"
    participant Train as Trainer

    Train->>DB: Load listings and time-safe comps
    Train->>Indices: Pull hedonic and rent indices
    Train->>Train: Normalize prices to the target month
    Train->>Train: Build robust baseline and log-residual targets
    Train->>Train: Optimize pinball loss with label weights
```

- VLM descriptions are stored in `vlm_description` and treated as extra text.
- Comp selection is time-safe and deduped; retriever mode freezes the encoder + VLM policy and can persist comp IDs for train/infer parity.
- Time+geo splits are available (`--split-strategy time_geo`) to reduce leakage.
- Valuation is strict: if comps, indices, or model artifacts are missing, evaluation stops rather than guessing.
