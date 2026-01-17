# 🦅 The Scout V2: Agentic Property Intelligence System

> **"Comparable sales tell you the price. The Scout V2 tells you the value."**

The Scout V2 is a local-first property intelligence stack. It harvests listings, enriches them with multimodal signals, and produces investment-grade valuations that blend comps, income potential, and area intelligence.

---

## The Command Center
The dashboard is the primary interface. It is designed as a premium intelligence cockpit:
- **Atlas View** for geospatial deal discovery.
- **Investment Memo** with comps, projections, and thesis.
- **Signal Lab** for momentum, yield, and area sentiment.
- **Pipeline Freshness** so you always know what is stale and what is live.

---

## What Makes It Different
- **Multimodal fusion model** (PropertyFusionModel) predicts log-residuals over a robust comp baseline.
- **Income-aware valuation** blends rent estimates with market yield to reward higher rental alpha.
- **Area intelligence** adds sentiment and development signals from market indices.
- **Sold-price training labels** prefer transaction prices for sales and keep rent labels aligned to rent indices.
- **Preflight orchestration** is the canonical entry point; it checks freshness and runs only what is stale.
- **Quality gates** stop bad harvests before they pollute the lake, with run logs in `pipeline_runs`.

---

## How It Works (High Level)
1) **Harvest**: crawl, normalize, fuse, and augment listings.
2) **Transactions**: ingest sold/registry data to ground truth sales labels.
3) **Market data**: build macro, market indices, hedonic indices, and area intelligence.
4) **Vector index**: build FAISS for time-safe comps.
5) **Training**: train the fusion model and optional calibrators.
6) **Valuation**: comps + model + income blend + area adjustments.

---

## Quick Start

### 0) Start Ollama (required for local LLM/VLM)
```bash
ollama serve
```

### 1) Install dependencies
```bash
# Option A (Poetry)
poetry install

# Option B (pip)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Launch the dashboard (runs preflight by default)
```bash
python3 -m src.interfaces.cli dashboard
```

If you want UI only:
```bash
python3 -m src.interfaces.cli dashboard -- --skip-preflight
```

---

## CLI Commands
All commands run from the project root.

```bash
python3 -m src.interfaces.cli preflight                 # Refresh stale data and artifacts
python3 -m src.interfaces.cli schedule                  # Scheduled preflight refreshes
python3 -m src.interfaces.cli harvest -- --mode sale     # Harvest listings
python3 -m src.interfaces.cli transactions -- --path data/transactions.csv
python3 -m src.interfaces.cli build-market               # Macro + market + hedonic data
python3 -m src.interfaces.cli build-index                # Build vector index for comps
python3 -m src.interfaces.cli train -- --listing-type sale
python3 -m src.interfaces.cli backfill                   # Backfill cached valuations
python3 -m src.interfaces.cli calibrators -- --input <samples.jsonl>
python3 -m src.interfaces.cli dashboard                  # Streamlit UI
python3 -m src.interfaces.cli agent "Find deals" <areas>
```

## Additional Sources (UK + Italy)
The agent crawler/normalizer stack now includes:
- **Rightmove (UK)**: `rightmove_uk` source id. Rightmove caps search pagination at 42 pages; split searches by smaller geos or multiple URLs.
- **Zoopla (UK)**: `zoopla_uk` source id. Zoopla listings API is not public; this integration scrapes HTML/JSON-LD.
- **Immobiliare.it (Italy)**: `immobiliare_it` source id. Uses HTML snapshots; optional Insights APIs can enrich later.

Local harness (writes normalized JSON/JSONL without touching the full pipeline):

```bash
python3 scripts/source_harness.py --source rightmove_uk --search-url "<RIGHTMOVE_SEARCH_URL>" --output data/rightmove.jsonl --jsonl
python3 scripts/source_harness.py --source zoopla_uk --search-url "<ZOOPLA_SEARCH_URL>" --output data/zoopla.jsonl --jsonl
python3 scripts/source_harness.py --source immobiliare_it --search-url "<IMMOBILIARE_SEARCH_URL>" --output data/immobiliare.jsonl --jsonl
```

---

## Automation (Scheduler)
Preflight is the canonical automation entry point. Run the scheduler to keep the pipeline fresh:

```bash
python3 -m src.interfaces.cli schedule --interval-minutes 360
python3 -m src.interfaces.cli schedule --cron "0 3 * * *"
```

The scheduler uses the same preflight checks, so only stale steps run.

---

## Library API (Python)
The CLI, agent, and dashboard are thin wrappers over a shared API you can call directly:

```python
from src.interfaces.api import PipelineAPI

api = PipelineAPI()
api.preflight()
api.harvest(mode="sale", target_count=1000)
api.ingest_transactions(path="data/transactions.jsonl")
api.build_market_data()
api.build_vector_index(listing_type="sale")
analysis = api.evaluate_listing_id("listing-id", persist=True)
```

---

## Core Components
- **Interfaces**: CLI, API, and dashboard entry points in `src/interfaces/`.
- **Agentic**: LangGraph tools, orchestrator, and analyst agents in `src/agentic/`.
- **Listings**: Crawlers, normalizers, listing services, and harvest workflows in `src/listings/`.
- **Market**: Macro/indices/registry signals in `src/market/`.
- **Valuation**: Retrieval + valuation services/workflows in `src/valuation/`.
- **ML**: Models/encoders and training pipelines in `src/ml/`.
- **Platform**: Config, storage, migrations, pipeline state/runs in `src/platform/`.

---

## Docs
- `docs/01_system_overview.md`
- `docs/02_data_pipeline.md`
- `docs/03_model_architecture.md`
