# Data and Training Pipeline

This document summarizes how listings flow through the system and how data is managed on disk.

## 1. Ingestion (Batch Harvester)

```mermaid
flowchart LR
    Portal["Web portal"] --> HB["harvest_batch.py"]
    HB --> Seen[("harvest_seen_urls.sqlite3")]
    HB --> State["harvest_state_*.json"]
    HB --> Norm["Normalizer agents"]
    Norm --> Fusion["FeatureFusionService (optional VLM)"]
    Fusion --> Store["StorageService"]
    Store --> DB[("SQLite: data/listings.db")]
```

- URL de-dupe and resume are handled by `SeenUrlStore` and `HarvestState`.
- Listings are upserted into `listings` with enrichment and analysis during save.

## 2. Derived Data and Caches

```mermaid
flowchart LR
    Listings[("listings")] --> BuildMarket["build_market_data.py"]
    BuildMarket --> MI["market_indices"]
    BuildMarket --> HI["hedonic_indices"]
    BuildMarket --> Macro["macro_indicators"]
    BuildMarket --> Area["area_intelligence"]

    Listings --> BuildIndex["build_vector_index.py"]
    BuildIndex --> VI["vector_index.faiss + vector_metadata.json"]

    MacroCrawler["macro_intel crawler"] --> MS["macro_scenarios"]
    Listings --> ValFlow["ValuationService / backfill_valuations.py"]
    ValFlow --> Val["valuations"]
```

Recommended order (strict):
1) Harvest + normalize + store
2) Build market indices
3) Build vector index
4) Train fusion model
5) Run valuations / backfill

## 3. Data Assets (On Disk)

| Artifact | Purpose | Produced by | Notes |
| --- | --- | --- | --- |
| `data/listings.db` (listings) | Primary dataset | `StorageService` | Core system of record |
| `data/listings.db` (market/hedonic/macro/area) | Derived indices | `build_market_data.py` | Rebuildable |
| `data/listings.db` (valuations) | Cached deal analyses | `ValuationService` or `backfill_valuations.py` | Rebuildable |
| `data/listings.db` (macro_scenarios) | Scenario forecasts | `macro_intel` crawler | Optional |
| `data/vector_index.faiss` | Dense comp index | `build_vector_index.py` | Required for comps |
| `data/vector_metadata.json` | Comp metadata | `build_vector_index.py` | Required for comps |
| `data/harvest_seen_urls.sqlite3` | URL de-dupe | `SeenUrlStore` | Safe to delete to re-crawl |
| `data/harvest_state_*.json` | Resume state | `HarvestState` | Safe to delete to restart |
| `data/harvest_urls_*.json` | URL checkpoint | Harvester | Optional safety net |
| `models/fusion_model.pt` | Trained fusion model | `src/training/train.py` | Required for valuation |
| `models/fusion_config.json` | Fusion model config | `src/training/train.py` | Required for valuation |

## 4. Multimodal Training (Short View)

```mermaid
sequenceDiagram
    participant DB as listings.db
    participant VLM as "Ollama (Llava)"
    participant Train as Trainer

    Train->>DB: Load listing + comps (+ vlm_description if present)
    Train->>Train: Encode tabular + text, cross-attend comps
    Train->>Train: Quantile loss optimization
```

- VLM descriptions are stored in `vlm_description` and treated as extra text during training.
- Comp selection during training is two-stage (geo radius, then property_type + size filter).
- Valuations are strict: comps, indices, and model artifacts must exist or the evaluation fails.
