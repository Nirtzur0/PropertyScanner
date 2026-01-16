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
python3 -m src.cli dashboard
```

If you want UI only:
```bash
python3 -m src.cli dashboard -- --skip-preflight
```

---

## CLI Commands
All commands run from the project root.

```bash
python3 -m src.cli preflight                 # Refresh stale data and artifacts
python3 -m src.cli schedule                  # Scheduled preflight refreshes
python3 -m src.cli harvest -- --mode sale     # Harvest listings
python3 -m src.cli transactions -- --path data/transactions.csv
python3 -m src.cli build-market               # Macro + market + hedonic data
python3 -m src.cli build-index                # Build vector index for comps
python3 -m src.cli train -- --listing-type sale
python3 -m src.cli backfill                   # Backfill cached valuations
python3 -m src.cli calibrators -- --input <samples.jsonl>
python3 -m src.cli dashboard                  # Streamlit UI
python3 -m src.cli agent "Find deals" <areas>
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
python3 -m src.cli schedule --interval-minutes 360
python3 -m src.cli schedule --cron "0 3 * * *"
```

The scheduler uses the same preflight checks, so only stale steps run.

---

## Library API (Python)
The CLI, agent, and dashboard are thin wrappers over a shared API you can call directly:

```python
from src.api import PipelineAPI

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
- **Agents**: Crawlers and normalizers in `src/agents/`.
- **Workflows**: Batch entry points in `src/workflows/` (harvest, market data, indexing, preflight).
- **Repositories**: Centralized data access in `src/repositories/` (no service-level raw SQL).
- **Services**: Valuation, forecasting, retrieval, and augmentation in `src/services/`.
- **Dashboard**: Premium UI in `src/dashboard/`.

---

## Docs
- `docs/01_system_overview.md`
- `docs/02_data_pipeline.md`
- `docs/03_model_architecture.md`

---

## Path to Production
To transition from a research MVP to a resilient, automated data product:

### 1. Industrial-Grade Scraping
- **Distributed Extraction**: Deploy agents to a containerized cluster (k8s/ECS) capabilities.
- **Resilience**: Implement robust proxy rotation and browser fingerprinting to handle anti-bot measures.
- **Orchestration**: Decouple the "preflight" logic into a proper workflow engine (Airflow, Dagster, or Prefect) for retry logic and dependency management.

### 2. Inference as a Service
- **Scalable Serving**: Move local Ollama dependencies to dedicated, auto-scaling inference endpoints (e.g., vLLM or TGI containers).
- **Model API**: Expose the `PropertyFusionModel` via a high-throughput API (FastAPI + Triton) to decouple expensive inference from the dashboard UI.

### 3. Observability & Monitoring
- **Full-Stack Telemetry**: Implement Prometheus/Grafana to track scraper yield, VLM latency, and system health.
- **Data Contracts**: Use "Great Expectations" or Pydantic validation to gate bad harvests before they pollute the data lake.
- **Drift Detection**: Monitor input distribution shifts (e.g., if a source changes its HTML structure or listing quality drops).

### 4. Continuous Training Loop
- **Automated Retraining**: Create a pipeline that automatically promotes new "Sold" listings into the training set.
- **Model Registry**: Version control model artifacts (MLflow/WandB) to track accuracy improvements over time.
- **Safe Rollouts**: Implement shadow deployment or A/B testing to validate new models against live traffic before full promotion.

### 5. Production Hardening
- **Containerization**: Dockerize all services (Crawlers, Dashboard, API).
- **CI/CD**: specific automated testing (unit, integration, and data integrity checks) on every commit.
- **Security**: Move credentials to a secrets manager (Vault/AWS Secrets Manager) and implement proper RBAC.
