# Model Architecture

This page explains valuation modeling from data -> training -> inference -> outputs, and how market/area signals are blended.

Canonical runtime and reliability controls live in:
- `docs/manifest/01_architecture.md`
- `docs/manifest/07_observability.md`
- `docs/manifest/10_testing.md`

## Model Layers

1. Retriever + encoders (SentenceTransformer + tabular encoder; optional VLM text)
2. Fusion model (cross-attention over comps; predicts residual quantiles)
3. Forecasting model (analytic drift or optional TFT)
4. Conformal calibration + blending (intervals, rent/yield, area intelligence)

## Valuation Path

```mermaid
flowchart TB
    subgraph Inputs
        T_Tab["Target tabular"]
        T_Txt["Target text"]
        T_Img["Target image (optional)"]
        C_Tab["Comp tabular"]
        C_Txt["Comp text"]
        C_Img["Comp image (optional)"]
        C_Prices["Comp prices (time-adjusted)"]
    end

    subgraph "Target encoding"
        T_TabProj["Tabular projector"]
        T_TxtProj["Text projector"]
        T_ImgProj["Image projector"]
        T_Fuse["Modality fusion"]
    end

    subgraph "Comp encoding"
        C_TabProj["Tabular projector"]
        C_TxtProj["Text projector"]
        C_ImgProj["Image projector"]
        C_Fuse["Modality fusion"]
    end

    subgraph Reasoning
        Attn["Cross-attention"]
        Reason["Reasoned embedding"]
    end

    subgraph Heads
        PriceRes["Price residual quantiles (log-residual)"]
        RentRes["Rent residual quantiles"]
        TimeRes["Time-to-sell quantiles"]
    end

    subgraph Anchors
        Baseline["Robust comp baseline (MAD-weighted median)"]
        PriceOut["Price quantiles (p10/p50/p90) via exp(baseline_log + residual)"]
    end

    T_Tab --> T_TabProj --> T_Fuse
    T_Txt --> T_TxtProj --> T_Fuse
    T_Img --> T_ImgProj --> T_Fuse

    C_Tab --> C_TabProj --> C_Fuse
    C_Txt --> C_TxtProj --> C_Fuse
    C_Img --> C_ImgProj --> C_Fuse

    T_Fuse -->|Query| Attn
    C_Fuse -->|Key/Value| Attn
    Attn --> Reason --> PriceRes
    Reason --> RentRes
    Reason --> TimeRes

    C_Prices --> Baseline --> PriceOut
    PriceRes --> PriceOut
```

## End-To-End Flow

### Training

1. Load listings from `data/listings.db` and sanitize features.
2. Build comps (geo-radius + structure filters, optional semantic retriever).
3. Time-normalize prices using `HedonicIndexService`.
4. Compute baseline with MAD-filtered weighted median.
5. Target label: `log(target_price_adj) - log(baseline)`.
6. Train `PropertyFusionModel` with quantile pinball loss.
7. Save artifacts: `models/fusion_model.pt`, `models/fusion_config.json`, optional `models/comp_cache.json`.

### Inference

1. Retrieve comps with strict retriever metadata matching.
2. Time-adjust comp prices.
3. Compute robust baseline.
4. Encode features (text + tabular; vision optional by policy).
5. Predict residual quantiles via `FusionModelService`.
6. Reconstruct price quantiles from baseline + residual.
7. Apply conformal calibration (if registry exists).
8. Blend rent/yield and area-intelligence signals.
9. Produce forward projections (price/rent/yield).

If fusion fails or returns invalid quantiles, valuation falls back to comp-baseline-derived quantiles.

## Key Modeling Policies

### Cross-attention pricing

- Model predicts price relative to market baseline.
- Baseline is computed outside the model from time-adjusted comps.
- `target_mode=log_residual` aligns train and infer behavior.

### Quantile-first outputs

- p10: conservative
- p50: fair value
- p90: optimistic

Quantile heads are trained with weighted pinball loss.

### Strict comp selection

- time-safe comp dates
- retriever metadata/policy lock
- optional persisted comp IDs for train/infer parity
- explicit failures for missing required artifacts

### Label strategy

- sale labels prefer `sold_price` when available, then ask fallback
- rent labels use rent ask and rent-index normalization
- reliability weighting: sold > rent ask > sale ask

## Signal Blending

```mermaid
flowchart LR
    Base["Model fair value"] --> Blend["Income blend"]
    Rent["Estimated rent"] --> Blend
    Yield["Market yield (local distribution)"] --> Blend
    Blend --> AreaAdj["Area adjustment"]
    Area["Area intelligence"] --> AreaAdj
    AreaAdj --> Final["Adjusted fair value"]
```

- Income blend uses local yield distributions with coverage/variance weighting.
- Area adjustment applies sentiment/development signals with freshness + confidence scaling.
- Evidence is persisted for auditability.

## Current Config Snapshot

Defined in `models/fusion_config.json` (loaded by `FusionModelService`).

| Parameter | Value | Description |
| --- | --- | --- |
| Tabular dim | 11 | structured listing features |
| Text dim | 384 | SentenceTransformer embedding size |
| Image dim | 512 | optional image embedding size |
| Hidden dim | 64 | projection size |
| Heads | 2 | attention heads |
| Params | ~92k | lightweight CPU-friendly model |
| Target mode | `log_residual` | residual target for train/infer parity |

## Required Artifacts

- `models/fusion_model.pt`
- `models/fusion_config.json`
- `data/vector_index.lancedb`
- `data/vector_metadata.json`
- market tables in `data/listings.db`
- optional: `models/calibration_registry.json`
