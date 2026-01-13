# Data & Training Pipeline

This document details how raw web data is transformed into a high-quality dataset and used to train the valuation model.

## 1. Data Ingestion Pipeline

The ingestion process focuses on **robustness** and **reproducibility**. We do not just scrape data; we archive the world state.

```mermaid
graph LR
    Portal["Web Portal"] -->|Scrape| Agent["Crawler Agent"]
    
    subgraph "Ingestion Flow"
        Agent -->|"1. Save Raw"| Snapshot("SnapshotService")
        Snapshot -->|"HTML/JSON"| Normalizer["Normalizer Agent"]
        Normalizer -->|"2. Canonize"| Schema{"Canonical Schema"}
        Schema -->|"3. Enrich"| Enrich["EnrichmentService"]
        Enrich -->|"4. Persist"| DB[("Listings DB")]
    end
    
    subgraph "Enrichment"
        Enrich -->|Geo| Geocoder["Geocoder"]
        Enrich -->|NLP| Sentiment["DescriptionAnalyst"]
    end
```

### Key Services
- **`SnapshotService`**: Saves raw HTML with metadata (`source_id`, `timestamp`). Allows re-parsing if schemas change.
- **`EnrichmentService`**: Fills gaps in data (e.g., missing city names) using heuristics and external APIs.
- **`DescriptionAnalyst`**: Uses lightweight NLP to extract sentiment scores and key facts (e.g., "needs renovation") from descriptions.

---

## 2. Multimodal Training Pipeline

The training pipeline prepares data for the `PropertyFusionModel`. It is unique because it handles text, images, and tabular data simultaneously.

The VLM enrichment is decoupled from the training loop to improve efficiency. It runs as a preprocessing step (`src/training/preprocess_vlm.py`), storing generated descriptions in the database.

```mermaid
sequenceDiagram
    participant DB as SQLite DB
    participant VLM_Script as Preprocess VLM
    participant VLM as "Ollama (Llava)"
    participant DS as PropertyDataset
    participant Enc as Encoders
    participant Train as Trainer

    rect rgb(230, 230, 255)
        Note over VLM_Script, DB: Phase 1: Preprocessing
        VLM_Script->>DB: Fetch Listings with Images
        VLM_Script->>VLM: Describe Images
        VLM-->>VLM_Script: "Modern kitchen..."
        VLM_Script->>DB: Update vlm_description
    end

    rect rgb(240, 255, 240)
        Note over Train, DS: Phase 2: Training
        Train->>DS: Request Batch
        DS->>DB: Fetch Listing + Comps + VLM Desc

        DS->>Enc: Encode Text (Title + Desc + VLM)
        DS->>Enc: Normalize Tabular Features

        DS-->>Train: Tensors (Target + Comps)
        Train->>Train: Forward Pass (Quantile Loss)
        Train->>Train: Backprop
    end
```

### Dataset Logic (`PropertyDataset`)
- **Comparison-Based**: The model is never shown a listing in isolation. It always sees:
  - **Target Listing**: The property to value.
  - **Context Set**: 5 comparable listings from the same city/neighborhood.
- **VLM Integration**: The dataset loads pre-computed VLM descriptions from the database (`vlm_description` column). This textual description is concatenated with the listing's title and description before embedding, allowing the model to "see" the condition of the property without needing to process images during training.
