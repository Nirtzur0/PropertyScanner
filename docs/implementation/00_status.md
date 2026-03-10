# Implementation Status

## Product Validation And Recovery Packet (2026-03-10)

- Objective: make the current product packet internally consistent by fixing the failing local contract gate, turning browser-crawl failures into explicit diagnosable outcomes, reducing `pisos` parser corruption at the source, and replacing train/benchmark `--research-only` gating with explicit dataset-readiness behavior.
- This step advances objective by: rebaselining the listing-quality reason taxonomy in tests and runtime, propagating browser batch failures through `FetchResult` and crawler `errors`, hardening `pisos` price/surface parsing against mixed price-box noise and out-of-range area captures, and surfacing sale-model readiness directly from DB truth instead of a hidden compatibility flag.
- Risks of misalignment: if browser-task failures still collapse into empty crawler errors, or if sale training/benchmarking pretend to be runnable without sold labels, the product continues to look flaky even when the core site and valuation path are healthy.
- Cycle stage: `build`
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - aligned the stale quality-gate unit test with the stricter runtime taxonomy and added explicit coverage for:
    - missing coordinates,
    - missing vs out-of-range surface area
  - made browser batch failures explicit all the way through the scrape stack:
    - `BrowserFetchResult.error`
    - `FetchResult.error`
    - crawler error surfaces now prefer structured browser failure codes over generic `fetch_failed:<url>`
  - added sequential fallback after failed browser batch fetches so detail pages can still recover under lower concurrency
  - tuned the Rightmove crawler to use lower browser concurrency and shorter default browser wait time
  - hardened `PisosNormalizerAgent` against the two live corruption patterns seen in the DB:
    - price boxes that concatenate the main sale price with `€/m²`
    - loose `m2` fallback captures that produced out-of-range surface areas
  - changed train/benchmark readiness behavior:
    - `--research-only` is now deprecated compatibility only
    - sale flows resolve `label_source=auto` to sold-label mode
    - sale flows fail fast with explicit readiness diagnostics when closed-sale thresholds are unmet
  - updated product docs for the new readiness-gated train/benchmark contract:
    - `README.md`
    - `docs/reference/cli.md`
- In progress:
  - none

### Next

- Backfill or refresh live `pisos` rows so the parser fixes reduce ES degradation in the actual served corpus, not just on new ingests and tests.

### Not now

- No historical DB cleanup/migration packet in this slice.
- No attempt to make sale-model training genuinely runnable without sold-label data.

### Blocked

- The live DB still has `4737` sale rows and `0` closed-sale labels, so sale training/benchmarking remain correctly blocked by readiness.
- Existing corrupted `pisos` rows already stored in `data/listings.db` are not rewritten by the parser fix alone.

### Verification commands run

- `venv/bin/python -m pytest tests/unit/listings/quality_gate/test_listing_quality_gate__validate_listing__returns_reasons.py tests/unit/listings/normalizers/test_pisos__inline_html__extracts_fields.py tests/unit/listings/scraping/test_scrape_client__batch_error_propagation.py tests/unit/listings/crawlers/test_rightmove_crawler__structured_fetch_errors.py tests/unit/ml/test_training_and_benchmark_policy.py -q`
- `venv/bin/python -m pytest -m "not integration and not e2e and not live" -q`
- `venv/bin/python -m pytest --run-integration -m integration -q`
- `venv/bin/python -m pytest --run-e2e -m e2e -q`
- `venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py --run-live -q`
- `venv/bin/python -m pytest tests/live/scrapers/test_pisos_real_live.py tests/live/scrapers/test_rightmove_real_live.py --run-live -q`
- `npm run build` (in `frontend/`)
- `npm run build` (in `scraper/`)
- `venv/bin/python -m src.interfaces.cli -h`
- `venv/bin/python -m src.ml.training.train --help`
- `venv/bin/python -m src.ml.training.benchmark --help`
- `venv/bin/python -m src.ml.training.train`
- `venv/bin/python -m src.ml.training.benchmark`
- `venv/bin/python -m src.interfaces.cli api --host 127.0.0.1 --port 8771`
- `curl http://127.0.0.1:8771/api/v1/health`
- `curl http://127.0.0.1:8771/api/v1/sources`
- `curl http://127.0.0.1:8771/api/v1/workbench/explore?country=PT&limit=10`
- `curl http://127.0.0.1:8771/api/v1/workbench/listings/4407e016fedf87c111257f9fa662083b/context`
- `curl -X POST http://127.0.0.1:8771/api/v1/valuations ... listing_id=4407e016fedf87c111257f9fa662083b persist=false`
- `curl -X POST http://127.0.0.1:8771/api/v1/valuations ... listing_id=55b4232e50a23b1855d3d64ff93ffb84 persist=false`

## M9 / C-10 Fallback Interval Policy Packet (2026-03-10)

- Objective: close the weak-regime interval-policy gap by making bootstrap fallback triggers explicit in runtime logic, valuation evidence, pipeline trust surfaces, and operator docs.
- This step advances objective by: promoting segmented conformal to an explicit primary mode with deterministic bootstrap fallback for unseen, under-sampled, or under-covered segments; persisting fallback reasons and diagnostics in valuation evidence; and replacing the pipeline `jackknife_fallback` gap badge with a policy-backed caution badge.
- Risks of misalignment: if fallback behavior remains implicit or sample-only, operators can over-trust low-coverage segments and milestone `M9` stays blocked behind a docs/runtime contradiction.
- Cycle stage: `build`
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - added a shared interval-policy decision helper in `src/valuation/services/conformal_calibrator.py`:
    - `calibrated` only when the segment is seen, `n_samples >= 20`, and `coverage_rate >= coverage_floor`
    - `bootstrap` for `unseen_segment`, `insufficient_samples`, and `coverage_below_floor`
  - routed both spot and projection interval selection through the shared policy helper in `src/valuation/services/valuation.py`
  - persisted fallback visibility in valuation evidence:
    - `EvidencePack.calibration_fallback_reason`
    - numeric `calibration_diagnostics` trigger fields
  - updated runtime trust badges in `src/interfaces/api/pipeline.py` so `jackknife_fallback` is now a `caution`, not a `gap`
  - updated runbook, literature, interpretation, decision, and alignment docs to map `lit-jackknifeplus-2021` to the shipped runtime policy
  - marked the `Prompt-02` `C-10` line complete in `docs/implementation/checklists/02_milestones.md`
- In progress:
  - `M9` remains open until the prompt-03 follow-up closes routing evidence and explicitly carries `C-11`/`C-12`

### Next

- Run the prompt-03 follow-up packet for `M9` closure evidence, then decide whether `C-11` or `C-12` is the next small corrective packet.

### Not now

- No retriever ablation cadence policy in this packet.
- No decomposition re-evaluation trigger policy in this packet.

### Blocked

- None at the runtime/test level after the focused `C-10` packet.

## Backend Recovery Packet: Data Contracts, Research Gates, and Scraper Sidecar Scaffold (2026-03-10)

- Objective: stop the backend from continuing invalid sale-model and crawl assumptions while laying the first real Bronze/Silver/Gold and sidecar foundations.
- This step advances objective by: tightening listing ingestion contracts, persisting raw/normalized observations into `listing_observations`, exporting Parquet analytics artifacts for quality and benchmark datasets, re-enabling robots enforcement, freezing fusion train/benchmark paths behind explicit research-only gates, and adding a buildable Node/TypeScript scraper sidecar contract.
- Risks of misalignment: if invalid rows still persist silently, sale-model commands still run on ask-price-only data, or the crawl stack remains Python-browser-only without a transition path, the product keeps accumulating operational debt faster than the new UI/runtime can repay it.
- Cycle stage: `build`
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - strengthened the crawl-time listing quality gate to enforce identifier, price, area, room-count, currency, listing-type, and location contracts:
    - `src/listings/services/quality_gate.py`
  - wired Bronze/Silver/Gold-ish persistence into live crawl flow:
    - raw fetches persist as `bronze_raw`,
    - validated canonicals persist as `silver_validated`,
    - rejected canonicals persist as `silver_rejected`,
    - canonical source/entity links persist into `listing_entities`:
      - `src/listings/services/observation_persistence.py`
      - `src/listings/workflows/unified_crawl.py`
  - re-enabled robots enforcement in the shared compliance manager:
    - `src/platform/utils/compliance.py`
  - added the local analytics artifact layer for Parquet + JSON metadata exports and used it for source-quality audits and benchmark datasets:
    - `src/application/analytics.py`
    - `src/application/container.py`
    - `src/application/pipeline.py`
  - blocked invalid sale-model/fusion paths by default:
    - fusion training now requires `--research-only`,
    - fusion benchmarking now requires `--research-only`,
    - sale training/benchmarking require closed-sale readiness and sold-label mode:
      - `src/ml/training/policy.py`
      - `src/ml/training/train.py`
      - `src/ml/training/benchmark.py`
  - added the first real Python-to-Node sidecar crawl contract and a buildable Crawlee + Playwright sidecar:
    - `src/listings/scraping/sidecar.py`
    - `scraper/package.json`
    - `scraper/tsconfig.json`
    - `scraper/src/index.ts`
  - updated runtime docs to match the new canonical direction:
    - `README.md`
    - `docs/manifest/02_tech_stack.md`
    - `docs/explanation/scraping_architecture.md`
    - `docs/reference/cli.md`
- In progress:
  - none

### Next

- Migrate the first browser-heavy sources (`pisos`, `rightmove`, `zoopla`, `imovirtual`) from the legacy Python browser stack onto the new sidecar fetch contract, then replace the sale benchmark with a true closed-label quantile baseline instead of the old fusion-vs-tree product narrative.

### Not now

- No full Alembic migration stack in this packet.
- No complete transaction-match confidence pipeline in this packet.
- No product promotion of the sidecar yet; the contract and buildable runtime are in place first.

### Blocked

- The live SQLite corpus is still dominated by corrupted `pisos` rows, so the new contract/persistence gates stop future damage but do not clean the historical backlog by themselves.
- Sale-model production benchmarking remains blocked by zero closed-sale labels in the live DB.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/listings/services/test_quality_gate__strict_contract.py tests/unit/listings/services/test_observation_persistence.py tests/unit/application/test_analytics_service.py tests/unit/ml/test_training_and_benchmark_policy.py tests/unit/listings/scraping/test_sidecar_contract.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py tests/unit/application/test_reporting_service.py tests/unit/application/test_source_capability_service.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/integration/listings/unified_crawl/test_crawl_normalize_persist__fixture_html__saves_rows.py -q`
- `python3 -m compileall src/application src/listings/services src/listings/workflows src/listings/scraping src/ml/training src/platform/utils src/interfaces`
- `python3 -m src.interfaces.cli audit-serving-data`
- `python3 -m src.listings.scraping.sidecar --source-id pisos --start-url https://example.com/search --write-only`
- `python3 -m src.ml.training.train --help`
- `python3 -m src.ml.training.benchmark --help`
- `python3 -m src.listings.scraping.sidecar --help`
- `npm install` (in `scraper/`)
- `npm run build` (in `scraper/`)

## Routing, Data Trust, and Workbench Usability Packet (2026-03-10)

- Objective: make the React app deep-link safe, stop corrupted listings from reaching serving surfaces, switch the workbench to explicit cached-valuation semantics, and demote Streamlit to a legacy path.
- This step advances objective by: moving the JSON API behind `/api/v1`, restoring SPA route ownership for `/workbench` and related browser routes, applying one shared serving-eligibility gate to both the React workbench and the legacy dashboard, and exposing `available` / `not_evaluated` / `missing_required_fields` / `insufficient_comps` states explicitly.
- Risks of misalignment: if root-path API collisions remain or corrupted rows keep leaking into explorer surfaces, the redesign will still feel operationally unreliable even with the new UI shell.
- Cycle stage: `build`
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - moved HTTP JSON routes to `/api/v1/...` and simplified SPA fallback so direct loads and refreshes on browser routes return the React shell:
    - `src/adapters/http/app.py`
  - added the shared serving-eligibility contract and a one-shot audit command:
    - `src/application/serving.py`
    - `src/application/reporting.py`
    - `src/interfaces/cli.py`
  - updated the workbench read model to:
    - hide ineligible/blocked rows from markers and ranking tables,
    - emit `serving_eligible`, `serving_reason`, and `valuation_ready`,
    - stop hidden live valuation fallback in the explore path,
    - classify rows as `available`, `not_evaluated`, `missing_required_fields`, or `insufficient_comps`:
      - `src/application/workbench.py`
  - updated the React client to use `/api/v1`, broaden default filters, surface the “no cached valuations in view” state, and expose explicit manual valuation actions:
    - `frontend/src/api.ts`
    - `frontend/src/types.ts`
    - `frontend/src/pages.tsx`
    - `frontend/vite.config.ts`
  - routed the legacy dashboard through the same serving gate, added an in-app deprecation banner, and removed the current `use_container_width` deprecation warnings:
    - `src/interfaces/dashboard/services/loaders.py`
    - `src/interfaces/dashboard/app.py`
  - updated regression coverage for the new API namespace, SPA deep links, and workbench status semantics:
    - `tests/unit/adapters/http/test_fastapi_local_api.py`
    - `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`
- In progress:
  - none

### Next

- Replace the remaining redesign destinations with deeper React workflow pages and remove the legacy Streamlit alias once React parity covers the remaining operator flows.

### Not now

- No source-parser root-cause cleanup in this packet beyond hiding corrupted rows from serving and auditing them into `data_quality_events`.
- No DB schema change for a persistent quarantine flag; current enforcement is at the serving/read-model layer plus quality-event audit records.

### Blocked

- The live corpus still contains a large invalid slice. The new audit command reported `5891 / 7851` listings failing serving eligibility, overwhelmingly from `pisos`, so source/parser cleanup is still required after this guardrail packet.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py -q`
- `python3 -m compileall src/application src/adapters/http src/interfaces/dashboard src/interfaces`
- `npm run build` (in `frontend/`)
- `python3 -m src.interfaces.cli audit-serving-data`
- `python3 -m src.interfaces.cli api --help`

## Map-Centric React Workbench Packet (2026-03-10)

- Objective: make the redesign the canonical UI direction by shipping a real React/Vite workbench with the map as the dominant exploration surface.
- This step advances objective by: replacing the placeholder frontend scaffold with a routed React shell, introducing a real map-centric workbench backed by the new read-model endpoints, and serving the built frontend from the local FastAPI app.
- Risks of misalignment: if the map remains secondary or the React shell stays unmounted, the redesign remains presentation-only and the product keeps drifting around the legacy Streamlit interface.
- Cycle stage: `build`
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - shipped the first canonical React application shell with routed redesign destinations:
    - `frontend/src/App.tsx`
    - `frontend/src/main.tsx`
    - `frontend/src/index.css`
    - `frontend/src/styles.css`
    - `frontend/index.html`
    - `frontend/vite.config.ts`
  - implemented the map-centric workbench page with dense analyst filters, a dominant deck.gl/MapLibre canvas, live selection basket behavior, and synchronized listing dock / right rail:
    - `frontend/src/pages.tsx`
    - `frontend/src/components/WorkbenchMap.tsx`
    - `frontend/src/api.ts`
    - `frontend/src/types.ts`
  - kept the backend/read-model workbench contract live and verified from the local API:
    - `src/application/workbench.py`
    - `src/application/container.py`
    - `src/adapters/http/app.py`
  - extended API regression coverage to cover the new workbench routes:
    - `tests/unit/adapters/http/test_fastapi_local_api.py`
- In progress:
  - none

### Next

- Add viewport-bound querying, richer layer toggles, and code-splitting/manual chunking so the map workbench scales better on the live corpus without carrying a 2 MB frontend bundle.

### Not now

- No additional investment in the old Streamlit workbench.
- No polygon/choropleth geography packet in this slice.
- No Figma screenshot refresh because the Figma MCP seat hit tool-call limits during implementation.

### Blocked

- Playwright MCP browser transport was unavailable during verification, so the browser smoke pass used the local Playwright skill wrapper instead.

### Verification commands run

- `python3 -m compileall src/application src/adapters/http`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py -q`
- `npm install`
- `npm run build` (in `frontend/`)
- `python3 -m src.interfaces.cli api --host 127.0.0.1 --port 8001`
- Playwright CLI wrapper smoke flow against `http://127.0.0.1:8001/workbench`
  - verified shell load
  - verified map workbench renders live listings
  - verified table-row selection updates the right rail
  - verified `Open dossier` navigates to `/listings/{id}`

## Refactor Packet: Persist Runtime Quality Artifacts (2026-03-10)

- Objective: make the new runtime refactor tables operational by persisting source-contract audits, source-level quality events, benchmark runs, and calibration coverage reports.
- This step advances objective by: turning `source_contract_runs`, `data_quality_events`, `benchmark_runs`, and `coverage_reports` into live artifacts instead of schema-only placeholders, while keeping the local CLI/API surfaces stable.
- Risks of misalignment: if these records are not persisted, the refactor still looks architectural on paper but remains operationally weak because quality/benchmark state is not queryable or trendable from the system of record.
- Cycle stage: `build`
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - persisted source audits and source-level quality events from the new source capability service:
    - `src/application/sources.py`
  - persisted benchmark run lifecycle records from the local application pipeline:
    - `src/application/reporting.py`
    - `src/application/pipeline.py`
    - `src/application/container.py`
  - persisted segmented calibration coverage rows into `coverage_reports` during calibration updates:
    - `src/valuation/workflows/calibration.py`
  - added focused regression coverage for the new persistence paths:
    - `tests/unit/application/test_source_capability_service.py`
    - `tests/unit/application/test_reporting_service.py`
- In progress:
  - none

### Next

- Backfill or populate `listing_observations` and `listing_entities` from actual crawl/normalization flows so the Bronze/Silver/Gold data contract becomes operational rather than schema-only.

### Not now

- No React frontend scaffold in this packet.
- No Alembic migration stack in this packet.
- No LightGBM quantile training reset in this packet.

### Blocked

- `pytest` collection in the host Python environment still depends on constraining plugin autoload; focused and broader repo slices were verified with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/unit/application/test_source_capability_service.py tests/unit/application/test_reporting_service.py tests/unit/adapters/http/test_fastapi_local_api.py tests/unit/platform/test_migrations__runtime_tables.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/unit/interfaces tests/unit/application tests/unit/adapters/http tests/unit/platform tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/valuation/test_valuation_persister__confidence_semantics.py`
- `python3 -m src.interfaces.cli preflight --skip-crawl --skip-market-data --skip-index --skip-training`
- `python3 -m src.interfaces.cli api --help`

## ChatMock Default Backend Packet (2026-03-10)

- Objective: unify text and vision model routing behind ChatMock/OpenAI-compatible defaults while keeping Ollama as an explicit compatibility mode.
- This step advances objective by: removing direct Ollama-only text calls, moving vision requests onto the same config-driven endpoint model, and making unsupported vision behavior explicit/tested.
- Risks of misalignment: if any hidden Ollama-only path remains, backend changes will still be partial and VLM failures can stay silent.
- Cycle stage: `build`
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - added provider-level routing fields for shared LLM, description-analysis, and VLM config surfaces:
    - `src/platform/settings.py`
    - `config/llm.yaml`
    - `config/description_analyst.yaml`
    - `config/vlm.yaml`
  - refactored model calls onto ChatMock/OpenAI-compatible defaults:
    - `src/platform/utils/llm.py`
    - `src/listings/services/description_analyst.py`
    - `src/listings/services/llm_normalizer.py`
    - `src/listings/services/vlm.py`
  - added regression and integration coverage:
    - `tests/unit/platform/test_llm__chatmock_routing.py`
    - `tests/unit/listings/services/test_description_analyst__chatmock.py`
    - `tests/unit/listings/services/test_vlm__chatmock.py`
    - `tests/integration/listings/test_feature_fusion__chatmock_paths.py`
  - updated operator docs for the new default backend and VLM failure semantics:
    - `README.md`
    - `docs/reference/configuration.md`
    - `docs/how_to/configuration.md`
    - `docs/manifest/02_tech_stack.md`
    - `docs/manifest/03_decisions.md`
    - `docs/manifest/07_observability.md`
    - `docs/manifest/10_testing.md`
    - `docs/implementation/checklists/01_plan.md`
- In progress:
  - none

### Next

- Monitor the first live run against the actual ChatMock endpoint/model set and adjust configured model names if the local deployment exposes a different catalog.

### Not now

- No repo-managed ChatMock bootstrap or launcher script in this packet; the backend remains an external service.

### Blocked

- No blocker for the code/config packet itself.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/platform/test_llm__chatmock_routing.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/listings/services/test_description_analyst__chatmock.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/listings/services/test_vlm__chatmock.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q`
- `python3 -m src.interfaces.cli preflight --help`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/platform/test_llm__chatmock_routing.py tests/unit/listings/services/test_description_analyst__chatmock.py tests/unit/listings/services/test_vlm__chatmock.py --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q`

## UI Hotfix: stale cached valuations keep dashboard usable (2026-03-10)

- Objective: keep the live dashboard usable when preflight is overdue by rendering from the latest persisted valuations instead of dropping to an empty state.
- This step advances objective by: restoring deal cards, memo view, insights, and atlas in the real Streamlit runtime for the existing `data/listings.db`.
- Risks of misalignment: if the dashboard treats stale cached valuations as missing, users see `No listings yet` even while `Pipeline Status` reports thousands of tracked listings.
- Cycle stage: `build`
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - reproduced the live regression with Playwright MCP against `python -m src.interfaces.cli dashboard --skip-preflight`
  - traced the empty state to the dashboard loader rejecting all cached valuations older than 7 days
  - updated the dashboard loader to use the latest persisted valuation while freshness remains visible in pipeline status
  - added focused regression coverage for stale cached valuation reuse:
    - `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`
- In progress:
  - none

### Next

- Re-run broader dashboard exploration only if the agent command-center flow needs live-runtime verification beyond the existing fixture-backed tests.

### Not now

- No broader preflight/data-refresh policy changes in this packet; this change only restores dashboard rendering from existing persisted valuations.

### Blocked

- No blockers.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q`
- manual Playwright MCP session against `http://127.0.0.1:63073` after launching `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m src.interfaces.cli dashboard --skip-preflight --server.headless true --server.address 127.0.0.1 --server.port 63073`

## Prompt-03 M8 Closure + M9 Activation (2026-02-09, next suggested prompt)

- Objective: execute the next suggested prompt (`prompt-03-alignment-review-gate`) to close `M8` routing evidence after retriever ablation/decomposition decision delivery.
- This step advances objective by: converting `M8` from implementation-done to alignment-closed state and promoting a single active packet for the remaining uncertainty-policy gap (`C-10`).
- Risks of misalignment: if `M8` remains open in routing docs after implementation closure, packet sequencing drifts and fallback-interval policy work (`C-10`) remains underspecified.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Refreshed alignment gate artifacts for current repo truth:
    - `docs/implementation/checklists/07_alignment_review.md`
    - `docs/implementation/reports/alignment_review.md`
  - Closed `M8` and activated the next single packet in milestone routing:
    - `docs/implementation/checklists/02_milestones.md`
  - Reframed top corrective actions from implementation gaps to policy/ops gaps:
    - `C-10` fallback interval strategy (active),
    - `C-11` ablation rerun cadence (deferred),
    - `C-12` decomposition re-evaluation trigger (deferred).
- In progress:
  - none

### Next

- Execute `prompt-02-app-development-playbook` for active `M9` scope (`C-10`, with optional `C-11`/`C-12` if appetite allows), then rerun `prompt-03`.

### Not now

- Keep `C-11` and `C-12` deferred unless they can be absorbed without expanding `M9` beyond small appetite.

### Blocked

- No blocker for this prompt-03 rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `rg -n "C-08|C-09|C-10|C-11|C-12|\\[x\\] M8|\\[ \\] M9|Packet M8|Packet M9|Next suggested prompt" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/07_alignment_review.md docs/implementation/reports/alignment_review.md -S`
- `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/07_alignment_review.md --changed-file docs/implementation/reports/alignment_review.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-02 M8 Retriever Ablation + Decomposition Decision Packet (2026-02-09, next suggested prompt)

- Objective: execute the next suggested prompt (`prompt-02-app-development-playbook`) for active `M8` scope (`C-08` + `C-09`).
- This step advances objective by: converting retriever/decomposition uncertainty into a reproducible decision packet with explicit keep/simplify thresholds and drift checks.
- Risks of misalignment: without this packet, semantic retriever complexity and decomposition caveats remain undocumented assumptions instead of measurable routing decisions.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Added retriever ablation workflow and decision surfaces:
    - `src/ml/training/retriever_ablation.py`
    - `src/interfaces/cli.py` (`retriever-ablation` command)
    - `tests/unit/ml/test_retriever_ablation_workflow__decisions.py`
    - `tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py`
  - Generated decision artifacts:
    - `docs/implementation/reports/retriever_ablation_report.json`
    - `docs/implementation/reports/retriever_ablation_report.md`
  - Synced packet docs and artifact alignment routing:
    - `docs/manifest/09_runbook.md`
    - `docs/manifest/10_testing.md`
    - `docs/manifest/03_decisions.md`
    - `docs/manifest/20_literature_review.md`
    - `docs/implementation/checklists/08_artifact_feature_alignment.md`
    - `docs/implementation/reports/artifact_feature_alignment.md`
    - `docs/implementation/checklists/02_milestones.md`
- In progress:
  - none

### Next

- Execute `prompt-03-alignment-review-gate` follow-up to close `M8` routing evidence and keep `C-10` as the remaining active corrective packet.

### Not now

- `C-10` fallback interval strategy implementation remains deferred until prompt-03 revalidates post-`M8` alignment routing.

### Blocked

- No blocker for this prompt-02 packet.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/ml/test_retriever_ablation_workflow__decisions.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py -q`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m src.interfaces.cli retriever-ablation --listing-type sale --max-targets 80 --num-comps 5 --output-json docs/implementation/reports/retriever_ablation_report.json --output-md docs/implementation/reports/retriever_ablation_report.md`
- `python3 scripts/check_artifact_feature_contract.py`
- `python3 scripts/check_command_map.py`
- `python3 scripts/check_docs_sync.py --changed-file src/ml/training/retriever_ablation.py --changed-file src/interfaces/cli.py --changed-file tests/unit/ml/test_retriever_ablation_workflow__decisions.py --changed-file tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/manifest/03_decisions.md --changed-file docs/manifest/20_literature_review.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-03 M7 Alignment Gate Closure (2026-02-09, next suggested prompt)

- Objective: execute the next suggested prompt (`prompt-03-alignment-review-gate`) to close `M7` routing evidence after trust-surface implementation and live-browser verification.
- This step advances objective by: removing stale trust-gap assumptions from alignment artifacts, marking `M7` complete, and promoting `M8` as the single active packet.
- Risks of misalignment: without this rerun, alignment docs continue to indicate already-closed gaps (`O-04`, `G-02`) and delay the retrieval/decomposition decision packet.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Refreshed alignment gate artifacts for current repo truth:
    - `docs/implementation/checklists/07_alignment_review.md`
    - `docs/implementation/reports/alignment_review.md`
  - Closed `M7` packet bookkeeping and moved active packet to `M8`:
    - `docs/implementation/checklists/02_milestones.md`
  - Reframed top corrective actions to current open outcomes:
    - `C-08` retriever ablation (`O-02`)
    - `C-09` decomposition diagnostics (`O-03`)
    - `C-10` fallback interval policy gap (`lit-jackknifeplus-2021`)
- In progress:
  - none

### Next

- Execute `prompt-02-app-development-playbook` for active `M8` scope (`C-08` + `C-09`), then rerun `prompt-03`.

### Not now

- Release-readiness expansion and additional polish packets remain deferred until `M8` decisions are evidence-backed.

### Blocked

- No blocker for this prompt-03 rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q`
- `rg -n "\\[x\\] Packet M7|\\[ \\] Packet M8|Prompt-03 follow-up|C-08|C-09|C-10" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/07_alignment_review.md docs/implementation/reports/alignment_review.md`
- `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/07_alignment_review.md --changed-file docs/implementation/reports/alignment_review.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-06 M7 Live-Browser Trust Closure (2026-02-09, next suggested prompt)

- Objective: execute the next suggested prompt (`prompt-06-ui-e2e-verification-loop`) for remaining `M7/C-07` + `O-05` trust-evidence scope.
- This step advances objective by: adding real Streamlit runtime verification for source-support/assumption trust surfaces and closing fixture-only evidence drift.
- Risks of misalignment: without live-browser evidence, trust-surface claims can appear complete while remaining unverified outside fixture runtime.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Added live-browser Playwright coverage:
    - `tests/live/ui/test_dashboard_live_browser__source_support.py`
  - Closed `G-02` in prompt-06 artifacts with real-runtime evidence:
    - `docs/implementation/checklists/05_ui_verification.md`
    - `docs/implementation/reports/ui_verification_final_report.md`
  - Marked artifact-alignment outcomes closed:
    - `docs/implementation/checklists/08_artifact_feature_alignment.md` (`C-07`, `O-05`)
    - `docs/implementation/reports/artifact_feature_alignment.md`
  - Kept milestone packet state explicit:
    - `docs/implementation/checklists/02_milestones.md` (`P1-H` closed, `M7` prompt-03 follow-up still open)
- In progress:
  - none

### Next

- Execute prompt-03 follow-up to rerun the alignment gate and close `M7` packet routing evidence.

### Not now

- Retrieval ablation/decomposition packet (`M8`: `C-08`, `C-09`) remains deferred until the prompt-03 follow-up lands.

### Blocked

- No blocker for this prompt-06 follow-up packet.

### Verification commands run

- `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `python3 scripts/check_artifact_feature_contract.py`
- `python3 scripts/check_command_map.py`
- `python3 scripts/check_docs_sync.py --changed-file tests/live/ui/test_dashboard_live_browser__source_support.py --changed-file docs/implementation/checklists/05_ui_verification.md --changed-file docs/implementation/reports/ui_verification_final_report.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/09_runbook.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-02 M7 Assumption-Badge Packet (2026-02-09, next suggested prompt)

- Objective: execute the next suggested prompt (`prompt-02-app-development-playbook`) for active `M7/C-06` scope.
- This step advances objective by: surfacing artifact-backed assumption badges in runtime API/dashboard status outputs and closing docs-only trust caveat drift.
- Risks of misalignment: if assumption cues remain docs-only, operators can over-trust status surfaces without seeing open caveats and missing safeguards.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Added `PipelineAPI.assumption_badges(...)` and embedded `assumption_badges` in `PipelineAPI.pipeline_status(...)`.
  - Updated dashboard status rendering to show assumption badge lines in:
    - compact system-status expander,
    - `🧭 Pipeline Status` insight panel.
  - Updated fallback loader payload to include `assumption_badges`.
  - Added/updated regression coverage:
    - `tests/unit/interfaces/test_pipeline_api__source_support.py`
    - `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Synced contract/interpretation/observability docs and artifact-alignment governance for `C-06`/`O-04`.
- In progress:
  - none

### Next

- Execute prompt-06 follow-up for `C-07/O-05` (`G-02` live-browser evidence), then rerun prompt-03 alignment gate.

### Not now

- Retrieval ablation/decomposition packet (`M8`: `C-08`, `C-09`) until remaining `M7` trust-evidence scope closes.

### Blocked

- No blocker for this prompt-02 packet.

### Verification commands run

- `rg -n "assumption_badges|artifact-backed|artifact_ids|Assumption badges" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py docs/implementation/checklists/08_artifact_feature_alignment.md -S`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_pipeline_api__source_support.py -q`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `rg -n "assumption_badges|artifact_ids|Source labels: supported / blocked / fallback|Assumption badges:" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py tests/unit/interfaces/test_pipeline_api__source_support.py tests/e2e/ui/test_dashboard_ui_verification_loop.py docs/implementation/checklists/05_ui_verification.md docs/implementation/reports/ui_verification_final_report.md docs/how_to/interpret_outputs.md docs/manifest/04_api_contracts.md docs/manifest/07_observability.md -S`
- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `python3 scripts/check_artifact_feature_contract.py`
- `python3 scripts/check_docs_sync.py --changed-file src/interfaces/api/pipeline.py --changed-file src/interfaces/dashboard/app.py --changed-file src/interfaces/dashboard/services/loaders.py --changed-file tests/unit/interfaces/test_pipeline_api__source_support.py --changed-file tests/e2e/ui/test_dashboard_ui_verification_loop.py --changed-file docs/manifest/03_decisions.md --changed-file docs/manifest/04_api_contracts.md --changed-file docs/manifest/07_observability.md --changed-file docs/how_to/interpret_outputs.md --changed-file docs/crawler_status.md --changed-file docs/implementation/checklists/05_ui_verification.md --changed-file docs/implementation/reports/ui_verification_final_report.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-15 Artifact-Feature Alignment Gate (2026-02-09, post-`M6` trust-packet routing)

- Objective: execute `prompt-15-artifact-feature-alignment-gate` as the next suggested packet after `M6` closure.
- This step advances objective by: refreshing artifact-to-feature evidence and routing remaining trust gaps into one active packet (`M7`) plus one deferred follow-on packet (`M8`).
- Risks of misalignment: without explicit post-`M6` milestone routing, assumption-badge and live-browser trust gaps can remain open while appearing complete.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_GAPS`

### Now

- Completed:
  - Refreshed `docs/implementation/reports/artifact_feature_alignment.md` with post-`M6` evidence and updated corrective/opportunity routing.
  - Refreshed `docs/implementation/checklists/08_artifact_feature_alignment.md` with current open outcomes (`C-06`, `C-07`, `O-02`, `O-03`, `O-04`, `O-05`).
  - Updated `docs/implementation/checklists/02_milestones.md` with active packet `M7` and follow-on packet `M8`, including measurable AC/Verify entries.
- In progress:
  - none

### Next

- Execute `M7` via `prompt-02 -> prompt-06 -> prompt-03` (`C-06` assumption badges + `C-07` live-browser evidence).

### Not now

- `M8` retrieval ablation/decomposition packet (`C-08`, `C-09`) until `M7` trust-surface closure is complete.

### Blocked

- No blocker for this prompt-15 packet.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "C-06|C-07|O-05|\\[ \\]" docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/checklists/02_milestones.md docs/implementation/reports/artifact_feature_alignment.md -S`
- `python3 scripts/check_artifact_feature_contract.py`
- `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-03 Alignment Review Gate (2026-02-09, post-M6 closure rerun)

- Objective: execute `prompt-03-alignment-review-gate` after `M6` closure to re-check objective drift and route remaining corrections.
- This step advances objective by: confirming `M6` closure evidence (`UI verification + source-support labels`) and narrowing remaining risk to schedulable follow-up packets.
- Risks of misalignment: without explicit follow-up on `O-04` and `G-02`, trust cues may remain incomplete for live operator workflows.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Refreshed `docs/implementation/checklists/07_alignment_review.md` with current evidence and required-question answers.
  - Refreshed `docs/implementation/reports/alignment_review.md` with post-`M6` verdict and correction routing.
  - Kept verdict at `ALIGNED_WITH_RISKS` and mapped next packet to `O-04` + `G-02`.
- In progress:
  - none

### Next

- Execute next correction packet for assumption badges + live-browser evidence (`prompt-15 -> prompt-02 -> prompt-06 -> prompt-03`).

### Not now

- Retrieval ablation/embedding-drift packet (`O-02`) until the trust-surface packet closes.

### Blocked

- No blocker for this alignment packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `test -f docs/implementation/checklists/05_ui_verification.md && test -f docs/implementation/reports/ui_verification_final_report.md && test -d tests/e2e`
- `rg --files tests/e2e`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `rg -n "supported|blocked|fallback|source_support|Source labels" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py docs/crawler_status.md -S`
- `rg -n "O-04|\\[ \\]" docs/implementation/checklists/03_improvement_bets.md docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/checklists/02_milestones.md -S`
- `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/07_alignment_review.md --changed-file docs/implementation/reports/alignment_review.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-02 M6 Source-Support Packet (2026-02-09, manual run)

- Objective: execute the next suggested prompt (`prompt-02-app-development-playbook`) for open `M6/C-02` runtime source-support visibility.
- This step advances objective by: exposing `supported|blocked|fallback` labels in API/dashboard runtime status surfaces and closing `IB-06`.
- Risks of misalignment: if alignment artifacts are not rerun after this packet, `C-02` closure may remain under-reported in prompt-03 gate docs.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Added source-support runtime payloads in `src/interfaces/api/pipeline.py`:
    - `PipelineAPI.source_support_summary(...)`
    - `PipelineAPI.pipeline_status(...)`
  - Updated dashboard runtime status loading/rendering:
    - `src/interfaces/dashboard/services/loaders.py`
    - `src/interfaces/dashboard/app.py`
  - Added regression coverage:
    - `tests/unit/interfaces/test_pipeline_api__source_support.py`
    - `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_pipeline_status__shows_source_support_labels`
  - Updated packet docs/checklists (`IB-06`, `M6`, observability/crawler status/API contracts).
- In progress:
  - none

### Next

- Re-run `prompt-03-alignment-review-gate` to refresh `C-02` closure evidence and route `O-04`.

### Not now

- Live browser verification against a real Streamlit server remains deferred (`G-02`).

### Blocked

- No blocker for this prompt-02 packet.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_pipeline_api__source_support.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q`
- `rg -n "supported|blocked|fallback|source_support|source support" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py -S`
- `python3 scripts/check_command_map.py`
- `python3 scripts/check_docs_sync.py --changed-file src/interfaces/api/pipeline.py --changed-file src/interfaces/dashboard/services/loaders.py --changed-file src/interfaces/dashboard/app.py --changed-file tests/unit/interfaces/test_pipeline_api__source_support.py --changed-file tests/e2e/ui/test_dashboard_ui_verification_loop.py --changed-file docs/crawler_status.md --changed-file docs/manifest/03_decisions.md --changed-file docs/manifest/04_api_contracts.md --changed-file docs/manifest/07_observability.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/05_ui_verification.md --changed-file docs/implementation/reports/ui_verification_final_report.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`

## Prompt-06 UI Verification Refresh (2026-02-09, manual rerun)

- Objective: rerun `prompt-06-ui-e2e-verification-loop` and refresh UI verification artifacts against current repo state.
- This step advances objective by: revalidating dashboard critical-flow smoke coverage and publishing explicit prompt-06 checklist/report outputs with command-map linkage.
- Risks of misalignment: if prompt-06 docs drift from the current harness, `M6` closure evidence becomes ambiguous.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Refreshed UI command-map entries in `docs/manifest/09_runbook.md` (`CMD-DASHBOARD-HELP`, `CMD-DASHBOARD-SKIP-PREFLIGHT`).
  - Updated prompt-06 artifacts:
    - `docs/implementation/checklists/05_ui_verification.md`
    - `docs/implementation/reports/ui_verification_final_report.md`
  - Revalidated deterministic UI smoke tests and full offline E2E suite.
- In progress:
  - none

### Next

- Continue active `M6` implementation scope for `C-02` (runtime source-support/fallback visibility).
- Re-run prompt-03 once `C-02` evidence is available.

### Not now

- Atlas map click-interaction automation (explicitly gated in prompt-06 artifacts).

### Blocked

- No blocker for this prompt-06 rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli -h`
- `python3 -m src.interfaces.cli dashboard --help`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q`

## Prompt-06 UI Verification Loop (2026-02-09, M6 packet)

- Objective: execute `prompt-06-ui-e2e-verification-loop` to verify and stabilize the Streamlit dashboard critical user flows with deterministic E2E coverage.
- This step advances objective by: adding reproducible UI flow checks, fixing a runtime memo-navigation exception, and creating the missing prompt-06 verification artifacts.
- Risks of misalignment: runtime source support/fallback status is still not surfaced in user-facing API/dashboard outputs (`IB-06` remains open).
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Added prompt-06 deliverables:
    - `docs/implementation/checklists/05_ui_verification.md`
    - `docs/implementation/reports/ui_verification_final_report.md`
  - Added deterministic dashboard UI E2E harness and critical-flow tests:
    - `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Fixed Streamlit session-state memo-navigation regression in:
    - `src/interfaces/dashboard/app.py`
  - Updated canonical command map with dedicated UI verification command:
    - `docs/manifest/09_runbook.md` (`CMD-TEST-E2E-UI`)
- In progress:
  - none

### Next

- Implement remaining `IB-06` scope: surface source support/fallback status in API/dashboard runtime outputs.
- Re-run `prompt-03-alignment-review-gate` after `IB-06` evidence is in place.

### Not now

- Additional UI polish and live-browser exploratory packets beyond the stabilized critical flows.

### Blocked

- Source support/fallback labels are still missing from user-visible runtime surfaces (tracked in `docs/implementation/checklists/03_improvement_bets.md` and `docs/implementation/checklists/07_alignment_review.md`).

### Verification commands run

- `python3 -m src.interfaces.cli -h`
- `python3 scripts/check_command_map.py`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q`

## Prompt-03 Alignment Review Refresh (2026-02-09, post prompt-12/prompt-13 reruns)

- Objective: execute `prompt-03-alignment-review-gate` to refresh objective-drift checks after the manual research verification reruns.
- This step advances objective by: confirming that current drift remains bounded to runtime/UI trust surfaces and preserving explicit correction routing (`M6` + `O-04`) without scope creep.
- Risks of misalignment: stale gate metadata can route work to the wrong prompt order and leave trust-critical UI/runtime gaps unresolved.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Refreshed `docs/implementation/checklists/07_alignment_review.md` with current routing evidence and updated end-to-end usability evidence.
  - Refreshed `docs/implementation/reports/alignment_review.md` with current rerun context and corrective mapping.
  - Added explicit keep-the-slate-clean decision: `Reshape Next Bet` (`M6` for `C-01`/`C-02`, then `O-04` for `C-03`).
- In progress:
  - none

### Next

- Execute Packet `M6` via `prompt-02 -> prompt-06` and rerun prompt-03 after packet closure evidence exists.
- Route `C-03` as `O-04` follow-on only after `M6` completion or explicit reshape.

### Not now

- Additional correction tracks beyond `C-01`/`C-02`/`C-03` while `M6` remains active.

### Blocked

- No blocker for this alignment packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `test -f docs/implementation/checklists/05_ui_verification.md; test -f docs/implementation/reports/ui_verification_final_report.md; test -d tests/e2e`
- `rg --files tests/e2e`
- `rg -n "supported|blocked|fallback|source_status|source support" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py -S`
- `rg -n "O-04|IB-06|\\[ \\]" docs/implementation/checklists/03_improvement_bets.md docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/checklists/07_alignment_review.md docs/implementation/checklists/02_milestones.md -S`
- `rg -n "prompt-12|prompt-13|M6|prompt-02 -> prompt-06 -> prompt-03" docs/implementation/00_status.md docs/implementation/03_worklog.md docs/implementation/reports/prompt_execution_plan.md -S`

## Prompt-13 Paper Verification Refresh (2026-02-09, manual rerun)

- Objective: execute `prompt-13-research-paper-verification` as a bounded reproducibility and verification rerun.
- This step advances objective by: revalidating paper-to-code contract integrity, deterministic paper tests, and reproducible paper build outputs.
- Risks of misalignment: if verification artifacts drift from code or fail silently, paper claims can overstate what is actually tested.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Regenerated paper sanity artifact (`paper/artifacts/sanity_case.json`).
  - Revalidated paper contract map (`scripts/verify_paper_contract.py`).
  - Re-ran paper unit verification tests with plugin-autoload fallback (`12 passed`).
  - Rebuilt `paper/main.pdf` successfully.
  - Updated `paper/verification_log.md` with this run's evidence.
- In progress:
  - none

### Next

- Continue active build packet `M6` (`prompt-02 -> prompt-06 -> prompt-03`).
- Re-run prompt-13 only if paper claims, mappings, or verification surfaces change materially.

### Not now

- Expanding paper scope beyond current verified claim set while `M6` remains active.

### Blocked

- Known environment issue: plain pytest path fails due external `langsmith` plugin autoload; fallback path is stable.

### Verification commands run

- `python3 scripts/paper_generate_sanity_artifact.py`
- `python3 scripts/verify_paper_contract.py`
- `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails in this environment due external plugin autoload)
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q`
- `python3 scripts/build_paper.py`

## Prompt-12 Literature Validation Refresh (2026-02-09, manual rerun)

- Objective: execute `prompt-12-research-literature-validation` as a bounded revalidation packet.
- This step advances objective by: confirming load-bearing literature artifacts and claim-traceability docs remain valid while active build packet `M6` is in progress.
- Risks of misalignment: if literature artifacts drift silently, research-backed modeling and uncertainty decisions can become untraceable.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Revalidated artifact index integrity (`OK: 14 artifacts`).
  - Revalidated review section/claims-table and bibliography-table structures.
  - Logged this rerun in Prompt-12 report/checklist artifacts.
- In progress:
  - none

### Next

- Continue routed build packet `M6` execution (`prompt-02 -> prompt-06 -> prompt-03`).
- Re-run prompt-12 only if citation set or load-bearing claims materially change.

### Not now

- Citation-set expansion while runtime/UI trust packet `M6` remains the active objective-critical bet.

### Blocked

- No blocker for this rerun packet.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`

## Prompt-00 Routing Refresh (2026-02-09, prompt-pack sync to latest upstream)

- Objective: refresh the prompt library to the latest upstream pack and regenerate routing in the current prompt-00 format.
- This step advances objective by: locking execution to the current packet (`M6`) with explicit immediate/deferred/exploration prompt IDs and circuit-breaker rules.
- Risks of misalignment: stale routing output could prioritize non-critical prompts while leaving runtime/UI trust gaps open.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Updated `prompts/` submodule to latest upstream commit (`63d6ac94e91b4e303caa895e394176b8d6c6fd15`).
  - Ran prompt-pack validation checks from the updated library.
  - Rewrote `docs/implementation/reports/prompt_execution_plan.md` in `prompt-00` format with:
    - inferred stage/cadence,
    - finalist betting table,
    - ordered immediate prompt chain (`prompt-02 -> prompt-06 -> prompt-03`),
    - explicit deferred and exploration IDs,
    - scope-cut/circuit-breaker/carryover rules.
- In progress:
  - none

### Next

- Execute Packet `M6` as routed (`prompt-02 -> prompt-06 -> prompt-03`).
- Route `O-04` via `prompt-15` only after `M6` closes.

### Not now

- Release-readiness expansion (`prompt-11`) until runtime/UI trust packet `M6` is closed.

### Blocked

- No blocker for this packet.

### Verification commands run

- `git submodule update --init --remote prompts`
- `python3 prompts/scripts/prompts_manifest.py --check`
- `python3 prompts/scripts/system_integrity.py --mode prompt_pack`
- `rg -n "\\[ \\]" docs/implementation/checklists -S`

## Prompt-03 Alignment Review Gate (2026-02-09, alignment refresh after reliability gate closure)

- Objective: re-run the alignment gate to confirm current work still matches the Core Objective and route the next corrective packet.
- This step advances objective by: surfacing the remaining UI verification and runtime trust gaps that can block the core dashboard workflow.
- Risks of misalignment: without UI verification artifacts and runtime source-status visibility, operators can misinterpret coverage and UI behavior can drift undetected.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Updated alignment checklist/report with current evidence and corrective actions.
  - Added Packet `M6` to milestones for UI verification + source-status surfacing.
  - Logged this alignment gate rerun in the worklog.
- In progress:
  - none

### Next

- Execute Packet `M6` (prompt-06 UI verification + runtime source-support visibility).
- Follow-on: surface artifact-backed assumption badges (`O-04`) after Packet `M6`.

### Not now

- Additional prompt routing refreshes until Packet `M6` completes.

### Blocked

- No blocker for this packet.

### Verification commands run

- `rg -n "confidence = 0.85|placeholder confidence|confidence_components|calibration_status" src/valuation/services/valuation_persister.py docs/how_to/interpret_outputs.md`
- `rg -n "source support|fallback|blocked|crawler status|source status" docs/crawler_status.md src/interfaces/dashboard/app.py src/interfaces/api/pipeline.py -S`
- `rg -n "e2e|dashboard|Streamlit|ui verification" docs/implementation/checklists docs/implementation/reports README.md -S`
- `rg -n "\\[ \\]" docs/implementation/checklists -S`

## Prompt-11 Docs/Release Packet (2026-02-09, manual legacy-docs migration to Diataxis format)

- Objective: migrate legacy top-level docs (`docs/00..08`) into the Diataxis-format docs tree and remove the legacy files.
- This step advances objective by: consolidating docs navigation and content into the canonical `docs/INDEX.md` + `docs/explanation/*` structure required by the prompt-library docs system.
- Risks of misalignment: keeping parallel legacy and Diataxis docs would cause drift, stale links, and conflicting documentation surfaces.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Migrated legacy docs content into new-format explanation pages:
    - `docs/explanation/system_overview.md`
    - `docs/explanation/data_pipeline.md`
    - `docs/explanation/scraping_architecture.md`
    - `docs/explanation/services_map.md`
    - `docs/explanation/agent_system.md`
    - `docs/explanation/model_architecture.md`
    - `docs/explanation/production_path.md`
  - Updated canonical docs navigation and architecture entrypoint links:
    - `docs/INDEX.md`
    - `docs/explanation/architecture.md`
    - `README.md`
  - Updated downstream docs references to migrated paths.
  - Removed legacy docs files:
    - `docs/00_docs_index.md`
    - `docs/01_system_overview.md`
    - `docs/02_data_pipeline.md`
    - `docs/03_unified_scraping_architecture.md`
    - `docs/04_services_map.md`
    - `docs/05_agents_map.md`
    - `docs/06_agent_workflow.md`
    - `docs/07_model_architecture.md`
    - `docs/08_path_to_production.md`
- In progress:
  - none

### Next

- Continue with remaining open implementation packet (`IB-06`) for runtime source support/fallback visibility.

### Not now

- Further docs restructuring beyond this legacy -> Diataxis migration.

### Blocked

- No blocker for this packet.

### Verification commands run

- `rg -n "00_docs_index\\.md|01_system_overview\\.md|02_data_pipeline\\.md|03_unified_scraping_architecture\\.md|04_services_map\\.md|05_agents_map\\.md|06_agent_workflow\\.md|07_model_architecture\\.md|08_path_to_production\\.md" README.md docs -g "*.md"`
- `python3 scripts/check_docs_sync.py --changed-file README.md --changed-file docs/INDEX.md --changed-file docs/explanation/architecture.md --changed-file docs/explanation/system_overview.md --changed-file docs/explanation/data_pipeline.md --changed-file docs/explanation/scraping_architecture.md --changed-file docs/explanation/services_map.md --changed-file docs/explanation/agent_system.md --changed-file docs/explanation/model_architecture.md --changed-file docs/explanation/production_path.md --changed-file docs/how_to/run_end_to_end.md --changed-file docs/manifest/20_literature_review.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/checklists/01_plan.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/reports/20_literature_review_log.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/reports/architecture_coherence_report.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md --changed-file docs/00_docs_index.md --changed-file docs/01_system_overview.md --changed-file docs/02_data_pipeline.md --changed-file docs/03_unified_scraping_architecture.md --changed-file docs/04_services_map.md --changed-file docs/05_agents_map.md --changed-file docs/06_agent_workflow.md --changed-file docs/07_model_architecture.md --changed-file docs/08_path_to_production.md`
- `python3 scripts/check_command_map.py`

## Prompt-11 Docs/Release Packet (2026-02-08, manual contract packet for IB-05 artifact mapping gate)

- Objective: execute `prompt-11-docs-diataxis-release` as a manual small packet to close `IB-05` (artifact-feature mapping contract enforcement).
- This step advances objective by: converting artifact-feature alignment from manual review into an executable docs/CI contract check.
- Risks of misalignment: without an enforced contract, load-bearing artifact claims can silently drift away from mapped feature/test evidence.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Added `scripts/check_artifact_feature_contract.py` to validate artifact IDs from `docs/artifacts/index.json` are mapped in alignment report rows and governance checklist surfaces.
  - Added unit tests for the new contract checker:
    - `tests/unit/docs/test_check_artifact_feature_contract.py`
  - Wired CI docs guardrail to run `CMD-ARTIFACT-FEATURE-CONTRACT-CHECK`.
  - Added runbook/CI command-map entries and updated testing docs.
  - Closed `IB-05` in `docs/implementation/checklists/03_improvement_bets.md`.
  - Closed `O-01` in `docs/implementation/checklists/08_artifact_feature_alignment.md`.
  - Closed the remaining combined gate item (`IB-03`) in `docs/implementation/checklists/02_milestones.md`.
- In progress:
  - none

### Next

- Execute `IB-06` packet (source support/fallback status surfaced in runtime outputs).

### Not now

- Additional reruns of already-closed benchmark/alignment packets.

### Blocked

- No blocker for this packet.

### Verification commands run

- `python3 scripts/check_artifact_feature_contract.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/docs/test_check_artifact_feature_contract.py -q`
- `python3 scripts/check_docs_sync.py --changed-file scripts/check_artifact_feature_contract.py --changed-file tests/unit/docs/test_check_artifact_feature_contract.py --changed-file .github/workflows/ci.yml --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/manifest/11_ci.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- `python3 scripts/check_command_map.py`

## Prompt-03 Milestone Closure (2026-02-08, manual packet for P1-F alignment gate surface)

- Objective: execute `prompt-03-docs-sync-and-gap-reporter` as a manual small packet to close `P1-F` (artifact-feature alignment gate remains checkable).
- This step advances objective by: keeping alignment artifacts and milestone references synchronized after the `P1-E` benchmark gate implementation.
- Risks of misalignment: if alignment docs are not kept in lockstep with closed milestones, trust claims drift from actual implementation evidence.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Marked `P1-F` complete in `docs/implementation/checklists/02_milestones.md` with explicit verification references.
  - Kept artifact-feature alignment checklist/report synced with `P1-E` benchmark closure (`C-04` marked complete, literature mapping updated to supported).
  - Synced status/worklog references so alignment surfaces remain part of active milestone evidence.
- In progress:
  - none

### Next

- Move to next open packet beyond current P1 closure set (`IB-05` artifact-feature contract enforcement is the remaining alignment governance gap).

### Not now

- Additional prompt reruns that do not close remaining open governance outcomes.

### Blocked

- No blocker for this packet.

### Verification commands run

- `test -f docs/implementation/checklists/08_artifact_feature_alignment.md && test -f docs/implementation/reports/artifact_feature_alignment.md`
- `rg -n "C-04|P1-E|P1-F|artifact_feature_alignment" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/reports/artifact_feature_alignment.md docs/implementation/00_status.md docs/implementation/03_worklog.md`

## Prompt-02 App Development Playbook (2026-02-08, manual trust packet for P1-E benchmark gate)

- Objective: execute `prompt-02-app-development-playbook` as a manual small packet to close `P1-E` (fusion-vs-RF/XGBoost benchmark gate).
- This step advances objective by: making fusion-model claims checkable against strong tree baselines under leak-safe time+geo splits with explicit threshold gating.
- Risks of misalignment: without enforced baselines, fusion regressions can be masked by architecture complexity and non-comparable evaluation slices.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Added benchmark harness at `src/ml/training/benchmark.py` for dataset loading, time+geo split generation, RF/XGBoost training, fusion subset evaluation, threshold gating, and JSON/Markdown artifact output.
  - Added CLI wrapper command `benchmark` in `src/interfaces/cli.py`.
  - Added/expanded tests:
    - `tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py`
    - `tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py`
  - Generated benchmark artifacts:
    - `docs/implementation/reports/fusion_tree_benchmark.json`
    - `docs/implementation/reports/fusion_tree_benchmark.md`
  - Synced runbook/testing/CLI and alignment docs for benchmark gate surface.
  - Closed `P1-E` in `docs/implementation/checklists/02_milestones.md`.
- In progress:
  - none

### Next

- Execute `P1-F` packet (artifact-feature alignment gate as an enforceable milestone surface).

### Not now

- Re-running prompt-routing loops that do not close remaining open milestones.

### Blocked

- No blocker for this packet.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py -q`
- `python3 -m src.interfaces.cli benchmark --listing-type sale --label-source auto --geo-key city --val-split 0.1 --test-split 0.2 --split-seed 42 --max-fusion-eval 80 --min-test-rows 50 --fusion-min-coverage 0.6 --fusion-mae-ratio-threshold 1.2 --fusion-mape-ratio-threshold 1.2 --output-json docs/implementation/reports/fusion_tree_benchmark.json --output-md docs/implementation/reports/fusion_tree_benchmark.md`
- `python3 -m src.ml.training.benchmark --max-fusion-eval 5 --output-json /tmp/fusion_tree_benchmark_smoke.json --output-md /tmp/fusion_tree_benchmark_smoke.md --fail-on-gate` (expected non-zero when gate fails)

## Prompt-02 App Development Playbook (2026-02-08, manual trust packet for P1-D spatial diagnostics)

- Objective: execute `prompt-02-app-development-playbook` as a manual small packet to close `P1-D` (spatial residual diagnostics + triage wiring).
- This step advances objective by: emitting checkable spatial drift/outlier diagnostics from calibration inputs and wiring triage paths into runbook/observability docs.
- Risks of misalignment: if spatial diagnostics stay docs-only, localized model drift can stay hidden behind aggregate coverage metrics.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Added spatial residual diagnostics output in `src/valuation/workflows/calibration.py` with drift/outlier warning states and Moran/LISA proxy fields.
  - Added CLI-accessible workflow flags for spatial diagnostics output and thresholds.
  - Added tests for spatial diagnostics report generation and CLI passthrough flag forwarding.
  - Updated runbook, observability, CLI/data-format reference docs, and milestone/alignment checklists.
  - Closed `P1-D` in `docs/implementation/checklists/02_milestones.md`.
- In progress:
  - none

### Next

- Execute `P1-E` packet (fusion-vs-RF/XGBoost benchmark gate).

### Not now

- Additional prompt reruns that do not close remaining open P1 milestones.

### Blocked

- No blocker for this packet.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q`
- `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --output <registry.json> --coverage-report-output <coverage.json> --coverage-min-samples 20 --coverage-floor 0.80 --spatial-diagnostics-output <spatial.json> --spatial-min-samples 20 --spatial-drift-threshold-pct 0.08 --spatial-outlier-rate-threshold 0.15 --spatial-outlier-zscore 2.5`
- `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file src/valuation/services/conformal_calibrator.py --changed-file src/valuation/workflows/calibration.py --changed-file src/valuation/services/valuation_persister.py --changed-file tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py --changed-file tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py --changed-file tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py --changed-file tests/unit/valuation/test_valuation_persister__confidence_semantics.py --changed-file docs/manifest/07_observability.md --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/reference/cli.md --changed-file docs/reference/data_formats.md --changed-file docs/how_to/interpret_outputs.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- `python3 scripts/check_command_map.py`

## Prompt-02 App Development Playbook (2026-02-08, manual trust packet for P0-F segmented coverage gate)

- Objective: execute `prompt-02-app-development-playbook` as a manual small packet to close `P0-F` (segmented conformal coverage gate).
- This step advances objective by: producing per-segment coverage outputs with explicit pass/fail thresholds so calibration quality is operationally checkable.
- Risks of misalignment: without segmented outputs, aggregate coverage can hide local calibration failures and weaken confidence semantics.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Fixed passthrough CLI forwarding in `src/interfaces/cli.py` so non-preflight wrapper commands preserve dash-prefixed flags in order.
  - Added segmented coverage reporting in `src/valuation/services/conformal_calibrator.py` (`region_id`, `listing_type`, `price_band`, `horizon_months` + threshold status).
  - Added calibration workflow output flags in `src/valuation/workflows/calibration.py` (`--coverage-report-output`, `--coverage-min-samples`, `--coverage-floor`).
  - Added targeted tests for segmented coverage/workflow report emission and passthrough flag forwarding.
  - Updated runbook/observability/reference docs for the new coverage-gate surface.
  - Closed `P0-F` in `docs/implementation/checklists/02_milestones.md`.
- In progress:
  - none

### Next

- Execute `P1-D` packet (spatial residual diagnostics emitted and triage-mapped).

### Not now

- Additional rerun packets that do not advance open reliability milestones.

### Blocked

- No blocker for this packet.

### Verification commands run

- `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --output <registry.json> --coverage-report-output <coverage.json> --coverage-min-samples 20 --coverage-floor 0.80`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q`
- `python3 scripts/check_docs_sync.py --changed-file src/valuation/services/conformal_calibrator.py --changed-file src/valuation/workflows/calibration.py --changed-file tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py --changed-file src/valuation/services/valuation_persister.py --changed-file tests/unit/valuation/test_valuation_persister__confidence_semantics.py --changed-file docs/manifest/07_observability.md --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/reference/cli.md --changed-file docs/reference/data_formats.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- `python3 scripts/check_command_map.py`

## Prompt-02 App Development Playbook (2026-02-08, manual trust packet for P0-E confidence semantics)

- Objective: execute `prompt-02-app-development-playbook` as a manual small packet to close `P0-E` (confidence semantics trust gap).
- This step advances objective by: replacing placeholder persisted confidence with a calibration/interval-derived and auditable confidence computation.
- Risks of misalignment: if confidence remains heuristic, downstream triage and UI interpretation can overstate valuation reliability.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Replaced static confidence persistence in `src/valuation/services/valuation_persister.py` with a composite derived from uncertainty, calibration status, projection confidence, comp support, and risk penalties.
  - Persisted `confidence_components` breakdown for auditability in valuation evidence.
  - Added targeted tests in `tests/unit/valuation/test_valuation_persister__confidence_semantics.py`.
  - Updated confidence interpretation/testing docs and alignment artifacts (`docs/how_to/interpret_outputs.md`, `docs/manifest/10_testing.md`, alignment checklist/report).
  - Closed `P0-E` in `docs/implementation/checklists/02_milestones.md`.
- In progress:
  - none

### Next

- Execute the next trust-critical packet for `P0-F` (segmented conformal coverage reporting and gates).

### Not now

- Additional rerun-only prompt packets that do not close open P0/P1 trust milestones.

### Blocked

- No blocker for this packet.

### Verification commands run

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q`
- `rg -n "confidence_components|calibration_status|projection_component|volatility_penalty" src/valuation/services/valuation_persister.py docs/how_to/interpret_outputs.md`
- `python3 scripts/check_docs_sync.py --changed-file src/valuation/services/valuation_persister.py --changed-file tests/unit/valuation/test_valuation_persister__confidence_semantics.py --changed-file docs/how_to/interpret_outputs.md --changed-file docs/manifest/10_testing.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- `python3 scripts/check_command_map.py`

## Prompt-11 Docs Diataxis Release (2026-02-08, manual lockfile convergence packet for P1-C)

- Objective: execute `prompt-11-docs-diataxis-release` as a manual small packet to close `P1-C` with a single lockfile-backed install path.
- This step advances objective by: making installs reproducible and reducing dependency-drift risk between local runs, CI, and release prep.
- Risks of misalignment: if lock policy remains ambiguous, environment drift can invalidate CLI/docs verification and release checks.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Generated `requirements.lock` from `requirements.txt` using `pip-tools`.
  - Updated install docs to make `requirements.lock` the canonical install path (`README.md`, `docs/getting_started/installation.md`).
  - Updated stack policy docs (`docs/manifest/02_tech_stack.md`) and closed `P1-C` in `docs/implementation/checklists/02_milestones.md`.
- In progress:
  - none

### Next

- Execute a trust-critical manual packet to close `P0-E` by replacing placeholder persisted confidence semantics with calibration-derived confidence evidence.

### Not now

- Another router-loop-style rerun packet unless it directly closes an open P0/P1 milestone.

### Blocked

- No blocker for this packet.

### Verification commands run

- `python3 -m piptools compile --resolver=backtracking --output-file requirements.lock requirements.txt`
- `rg -n "requirements.lock|piptools|Poetry" README.md docs/getting_started/installation.md docs/manifest/02_tech_stack.md`
- `python3 scripts/check_docs_sync.py --changed-file README.md --changed-file docs/getting_started/installation.md --changed-file docs/manifest/02_tech_stack.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md`
- `python3 scripts/check_command_map.py`

## Prompt-02 App Development Playbook (2026-02-08, manual next-prompt hardening packet)

- Objective: execute `prompt-02-app-development-playbook` as a manual small packet to break routing loop churn and close `P1-B`.
- This step advances objective by: making top-level preflight CLI help actionable for operators while keeping wrapper behavior backward-compatible.
- Risks of misalignment: if CLI help remains opaque, users can misconfigure preflight and rely on unstable secondary command paths.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Updated `src/interfaces/cli.py` so `preflight --help` exposes concrete top-level flags.
  - Updated user/operator docs to match new CLI behavior (`README.md`, `docs/reference/cli.md`, `docs/troubleshooting.md`, `docs/manifest/09_runbook.md`).
  - Closed milestone `P1-B` in `docs/implementation/checklists/02_milestones.md`.
- In progress:
  - none

### Next

- Execute next manual packet to close `P1-C` (lockfile-backed install path) or move to trust-critical `P0-E`/`P0-F` implementation.

### Not now

- Additional prompt-loop reruns (`prompt-03`/`prompt-12`/`prompt-07`) until implementation-focused outcomes continue to close.

### Blocked

- No blocker for this packet; Prefect CLI entrypoint import mismatch remains an environment issue outside this UX change.

### Verification commands run

- `python3 -m src.interfaces.cli -h`
- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file README.md --changed-file docs/reference/cli.md --changed-file docs/troubleshooting.md --changed-file docs/manifest/09_runbook.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md`

## Prompt-07 Repo Audit Refresh (2026-02-08, after prompt-12 post prompt-03 post prompt-14 packet)

- Objective: execute packet 3 (`prompt-07-repo-audit-checklist`) as the next router-ordered prompt after the latest prompt-12 rerun.
- This step advances objective by: revalidating repo-level trust/usability risks and refreshing Prompt-00 handoff outcomes with current evidence.
- Risks of misalignment: stale audit context can hide persistent environment dependency drift and overstate readiness.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Refreshed `checkbox.md` with current rerun context and updated maintenance-risk wording.
  - Revalidated that top risks remain centered on confidence semantics, source-support visibility, and CLI usability.
  - Regenerated `docs/implementation/reports/prompt_execution_plan.md`.
- In progress:
  - none

### Next

- Execute packet 4 in router order: `prompt-13-research-paper-verification` (bounded rerun).

### Not now

- Citation expansion or broader research-track scope changes.

### Blocked

- No hard blocker for this docs packet; runtime Prefect CLI entrypoint still fails in active environment due dependency mismatch.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m src.interfaces.cli prefect preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "P0-E|P0-F|P1-B|P1-C|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-12 Literature Validation Refresh (2026-02-08, after prompt-03 post prompt-14 packet)

- Objective: execute packet 2 (`prompt-12-research-literature-validation`) as the next router-ordered prompt after the latest prompt-03 run.
- This step advances objective by: confirming literature evidence and artifact traceability remain stable while P0/P1 trust packets stay prioritized.
- Risks of misalignment: unbounded research expansion can dilute focus from open trust/usability outcomes.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - Added a new rerun section in `docs/implementation/reports/20_literature_review_log.md`.
  - Added a new rerun checklist item in `docs/implementation/checklists/20_literature_review.md`.
  - Regenerated `docs/implementation/reports/prompt_execution_plan.md`.
- In progress:
  - none

### Next

- Execute packet 3 in router order: `prompt-07-repo-audit-checklist`.

### Not now

- Citation-set expansion or additional research-track scope changes.

### Blocked

- No hard blocker for this prompt-12 packet.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-03 Alignment Review Gate (2026-02-08, post prompt-14 prompt-lib sequence)

- Objective: execute selected packet 1 (`prompt-03-alignment-review-gate`) from the updated prompt library.
- This step advances objective by: re-validating objective fit after recent planning/alignment packets and routing the next trust-critical corrections into milestones.
- Risks of misalignment: if this gate is skipped, stale alignment findings can mask unresolved trust semantics and operator UX drift.
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - Refreshed `docs/implementation/checklists/07_alignment_review.md` with current evidence and updated correction mapping.
  - Refreshed `docs/implementation/reports/alignment_review.md` for current router phase/cycle and milestone links.
  - Regenerated `docs/implementation/reports/prompt_execution_plan.md`.
- In progress:
  - none

### Next

- Execute packet 2 in router order: `prompt-12-research-literature-validation` (bounded rerun unless trust packet scope expands).

### Not now

- Additional research citation expansion while P0 trust and P1-B usability outcomes remain open.

### Blocked

- No hard blocker for this prompt-03 packet.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "P0-E|P0-F|P1-B|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-14 Improvement Direction Bet Loop (2026-02-08, post prompt-lib routing refresh)

- Objective: execute selected packet 1 (`prompt-14-improvement-direction-bet-loop`) from the updated prompt library.
- This step advances objective by: converting open trust/reliability and integration opportunities into ranked, milestone-ready improvement bets.
- Risks of misalignment: without explicit improvement bet routing, repeated audit/alignment passes can loop without converging on implementation packets.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - Added `docs/implementation/reports/improvement_directions.md` with ranked opportunity inventory and selected directions.
  - Added `docs/implementation/checklists/03_improvement_bets.md` with actionable improvement bet checkboxes.
  - Updated `docs/implementation/checklists/02_milestones.md` with improvement-bet milestone outcomes (`IB-01`, `IB-02`, `IB-03`) and packet `M5`.
  - Regenerated `docs/implementation/reports/prompt_execution_plan.md`.
- In progress:
  - none

### Next

- Execute next router-selected packet from updated plan (expected: `prompt-07-repo-audit-checklist`).

### Not now

- Spatial residual diagnostics as a separate packet until confidence/coverage packet is in flight.

### Blocked

- No hard blocker for prompt-14 packet completion.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
- `rg -n "RandomForest|XGBoost|xgboost|sklearn\\.ensemble" src tests`
- `rg -n "LISA|Moran|coverage by segment|segmented coverage" src tests docs`
- `test -f docs/implementation/reports/improvement_directions.md && test -f docs/implementation/checklists/03_improvement_bets.md`

## Prompt-15 Artifact-Feature Alignment Gate (2026-02-08, post prompt-lib refresh)

- Objective: execute selected packet 1 (`prompt-15-artifact-feature-alignment-gate`) from the updated prompt library.
- This step advances objective by: mapping load-bearing external artifacts to concrete feature/test coverage and routing top corrections into measurable milestones.
- Risks of misalignment: artifact-backed claims in literature/docs can drift from implementation and confidence semantics if not tied to verification surfaces.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_GAPS`

### Now

- Completed:
  - Added `docs/implementation/checklists/08_artifact_feature_alignment.md`.
  - Added `docs/implementation/reports/artifact_feature_alignment.md`.
  - Updated `docs/implementation/checklists/02_milestones.md` with measurable artifact-backed outcomes (`P0-E`, `P0-F`, `P1-D`, `P1-E`, `P1-F`) and packet `M4`.
  - Updated stale defer language for research prompts in milestones to reflect executed state.
  - Regenerated `docs/implementation/reports/prompt_execution_plan.md`.
- In progress:
  - none

### Next

- Execute next router-selected packet from updated plan (expected: `prompt-14-improvement-direction-bet-loop`).

### Not now

- Expanding research citations beyond current artifact index in this packet.

### Blocked

- No hard blocker for prompt-15 packet completion.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
- `rg -n "RandomForest|XGBoost|xgboost|sklearn\\.ensemble" src tests`
- `rg -n "LISA|Moran|coverage by segment|segmented coverage" src tests docs`
- `test -f docs/implementation/checklists/08_artifact_feature_alignment.md && test -f docs/implementation/reports/artifact_feature_alignment.md`

## Prompt-13 Research Paper Verification Refresh (2026-02-08, after latest prompt-07 post prompt-12/03 sequence)

- Objective: execute packet 4 in sequence (`prompt-13-research-paper-verification`) after the latest prompt-07 rerun.
- This step advances objective by: revalidating paper-to-code verification evidence and confirming reproducible paper build behavior remains healthy.
- Risks of misalignment: environment-level pytest plugin drift can invalidate naive verification commands even when paper/code remain aligned.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `paper/verification_log.md` rerun context refreshed with current command outcomes.
  - `paper/artifacts/sanity_case.json` regenerated.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 1 in current routing order: `prompt-03-alignment-review-gate`.

### Not now

- Expanding paper scope or introducing new literature claims in this rerun.

### Blocked

- No hard blocker for prompt-13 packet completion; raw pytest invocation remains fragile without plugin-autoload disable in local environment.

### Verification commands run

- `python3 scripts/paper_generate_sanity_artifact.py`
- `python3 scripts/verify_paper_contract.py`
- `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails in active env due third-party pytest plugin autoload)
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (passes: 12 tests)
- `python3 scripts/build_paper.py` (passes; builds `paper/main.pdf`)
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-07 Repo Audit Refresh (2026-02-08, after latest prompt-12 post prompt-03 post prompt-13 sequence)

- Objective: execute packet 3 in sequence (`prompt-07-repo-audit-checklist`) after the latest prompt-12 rerun.
- This step advances objective by: revalidating repo-level trust/usability risks and refreshing Prompt-00 handoff outcomes with current evidence.
- Risks of misalignment: stale audit context can hide persistent environment dependency drift and under-prioritize trust-critical corrections.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` rerun context refreshed with current evidence.
  - Prompt-00 handoff remains focused on confidence semantics, source-support visibility, and CLI/dependency hardening outcomes.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 4 in current routing order: `prompt-13-research-paper-verification` (bounded rerun).

### Not now

- Additional research-scope expansion beyond the bounded packet sequence.

### Blocked

- No hard blocker for this prompt-07 rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m src.interfaces.cli prefect preflight --help` (fails with Prefect/Pydantic import mismatch in active environment)
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-12 Literature Validation Refresh (2026-02-08, after latest prompt-03 post prompt-13 post prompt-07 sequence)

- Objective: execute packet 2 in sequence (`prompt-12-research-literature-validation`) after the latest prompt-03 rerun.
- This step advances objective by: revalidating literature evidence traceability while keeping research scope bounded.
- Risks of misalignment: unbounded citation expansion can distract from open trust/usability correction packets.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/20_literature_review_log.md` rerun section added for this packet.
  - `docs/implementation/checklists/20_literature_review.md` rerun checklist item added.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 3 in current routing order: `prompt-07-repo-audit-checklist`.

### Not now

- Citation-set expansion or new research artifacts beyond bounded prompt-12 revalidation scope.

### Blocked

- No blocker for this prompt-12 rerun packet.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-03 Alignment Review Gate Refresh (2026-02-08, after latest prompt-13 post prompt-07 post prompt-12 sequence)

- Objective: execute packet 1 in sequence (`prompt-03-alignment-review-gate`) after completing the latest prompt-13 rerun.
- This step advances objective by: revalidating objective alignment and ensuring trust/usability corrective actions remain schedulable.
- Risks of misalignment: stale alignment artifacts can hide unresolved confidence semantics, source-support visibility gaps, and operator UX drift.
- Cycle stage: `cool_down` (phase hint `phase_5`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md` rerun context refreshed with current evidence.
  - `docs/implementation/reports/alignment_review.md` rerun context refreshed with unchanged top-3 corrections.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 2 in current routing order: `prompt-12-research-literature-validation` (bounded rerun).

### Not now

- Research-scope expansion beyond bounded packet sequencing.

### Blocked

- No hard blocker for this alignment rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "P1-B|P1-C|Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-13 Research Paper Verification Refresh (2026-02-08, after latest prompt-07 post prompt-12 sequence)

- Objective: execute packet 4 in sequence (`prompt-13-research-paper-verification`) after the latest prompt-07 rerun.
- This step advances objective by: revalidating paper-to-code verification evidence and confirming reproducible paper build behavior remains healthy.
- Risks of misalignment: environment-level pytest plugin drift can invalidate naive verification commands even when paper/code remain aligned.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `paper/verification_log.md` rerun context refreshed with current command outcomes.
  - `paper/artifacts/sanity_case.json` regenerated.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 1 in current routing order: `prompt-03-alignment-review-gate`.

### Not now

- Expanding paper scope or introducing new literature claims in this rerun.

### Blocked

- No hard blocker for prompt-13 packet completion; raw pytest invocation remains fragile without plugin-autoload disable in local environment.

### Verification commands run

- `python3 scripts/paper_generate_sanity_artifact.py`
- `python3 scripts/verify_paper_contract.py`
- `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails in active env due third-party pytest plugin autoload)
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (passes: 12 tests)
- `python3 scripts/build_paper.py` (passes; builds `paper/main.pdf`)
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-07 Repo Audit Refresh (2026-02-08, after latest prompt-12 post prompt-13 packet-4 sequence)

- Objective: execute packet 3 in sequence (`prompt-07-repo-audit-checklist`) after the latest prompt-12 rerun.
- This step advances objective by: revalidating repo-level trust/usability risks and refreshing Prompt-00 handoff outcomes with current evidence.
- Risks of misalignment: stale audit context can hide persistent environment dependency drift and under-prioritize trust-critical corrections.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` rerun context refreshed with current evidence.
  - Prompt-00 handoff remains focused on confidence semantics, source-support visibility, and CLI/dependency hardening outcomes.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 4 in current routing order: `prompt-13-research-paper-verification` (bounded rerun).

### Not now

- Additional research-scope expansion beyond the bounded packet sequence.

### Blocked

- No hard blocker for this prompt-07 rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m src.interfaces.cli prefect preflight --help` (fails with Prefect/Pydantic import mismatch in active environment)
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-12 Literature Validation Refresh (2026-02-08, after latest prompt-03 post prompt-13 packet-4 refresh)

- Objective: execute packet 2 in sequence (`prompt-12-research-literature-validation`) after the latest prompt-03 rerun.
- This step advances objective by: revalidating literature evidence traceability while keeping research scope bounded.
- Risks of misalignment: unbounded citation expansion can distract from open trust/usability correction packets.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/20_literature_review_log.md` rerun section added for this packet.
  - `docs/implementation/checklists/20_literature_review.md` rerun checklist item added.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 3 in current routing order: `prompt-07-repo-audit-checklist`.

### Not now

- Citation-set expansion or new research artifacts beyond bounded prompt-12 revalidation scope.

### Blocked

- No blocker for this prompt-12 rerun packet.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-03 Alignment Review Gate Refresh (2026-02-08, after latest prompt-13 packet-4 refresh)

- Objective: execute packet 1 in sequence (`prompt-03-alignment-review-gate`) after completing the latest prompt-13 rerun.
- This step advances objective by: revalidating objective alignment and ensuring trust/usability corrective actions remain schedulable.
- Risks of misalignment: stale alignment artifacts can hide unresolved confidence semantics, source-support visibility gaps, and operator UX drift.
- Cycle stage: `cool_down` (phase hint `phase_5`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md` rerun context refreshed with current evidence.
  - `docs/implementation/reports/alignment_review.md` rerun context refreshed with unchanged top-3 corrections.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 2 in current routing order: `prompt-12-research-literature-validation` (bounded rerun).

### Not now

- Research-scope expansion beyond bounded packet sequencing.

### Blocked

- No hard blocker for this alignment rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "P1-B|P1-C|Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- `python3 scripts/build_paper.py`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-13 Research Paper Verification Refresh (2026-02-08, packet-4 execution refresh)

- Objective: execute packet 4 in sequence (`prompt-13-research-paper-verification`) after the latest prompt-07 rerun.
- This step advances objective by: revalidating the paper-to-code verification harness and restoring end-to-end reproducible paper build behavior.
- Risks of misalignment: paper reproducibility claims drift if LaTeX build commands fail or verification commands are environment-fragile.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `paper/main.tex` corrected for LaTeX-safe path rendering and citation usage.
  - `paper/verification_log.md` rerun section refreshed with current command outcomes.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 1 in current routing order: `prompt-03-alignment-review-gate`.

### Not now

- Expanding research/paper scope beyond bounded prompt-13 verification rerun.

### Blocked

- No hard blocker for prompt-13 packet completion; raw pytest invocation still requires plugin-autoload workaround in this local environment.

### Verification commands run

- `python3 scripts/paper_generate_sanity_artifact.py`
- `python3 scripts/verify_paper_contract.py`
- `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails in active env due third-party pytest plugin autoload)
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (passes: 12 tests)
- `python3 scripts/build_paper.py` (passes; builds `paper/main.pdf`)
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-07 Repo Audit Refresh (2026-02-08, after latest prompt-12)

- Objective: execute packet 3 in sequence (`prompt-07-repo-audit-checklist`) after the latest prompt-12 rerun.
- This step advances objective by: revalidating repo-level risks and refreshing Prompt-00 handoff outcomes with current evidence.
- Risks of misalignment: stale audit framing can miss persistent environment dependency drift and under-prioritize trust-critical corrections.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` rerun context refreshed with current evidence.
  - Prompt-00 handoff remains focused on confidence semantics, source-support visibility, and CLI/dependency hardening outcomes.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 4 in current routing order: `prompt-13-research-paper-verification` (bounded rerun).

### Not now

- Additional research-scope expansion beyond the bounded packet sequence.

### Blocked

- No hard blocker for this prompt-07 rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m src.interfaces.cli prefect preflight --help` (fails with Prefect/Pydantic import mismatch in active environment)
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "Deferred / Not Now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-12 Literature Validation Refresh (2026-02-08, after latest prompt-03)

- Objective: execute packet 2 in sequence (`prompt-12-research-literature-validation`) after the latest prompt-03 rerun.
- This step advances objective by: revalidating literature evidence traceability while keeping research scope bounded.
- Risks of misalignment: unbounded literature expansion can distract from open trust/usability corrections if packet boundaries are not explicit.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/20_literature_review_log.md` rerun section added for this packet.
  - `docs/implementation/checklists/20_literature_review.md` rerun checklist item added.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 3 in current routing order: `prompt-07-repo-audit-checklist`.

### Not now

- Citation-set expansion or new research artifacts beyond bounded prompt-12 revalidation scope.

### Blocked

- No blocker for this prompt-12 rerun packet.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-03 Alignment Review Gate Refresh (2026-02-08, after latest prompt-13)

- Objective: execute packet 1 in sequence (`prompt-03-alignment-review-gate`) after the latest prompt-13 rerun.
- This step advances objective by: revalidating objective alignment and confirming trust-risk corrections remain explicit and schedulable.
- Risks of misalignment: stale alignment artifacts can hide unresolved confidence semantics, source-support visibility gaps, and operator UX drift.
- Cycle stage: `cool_down` (phase hint `phase_5`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md` rerun context refreshed and required-question evidence revalidated.
  - `docs/implementation/reports/alignment_review.md` rerun context refreshed with unchanged top-3 corrections.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 2 in current routing order: `prompt-12-research-literature-validation` (bounded rerun).

### Not now

- Research-scope expansion beyond bounded packet sequencing.

### Blocked

- No hard blocker for this alignment rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "P1-B|P1-C|Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-13 Research Paper Verification Refresh (2026-02-08, after latest prompt-07)

- Objective: execute packet 4 in sequence (`prompt-13-research-paper-verification`) after the latest prompt-07 rerun.
- This step advances objective by: revalidating the paper-to-code contract and preserving reproducible verification evidence for load-bearing claims.
- Risks of misalignment: environment-level dependency/plugin drift can invalidate verification commands even when paper and code stay aligned.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `paper/verification_log.md` rerun section added with current command outcomes.
  - `paper/README.md` updated with pytest plugin-autoload fallback command for reproducibility.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Continue with the next routing packet (`prompt-03-alignment-review-gate`) if maintaining strict router order.

### Not now

- Expanding paper scope or introducing new literature claims in this rerun.

### Blocked

- No hard blocker for prompt-13 packet completion; note environment plugin fragility for raw pytest invocation.

### Verification commands run

- `python3 scripts/paper_generate_sanity_artifact.py`
- `python3 scripts/verify_paper_contract.py`
- `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails in active env due third-party pytest plugin autoload)
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (passes: 12 tests)
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-07 Repo Audit Refresh (2026-02-08, after latest prompt-12)

- Objective: execute packet 3 in sequence (`prompt-07-repo-audit-checklist`) after the latest prompt-12 rerun.
- This step advances objective by: revalidating repo-level risks and refreshing Prompt-00 handoff outcomes with current evidence.
- Risks of misalignment: stale audit framing can miss emergent runtime fragility (dependency/import drift) and under-prioritize trust-critical fixes.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` rerun context refreshed with current evidence.
  - Prompt-00 handoff in `checkbox.md` remains focused on confidence semantics, source support visibility, and CLI/dependency hardening outcomes.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 4 in current routing order: `prompt-13-research-paper-verification` (bounded rerun).

### Not now

- Additional research-scope expansion beyond the bounded packet sequence.

### Blocked

- No hard blocker for this prompt-07 rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m src.interfaces.cli prefect preflight --help` (fails with Prefect/Pydantic import mismatch in active environment)
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "Deferred / Not Now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-12 Literature Validation Refresh (2026-02-08, after latest prompt-03)

- Objective: execute packet 2 in sequence (`prompt-12-research-literature-validation`) after the latest prompt-03 rerun.
- This step advances objective by: revalidating literature evidence traceability while keeping research scope bounded.
- Risks of misalignment: unbounded research expansion can distract from open trust/usability corrections.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/20_literature_review_log.md` rerun section added for this packet.
  - `docs/implementation/checklists/20_literature_review.md` rerun checklist item added.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 3 in current routing order: `prompt-07-repo-audit-checklist`.

### Not now

- Citation-set expansion or new research artifacts beyond bounded prompt-12 revalidation scope.

### Blocked

- No blocker for this prompt-12 rerun packet.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-03 Alignment Review Gate Refresh (2026-02-08, after latest prompt-07)

- Objective: execute the next packet in sequence (`prompt-03-alignment-review-gate`) after the latest prompt-07 rerun.
- This step advances objective by: revalidating alignment evidence and confirming current trust-risk corrections remain explicitly packeted.
- Risks of misalignment: stale alignment artifacts can hide unresolved confidence semantics and source-support visibility gaps.
- Cycle stage: `cool_down` (phase hint `phase_5`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md` rerun context refreshed and required-question evidence revalidated.
  - `docs/implementation/reports/alignment_review.md` rerun context refreshed with unchanged top-3 corrections.
  - `docs/implementation/reports/prompt_execution_plan.md` regenerated after packet completion.
- In progress:
  - none

### Next

- Execute packet 2 in current routing order: `prompt-12-research-literature-validation` (bounded rerun).

### Not now

- Citation-set expansion or new research artifacts beyond bounded prompt-12 revalidation scope.

### Blocked

- No hard blocker for this alignment rerun packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "P1-B|P1-C|Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-07 Repo Audit Refresh (2026-02-08, after latest prompt-12)

- Objective: execute the next packet in sequence (`prompt-07-repo-audit-checklist`) after the latest bounded prompt-12 rerun.
- This step advances objective by: revalidating repo-level risks and keeping `checkbox.md` handoff priorities current.
- Risks of misalignment: stale audit framing can leave milestones chasing old gaps and underweight current trust risks.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` rerun context updated and findings revalidated against current evidence.
- In progress:
  - none

### Next

- Execute the next packet according to router order.

### Not now

- Additional research packet expansion before trust/usability outcomes are scheduled.

### Blocked

- No blocker for this prompt-07 rerun.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m src.interfaces.cli prefect preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "placeholder logic|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `rg -n "Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`

## Prompt-12 Literature Validation Refresh (2026-02-08, after prompt-03)

- Objective: execute the next recommended packet (`prompt-12-research-literature-validation`) after the latest alignment refresh.
- This step advances objective by: revalidating literature-grounded evidence and keeping research artifacts in sync without expanding scope.
- Risks of misalignment: repeated research expansion can distract from scheduled trust/usability corrections if packet boundaries are not explicit.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/20_literature_review_log.md` rerun section added.
  - `docs/implementation/checklists/20_literature_review.md` rerun verification item added.
- In progress:
  - none

### Next

- Execute the next packet after this rerun according to router ordering.

### Not now

- Citation-set expansion beyond the current 14 load-bearing sources.

### Blocked

- No blocker for this prompt-12 rerun.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`

## Prompt-03 Alignment Review Gate Refresh (2026-02-08)

- Objective: execute the next recommended packet (`prompt-03-alignment-review-gate`) after prompt-07 audit refresh.
- This step advances objective by: re-validating alignment with current audit evidence and remapping top corrective outcomes to next packets.
- Risks of misalignment: if confidence semantics and source-support visibility gaps stay unscheduled, user trust can drift even with passing CI/tests.
- Cycle stage: `cool_down` (phase hint `phase_5`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md` refreshed with audit-aligned top-3 corrections.
  - `docs/implementation/reports/alignment_review.md` refreshed with updated misalignment summary and packet mapping.
- In progress:
  - none

### Next

- Schedule and execute `C-01`/`C-02`/`C-03` via a small `prompt-02` hardening packet.

### Not now

- Additional research packet expansion before trust/usability corrections are scheduled in milestones.

### Blocked

- No hard blocker for this alignment refresh packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `rg -n "placeholder logic|confidence" src/valuation/services/valuation_persister.py`
- `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
- `python3 scripts/check_command_map.py`
- `rg -n "P1-B|P1-C|Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`

## Prompt-07 Repo Audit Refresh (2026-02-08)

- Objective: execute the next recommended packet (`prompt-07-repo-audit-checklist`) after the prompt-12 rerun.
- This step advances objective by: refreshing `checkbox.md` with current evidence and updating the prompt-00 handoff outcomes.
- Risks of misalignment: if the audit is not refreshed, milestones can continue to target already-closed gaps and miss current trust risks (confidence semantics, source support visibility, CLI UX).
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` refreshed with current-state audit findings and Prompt-00 handoff.
- In progress:
  - none

### Next

- Re-run prompt routing and execute the next selected packet from the updated audit state.

### Not now

- Additional research packet expansion before P1 trust and usability outcomes from the new audit are scheduled.

### Blocked

- No blocker for this audit refresh packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`

## Prompt-12 Literature Validation Refresh (2026-02-08)

- Objective: execute the next recommended packet (`prompt-12-research-literature-validation`) after the alignment refresh.
- This step advances objective by: revalidating literature evidence and confirming artifact traceability remains consistent after prompt-13.
- Risks of misalignment: stale literature claims or missing artifacts could weaken research-backed decisions and verification logs.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/20_literature_review_log.md` rerun section added.
  - `docs/implementation/checklists/20_literature_review.md` remains consistent for bounded rerun.
- In progress:
  - none

### Next

- Execute the next routing packet (`prompt-07-repo-audit-checklist`) if still selected.

### Not now

- Expanding citation set beyond the current 14 load-bearing sources in this rerun.

### Blocked

- No blocker for this packet rerun.

### Verification commands run

- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`

## Prompt-07 Repo Audit Refresh (2026-02-08)

- Objective: execute the next recommended packet (`prompt-07-repo-audit-checklist`) after the prompt-12 rerun.
- This step advances objective by: replacing stale audit findings with current evidence and producing a fresh P0/P1 handoff in `checkbox.md`.
- Risks of misalignment: if this audit is not refreshed, milestones can continue to target already-closed gaps and miss current trust risks (confidence semantics, source support visibility, CLI UX).
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` fully refreshed with current-state audit findings and Prompt-00 handoff.
- In progress:
  - none

### Next

- Re-run prompt routing and execute the next selected packet from the updated audit state.

### Not now

- Additional research packet expansion before P0/P1 trust and usability outcomes from the new audit are scheduled.

### Blocked

- No blocker for this audit refresh packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m src.interfaces.cli prefect preflight --help`
- `python3 scripts/check_command_map.py`
- `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/09_runbook.md`
- `python3 -m pytest --markers`
- `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q`

## Prompt-03 Alignment Review Gate Refresh (2026-02-08)

- Objective: rerun `prompt-03-alignment-review-gate` after prompt-13 to confirm objective alignment and update corrective actions.
- This step advances objective by: refreshing the alignment gate, documenting drift risks, and mapping next corrective packets to milestones.
- Risks of misalignment: stale milestone routing language and open UX/install gaps can degrade onboarding metrics.
- Cycle stage: `cool_down` (phase hint `phase_5`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md` refreshed with current evidence.
  - `docs/implementation/reports/alignment_review.md` refreshed with updated verdict and corrective actions.
- In progress:
  - none

### Next

- Address `P1-B` (preflight help UX), `P1-C` (lockfile-backed install path), and refresh deferred routing language in `docs/implementation/checklists/02_milestones.md`.

### Not now

- Additional research packets until corrective actions above are closed.

### Blocked

- No hard blocker for this alignment refresh packet.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `rg -n "Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`

## Prompt-13 Research Paper Verification (2026-02-08)

- Objective: execute `prompt-13-research-paper-verification` to convert literature-backed claims into a paper-linked verification harness.
- This step advances objective by: producing a LaTeX paper, code-to-equation mapping, verification log, regression artifact, and unit tests that lock load-bearing equations to implementation.
- Risks of misalignment: contract drift between paper and code, missing reproducibility checks, and unpinned regression anchors.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - `paper/main.tex`
  - `paper/references.bib`
  - `paper/implementation_map.md`
  - `paper/verification_log.md`
  - `paper/README.md`
  - `paper/artifacts/sanity_case.json`
  - `scripts/build_paper.py`
  - `scripts/verify_paper_contract.py`
  - `scripts/paper_generate_sanity_artifact.py`
  - `tests/unit/paper/test_paper_verification.py`
- In progress:
  - none

### Next

- Router recommends `prompt-03-alignment-review-gate` as the next packet (cycle `cool_down`, phase `phase_5`).

### Not now

- Expanding paper scope beyond verification and reproducibility claims.

### Blocked

- No hard blocker for prompt-13 completion.

### Verification commands run

- `python3 scripts/paper_generate_sanity_artifact.py`
- `python3 scripts/verify_paper_contract.py`
- `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live"`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Prompt-12 Literature Validation Refresh (2026-02-08)

- Objective: execute the next recommended packet (`prompt-12-research-literature-validation`) after the alignment gate refresh.
- This step advances objective by: revalidating evidence-grounded modeling claims and ensuring artifact-traceable literature inputs remain consistent.
- Risks of misalignment: unbounded literature expansion can pull focus away from open execution risks (`P1-B`, `P1-C`) if not kept as a bounded rerun.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/20_literature_review_log.md` (rerun section added).
  - `docs/implementation/checklists/20_literature_review.md` (rerun revalidation item added).
- In progress:
  - none

### Next

- Run packet 3 from the current routing plan: `prompt-07-repo-audit-checklist`.

### Not now

- Expanding citation set beyond the current 14 load-bearing sources in this rerun.

### Blocked

- No blocker for this packet rerun.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
- `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- `test -f docs/manifest/20_literature_review.md && test -f docs/implementation/reports/20_literature_review_log.md && test -f docs/implementation/checklists/20_literature_review.md`

## Prompt-03 Alignment Review Gate Refresh (2026-02-08)

- Objective: rerun `prompt-03-alignment-review-gate` after prompt-pack update and current-state routing.
- This step advances objective by: replacing stale alignment findings with evidence that matches current repo artifacts and open P1 execution risks.
- Risks of misalignment: stale milestone/defer language can produce contradictory packet routing; unresolved CLI/dependency UX gaps can degrade onboarding and objective metrics.
- Cycle stage: `cool_down` (phase hint `phase_5`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md` refreshed with current evidence and mapped corrections.
  - `docs/implementation/reports/alignment_review.md` refreshed with updated verdict, risks, and packet mapping.
- In progress:
  - none

### Next

- Execute C-01 (`P1-B`): make `preflight --help` actionable and sync docs/runbook.
- Execute C-03: refresh stale deferred research gating language in milestones + status.
- Execute C-02 (`P1-C`): converge on lockfile-backed install policy and docs.

### Not now

- Additional research packet expansion until `P1-B`/`P1-C` and routing-language cleanup are closed.

### Blocked

- No hard blocker for this alignment refresh packet.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- `python3 -m src.interfaces.cli preflight --help`
- `python3 scripts/check_command_map.py`
- `python3 -m pytest --markers`
- `test -f docs/manifest/07_observability.md && test -f docs/implementation/checklists/02_milestones.md && test -f .github/workflows/ci.yml && test -f docs/reference/versioning_policy.md && test -f docs/implementation/checklists/06_release_readiness.md`
- `rg -n "P1-B|P1-C|\\[ \\]" docs/implementation/checklists/02_milestones.md`

## Prompt-12 Literature Validation Packet (2026-02-08)

- Objective: execute `prompt-12-research-literature-validation` to ground valuation architecture decisions in primary sources with traceable evidence.
- This step advances objective by: producing a curated literature review, claim-validation log, and artifact index links that map directly to build/avoid decisions for the repo.
- Risks of misalignment: router heuristics still surface `prompt-07` due uncommitted CI changes; without explicit packeting this can cause audit-loop churn instead of progressing the research track.
- Cycle stage: `research_bet` (phase hint `phase_6`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/manifest/20_literature_review.md`
  - `docs/implementation/reports/20_literature_review_log.md`
  - `docs/implementation/checklists/20_literature_review.md`
  - `docs/artifacts/index.json` + `docs/artifacts/README.md` initialized and populated with 14 load-bearing literature artifacts.
- In progress:
  - none

### Next

- Run `prompt-13-research-paper-verification` to convert load-bearing claims into paper-linked verification matrix and reproducibility checks.

### Not now

- Additional `prompt-07` reruns unless CI workflow scope materially changes beyond current baseline.
- Non-load-bearing literature expansion beyond the current valuation/retrieval/uncertainty decision set.

### Blocked

- No hard blocker for Prompt-12 packet completion.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
- `python3 prompts/scripts/web_artifacts.py --repo-root . init`
- `python3 prompts/scripts/web_artifacts.py --repo-root . add-meta ...` (14 entries)
- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `curl -Ls "https://api.crossref.org/works/<doi>"`
- `curl -Ls "https://export.arxiv.org/api/query?id_list=<arxiv_id>"`

## Prompt-07 Post-CI Audit (2026-02-08)

- Objective: rerun repo audit after CI baseline landed to refresh risks and packet routing.
- This step advances objective by: replacing stale pre-CI findings in `checkbox.md` with current evidence and updated prompt handoff outcomes.
- Risks of misalignment: CI file changes can keep routing biased toward repeated audit runs unless findings are explicitly refreshed.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `checkbox.md` refreshed with post-CI baseline findings and Prompt-00 handoff.
- In progress:
  - none

### Next

- Run `prompt-11-docs-diataxis-release` for release discipline artifacts (`CHANGELOG.md`, versioning policy, release readiness checklist, upgrade notes template).

### Not now

- Research-track prompts (`prompt-12`, `prompt-13`) remain deferred until release-discipline outcomes are closed.

### Blocked

- No hard blocker for post-CI audit completion.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- `python3 scripts/check_command_map.py`
- `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/09_runbook.md`
- `python3 -m src.interfaces.cli preflight --help`

## Prompt-02 Packet 2 (2026-02-08)

- Objective: execute the next recommended packet by implementing CI baseline + docs-sync guardrails.
- This step advances objective by: adding enforceable GitHub Actions checks that run offline quality gates and fail on docs drift for runtime/test/CI changes.
- Risks of misalignment: CI install/runtime may drift from local expectations if dependency and command-map docs are not kept in sync.
- Intensity mode: `Standard`
- Cycle stage: `build` (phase hint `phase_3.5`)
- Appetite: `medium`
- Packet state: `downhill`

### Now

- Completed:
  - `.github/workflows/ci.yml`
  - `scripts/check_docs_sync.py`
  - `scripts/check_command_map.py`
  - `docs/manifest/09_runbook.md` (new CI guard command IDs)
  - `docs/manifest/11_ci.md` (workflow and required checks mapping)
  - `docs/manifest/10_testing.md` (CI baseline status update)
  - `docs/implementation/checklists/02_milestones.md` (Packet M2 marked complete)
  - `docs/implementation/epics/epic_reliability_baseline.md` (task completion)
  - `docs/manifest/03_decisions.md` (CI baseline ADR entry)
- In progress:
  - none

### Next

- Re-run `prompt-00-prompt-routing-plan` to refresh recommended prompt order after CI baseline.
- Start P1 release discipline packet (`prompt-11`) unless refreshed routing introduces higher-priority objective risk.

### Not now

- `prompt-12-research-literature-validation` and `prompt-13-research-paper-verification` remain deferred by active milestone policy.
- Broad release polish beyond required discipline artifacts remains deferred until prompt routing is refreshed.

### Blocked

- No hard blocker for Packet 2 completion.

### Verification commands run

- `python3 scripts/check_command_map.py`
- `python3 scripts/check_docs_sync.py --changed-file .github/workflows/ci.yml --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/11_ci.md`
- `python3 -m src.interfaces.cli -h`
- `python3 -m pytest --markers`
- `python3 -m pytest --run-integration --run-e2e -m "not live"`

## Prompt-02 Packet 1 (2026-02-08)

- Objective: execute the next recommended prompt (`prompt-02`) as a bounded reliability-governance packet.
- This step advances objective by: adding milestones, observability, runbook command map, CI pointer mapping, and assumptions tracking required for P0 closure.
- Risks of misalignment: router heuristics still detect research artifacts; without explicit defers, work can drift away from core reliability gates.
- Intensity mode: `Standard`
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/checklists/02_milestones.md`
  - `docs/implementation/reports/project_plan.md`
  - `docs/implementation/reports/assumptions_register.md`
  - `docs/implementation/reports/README.md`
  - `docs/implementation/epics/epic_reliability_baseline.md`
  - `docs/manifest/02_tech_stack.md`
  - `docs/manifest/06_security.md`
  - `docs/manifest/07_observability.md`
  - `docs/manifest/08_deployment.md`
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/10_testing.md` (command-map pointer update)
  - `docs/manifest/11_ci.md` (runbook command-ID mapping)
  - `docs/manifest/12_conventions.md`
  - `docs/.prompt_system.yml` (`command_map_file` now points to runbook)
  - `docs/manifest/03_decisions.md` (prompt-02 packet decisions)
  - `docs/INDEX.md` (canonical navigation update)
- In progress:
  - none

### Next

- Run Packet M2 (P0-C execution): add `.github/workflows/ci.yml` with offline test gates mapped to runbook command IDs.
- Add docs-sync integrity guardrail in CI for status/checklist/manifest updates.
- Re-run `prompt-00` routing after CI baseline lands to confirm next bounded packet.

### Not now

- `prompt-11-docs-diataxis-release` until P0 CI baseline and observability checks are in place.
- `prompt-12-research-literature-validation` and `prompt-13-research-paper-verification` remain deferred by milestone policy.
- CLI preflight UX refactor (P1) remains deferred.

### Blocked

- No hard blocker for Packet 1 docs completion.

### Verification commands run

- `python3 -m src.interfaces.cli -h`
- `python3 -m src.interfaces.cli preflight --help`
- `python3 -m pytest --markers`
- `rg -n "## Command Map|CMD-" docs/manifest/09_runbook.md docs/manifest/11_ci.md`
- `rg -n "Logging Schema|golden signals|SLI|SLO|Debug Playbook|Objective metric mapping" docs/manifest/07_observability.md`
- `test -f docs/implementation/checklists/02_milestones.md && test -f docs/implementation/reports/project_plan.md && test -f docs/implementation/reports/assumptions_register.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`

## Prompt Routing Packet (2026-02-08)

- Objective: select the next execution prompt as a bounded packet that closes P0 gaps from the repo audit.
- This step advances objective by: committing a single immediate prompt (`prompt-02`) for milestones + observability/CI gating and explicitly deferring non-objective tracks.
- Risks of misalignment: router heuristics detect research artifacts and may recommend research prompts unless objective-gated by current P0 backlog.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`

### Now

- Completed:
  - `docs/implementation/reports/prompt_execution_plan.md` updated via `prompt-00`.
- In progress:
  - none

### Next

- Run `prompt-02-app-development-playbook` Packet 1:
  - create `docs/implementation/checklists/02_milestones.md`
  - map P0 outcomes (A/B/C) from `checkbox.md`
  - create observability/CI gate mapping references from `docs/manifest/11_ci.md`

### Not now

- `prompt-11-docs-diataxis-release` until P0 milestones/observability/CI gates are scheduled.
- `prompt-12-research-literature-validation` and `prompt-13-research-paper-verification` per defer note in `checkbox.md`.

### Blocked

- No hard blocker for routing packet completion.

### Verification commands run

- `python3 prompts/scripts/prompt_router.py --root prompts registry --format json`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`

## Alignment Review Gate Packet (2026-02-08)

- Objective: verify current implementation is still aligned with `docs/manifest/00_overview.md#Core Objective`.
- This step advances objective by: producing explicit drift findings, corrective actions, and next-packet routing for alignment.
- Risks of misalignment: without milestones/observability/CI artifacts, alignment can regress between packets.
- Cycle stage: `bet` (phase hint `phase_2`)
- Appetite: `small`
- Packet state: `downhill`
- Alignment verdict: `ALIGNED_WITH_RISKS`

### Now

- Completed:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- In progress:
  - none

### Next

- Run `prompt-07-repo-audit-checklist` and produce `checkbox.md`.
- Create `docs/implementation/checklists/02_milestones.md` and map C-01/C-02/C-03 corrections.
- Implement observability and CI discipline packets.

### Not now

- Research packet execution (`prompt-12` / `prompt-13`) until C-01/C-02/C-03 are scheduled.

### Blocked

- No blocker for alignment gate completion.

### Verification commands run

- `python3 -m src.interfaces.cli preflight --help`
- `rg -n "time-to-first-dashboard|Success metrics|pipeline_runs|agent_runs|SLI|SLO|observability|runbook" docs src`
- `rg -n "multi-tenant|SaaS|financial advice|investment execution|automated investment|trade execution|hosted" docs src README.md`
- `sqlite3 data/listings.db "select count(*) from listings;"`
- `sqlite3 data/listings.db "select count(*) from valuations;"`
- `sqlite3 -cmd ".timeout 3000" data/listings.db "select count(*) from pipeline_runs;"`
- `sqlite3 data/listings.db "select count(*) from agent_runs;"`

## Architecture Coherence Packet (2026-02-08)

- Objective: establish a canonical, repo-grounded architecture baseline that can gate future implementation packets.
- This step advances objective by: creating C4/runtime/deployment architecture docs plus contracts/data-model docs and a coherence verdict.
- Risks of misalignment: without CI/release/runbook artifacts, architecture can still drift from implementation during fast iteration.
- Cycle stage: `shape` (phase hint `phase_0.5`)
- Appetite: `medium`
- Packet state: `downhill`
- Readiness verdict: `GO_WITH_RISKS`

### Now

- Completed:
  - `docs/manifest/01_architecture.md`
  - `docs/manifest/04_api_contracts.md`
  - `docs/manifest/05_data_model.md`
  - `docs/implementation/checklists/00_architecture_coherence.md`
  - `docs/implementation/reports/architecture_coherence_report.md`
  - `docs/.prompt_system.yml` (DOCS_ROOT lock)
- In progress:
  - none

### Next

- Run `prompt-03-alignment-review-gate` packet.
- Run `prompt-07-repo-audit-checklist` packet.
- Convert top outcomes into `docs/implementation/checklists/02_milestones.md`.

### Not now

- CI workflow and docs-update guardrails.
- Release discipline artifacts (`CHANGELOG.md`, versioning policy, release checklist).
- Dedicated `docs/manifest/09_runbook.md` command map page.

### Blocked

- No hard blocker for this packet.

### Verification commands run

- `python3 -m src.interfaces.cli -h`
- `python3 -m src.platform.workflows.prefect_orchestration -h`
- `python3 -m pytest --markers`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`

## Prior Packet: Test Stabilization (2026-02-06)

## Current

- Status: Complete (all offline suites green; live suite remains opt-in)
- Goal: clean, stable, meaningful green across unit/integration/e2e + data contracts.

## Latest Results (Baseline)

- Unit (excluding integration/e2e/live): pass (62 passed; 2026-02-06)
- Unit data contracts: pass (9 passed; 2026-02-06)
- Integration (`--run-integration -m integration`): pass (19 passed; 2026-02-06)
- E2E (`--run-e2e -m e2e`): pass (1 passed; 2026-02-06)

## Latest Results (Stability Verification)

- Unit: pass (3 consecutive runs; 62 passed each; 2026-02-06)
- Unit data contracts: pass (3 consecutive runs; 9 passed each; 2026-02-06)
- Integration: pass (1 run; 19 passed; 2026-02-06)
- E2E: pass (1 run; 1 passed; 2026-02-06)

## Commands

- Unit:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"`
- Unit data contracts:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"`
- Integration:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration`
- E2E:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e`
- All offline:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration --run-e2e -m "not live"`

## Next

- Optional: decide whether to keep `@pytest.mark.live` tests in CI (currently opt-in only).

## Current Packet: Figma-to-Live Alignment Audit (2026-03-10)

## Current

- Status: Complete for backend/trust-surface packet; UI parity remains partial.
- Goal: make the Figma redesign auditable against the live app with real DB-backed surfaces and structured runtime failures instead of broken placeholders.

## Delivered

- Stabilized `POST /valuations` so real insufficiency cases now return structured `422` responses instead of uncaught `500`s.
- Added live read APIs for pipeline/source-health screens:
  - `/job-runs`
  - `/benchmarks`
  - `/coverage-reports`
  - `/data-quality-events`
  - `/source-contract-runs`
- Added persisted product APIs for Figma-first-class flows:
  - `/watchlists`
  - `/saved-searches`
  - `/memos`
  - `/memos/{id}`
  - `/memos/{id}/export`
  - `/comp-reviews`
  - `/command-center/runs`
- Reduced dashboard startup coupling by removing eager retriever initialization from dashboard service loading.
- Wrote the alignment artifact:
  - `docs/implementation/reports/figma_live_alignment_matrix.md`

## Verification

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/application/test_workspace_service.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/application/test_reporting_service.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py -q`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- `python3 -m compileall src/application src/adapters/http src/interfaces/dashboard/services`
- live API checks on March 10, 2026:
  - `GET /health`
  - `GET /coverage-reports`
  - `GET /source-contract-runs`
  - `POST /jobs/preflight` with all refresh steps skipped to seed one real `job_runs` entry
  - `POST /valuations` success for listing `3cddb9e0c75d`
  - `POST /valuations` structured unavailable for listing `3fe641d70a322bf312591463cebc7bbe`
  - `POST /valuations` structured unavailable for listing `4zLGu`

## Remaining gaps

- New watchlist/memo/comp-review/saved-search surfaces are API-backed but not yet implemented as dedicated UI routes.
- Listing Detail still lacks a live dossier route and listing-scoped provenance timeline.
- Pipeline benchmark panel remains blocked by live data because `benchmark_runs` is still empty.
