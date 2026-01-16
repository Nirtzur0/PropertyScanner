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
- **Preflight orchestration** is the canonical entry point; it checks freshness and runs only what is stale.
- **Quality gates** stop bad harvests before they pollute the lake, with run logs in `pipeline_runs`.

---

## How It Works (High Level)
1) **Harvest**: crawl, normalize, fuse, and augment listings.
2) **Market data**: build macro, market indices, hedonic indices, and area intelligence.
3) **Vector index**: build FAISS for time-safe comps.
4) **Training**: train the fusion model and optional calibrators.
5) **Valuation**: comps + model + income blend + area adjustments.

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
python3 -m src.cli build-market               # Macro + market + hedonic data
python3 -m src.cli build-index                # Build vector index for comps
python3 -m src.cli train -- --listing-type sale
python3 -m src.cli backfill                   # Backfill cached valuations
python3 -m src.cli calibrators -- --input <samples.jsonl>
python3 -m src.cli dashboard                  # Streamlit UI
python3 -m src.cli agent "Find deals" <areas>
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

## Roadmap
- [ ] Negotiation agent to draft offers from valuation deltas.
- [ ] Geo-spatial feature layer (transit, parks, schools).
- [ ] Feedback loop for continuous calibration.
