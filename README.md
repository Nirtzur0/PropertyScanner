# 🦅 Property Scanner: The Scout V2

> **Comparable sales tell you the price. The Scout tells you the story.**

**Property Scanner (The Scout V2)** is a local-first, agentic property intelligence stack. It crawls listings, enriches them with multimodal and market signals, and produces valuations that blend **time-safe comps**, **income potential**, and **area intelligence**.

If you like your deal flow like your espresso: strong, fast, and mildly judgmental, you’re in the right place.

---

## What You Get

- **Scout dashboard** (Streamlit): Deal Flow, Atlas map, Investment Memo, Signal Lab, Pipeline Status.
- **Canonical orchestration**: `preflight` checks freshness and runs only what’s stale.
- **Unified crawler**: multi-source scraping with quality gates so bad data doesn’t pollute the lake.
- **Time-safe comp retrieval**: LanceDB-backed vector index + metadata locks.
- **Fusion valuation**: comp baseline + residual model + income blend + area adjustments.
- **Agents**: a cognitive orchestrator that can plan work, ask for approval on sensitive steps, and explain picks.

---

## What Makes It Different (The “No, Really” Bits)

- **Multimodal fusion model** predicts log-residuals on top of a robust comp baseline.
- **Time-safe comps** with retriever metadata enforcement (encoder + VLM policy locks).
- **Income-aware valuation** blends rent estimates with local yield distributions and comp coverage weighting.
- **Area intelligence** adds sentiment/development signals with credibility and freshness scaling.
- **Sold-price labels preferred**: training labels favor transaction prices when available.
- **Preflight orchestration is canonical**: freshness checks first, work only if stale.
- **Quality gates + run logs**: bad crawls stop early; everything is recorded in `pipeline_runs`.

---

## How It Works (60 Seconds)

1. **Crawl backfill**: crawl listings, normalize, fuse signals, augment, persist.
2. **Transactions**: ingest sold/registry data so “sale” labels are real, not vibes.
3. **Market data**: build macro signals, market indices, hedonic indices, and area intelligence.
4. **Vector index**: build the LanceDB comp index with time-safe metadata locks.
5. **Training**: train the fusion model (time+geo splits supported).
6. **Valuation**: time-adjusted comps + fusion residuals + income blend + area adjustments.

---

## UI Tour (With Real UI Examples)

The Scout UI keeps controls minimal and intent maximal: pick your **lens** (country/city/type/budget), then let the system rank and explain.

### Example 1: “Scout Command” (Mission Control)

In the UI’s **Scout Command** box you’ll see built-in examples like:

```text
💰 High Yield deals
📉 Undervalued gems
🚀 High Momentum
📍 Only Barcelona
```

Pick one, and the orchestrator will propose (and sometimes auto-run) a plan, then return:
- **Scout Picks** (curated shortlist for your current lens)
- **Deal Flow** sorted for your current strategy (Balanced/Yield/Value/Momentum)
- Optional **Agent Lens** blocks (comparison table, deal score chart, map focus)

### Example 2: “Signal Lab” (Explain The Landscape)

Open **Insights → 🧪 Signal Lab** and you get a scatter plot (Yield vs Value Delta, colored by Deal Score).

```text
Lasso a cluster → drill down into the exact listings behind the pattern.
```

It’s the quickest way to answer: “Are we seeing one weird outlier… or a whole pocket of mispricing?”

---

## Quick Start (Choose Your Adventure)

Prereqs:
- Python 3.10+ (Docker image uses 3.10)
- For dynamic sources: Playwright browsers (`python3 -m playwright install`)
- Optional: Ollama for local LLM/VLM features (`ollama serve`)

### A) “Show me deals” (Dashboard)

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python3 -m playwright install

python3 -m src.interfaces.cli dashboard
```

Notes:
- The dashboard **runs `preflight` by default**. To launch UI only: `python3 -m src.interfaces.cli dashboard -- --skip-preflight`
- If you use local LLM/VLM features via Ollama: `ollama serve` (then see `config/llm.yaml`)
- Convenience: `./run_dashboard.sh` kills port `8501` and launches the dashboard

### B) “Run the pipeline” (Preflight)

```bash
python3 -m src.interfaces.cli preflight
```

Preflight is the canonical entry point. It checks freshness and only runs what’s stale: crawl, transactions, market data, vector index, training, backfill, calibrators (as configured).

### C) “Just run it in Docker” (Dashboard on `:8505`)

```bash
docker compose up --build dashboard
```

---

## CLI Cheat Sheet

All commands run from the project root:

```bash
python3 -m src.interfaces.cli dashboard                  # Streamlit UI (runs preflight by default)
python3 -m src.interfaces.cli preflight                  # Refresh stale data and artifacts (Prefect flow)
python3 -m src.interfaces.cli unified-crawl              # Unified multi-source crawl
python3 -m src.interfaces.cli transactions -- --path data/transactions.csv
python3 -m src.interfaces.cli market-data                # Macro + market + hedonic + area intelligence
python3 -m src.interfaces.cli build-index                # Build comp vector index (LanceDB)
python3 -m src.interfaces.cli train                      # Train fusion model
python3 -m src.interfaces.cli train-pipeline             # VLM prep + fusion training (Prefect flow)
python3 -m src.interfaces.cli backfill                   # Backfill cached valuations (Prefect flow)
python3 -m src.interfaces.cli calibrators -- --input <samples.jsonl>
python3 -m src.interfaces.cli agent "Find deals" <areas>
python3 -m src.interfaces.cli migrate                    # DB schema migrations
```

Vector backend note:
- LanceDB is the default retriever backend. Customize paths via `config/paths.yaml` and `config/valuation.yaml`.

---

## Configuration (The Knobs That Matter)

Configuration is Hydra-composed via `config/app.yaml`. The most-used files:

| File | What it controls | You’ll change it when… |
| --- | --- | --- |
| `config/paths.yaml` | data/model/index locations (and env var overrides) | you want the DB/index somewhere else |
| `config/sources.yaml` | enabled sources + crawl defaults | you’re turning sources on/off or tuning crawl limits |
| `config/llm.yaml` | LiteLLM fallback list (Ollama/Gemini/OpenAI/etc.) | you’re switching models/providers |
| `config/valuation.yaml` | retriever + valuation policy | you’re changing comp/index behavior |
| `config/quality_gate.yaml` | “stop the crawl if it’s garbage” thresholds | a source got flaky or stricter validation is needed |

Path overrides are supported via env vars (examples):
- `PROPERTY_SCANNER_DATA_DIR`
- `PROPERTY_SCANNER_DB_PATH`
- `PROPERTY_SCANNER_VECTOR_INDEX_PATH`

---

## Data And Artifacts (What Shows Up On Disk)

Most of the system of record is SQLite-backed, plus a few model/index artifacts:

| Artifact | What it is | Produced by |
| --- | --- | --- |
| `data/listings.db` | listings + derived tables + run logs | pipeline workflows + `StorageService` |
| `data/unified_seen_urls.sqlite3` | URL de-dupe store | unified crawler |
| `data/vector_index.lancedb` | comp retriever index | `build-index` |
| `data/vector_metadata.json` | retriever metadata lock | `build-index` |
| `data/models/*` | model artifacts (quantiles, calibrators, etc.) | training/calibration workflows |

For the full “what depends on what” map: `docs/02_data_pipeline.md`.

---

## Crawler Status

Live crawling can vary with rate limits and anti-bot defenses. The short version:

| Source id | Region | Status | Notes |
| --- | --- | --- | --- |
| `idealista` | ES | flaky live | parsing tests pass; live crawling often blocked |
| `pisos` | ES | works | rate limited |
| `rightmove_uk` | UK | works | pagination limit (42 pages) |
| `zoopla_uk` | UK | works | HTML/JSON-LD; no public API |
| `immobiliare_it` | IT | works | HTML snapshots; optional Insights APIs later |

The longer, constantly-updated version lives in `docs/crawler_status.md`.

Local harness (writes normalized JSON/JSONL without touching the full pipeline):

```bash
python3 scripts/source_harness.py --source rightmove_uk --search-url "<RIGHTMOVE_SEARCH_URL>" --output data/rightmove.jsonl --jsonl
python3 scripts/source_harness.py --source zoopla_uk --search-url "<ZOOPLA_SEARCH_URL>" --output data/zoopla.jsonl --jsonl
python3 scripts/source_harness.py --source immobiliare_it --search-url "<IMMOBILIARE_SEARCH_URL>" --output data/immobiliare.jsonl --jsonl
```

---

## Automation (Prefect)

If you want observability, retries, run history, and scheduling, use Prefect:

```bash
prefect server start
python3 -m src.interfaces.cli preflight
python3 -m src.interfaces.cli prefect deploy
prefect agent start -q default
```

---

## Library API (Python)

The CLI, agent, and dashboard are thin wrappers over a shared API:

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

## Repo Map (Where Things Live)

- `src/interfaces/`: CLI, API, and dashboard entry points
- `src/agentic/`: LangGraph tools + cognitive orchestrator + agent memory
- `src/listings/`: crawlers, normalizers, listing services, crawl workflows
- `src/market/`: macro/indices/registry signals + workflows
- `src/valuation/`: retrieval + valuation services/workflows
- `src/ml/`: models/encoders + training pipelines
- `src/platform/`: config, storage, migrations, pipeline state/runs
- `scripts/`: workflow wrappers + debug harnesses

---

## Docs

Start here: `docs/00_docs_index.md`

- `docs/01_system_overview.md` (system map + services)
- `docs/02_data_pipeline.md` (artifacts + quality gates + run order)
- `docs/03_unified_scraping_architecture.md` (scraping stack internals)
- `docs/05_agents_map.md` + `docs/06_agent_workflow.md` (agent contracts + flow)
- `docs/07_model_architecture.md` (ML and valuation inputs)
- `docs/08_path_to_production.md` (reliability, ops, productionization)
