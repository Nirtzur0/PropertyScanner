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
    *   The `Trainer` creates dynamic batches of (Target + Comps) using strict geo + property_type + size filters.
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
By default, `harvest_batch.py` builds a Spain-wide (province-level) area list from Pisos.com's `mapaweb` pages to avoid geo-redirects to a single city. To scope the crawl, pass `--start-url` (single area) or `--areas-file` (JSON list of start URLs).
The harvester de-dupes URLs using a disk-backed store at `data/harvest_seen_urls.sqlite3` to keep memory usage stable even for very large crawls.

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
Example: harvest only Madrid sales:
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/harvest_batch.py --mode sale --start-url "https://www.pisos.com/venta/pisos-madrid/"
```

**Option C: Clean Start (Reset & Restart)**
If you want to wipe the local database (`data/listings.db`), harvest state, and URL de-dupe store to start from scratch:
```bash
# WARNING: This deletes all previously collected data!
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/harvest_batch.py --mode sale --clean
```
Note: You can use `--clean` with either `--mode sale` or `--mode rent`.

Tip: If you run out of memory, reduce parallelism and/or batch size:
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/harvest_batch.py --mode sale --max-workers 1 --process-batch-size 10 --no-vlm
```

#### 1b. Build Indices (for Projections)
Price/rent projections use market + macro time series. After harvesting, build/update them:
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/build_market_data.py
```

#### 1c. Build Vector Index (for Comps)
Comparable retrieval requires the FAISS vector index:
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/build_vector_index.py
```

#### 2. Run Orchestrator (Agent)
Ask the AI Agent to find specific properties (complex reasoning).
Requires at least one explicit area/URL.
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/main.py "Find undervalued apartments in Madrid" "https://www.pisos.com/venta/pisos-madrid/"
```

#### 3. Train Models
Run the training pipeline (requires data in `data/listings.db`).
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/training/train.py --epochs 10
```
This writes `models/fusion_model.pt` and `models/fusion_config.json`.

#### 4. Launch Dashboard
Visualize listings, valuations, and VLM insights.
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/streamlit run src/dashboard.py
```
Tip: For large databases, precompute/cache valuations (includes price/rent/yield projections) so the dashboard doesn’t re-run models on every refresh:
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/backfill_valuations.py --listing-type sale
```

#### 5. Utilities
Fix metadata, timestamps, or geocoding issues in the existing data (does **not** delete records).
```bash
export PYTHONPATH=$PYTHONPATH:. && ./venv/bin/python src/scripts/clean_data.py
```

---

## 🔮 Future Roadmap

*   [ ] **Negotiation Agent**: An LLM that uses the valuation delta to draft offer letters.
*   [ ] **Geo-Spatial Layer**: Integration with OSM for proximity features (distance to metro/parks).
*   [ ] **RLHF for Pricing**: Fine-tuning the model based on user feedback on "good deals".
