# 🏙️ Property Scanner: Multimodal AI Real Estate Valuation

> **"Comparable sales tell you the price. The Property Scanner tells you the *value*."**

Traditional automated valuation models (AVMs) look at numbers: square meters, bedroom counts, and zip codes. But real estate is visual. A "renovated kitchen" creates value that a spreadsheet row can't capture.

**Property Scanner** is an experimental AI Agent system that **"sees"** real estate. It creates a holistic valuation by fusing quantitative market data with qualitative insights extracted from property photos using Vision Multi-Modal Large Language Models (VLM).

---

## 🧠 The Brain: Multimodal Late-Fusion Model

At the heart of the system is the **PropertyFusionModel**, a custom PyTorch architecture designed to reason like a human appraiser.

### 1. The Senses (Inputs)
*   **Structured Data**: Normalized features (sqm, floor, built year, location) encoded via tabular scalers.
*   **Text & Context**: Title and descriptions encoded into dense vectors using **SentenceTransformers** (`all-MiniLM-L6-v2`).
*   **Visual Intelligence (VLM)**:
    *   We don't just crop images. We *read* them.
    *   A local **Ollama** agent (running **LLaVA**) acts as a virtual inspector, analyzing property photos to extract structured descriptions of condition, finishes, and architectural style.
*   **Semantic Extraction**:
    *   **LLaMA 3** is used to parse messy crawler text into clean, structured facts (like `has_elevator`) and perform critical sentiment analysis to filter out "marketing fluff."

### 🤖 The Model Stack
The project relies on a modular set of specialized AI models:

| Task | Model | Platform | Purpose |
| :--- | :--- | :--- | :--- |
| **Logic/Cleaning** | `llama3` | Ollama | Parses descriptions, extracts facts, and assigns sentiment. |
| **Visuals** | `llava` | Ollama | Transcribes property photos into descriptive text. |
| **Encoding** | `all-MiniLM-L6-v2` | PyTorch | Converts text into 384D mathematical vectors. |
| **Similarity** | `ViT-B-32` | OpenCLIP | (Optional) Direct image vector encoding for search. |
| **Predictions** | `PropertyFusionModel`| PyTorch | The custom "Reasoning" model that predicts fair value. |

### 2. The Logic (Architecture)
*   **Market Awareness**: The model doesn't look at a property in isolation. It takes standard comps (comparable listings) and learns the *relationship* between the target property and its market context using a **Transformer-based Cross-Attention** mechanism.
*   **Objective Function**: It is trained using **Quantile Loss**, allowing it to predict not just a single price, but a confidence interval (p10, p50, p90) representing the range of fair value.

---

## ⚙️ The Pipeline

The system operates as a set of autonomous agents and processors.

1.  **Discovery & Extraction**:
    *   `CrawlerAgents` scour target real estate portals.
    *   Raw HTML is parsed into a canonical schema using robust extractors.
    *   Data is immutable and stored in a local SQLite data lake (`data/listings.db`).

2.  **Enrichment (The "VLM Pass")**:
    *   Agents identify listings with images but no deep descriptions.
    *   They invoke the local VLM to generate "visual inspections" (e.g., *"Modern kitchen, stone countertops, good conversational light"*).

3.  **Training**:
    *   The `Trainer` creates dynamic batches of (Target + Comps).
    *   It optimizes the Fusion Model to minimize error in the median price prediction while calibrating uncertainty.

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
```

### Usage
All commands below assume you're in the project root.

#### 1. Collect Data (Bulk Harvest)
Run the bulk harvester. You **must** run in Rent mode first to build the yield estimator stats.

**Option A: Harvest Rentals (Baseline)**
*Required for Yield Estimation.*
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/harvest_batch.py --mode rent
```

**Option B: Harvest Sales (Main)**
*Finds active listings and estimates value/yield.*
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/harvest_batch.py --mode sale
```

**Clean Start (Reset DB)**
To purge the database and start fresh:
```bash
# WARNING: Deletes all data!
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/harvest_batch.py --mode sale --clean
```

#### 2. Run Orchestrator (Agent)
Ask the AI Agent to find specific properties (complex reasoning).
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/main.py "Find undervalued apartments in Madrid"
```

#### 3. Train Models
Run the training pipeline (requires data in `data/listings.db`).
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/training/train.py --epochs 10
```

#### 4. Launch Dashboard
Visualize listings, valuations, and VLM insights.
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/streamlit run src/dashboard.py
```

#### 5. Utilities
Clean data (fix timestamps/locations) or other maintenance.
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/clean_data.py
```

---

## 🔮 Future Roadmap

*   [ ] **Negotiation Agent**: An LLM that uses the valuation delta to draft offer letters.
*   [ ] **Geo-Spatial Layer**: Integration with OSM for proximity features (distance to metro/parks).
*   [ ] **RLHF for Pricing**: Fine-tuning the model based on user feedback on "good deals".
