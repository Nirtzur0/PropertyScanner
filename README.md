# 🦅 The Scout V2: Agentic Property Intelligence System

> **"Comparable sales tell you the price. The Scout V2 tells you the value."**

The Scout V2 is a local-first property intelligence stack. It crawls listings, enriches them with multimodal signals, and produces investment-grade valuations that blend comps, income potential, and area intelligence.

---

## The Command Center
The dashboard is the primary interface. It is designed as a premium intelligence cockpit:
- **Atlas View** for geospatial deal discovery.
- **Investment Memo** with comps, projections, and thesis.
- **Signal Lab** for momentum, yield, and area sentiment.
- **Pipeline Freshness** so you always know what is stale and what is live.
- **Mission Control** lets you ask for what you need; the AI picks the best deals and explains why.
- **User controls are minimal**: country, city, budget, property type. Ranking and lens logic are AI-managed.

---

## What Makes It Different
- **Multimodal fusion model** predicts log-residuals over a robust comp baseline.
- **Time-safe comps** with retriever metadata enforcement (model + VLM policy).
- **Income-aware valuation** blends rent estimates with local yield distributions and comp coverage weighting.
- **Area intelligence** adds sentiment/development signals with credibility and freshness scaling.
- **Sold-price training labels** prefer transaction prices; rent labels normalize to rent indices.
- **Preflight orchestration** is the canonical entry point; it checks freshness and runs only what is stale (Prefect flow or direct runner).
- **Quality gates** stop bad crawls before they pollute the lake, with run logs in `pipeline_runs`.

---

## How It Works (High Level)
1) **Crawl backfill**: crawl, normalize, fuse, and augment listings.
2) **Transactions**: ingest sold/registry data to ground truth sales labels.
3) **Market data**: build macro, market indices, hedonic indices, and area intelligence.
4) **Vector index**: build FAISS or LanceDB for time-safe comps.
5) **Training**: train the fusion model (time+geo splits available) and optional calibrators.
6) **Valuation**: time-adjusted comps + fusion residuals + income blend + area adjustments.

---

## Quick Start

### 0) Start Ollama (required for local LLM/VLM features)
```bash
ollama serve
```

If you want a hosted model instead, update `config/llm.yaml` and set the provider API key (e.g., `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

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
python3 -m src.interfaces.cli prefect preflight         # Prefect flow (retries + caching + UI)
python3 -m src.interfaces.cli schedule                  # Scheduled preflight refreshes
python3 -m src.interfaces.cli unified-crawl              # Crawl listings via unified runner
python3 -m src.interfaces.cli transactions -- --path data/transactions.csv
python3 -m src.interfaces.cli build-market               # Macro + market + hedonic data
python3 -m src.interfaces.cli build-index                # Build vector index for comps (FAISS/LanceDB)
python3 -m src.interfaces.cli train -- --listing-type sale
python3 -m src.interfaces.cli backfill                   # Backfill cached valuations
python3 -m src.interfaces.cli calibrators -- --input <samples.jsonl>
python3 -m src.interfaces.cli dashboard                  # Streamlit UI
python3 -m src.interfaces.cli agent "Find deals" <areas>
```

Vector backend note:
- Set `valuation.retriever_backend: lancedb` (and `valuation.retriever_lancedb_path`) to use LanceDB.
- Or override at runtime with `python3 -m src.interfaces.cli build-index -- --backend lancedb`.

## Crawler Status (Quick View)
Status reflects current parsing tests and known live-crawl behavior. Live crawling can vary with rate limits and anti-bot defenses.

| Source id | Region | Status | Notes |
| --- | --- | --- | --- |
| idealista | ES | flaky live | Parsing tests pass; live crawling is often blocked by anti-bot defenses. |
| pisos | ES | works | Parsing tests pass; live crawling is rate limited. |
| rightmove_uk | UK | works | HTML/JSON-LD; pagination limit (42 pages). |
| zoopla_uk | UK | works | HTML/JSON-LD; no public API. |
| immobiliare_it | IT | works | HTML snapshots; Insights API optional. |

---

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

## Automation (Prefect + Scheduler)
Preflight is the canonical automation entry point. Use Prefect for observability or the legacy scheduler for simple intervals.

Prefect (local UI):

```bash
prefect server start
python3 -m src.interfaces.cli prefect preflight
```

Legacy APScheduler:

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
api.crawl_backfill(max_pages=1)
api.ingest_transactions(path="data/transactions.jsonl")
api.build_market_data()
api.build_vector_index(listing_type="sale")
analysis = api.evaluate_listing_id("listing-id", persist=True)
```

---

## System components
- **Interfaces**: CLI, API, and dashboard entry points live in `src/interfaces/`.
- **Agents**: LangGraph tools, the orchestrator, and analyst agents live in `src/agentic/`.
- **Listings**: Crawlers, normalizers, listing services, and crawl workflows live in `src/listings/`.
- **Market**: Macro/indices/registry signals live in `src/market/`.
- **Valuation**: Retrieval + valuation services/workflows live in `src/valuation/`.
- **ML**: Models/encoders and training pipelines live in `src/ml/`.
- **Platform**: Config, storage, migrations, pipeline state/runs live in `src/platform/`.
- **Scripts**: Workflow wrappers and debug tooling live in `scripts/`.

---

## Docs
- `docs/00_docs_index.md` (start here)
- `docs/01_system_overview.md`
- `docs/02_data_pipeline.md`
- `docs/03_unified_scraping_architecture.md`
- `docs/04_services_map.md`
- `docs/05_agents_map.md`
- `docs/06_agent_workflow.md`
- `docs/07_model_architecture.md`
- `docs/08_path_to_production.md`
