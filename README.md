# 🦅 The Scout V2: Agentic Property Valuation System

> **"Comparable sales tell you the price. The Scout V2 tells you the *value*."**

Traditional automated valuation models (AVMs) look at numbers: square meters, bedroom counts, and zip codes. But real estate is visual and contextual. A "renovated kitchen" creates value that a spreadsheet row can't capture.

**The Scout V2** is an experimental AI Agent system that **"sees"** real estate. It creates a holistic valuation by fusing quantitative market data with qualitative insights extracted from property photos using Vision Multi-Modal Large Language Models (VLM).

---

## 🦅 The New "Command Center"
The system now features a **state-of-the-art Dashboard** designed with a "Luxurious Utility" philosophy ("Midnight Gold" theme). It serves as an Investment Command Center:
*   **Strategic Map**: Heatmaps overlaid with deal opportunities.
*   **Investment Memo**: Auto-generated deal sheets with projected yield, fair value, and comparisons.
*   **AI Vision Analysis**: Side-by-side comparison of agent descriptions vs. VLM visual inspections.

---

## 🧠 The Brain: Multimodal Late-Fusion Model

At the heart of the system is the **PropertyFusionModel**, a custom PyTorch architecture designed to reason like a human appraiser.

### 1. The Senses (Inputs)
*   **Structured Data**: Verified specs (sqm, floor, built year).
*   **Official Ground Truth**: Anchored by **INE (Instituto Nacional de Estadística)** housing indices and **ERI (Registral Statistics)** for liquidity verification.
*   **Visual Intelligence (VLM)**: A local **Ollama (LLaVA)** agent acts as a virtual inspector, analyzing property photos to extract structured descriptions of condition and finishes.

### 🤖 The Model Stack
The project relies on a modular set of specialized AI models:

| Task | Model | Platform | Purpose |
| :--- | :--- | :--- | :--- |
| **Logic/Cleaning** | `llama3` | Ollama | Parses descriptions, extracts facts, and assigns sentiment. |
| **Orchestrator** | `gpt-oss` | Ollama | Cognitive agent supervisor (custom model). |
| **Visuals** | `llava` | Ollama | Transcribes property photos into descriptive text. |
| **Encoding** | `all-MiniLM-L6-v2` | PyTorch | Converts text into 384D mathematical vectors. |
| **Predictions** | `PropertyFusionModel`| PyTorch | Cross-attention model that predicts log-residuals over a robust comp baseline (anchored by INE). |

---

## ⚙️ The Pipeline

The system operates as a set of autonomous agents and processors.

1.  **Discovery & Ingestion**:
    *   `CrawlerAgents` scour target real estate portals.
    *   **OfficialSourcesAgent** fetches authenticated government stats (INE IPV, ERI Transactions) to serve as macro anchors.
    *   Data is immutable and stored in a local SQLite data lake (`data/listings.db`).

2.  **Enrichment (The "VLM Pass")**:
    *   Agents identify listings with images but no deep descriptions.
    *   They invoke the local VLM to generate "visual inspections" (e.g., *"Modern kitchen, stone countertops, good conversational light"*).

3.  **Valuation & Intelligence**:
    *   **HedonicIndexService** computes time-adjustments, falling back to INE indices if local data is sparse.
    *   **ERISignalsService** validates liquidity assumptions against real registry volume.
    *   The model predicts a probability distribution (p10/p50/p90) for fair value.

---

## 🚀 Getting Started

### Prerequisites

### 0. Start Ollama (Required)
The AI engine needs to be running in the background.
```bash
ollama serve
```

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/yourusername/property_scanner.git
cd property_scanner

# 2. Install dependencies
poetry install

# 3. Pull the required models
ollama pull llava
ollama pull llama3
ollama pull gpt-oss # Or: ollama cp llama3 gpt-oss
```

### Usage
All commands below assume you're in the project root. Use the unified CLI to wrap core scripts:
`python -m src.cli <command> -- [args]`

#### 1. Collect Data (Bulk Harvest)
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python -m src.cli harvest -- --mode sale
```

#### 1b. Build Market Data (Official & Derived)
This step now ingests **INE & ERI Government Data** and builds hedonic indices.
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python -m src.cli build-market
```

#### 1c. Build Vector Index (for Comps)
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python -m src.cli build-index --model-name all-MiniLM-L6-v2
```

#### 2. Train Models
Run the training pipeline (requires data + indices).
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python -m src.cli train --listing-type sale --normalize-to latest
```

#### 3. Launch "The Scout V2" Dashboard
Visualize listings, valuations, and VLM insights in the new Command Center.
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python -m src.cli dashboard
```

---

## 🔮 Future Roadmap

*   [ ] **Negotiation Agent**: An LLM that uses the valuation delta to draft offer letters.
*   [ ] **Geo-Spatial Layer**: Integration with OSM for proximity features (distance to metro/parks).
*   [ ] **RLHF for Pricing**: Fine-tuning the model based on user feedback on "good deals".
