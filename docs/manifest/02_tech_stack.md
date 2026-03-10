# Tech Stack

## Scope

This document captures the selected implementation stack for the current milestone packet and the alternatives considered.

## Option A: Canonical Local Runtime (Selected)

- Runtime/API/CLI: Python 3.10+ with existing module entrypoints under `src/interfaces/*`.
- Product UI: React workbench + FastAPI (`frontend/`, `src/adapters/http/app.py`).
- Legacy UI: Streamlit (`src/interfaces/dashboard/app.py`) as a deprecated compatibility surface only.
- Runtime configuration: typed runtime settings (`src/core/runtime.py`, `config/runtime.yaml`).
- Legacy module configuration: Hydra composition for older workflows (`config/app.yaml` and includes).
- Persistence: SQLite system-of-record (`data/listings.db`) + SQLAlchemy models.
- Analytics/training artifacts: DuckDB + Parquet snapshots under `data/analytics/`.
- Default local orchestration: application services (`src/application/*`) and job records (`job_runs`).
- Optional orchestration: Prefect flows (`src/platform/workflows/prefect_orchestration.py`) for legacy or scheduled paths.
- Default retrieval/product inference: structured comparable-baseline services (`src/application/valuation.py`, `src/valuation/services/valuation.py`).
- Experimental retrieval/index: LanceDB + Sentence Transformers (`src/valuation/services/retrieval.py`).
- Agent orchestration: LangGraph/LangChain + LiteLLM with ChatMock/OpenAI-compatible routing by default (`src/agentic/*`, `src/platform/utils/llm.py`).
- Listing enrichment: ChatMock/OpenAI-compatible text + vision calls by default, with explicit Ollama compatibility mode for local fallback workflows (`src/listings/services/description_analyst.py`, `src/listings/services/vlm.py`).
- Browser scraping direction: Node/TypeScript sidecar with Crawlee + Playwright (`scraper/`) driven by Python crawl-plan contracts (`src/listings/scraping/sidecar.py`).
- Legacy browser automation: pydoll-based browser engine remains only as a transitional Python path.
- Tests: Pytest marker-gated suites (`pytest.ini`, `tests/conftest.py`).

Why this option now:
- It matches the runtime that is actually serving the product today.
- It lets us hard-stop invalid fusion and ask-price sale-model behavior without rewriting the whole repo in one packet.
- It supports local-first constraints in `docs/manifest/00_overview.md`.

## Option B: More Scalable/Advanced (Deferred)

- Promote default DB runtime from SQLite to Postgres.
- Split dashboard/API/worker deployment as separate services with mandatory CI + release gates.
- Add explicit observability backend (metrics/traces collector + dashboards as code).

Why deferred:
- P0 gaps are governance/reliability artifacts, not runtime scalability bottlenecks.
- Switching default persistence now would increase risk and delay CI/observability baseline.

## Decision

Selected: **Option A** for current packet.

Decision record: `docs/manifest/03_decisions.md` (2026-02-08 prompt-02 entries).

## Dependency Category Map (Current)

- packaging/locking: `pyproject.toml`, `requirements.txt` (constraint input), `requirements.lock` (canonical install lockfile), `scraper/package.json`
- config+settings: `pydantic-settings` runtime config + Hydra for legacy workflows
- logging/telemetry: Python logging + run tables (`pipeline_runs`, `agent_runs`)
- orchestration/retries: application services + `job_runs`, optional `prefect`
- DB+migrations: `sqlalchemy`, `src/platform/migrations.py`
- validation/contracts: domain schema contracts in `src/platform/domain/schema.py`
- testing: `pytest`, markers in `pytest.ini`
- UI: `react`, `vite`, `streamlit` (legacy), `plotly`
- analytics: `duckdb`, Parquet artifact exports
- crawling/browser automation: `playwright`, `crawlee`, legacy pydoll stack in crawler modules

## Packet Follow-up

- Lockfile policy and single install-path decision are now implemented:
  - install from `requirements.lock`
  - update dependency constraints in `requirements.txt`
  - regenerate lock with `python3 -m piptools compile --resolver=backtracking --output-file requirements.lock requirements.txt`
- Keep Option B as explicit `Not now` until P0 observability/CI outcomes are complete.
