# Model Architecture: PropertyFusionModel

The PropertyFusionModel is the core model that predicts fair value by reasoning over a target listing and its comps. It is designed to predict residuals over a comp baseline rather than raw price.

## Architecture Diagram

```mermaid
graph TD
    subgraph "Inputs"
        T_Tab["Target Tabular"]
        T_Txt["Target Text"]
        T_Img["Target Image (optional)"]
        C_Tab["Comp Tabular"]
        C_Txt["Comp Text"]
        C_Img["Comp Image (optional)"]
    end

    subgraph "Encoders"
        MLP1["Tabular Projector"]
        MLP2["Text Projector"]
        MLP3["Image Projector"]
    end

    T_Tab --> MLP1
    T_Txt --> MLP2
    T_Img --> MLP3
    C_Tab --> MLP1
    C_Txt --> MLP2
    C_Img --> MLP3

    subgraph "Fusion Layer"
        Concat_T["Concat Target Embeddings"]
        Concat_C["Concat Comp Embeddings"]
    end

    MLP1 & MLP2 & MLP3 --> Concat_T
    MLP1 & MLP2 & MLP3 --> Concat_C

    subgraph "Reasoning Core"
        Attn["Cross-Attention Mechanism"]
        Concat_T -->|Query| Attn
        Concat_C -->|Key/Value| Attn
    end

    subgraph "Prediction Heads"
        Res["Residual Predictor"]
        Attn --> Res

        Final["Final Price Calculation"]
        Baseline["Robust Comp Baseline"]
        CompPrices["Comp Prices"] --> Baseline
        Baseline --> Final
        Res --> Final
    end

    Final -->|Output| Quantiles["p10, p50, p90"]
```

## Core Concepts

### 1. Cross-Attention Pricing
The model predicts price relative to the market:
- The target listing queries comparable listings.
- A robust comp baseline (weighted median + MAD filtering) is computed outside the model.
- The model predicts log-residuals over the baseline.
- Hedonic indices time-adjust sale comps; rent comps use the rent index.
- INE IPV anchors are used when local data is thin.

### 2. Quantile Regression (Uncertainty)
The model outputs a distribution, not a single number:
- p10: conservative price
- p50: fair value
- p90: optimistic price

Weighted pinball loss trains the quantile heads and encodes label reliability.

### 3. Strict Comparable Selection
- Comps are time-safe (comp date <= target date).
- Retriever metadata (encoder + VLM policy) must match across train and infer.
- If comps or indices are missing, valuation fails instead of guessing.

### 4. Label Strategy
- Sale training labels prefer `sold_price` when available; ask prices are a fallback.
- Rent training labels use asking rent and are normalized via the rent index.
- Label weights reflect reliability: sold > rent ask > sale ask.

## System-Level Valuation Blend
The model output is combined with income and area intelligence signals:

```mermaid
flowchart LR
    Base["Model Fair Value"] --> Blend["Income Blend"]
    Rent["Estimated Rent"] --> Blend
    Yield["Market Yield"] --> Blend
    Blend --> AreaAdj["Area Adjustment"]
    Area["Area Intelligence"] --> AreaAdj
    AreaAdj --> Final["Adjusted Fair Value"]
```

- **Income blend** rewards listings with stronger rent-to-price economics.
- **Area adjustment** nudges valuation using sentiment and development scores derived from official ERI/INE data, with freshness and credibility scaling.
- Evidence is recorded in `external_signals` for transparency.

## Hyperparameters (Current Configuration)
Defined in `src/ml/services/fusion_model.py`.

| Parameter | Value | Description |
| --- | --- | --- |
| Tabular Dim | 11 | bedrooms, bathrooms, surface_area_sqm, year_built, floor, lat, lon, price_per_sqm (zeroed), text_sentiment, image_sentiment, has_elevator |
| Text Dim | 384 | SentenceTransformer embedding size |
| Image Dim | 512 | Optional image embedding size |
| Hidden Dim | 64 | Projection size |
| Heads | 2 | Attention heads |
| Parameters | ~92k | Lightweight, CPU-friendly |

## Runtime Requirements
- Model artifacts: `models/fusion_model.pt` and `models/fusion_config.json`.
- Vector index: `data/vector_index.faiss` + `data/vector_metadata.json`.
- Market tables in `data/listings.db`: `market_indices`, `hedonic_indices`, `macro_indicators`, `area_intelligence`.
- Optional calibrators: `models/calibration_registry.json`.
