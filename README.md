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
    *   A local **Ollama** agent (running LLaVA/BakLLaVA) acts as a virtual inspector, analyzing property photos to extract structured descriptions of condition, finishes, and architectural style.
    *   These VLM insights are fused with the listing text before embedding.

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
*   Python 3.10+
*   [Poetry](https://python-poetry.org/)
*   [Ollama](https://ollama.ai/) (for VLM features)

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/yourusername/property_scanner.git
cd property_scanner

# 2. Install dependencies
poetry install

# 3. Pull the VLM model
ollama pull llava
```

### Usage
All commands below assume you're in the project root.

#### 1. Collect Data (Real Listings)
Crawl active listings from real estate portals.
```bash
./venv/bin/python src/training/collect_data.py --target 50
```

#### 2. Train Models (Valuation + Trends)
Train the multimodal Fusion Model (Price) and TFT Forecaster (Trends).
```bash
# 2a. Train Valuation Model (requires "ollama serve" for VLM)
./venv/bin/python src/training/train.py --epochs 10

# 2b. Train Forecasting Model
./venv/bin/python src/training/forecasting_tft.py
```

#### 3. Run QA Verification
Validate the pipeline logic (monotonicity, hedonic adjustments, conformal coverage) on real data.
```bash
./venv/bin/python scripts/run_e2e_realdata_test.py --size 10
```
> Outputs JSON/HTML reports to `qa_reports/`.

#### 4. Launch Dashboard
Visualize valuations, comps, and AI descriptions.
```bash
./venv/bin/streamlit run src/dashboard.py
```

---

## 🔮 Future Roadmap

*   [ ] **Negotiation Agent**: An LLM that uses the valuation delta to draft offer letters.
*   [ ] **Geo-Spatial Layer**: Integration with OSM for proximity features (distance to metro/parks).
*   [ ] **RLHF for Pricing**: Fine-tuning the model based on user feedback on "good deals".
