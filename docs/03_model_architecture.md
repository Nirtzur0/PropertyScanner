# Model Architecture: PropertyFusionModel

The **PropertyFusionModel** is the "brain" of the system. It uses an attention-based architecture to estimate the fair market value of a property by reasoning over its attributes and its relationship to the market.

## Architecture Diagram

```mermaid
graph TD
    subgraph "Inputs"
        T_Tab["Target Tabular"]
        T_Txt["Target Text"]
        C_Tab["Comp Tabular"]
        C_Txt["Comp Text"]
    end

    subgraph "Encoders"
        MLP1["Tabular Projector"]
        MLP2["Text Projector"]
    end

    T_Tab --> MLP1
    T_Txt --> MLP2
    C_Tab --> MLP1
    C_Txt --> MLP2

    subgraph "Fusion Layer"
        Concat_T["Concat Target Embeddings"]
        Concat_C["Concat Comp Embeddings"]
    end

    MLP1 & MLP2 --> Concat_T
    MLP1 & MLP2 --> Concat_C

    subgraph "Reasoning Core"
        Attn["Cross-Attention Mechanism"]
        Concat_T -->|Query| Attn
        Concat_C -->|"Key/Value"| Attn
        
        Anchor["Anchor Calculation"]
        Attn -.->|Weights| Anchor
        CompPrices --> Anchor
    end

    subgraph "Prediction Heads"
        Res["Residual Predictor"]
        Attn --> Res
        
        Final["Final Price Calculation"]
        Anchor --> Final
        Res --> Final
    end

    Final -->|Output| Quantiles["p10, p50, p90"]
```

## Core Concepts

### 1. Cross-Attention Pricing
Traditional models predict price directly from features ($f(x) \rightarrow y$). Our model predicts price **relative to the market** ($f(x, \{comps\}) \rightarrow y$).
- The **Target Listing** queries the **Comparable Listings**.
- The model learns "how much better or worse" the target is compared to the comps.
- **Anchor Price**: The weighted average of comp prices (weighted by similarity).
- **Residual**: The model predicts a +/- adjustment to this anchor.

### 2. Quantile Regression (Uncertainty)
Real estate valuation is inherently uncertain. Instead of a single number, the model predicts a probability distribution:
- **p10 (Conservative)**: "Quick sale" price.
- **p50 (Fair)**: Probable market value.
- **p90 (Optimistic)**: High-end estimate.

This is achieved using **Pinball Loss** during training.

### 3. Hyperparameters (Current Configuration)
Defined in `src/services/fusion_model.py`.

| Parameter | Value | Description |
|-----------|-------|-------------|
| Tabular Dim | 10 | bedrooms, bathrooms, surface_area_sqm, year_built, floor, lat, lon, sentiment_score, has_elevator, price_per_sqm |
| Text Dim | 384 | SentenceTransformer embedding size (includes VLM descriptions) |
| Hidden Dim | 64 | Projection size (Compact for efficiency) |
| Heads | 2 | Attention heads |
| Parameters | ~92k | Lightweight, runs on CPU |
