# Worklog

## 2026-03-11 (CodeWiki teaching docs + README front-door packet)

- Executed the documentation/front-door packet to make the repository easier to understand as a system, not just a collection of commands.
- Root-cause changes:
  - added `docs/explanation/problem_landscape_and_solution.md` as a concept-first explanation page covering:
    - the property-intelligence problem landscape,
    - repository design beliefs and tradeoffs,
    - pipeline and concept-to-code diagrams,
    - valuation math and calibration logic,
    - curated references and code-reading guidance
  - rewrote `README.md` around the repo’s current primary surface:
    - FastAPI + React workbench first,
    - Streamlit explicitly framed as legacy,
    - verified install/run commands,
    - stronger links into the deeper docs set
  - added a real workbench screenshot for the README from the local UI verification artifacts:
    - `docs/images/workbench-overview.png`
  - updated `docs/INDEX.md` so the new teaching page is visible under Explanation
- References reviewed and used:
  - repeat-sales / housing index foundations:
    - Bailey, Muth, Nourse (1963)
    - Case and Shiller (1987, 1988)
  - hedonic and valuation framing:
    - Rosen (1974)
    - Deng, Gyourko, Wu (2012)
    - Eurostat HPI handbook
    - RICS Red Book page
  - quantile / uncertainty / retrieval / baseline modeling:
    - Koenker and Bassett (1978)
    - Breiman (2001)
    - Chen and Guestrin (2016)
    - Reimers and Gurevych (2019)
    - Romano, Patterson, Candès (2019)
    - Barber et al. (2021)
    - Angelopoulos and Bates (2021)
- Verification evidence:
  - `python3 -m src.interfaces.cli -h`
  - `python3 -m src.interfaces.cli preflight --help`
  - verified doc/runtime file existence for `requirements.lock`, `docker-compose.yml`, `config/runtime.yaml`, and `docs/INDEX.md`
  - verified new README image path:
    - `docs/images/workbench-overview.png`
  - manually checked that the new README links to the new teaching doc and that the docs index exposes it
- Notes:
  - this packet intentionally changed docs and image assets only
  - the teaching page is designed to sit above the existing manifest/explanation docs rather than replacing them

## 2026-03-10 (scraper reliability and coverage packet)

- Executed the scraper reliability/coverage packet to make live source health observable and truthful instead of doc-driven guesswork.
- Root-cause changes:
  - added a shared canonical source-ID map in `src/listings/source_ids.py` and used it to stop alias drift between crawlers, normalizers, persistence, and audits
  - added shared crawl-status/completeness helpers in `src/listings/crawl_contract.py`
  - upgraded `src/platform/utils/compliance.py` so robots failures now produce explicit reasons (`robots_fetch_denied`, `robots_fetch_failed`, `robots_disallowed`) instead of only a boolean block
  - changed `src/listings/scraping/client.py` to preserve policy-block reasons through batch preflight and avoid pointless sequential fallback on explicit policy blocks
  - updated the active crawler set (`pisos`, `imovirtual`, `rightmove`, `zoopla`, `onthemarket`, `idealista`, `immobiliare`) to emit measurable metadata and explicit terminal statuses such as `policy_blocked` / `fetch_failed`
  - canonicalized hardcoded legacy source IDs in blocked/deferred crawlers (`funda_nl`, `immowelt_de`, `seloger_fr`, `realtor_us`, `redfin_us`, `homes_us`)
  - fixed the `imovirtual` normalizer and persistence path so canonical DB rows now use `imovirtual_pt`
  - extended unified crawl to persist crawl-health evidence into `source_contract_runs`
  - updated `SourceCapabilityService` to:
    - aggregate alias IDs under one canonical source
    - include coverage ratios for title/price/area/location/bed/bath/images
    - prefer recent `source_contract_runs` over `docs/crawler_status.md`
  - updated `PipelineAPI.source_support_summary()` to prefer recent source-contract evidence and expose canonical IDs plus latest-run metadata
- Updated runtime/docs surfaces:
  - `src/listings/source_ids.py`
  - `src/listings/crawl_contract.py`
  - `src/platform/utils/compliance.py`
  - `src/listings/scraping/client.py`
  - `src/listings/agents/crawlers/uk/rightmove.py`
  - `src/listings/agents/crawlers/uk/zoopla.py`
  - `src/listings/agents/crawlers/spain/pisos.py`
  - `src/listings/agents/crawlers/portugal/imovirtual.py`
  - `src/listings/agents/crawlers/uk/onthemarket.py`
  - `src/listings/agents/crawlers/spain/idealista.py`
  - `src/listings/agents/crawlers/italy/immobiliare.py`
  - `src/listings/services/listing_persistence.py`
  - `src/listings/services/observation_persistence.py`
  - `src/listings/workflows/unified_crawl.py`
  - `src/application/sources.py`
  - `src/interfaces/api/pipeline.py`
  - `README.md`
  - `docs/explanation/scraping_architecture.md`
  - `docs/crawler_status.md`
  - `docs/implementation/00_status.md`
  - `docs/implementation/03_worklog.md`
- Added regression coverage:
  - `tests/unit/listings/scraping/test_scrape_client__batch_error_propagation.py`
  - `tests/unit/listings/crawlers/test_rightmove_crawler__structured_fetch_errors.py`
  - `tests/unit/application/test_source_capability_service.py`
  - `tests/unit/interfaces/test_pipeline_api__source_support.py`
  - `tests/integration/listings/unified_crawl/test_unified_crawl_runner__persists_observations_and_source_contracts.py`
  - updated `tests/integration/listings/unified_crawl/test_crawl_normalize_persist__fixture_html__saves_rows.py`
  - updated live tests for `idealista`, `onthemarket`, `immobiliare`, and `imovirtual`
- Verification evidence:
  - `venv/bin/python -m pytest tests/unit/listings/scraping/test_scrape_client__batch_error_propagation.py tests/unit/listings/crawlers/test_rightmove_crawler__structured_fetch_errors.py tests/unit/application/test_source_capability_service.py tests/unit/interfaces/test_pipeline_api__source_support.py tests/integration/listings/unified_crawl/test_unified_crawl_runner__persists_observations_and_source_contracts.py tests/integration/listings/unified_crawl/test_crawl_normalize_persist__fixture_html__saves_rows.py -q` (`9 passed, 8 skipped`)
  - `venv/bin/python -m pytest tests/live/scrapers/test_rightmove_real_live.py tests/live/scrapers/test_imovirtual_real_live.py tests/live/scrapers/test_idealista_real_live.py tests/live/scrapers/test_onthemarket_real_live.py tests/live/scrapers/test_immobiliare_real_live.py --run-live -q` (`5 passed`)
  - `venv/bin/python -m pytest -m "not integration and not e2e and not live" -q` (`140 passed, 1 skipped, 53 deselected`)
  - `venv/bin/python -m pytest --run-integration -m integration -q` (`26 passed, 168 deselected`)
- Residual limits:
  - the Node sidecar still is not source-aware enough to replace the Python crawler path
  - blocked portals remain blocked on current infrastructure; the improvement in this packet is truthful surfacing and evidence capture, not bypass
  - the main live DB still needs fresh unified-crawl runs to accumulate non-test `listing_observations` and `source_contract_runs`

## 2026-03-10 (product validation and recovery packet)

- Executed the product validation/recovery packet to turn one failing unit contract, one opaque live scraper failure, and one misleading train/benchmark workflow contract into explicit, test-backed product behavior.
- Root-cause changes:
  - aligned the older quality-gate test with the current strict validator semantics and added dedicated coverage for missing coordinates plus missing-vs-out-of-range surface area
  - propagated browser batch task failures through the scrape stack:
    - `src/listings/scraping/browser_engine.py`
    - `src/listings/scraping/client.py`
    - crawler agents now preserve structured fetch errors instead of degrading to empty failure payloads
  - lowered Rightmove’s default browser concurrency and wait time to make the live smoke less brittle under the PyDoll path
  - fixed the two observed `pisos` parser corruption modes in `src/listings/agents/processors/pisos.py`:
    - price extraction now takes the first real sale price instead of concatenating all digits in a noisy price box
    - surface-area fallback now uses narrower text blocks and drops out-of-range values instead of capturing arbitrary `m2` mentions
  - changed fusion train/benchmark policy from hidden `--research-only` gating to explicit readiness semantics in `src/ml/training/policy.py`
    - sale runs now resolve `label_source=auto` to sold-label mode
    - sale train/benchmark fail fast with clear readiness diagnostics derived from the DB
    - `--research-only` remains accepted only as a deprecated compatibility flag
- Updated runtime/docs surfaces:
  - `src/ml/training/policy.py`
  - `src/ml/training/train.py`
  - `src/ml/training/benchmark.py`
  - `src/listings/scraping/browser_engine.py`
  - `src/listings/scraping/client.py`
  - `src/listings/agents/crawlers/uk/rightmove.py`
  - `src/listings/agents/crawlers/uk/onthemarket.py`
  - `src/listings/agents/crawlers/uk/zoopla.py`
  - `src/listings/agents/crawlers/portugal/imovirtual.py`
  - `src/listings/agents/crawlers/spain/pisos.py`
  - `src/listings/agents/processors/pisos.py`
  - `README.md`
  - `docs/reference/cli.md`
  - `docs/implementation/00_status.md`
  - `docs/implementation/03_worklog.md`
- Added regression coverage:
  - `tests/unit/listings/quality_gate/test_listing_quality_gate__validate_listing__returns_reasons.py`
  - `tests/unit/listings/normalizers/test_pisos__inline_html__extracts_fields.py`
  - `tests/unit/listings/scraping/test_scrape_client__batch_error_propagation.py`
  - `tests/unit/listings/crawlers/test_rightmove_crawler__structured_fetch_errors.py`
  - `tests/unit/ml/test_training_and_benchmark_policy.py`
- Verification evidence:
  - `venv/bin/python -m pytest tests/unit/listings/quality_gate/test_listing_quality_gate__validate_listing__returns_reasons.py tests/unit/listings/normalizers/test_pisos__inline_html__extracts_fields.py tests/unit/listings/scraping/test_scrape_client__batch_error_propagation.py tests/unit/listings/crawlers/test_rightmove_crawler__structured_fetch_errors.py tests/unit/ml/test_training_and_benchmark_policy.py -q` (`15 passed`)
  - `venv/bin/python -m pytest -m "not integration and not e2e and not live" -q` (`137 passed, 53 deselected`)
  - `venv/bin/python -m pytest --run-integration -m integration -q` (`26 passed, 164 deselected`)
  - `venv/bin/python -m pytest --run-e2e -m e2e -q` (`6 passed, 184 deselected`)
  - `venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py --run-live -q` (`1 passed`)
  - `venv/bin/python -m pytest tests/live/scrapers/test_pisos_real_live.py tests/live/scrapers/test_rightmove_real_live.py --run-live -q` (`2 passed`)
  - `npm run build` in `frontend` (`built`, bundle-size warnings unchanged)
  - `npm run build` in `scraper` (`passed`)
  - `venv/bin/python -m src.interfaces.cli -h`
  - `venv/bin/python -m src.ml.training.train --help`
  - `venv/bin/python -m src.ml.training.benchmark --help`
  - `venv/bin/python -m src.ml.training.train`
    - exit `2`
    - readiness output showed `sale_rows=4737`, `closed_label_rows=0`
  - `venv/bin/python -m src.ml.training.benchmark`
    - exit `2`
    - readiness output showed `sale_rows=4737`, `closed_label_rows=0`
  - FastAPI smoke on `127.0.0.1:8771`
    - `/api/v1/health` returned `ok`
    - `/api/v1/sources` returned `supported=0 experimental=8 degraded=1 blocked=11`
    - `/api/v1/workbench/explore?country=PT&limit=10` returned `available_count=1` and `valuation_ready_count=9`
    - `/api/v1/workbench/listings/4407e016fedf87c111257f9fa662083b/context` returned `valuation_status=available`
    - `POST /api/v1/valuations` for `4407e016fedf87c111257f9fa662083b` returned a fair value successfully
    - `POST /api/v1/valuations` for `55b4232e50a23b1855d3d64ff93ffb84` returned structured `insufficient_comps`
- Residual limits:
  - the parser fixes improve future `pisos` ingests but do not rewrite already-corrupted DB rows
  - sale-model productization is still bounded by the absence of sold labels, which is now surfaced explicitly rather than hidden behind a special flag
- Next:
  - run a targeted refresh/backfill of `pisos` so the served ES corpus benefits from the parser corrections
  - decide whether the next packet is historical data cleanup or source-by-source sidecar migration

## 2026-03-10 (`M9 / C-10` fallback interval policy packet)

- Executed the active small packet to close the weak-regime interval-policy gap without broadening into `C-11` or `C-12`.
- Root-cause changes:
  - added an explicit registry-level interval-policy decision in `src/valuation/services/conformal_calibrator.py`
  - changed valuation spot/projection interval selection in `src/valuation/services/valuation.py` to use policy decisions instead of sample-count checks alone
  - persisted fallback reason and numeric trigger diagnostics in valuation evidence via `EvidencePack`
  - changed `PipelineAPI` assumption badges so `lit-jackknifeplus-2021` is a runtime `caution` policy rather than a `gap`
- Updated runtime/docs surfaces:
  - `src/platform/domain/schema.py`
  - `src/valuation/services/conformal_calibrator.py`
  - `src/valuation/services/valuation.py`
  - `src/interfaces/api/pipeline.py`
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/20_literature_review.md`
  - `docs/how_to/interpret_outputs.md`
  - `docs/manifest/03_decisions.md`
  - `docs/implementation/checklists/02_milestones.md`
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
  - `docs/implementation/reports/artifact_feature_alignment.md`
  - `docs/implementation/00_status.md`
  - `docs/implementation/03_worklog.md`
- Added regression coverage:
  - expanded `tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py` with explicit policy-decision cases
  - added `tests/unit/valuation/test_valuation_service__fallback_interval_policy.py`
  - updated `tests/unit/interfaces/test_pipeline_api__source_support.py`
- Verification evidence:
  - `python3 -m compileall src/platform/domain/schema.py src/valuation/services/conformal_calibrator.py src/valuation/services/valuation.py src/interfaces/api/pipeline.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/valuation/test_valuation_service__fallback_interval_policy.py tests/unit/interfaces/test_pipeline_api__source_support.py -q` (`10 passed`)
- Next:
  - rerun the prompt-03 alignment gate for `M9` closure evidence
  - keep `C-11` and `C-12` deferred until that follow-up decides otherwise

## 2026-03-10 (backend recovery packet: data contracts, research gates, and scraper sidecar scaffold)

- Executed the next backend recovery packet to stop the repo from treating invalid sale-model and browser-crawl paths as normal operation.
- Root-cause changes:
  - replaced the weak crawl-time listing contract with stricter validation for identifiers, ranges, currency, listing type, and location
  - persisted live crawl artifacts into the existing Bronze/Silver/Gold-adjacent tables:
    - raw fetches -> `listing_observations.status=bronze_raw`
    - normalized valid listings -> `silver_validated`
    - normalized rejected listings -> `silver_rejected`
    - canonical source/entity links -> `listing_entities`
  - re-enabled robots enforcement in the shared compliance manager so blocked domains are skipped explicitly rather than silently ignored
  - added a local analytics artifact service that writes Parquet + JSON metadata under `data/analytics/`
  - changed the benchmark/audit application path to export real artifact files instead of only DB rows
  - froze fusion model train/benchmark commands behind explicit research-only gates and blocked sale runs without sold-label readiness
  - added a Python crawl-plan contract plus a buildable Node/TypeScript Crawlee + Playwright sidecar in `scraper/`
- Updated runtime/code surfaces:
  - `src/listings/services/quality_gate.py`
  - `src/listings/services/observation_persistence.py`
  - `src/listings/workflows/unified_crawl.py`
  - `src/platform/utils/compliance.py`
  - `src/application/analytics.py`
  - `src/application/container.py`
  - `src/application/pipeline.py`
  - `src/ml/training/policy.py`
  - `src/ml/training/train.py`
  - `src/ml/training/benchmark.py`
  - `src/listings/scraping/sidecar.py`
  - `scraper/package.json`
  - `scraper/tsconfig.json`
  - `scraper/src/index.ts`
  - `README.md`
  - `docs/manifest/02_tech_stack.md`
  - `docs/explanation/scraping_architecture.md`
  - `docs/reference/cli.md`
- Added regression coverage:
  - `tests/unit/listings/services/test_quality_gate__strict_contract.py`
  - `tests/unit/listings/services/test_observation_persistence.py`
  - `tests/unit/application/test_analytics_service.py`
  - `tests/unit/ml/test_training_and_benchmark_policy.py`
  - `tests/unit/listings/scraping/test_sidecar_contract.py`
  - updated `tests/unit/application/test_reporting_service.py` to assert the new benchmark hard-stop instead of the old invalid success path
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/listings/services/test_quality_gate__strict_contract.py tests/unit/listings/services/test_observation_persistence.py tests/unit/application/test_analytics_service.py tests/unit/ml/test_training_and_benchmark_policy.py tests/unit/listings/scraping/test_sidecar_contract.py -q` (`10 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py tests/unit/application/test_reporting_service.py tests/unit/application/test_source_capability_service.py -q` (`8 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/integration/listings/unified_crawl/test_crawl_normalize_persist__fixture_html__saves_rows.py -q` (`7 skipped`, unchanged fixture/live gating behavior)
  - `python3 -m compileall src/application src/listings/services src/listings/workflows src/listings/scraping src/ml/training src/platform/utils src/interfaces`
  - `python3 -m src.interfaces.cli audit-serving-data`
    - exported a real quality artifact:
      - `data/analytics/quality/serving-eligibility-audit-3de3550a0a05.parquet`
      - `data/analytics/quality/serving-eligibility-audit-3de3550a0a05.json`
    - confirmed current live invalid slice remains:
      - `total_rows=7851`
      - `invalid_rows=5891`
      - dominant source: `pisos=5874`
  - `python3 -m src.listings.scraping.sidecar --source-id pisos --start-url https://example.com/search --write-only`
    - wrote a typed crawl plan under `data/crawl_plans/`
  - `python3 -m src.ml.training.train --help`
  - `python3 -m src.ml.training.benchmark --help`
  - `python3 -m src.listings.scraping.sidecar --help`
  - `npm install` and `npm run build` in `scraper/`
- Residual limits:
  - the sidecar contract is real and buildable, but product crawl jobs still default to the legacy Python crawler path until source-by-source cutover lands
  - the live DB still has no closed-sale labels, so sale-model benchmarking remains intentionally blocked
  - docs outside the touched runtime stack still contain older Prefect/fusion/LanceDB framing and need a broader docs pass
- Next: migrate the first browser-heavy sources onto the sidecar fetch runtime, then replace the invalid fusion-centered benchmark story with a true closed-label quantile baseline packet.

## 2026-03-10 (routing, data trust, and workbench usability packet)

- Executed the packet to fix the current product’s most immediate operational failures: SPA deep-link collisions, corrupted listing rows reaching deal surfaces, map workbench defaulting into unusable unavailable states, and Streamlit still presenting itself as a first-class UI.
- Root-cause changes:
  - moved the FastAPI JSON surface under `/api/v1/...` so `/workbench`, `/watchlists`, `/memos`, `/listings/{id}`, and `/comp-reviews/{id}` are clean SPA routes again
  - introduced a shared serving-eligibility contract for price/area/room-count/coordinate/source-state sanity and used it in both the React workbench and the legacy Streamlit loader
  - removed hidden live valuation fallback from the workbench explore path and replaced it with explicit cached-valuation semantics:
    - `available`
    - `not_evaluated`
    - `missing_required_fields`
    - `insufficient_comps`
  - added an operator-facing `audit-serving-data` CLI command to scan the current DB and persist serving-eligibility issues into `data_quality_events`
  - marked the Streamlit dashboard as deprecated in both CLI and UI while keeping it runnable during the migration window
- Updated runtime/product surfaces:
  - `src/adapters/http/app.py`
  - `src/application/serving.py`
  - `src/application/reporting.py`
  - `src/application/workbench.py`
  - `src/interfaces/cli.py`
  - `src/interfaces/dashboard/services/loaders.py`
  - `src/interfaces/dashboard/app.py`
  - `frontend/src/api.ts`
  - `frontend/src/types.ts`
  - `frontend/src/pages.tsx`
  - `frontend/vite.config.ts`
  - `README.md`
  - `docs/getting_started/quickstart.md`
  - `docs/reference/cli.md`
- Updated regression coverage:
  - `tests/unit/adapters/http/test_fastapi_local_api.py`
    - verifies `/api/v1` namespace,
    - verifies SPA deep-link HTML for colliding browser routes,
    - verifies workbench status semantics and corrupted-row exclusion
  - `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`
    - stays green after the shared serving gate was introduced into the legacy loader
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py -q` (`3 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py -q` (`1 passed`)
  - `python3 -m compileall src/application src/adapters/http src/interfaces/dashboard src/interfaces`
  - `npm run build` (in `frontend/`)
    - build passed; Vite still warns about the large map bundle and one browser-external `spawn` warning from a loaders dependency
  - `python3 -m src.interfaces.cli audit-serving-data`
    - recorded a real serving audit over the live DB:
      - `total_rows=7851`
      - `invalid_rows=5891`
      - dominant source contribution: `pisos=5874`
  - `python3 -m src.interfaces.cli api --help`
- Residual limits:
  - the data-trust gate is protecting serving surfaces now, but parser/root-cause fixes are still needed source-by-source because the invalid live slice is large
  - the legacy dashboard remains available during the transition and still carries non-strategic code we should remove once React parity is complete
  - the frontend bundle remains heavy and should be split in a follow-up packet
- Next: run the parser/source cleanup packet for the dominant corrupted source set, then continue migrating remaining operator flows from Streamlit into React so the `dashboard` alias can be removed.

## 2026-03-10 (map-centric React workbench packet)

- Executed the redesign-to-runtime packet that makes the new React workbench the canonical UI direction and moves spatial exploration to the center of the app.
- Root-cause changes:
  - replaced the Vite starter shell with a real routed React app served by the local FastAPI process
  - implemented a map-dominant workbench using MapLibre + deck.gl with real listing markers, live legend semantics, selection basket behavior, and synchronized table/right-rail context
  - kept the backend read model as the source of truth through `/workbench/explore`, `/workbench/layers`, and `/workbench/listings/{id}/context`
- Updated frontend/runtime surfaces:
  - `frontend/src/App.tsx`
  - `frontend/src/main.tsx`
  - `frontend/src/index.css`
  - `frontend/src/styles.css`
  - `frontend/src/pages.tsx`
  - `frontend/src/components/WorkbenchMap.tsx`
  - `frontend/src/api.ts`
  - `frontend/src/types.ts`
  - `frontend/index.html`
  - `frontend/vite.config.ts`
  - `src/application/workbench.py`
  - `src/application/container.py`
  - `src/adapters/http/app.py`
- Added/updated coverage:
  - `tests/unit/adapters/http/test_fastapi_local_api.py`
    - now validates `/workbench/explore`, `/workbench/layers`, and `/workbench/listings/{id}/context` in addition to the earlier local API surfaces
- Verification evidence:
  - `python3 -m compileall src/application src/adapters/http`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py -q` (`2 passed`)
  - `npm install` (in `frontend/`)
  - `npm run build` (in `frontend/`)
    - build passed; Vite emitted a non-blocking large-chunk warning because the first map bundle is still heavy
  - `python3 -m src.interfaces.cli api --host 127.0.0.1 --port 8001`
  - Playwright wrapper smoke verification against the live app:
    - `/workbench` loaded with live listings after removing the overly aggressive default support floor
    - selecting a listing row updated the right rail with real listing details and actions
    - `Open dossier` navigated successfully to `/listings/{id}`
- Residual limits:
  - no viewport-bound querying yet; the workbench still loads the current filtered result set rather than refetching on map pan/zoom
  - the frontend bundle is large and should be split in a follow-up packet
  - Figma MCP screenshot refresh was blocked by seat/tool-call limits; browser/runtime verification used the existing design context plus local Playwright CLI instead
- Next: add viewport-aware map querying and chunking/code-splitting, then start replacing remaining redesign destinations with deeper workflow views.

## 2026-03-10 (persist runtime quality artifacts packet)

- Executed a bounded refactor packet to make the new runtime refactor tables operational instead of schema-only.
- Root-cause changes:
  - persisted source capability audits into `source_contract_runs`
  - emitted source-level `data_quality_events` for blocked, stale, and corruption conditions
  - persisted benchmark execution history into `benchmark_runs`
  - persisted segmented conformal coverage output into `coverage_reports`
- Updated application/runtime paths:
  - `src/application/sources.py`
  - `src/application/reporting.py`
  - `src/application/pipeline.py`
  - `src/application/container.py`
  - `src/valuation/workflows/calibration.py`
- Added focused coverage:
  - `tests/unit/application/test_source_capability_service.py`
  - `tests/unit/application/test_reporting_service.py`
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/unit/application/test_source_capability_service.py tests/unit/application/test_reporting_service.py tests/unit/adapters/http/test_fastapi_local_api.py tests/unit/platform/test_migrations__runtime_tables.py` (`6 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/unit/interfaces tests/unit/application tests/unit/adapters/http tests/unit/platform tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/valuation/test_valuation_persister__confidence_semantics.py` (`21 passed`)
  - `python3 -m src.interfaces.cli preflight --skip-crawl --skip-market-data --skip-index --skip-training`
    - confirmed the local preflight path still runs and now writes persisted source audit rows against the live DB
  - `python3 -m src.interfaces.cli api --help`
- Residual limits:
  - `listing_observations` and `listing_entities` are still not wired into real crawl persistence paths
  - host-Python pytest collection still requires `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
- Next: wire Bronze/Silver/Gold persistence into actual ingest flows or move to the frontend/API serving split, but do not claim the full refactor plan is complete yet.

## 2026-03-10 (ChatMock default backend packet)

- Executed a bounded model-backend packet to replace default local-model assumptions with ChatMock/OpenAI-compatible routing.
- Root-cause changes:
  - moved shared completions, description analysis, and VLM requests onto config-driven `api_base` routing
  - removed the direct Ollama-only description-analysis client
  - made unsupported vision requests explicit (`vlm_backend_request_failed` / `fusion_vlm_failed`) instead of silently reverting to Ollama
- Updated config and runtime surfaces:
  - `src/platform/settings.py`
  - `config/llm.yaml`
  - `config/description_analyst.yaml`
  - `config/vlm.yaml`
  - `src/platform/utils/llm.py`
  - `src/listings/services/description_analyst.py`
  - `src/listings/services/llm_normalizer.py`
  - `src/listings/services/vlm.py`
- Added focused coverage:
  - `tests/unit/platform/test_llm__chatmock_routing.py`
  - `tests/unit/listings/services/test_description_analyst__chatmock.py`
  - `tests/unit/listings/services/test_vlm__chatmock.py`
  - `tests/integration/listings/test_feature_fusion__chatmock_paths.py`
- Updated docs and packet status:
  - `README.md`
  - `docs/reference/configuration.md`
  - `docs/how_to/configuration.md`
  - `docs/manifest/02_tech_stack.md`
  - `docs/manifest/03_decisions.md`
  - `docs/manifest/07_observability.md`
  - `docs/manifest/10_testing.md`
  - `docs/implementation/checklists/01_plan.md`
  - `docs/implementation/00_status.md`
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/platform/test_llm__chatmock_routing.py -q` (`2 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/listings/services/test_description_analyst__chatmock.py -q` (`2 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/listings/services/test_vlm__chatmock.py -q` (`3 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q` (`3 passed`)
  - `python3 -m src.interfaces.cli preflight --help`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/platform/test_llm__chatmock_routing.py tests/unit/listings/services/test_description_analyst__chatmock.py tests/unit/listings/services/test_vlm__chatmock.py --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q` (`10 passed`)
- Next: validate the configured ChatMock model names against the actual local deployment and adjust `config/*.yaml` if the served catalog differs.

## 2026-03-10 (live dashboard stale-valuation hotfix + manual Playwright rerun)

- Reproduced the live dashboard issue with Playwright MCP against the repo-native launch path:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m src.interfaces.cli dashboard --skip-preflight --server.headless true --server.address 127.0.0.1 --server.port 63073`
  - observed `Pipeline Status` reporting `Listings tracked: 7851` while the main surface stopped at `No listings yet`.
- Root cause:
  - `src/interfaces/dashboard/services/loaders.py` requested cached valuations via `ValuationPersister.get_latest_valuation(...)`,
  - `src/valuation/services/valuation_persister.py` only returned valuations newer than 7 days,
  - repo data contained 718 valuations, all from `2026-01-14` through `2026-01-17`, so the dashboard treated every cached valuation as missing and skipped rows when live valuation fallback failed.
- Implemented the smallest fix:
  - allowed `ValuationPersister.get_latest_valuation(..., max_age_days=None)` to return the latest persisted valuation without freshness filtering,
  - switched the dashboard loader to use that path while leaving freshness warnings in `PipelineAPI.pipeline_status()`.
- Added regression coverage:
  - `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`
    - verifies the dashboard renders a listing from a 45-day-old cached valuation without invoking live valuation fallback.
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py -q` (`1 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q` (`2 passed`)
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`5 passed`)
  - `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q` (`1 passed`)
  - manual Playwright MCP rerun after the fix:
    - deal flow rendered `23` listings,
    - memo panel opened for a live listing,
    - `🧭 Pipeline Status` rendered tracked counts, source labels, and assumption badges,
    - atlas loaded without browser console errors.
- Residual observation:
  - the browser still logs one Streamlit slider warning about the current budget range not aligning with slider step/min/max.
- Next: keep the stale-cache hotfix isolated unless the user wants a follow-up packet for the remaining slider warning or for live command-center execution.

## 2026-02-09 (prompt-03 rerun for `M8` closure and `M9` activation)

- Executed the next suggested prompt: `prompt-03-alignment-review-gate`.
- Updated alignment artifacts to current post-`M8` state:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Closed `M8` routing evidence and activated next packet:
  - `docs/implementation/checklists/02_milestones.md`
    - marked `M8` and `Packet M8` complete,
    - added active `M9` packet for `C-10`,
    - deferred `C-11`/`C-12` unless small-packet appetite allows.
- Reframed open corrective scope:
  - active: `C-10` (fallback interval policy),
  - deferred follow-ons: `C-11` (ablation cadence), `C-12` (decomposition re-evaluation trigger).
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`5 passed`)
  - `rg -n "C-08|C-09|C-10|C-11|C-12|\\[x\\] M8|\\[ \\] M9|Packet M8|Packet M9|Next suggested prompt" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/07_alignment_review.md docs/implementation/reports/alignment_review.md -S`
  - `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/07_alignment_review.md --changed-file docs/implementation/reports/alignment_review.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: execute `prompt-02-app-development-playbook` for active `M9` (`C-10` first), then rerun `prompt-03`.

## 2026-02-09 (prompt-02 packet for `M8/C-08` + `C-09` retriever/decomposition decisions)

- Executed the next suggested prompt: `prompt-02-app-development-playbook`.
- Added retriever ablation implementation packet:
  - `src/ml/training/retriever_ablation.py` (`geo_only` vs `geo_structure` vs `geo_structure_semantic` evaluation, decision thresholds, drift proxy, report writer).
  - `src/interfaces/cli.py` (`retriever-ablation` passthrough command).
- Added regression coverage:
  - `tests/unit/ml/test_retriever_ablation_workflow__decisions.py`
  - `tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py` (new `retriever-ablation` forwarding test).
- Produced packet evidence artifacts:
  - `docs/implementation/reports/retriever_ablation_report.json`
  - `docs/implementation/reports/retriever_ablation_report.md`
  - key outcomes: semantic decision `simplify`; decomposition status `insufficient_segment_samples`; drift proxy `ok`.
- Synced docs and routing surfaces:
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/10_testing.md`
  - `docs/manifest/03_decisions.md`
  - `docs/manifest/20_literature_review.md`
  - `docs/implementation/checklists/08_artifact_feature_alignment.md`
  - `docs/implementation/reports/artifact_feature_alignment.md`
  - `docs/implementation/checklists/02_milestones.md` (marked prompt-02 progress for `M8`; prompt-03 follow-up left open)
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/ml/test_retriever_ablation_workflow__decisions.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py -q` (`6 passed`)
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m src.interfaces.cli retriever-ablation --listing-type sale --max-targets 80 --num-comps 5 --output-json docs/implementation/reports/retriever_ablation_report.json --output-md docs/implementation/reports/retriever_ablation_report.md`
  - `python3 scripts/check_artifact_feature_contract.py`
  - `python3 scripts/check_command_map.py`
  - `python3 scripts/check_docs_sync.py --changed-file src/ml/training/retriever_ablation.py --changed-file src/interfaces/cli.py --changed-file tests/unit/ml/test_retriever_ablation_workflow__decisions.py --changed-file tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/manifest/03_decisions.md --changed-file docs/manifest/20_literature_review.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: run `prompt-03-alignment-review-gate` to close `M8` routing evidence and keep `C-10` as the remaining active corrective packet.

## 2026-02-09 (prompt-03 rerun for `M7` closure and `M8` activation)

- Executed the next suggested prompt: `prompt-03-alignment-review-gate`.
- Updated alignment artifacts to current trust-closure state:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Removed stale corrective focus on already-closed trust items (`O-04`, `G-02`) and re-centered top corrective actions on:
  - `C-08` retriever ablation / embedding-drift decision (`O-02`),
  - `C-09` decomposition diagnostics decision packet (`O-03`),
  - `C-10` fallback interval policy gap (`lit-jackknifeplus-2021`).
- Updated milestone routing state:
  - `docs/implementation/checklists/02_milestones.md`
    - marked `Packet M7` complete,
    - marked prompt-03 substep complete,
    - promoted `Packet M8` to active (`now`).
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`5 passed`)
  - `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q` (`1 passed`)
  - `rg -n "\\[x\\] Packet M7|\\[ \\] Packet M8|Prompt-03 follow-up|C-08|C-09|C-10" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/07_alignment_review.md docs/implementation/reports/alignment_review.md`
  - `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/07_alignment_review.md --changed-file docs/implementation/reports/alignment_review.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: execute `prompt-02-app-development-playbook` for active `M8` (`C-08` + `C-09`), then rerun `prompt-03`.

## 2026-02-09 (prompt-06 follow-up for `M7/C-07` live-browser trust evidence)

- Executed the next suggested prompt: `prompt-06-ui-e2e-verification-loop` (follow-up packet for `C-07` / `O-05`).
- Added live-runtime UI verification:
  - `tests/live/ui/test_dashboard_live_browser__source_support.py`
    - launches real dashboard runtime via CLI on an ephemeral local port,
    - validates `Source support` and `Assumption badges` captions plus artifact evidence marker (`lit-case-shiller-1988`) in a Playwright session.
- Refreshed prompt-06 closure artifacts:
  - `docs/implementation/checklists/05_ui_verification.md` (`G-02` closed with live-session evidence)
  - `docs/implementation/reports/ui_verification_final_report.md` (gating section now explicitly closed)
- Synced artifact-alignment closure:
  - `docs/implementation/checklists/08_artifact_feature_alignment.md` (`C-07`, `O-05` checked)
  - `docs/implementation/reports/artifact_feature_alignment.md` (live-browser closure reflected in summary/matrix/routing notes)
- Verification evidence:
  - `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q` (`1 passed`)
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
  - `python3 scripts/check_artifact_feature_contract.py`
  - `python3 scripts/check_command_map.py`
  - `python3 scripts/check_docs_sync.py --changed-file tests/live/ui/test_dashboard_live_browser__source_support.py --changed-file docs/implementation/checklists/05_ui_verification.md --changed-file docs/implementation/reports/ui_verification_final_report.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/09_runbook.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: run `prompt-03-alignment-review-gate` follow-up to refresh drift verdict with `G-02` + `O-05` now closed and finalize `M7` routing state.

## 2026-02-09 (prompt-02 packet for `M7/C-06` assumption badges)

- Executed the next suggested prompt: `prompt-02-app-development-playbook`.
- Implemented runtime assumption badge surfaces:
  - `src/interfaces/api/pipeline.py`
    - added `PipelineAPI.assumption_badges(...)`,
    - embedded `assumption_badges` into `PipelineAPI.pipeline_status(...)`.
  - `src/interfaces/dashboard/app.py`
    - added assumption badge parsing/rendering in system-status and `🧭 Pipeline Status` views.
  - `src/interfaces/dashboard/services/loaders.py`
    - added fallback `assumption_badges` payload key.
- Updated tests:
  - `tests/unit/interfaces/test_pipeline_api__source_support.py`
    - validates `assumption_badges` contract (`artifact_ids`, status classes).
  - `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
    - fixture payload includes `assumption_badges`,
    - asserts assumption badge captions appear in `🧭 Pipeline Status`.
- Updated docs/governance surfaces:
  - `docs/manifest/03_decisions.md`
  - `docs/manifest/04_api_contracts.md`
  - `docs/manifest/07_observability.md`
  - `docs/how_to/interpret_outputs.md`
  - `docs/crawler_status.md`
  - `docs/implementation/checklists/05_ui_verification.md`
  - `docs/implementation/reports/ui_verification_final_report.md`
  - `docs/implementation/checklists/08_artifact_feature_alignment.md` (`C-06` + `O-04` closed)
  - `docs/implementation/reports/artifact_feature_alignment.md`
  - `docs/implementation/checklists/02_milestones.md` (`P1-G` + `M7` prompt-02 substep closed)
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_pipeline_api__source_support.py -q` (`2 passed`)
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`5 passed`)
  - `rg -n "assumption_badges|artifact_ids|Source labels: supported / blocked / fallback|Assumption badges:" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py tests/unit/interfaces/test_pipeline_api__source_support.py tests/e2e/ui/test_dashboard_ui_verification_loop.py docs/implementation/checklists/05_ui_verification.md docs/implementation/reports/ui_verification_final_report.md docs/how_to/interpret_outputs.md docs/manifest/04_api_contracts.md docs/manifest/07_observability.md -S`
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `python3 scripts/check_artifact_feature_contract.py`
  - `python3 scripts/check_docs_sync.py --changed-file src/interfaces/api/pipeline.py --changed-file src/interfaces/dashboard/app.py --changed-file src/interfaces/dashboard/services/loaders.py --changed-file tests/unit/interfaces/test_pipeline_api__source_support.py --changed-file tests/e2e/ui/test_dashboard_ui_verification_loop.py --changed-file docs/manifest/03_decisions.md --changed-file docs/manifest/04_api_contracts.md --changed-file docs/manifest/07_observability.md --changed-file docs/how_to/interpret_outputs.md --changed-file docs/crawler_status.md --changed-file docs/implementation/checklists/05_ui_verification.md --changed-file docs/implementation/reports/ui_verification_final_report.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: execute prompt-06 follow-up (`C-07` / `O-05`) for live-browser trust evidence, then rerun prompt-03 alignment gate.

## 2026-02-09 (prompt-15 alignment gate rerun after `M6` closure)

- Executed the next suggested packet: `prompt-15-artifact-feature-alignment-gate`.
- Refreshed prompt-15 deliverables:
  - `docs/implementation/checklists/08_artifact_feature_alignment.md`
  - `docs/implementation/reports/artifact_feature_alignment.md`
  - `docs/implementation/checklists/02_milestones.md`
- Routing outcomes:
  - kept verdict at `ALIGNED_WITH_GAPS`,
  - preserved previously closed outcomes (`C-01`..`C-05`, `O-01`),
  - promoted open trust items into active packet `M7` (`C-06` assumption badges, `C-07` live-browser evidence),
  - deferred retrieval/decomposition packet to `M8` (`C-08`, `C-09`).
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "C-06|C-07|O-05|\\[ \\]" docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/checklists/02_milestones.md docs/implementation/reports/artifact_feature_alignment.md -S`
  - `python3 scripts/check_artifact_feature_contract.py`
  - `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: execute `M7` packet sequence (`prompt-02 -> prompt-06 -> prompt-03`) for assumption badges and live-browser trust evidence.

## 2026-02-09 (prompt-03 alignment gate rerun after M6 closure)

- Executed `prompt-03-alignment-review-gate` as the next suggested packet after `M6` closure.
- Updated alignment artifacts:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Refresh outcomes:
  - kept verdict at `ALIGNED_WITH_RISKS`,
  - marked `M6`-era gaps (`UI verification` + `runtime source labels`) as closed evidence,
  - narrowed open corrective set to `O-04` assumption badges, `G-02` live-browser verification, and `O-02` retrieval ablation decision packet.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `test -f docs/implementation/checklists/05_ui_verification.md && test -f docs/implementation/reports/ui_verification_final_report.md && test -d tests/e2e`
  - `rg --files tests/e2e`
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`5 passed`)
  - `rg -n "supported|blocked|fallback|source_support|Source labels" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py docs/crawler_status.md -S`
  - `rg -n "O-04|\\[ \\]" docs/implementation/checklists/03_improvement_bets.md docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/checklists/02_milestones.md -S`
  - `python3 scripts/check_docs_sync.py --changed-file docs/implementation/checklists/07_alignment_review.md --changed-file docs/implementation/reports/alignment_review.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: execute the post-`M6` trust packet for `O-04` + `G-02` (`prompt-15 -> prompt-02 -> prompt-06 -> prompt-03`).

## 2026-02-09 (prompt-02 M6 source-support packet)

- Executed the next suggested prompt: `prompt-02-app-development-playbook` for open `M6/C-02` scope.
- Implemented runtime source-support status surfaces:
  - `src/interfaces/api/pipeline.py`
    - added source status parsing/classification from `docs/crawler_status.md` + `config/sources.yaml`,
    - added `PipelineAPI.source_support_summary(...)` and `PipelineAPI.pipeline_status(...)`.
  - `src/interfaces/dashboard/services/loaders.py`
    - switched `load_pipeline_status()` to `PipelineAPI.pipeline_status()`.
  - `src/interfaces/dashboard/app.py`
    - rendered explicit `supported`, `blocked`, `fallback` labels, counts, examples, and crawler-status guide reference.
- Added regression coverage:
  - `tests/unit/interfaces/test_pipeline_api__source_support.py`
  - `tests/e2e/ui/test_dashboard_ui_verification_loop.py` (`test_dashboard_ui_pipeline_status__shows_source_support_labels`)
- Updated docs/checklists:
  - `docs/crawler_status.md`
  - `docs/manifest/03_decisions.md`
  - `docs/manifest/04_api_contracts.md`
  - `docs/manifest/07_observability.md`
  - `docs/implementation/checklists/02_milestones.md` (`M6` complete)
  - `docs/implementation/checklists/03_improvement_bets.md` (`IB-06` complete)
  - `docs/implementation/checklists/05_ui_verification.md`
  - `docs/implementation/reports/ui_verification_final_report.md`
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_pipeline_api__source_support.py -q` (`2 passed`)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`5 passed`)
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q` (`6 passed, 134 deselected`)
  - `rg -n "supported|blocked|fallback|source_support|source support" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py -S`
  - `python3 scripts/check_command_map.py`
  - `python3 scripts/check_docs_sync.py --changed-file src/interfaces/api/pipeline.py --changed-file src/interfaces/dashboard/services/loaders.py --changed-file src/interfaces/dashboard/app.py --changed-file tests/unit/interfaces/test_pipeline_api__source_support.py --changed-file tests/e2e/ui/test_dashboard_ui_verification_loop.py --changed-file docs/crawler_status.md --changed-file docs/manifest/03_decisions.md --changed-file docs/manifest/04_api_contracts.md --changed-file docs/manifest/07_observability.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/05_ui_verification.md --changed-file docs/implementation/reports/ui_verification_final_report.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
- Next: execute `prompt-03-alignment-review-gate` to refresh drift verdict and close `C-02` evidence in alignment artifacts.

## 2026-02-09 (prompt-06 manual rerun refresh)

- Re-executed `prompt-06-ui-e2e-verification-loop` as a bounded rerun to refresh UI verification artifacts and command-map pointers.
- Updated docs:
  - `docs/implementation/checklists/05_ui_verification.md`
  - `docs/implementation/reports/ui_verification_final_report.md`
  - `docs/manifest/09_runbook.md` (added `CMD-DASHBOARD-HELP`, `CMD-DASHBOARD-SKIP-PREFLIGHT`)
- Verification evidence:
  - `python3 -m src.interfaces.cli -h`
  - `python3 -m src.interfaces.cli dashboard --help`
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`4 passed`)
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q` (`5 passed`)
- Gating carried forward: deterministic map click-interaction automation remains deferred in prompt-06 report/checklist.
- Next: continue `M6` with `C-02` runtime source-status surfacing and rerun prompt-03 after that scope lands.

## 2026-02-09 (prompt-06 UI verification loop)

- Executed `prompt-06-ui-e2e-verification-loop` as the active `M6` packet for dashboard-flow verification and stabilization.
- Added prompt-06 artifacts:
  - `docs/implementation/checklists/05_ui_verification.md`
  - `docs/implementation/reports/ui_verification_final_report.md`
- Added deterministic fixture-backed Streamlit E2E tests:
  - `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - coverage: dashboard render smoke, country filter narrowing, assisted approval flow, memo navigation regression guard.
- Fixed runtime UI bug in `src/interfaces/dashboard/app.py`:
  - symptom: clicking `Memo` could raise `StreamlitAPIException` (session-state mutation after widget instantiation),
  - root cause: shared key collision between panel radio widget and mutable `left_panel_view` state,
  - fix: introduced `left_panel_view_selector` widget key and synchronized selector state from canonical panel state.
- Updated command-map docs:
  - `docs/manifest/09_runbook.md` with `CMD-TEST-E2E-UI`.
- Verification evidence:
  - `python3 -m src.interfaces.cli -h`
  - `python3 scripts/check_command_map.py`
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`4 passed`)
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q` (`5 passed, 132 deselected`)
- Next: complete remaining `IB-06` runtime source support/fallback surfacing and then rerun `prompt-03` alignment gate.

## 2026-02-09 (prompt-03 alignment review rerun after prompt-12/prompt-13)

- Executed `prompt-03-alignment-review-gate` as a bounded docs-only rerun after manual prompt-12/prompt-13 verification packets.
- Updated alignment artifacts:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Key refresh outcomes:
  - corrected routing evidence to current chain (`prompt-02 -> prompt-06 -> prompt-03`) from `docs/implementation/reports/prompt_execution_plan.md`,
  - kept verdict at `ALIGNED_WITH_RISKS`,
  - retained top 3 corrective actions (`C-01`, `C-02`, `C-03`) and explicit mapping to `M6` + `O-04`,
  - added required keep-the-slate-clean decision: `Reshape Next Bet`.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `test -f docs/implementation/checklists/05_ui_verification.md; test -f docs/implementation/reports/ui_verification_final_report.md; test -d tests/e2e`
  - `rg --files tests/e2e`
  - `rg -n "supported|blocked|fallback|source_status|source support" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py -S`
  - `rg -n "O-04|IB-06|\\[ \\]" docs/implementation/checklists/03_improvement_bets.md docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/checklists/07_alignment_review.md docs/implementation/checklists/02_milestones.md -S`
  - `rg -n "prompt-12|prompt-13|M6|prompt-02 -> prompt-06 -> prompt-03" docs/implementation/00_status.md docs/implementation/03_worklog.md docs/implementation/reports/prompt_execution_plan.md -S`
- Next: execute `M6` (runtime source-status surfacing + UI verification) and rerun prompt-03 after that packet closes.

## 2026-02-09 (prompt-13 manual paper verification rerun)

- Executed `prompt-13-research-paper-verification` as a bounded rerun (manual user-triggered run).
- Verification commands and outcomes:
  - `python3 scripts/paper_generate_sanity_artifact.py` -> passed (`paper/artifacts/sanity_case.json` regenerated).
  - `python3 scripts/verify_paper_contract.py` -> passed.
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` -> failed due external `langsmith` plugin autoload error in this environment.
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` -> passed (`12 passed`).
  - `python3 scripts/build_paper.py` -> passed (`paper/main.pdf` rebuilt).
- Updated prompt-13 deliverable evidence:
  - `paper/verification_log.md` (new rerun section for 2026-02-09).
  - `docs/implementation/00_status.md` (current packet snapshot and command evidence).
- Next: continue active build packet `M6`; rerun prompt-13 only after material paper/mapping/test changes.

## 2026-02-09 (prompt-12 manual literature validation rerun)

- Executed `prompt-12-research-literature-validation` as a bounded revalidation packet (manual user-triggered run).
- Revalidated artifact and review integrity without citation expansion:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate` (`OK: 14 artifacts`)
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- Updated prompt-12 deliverables:
  - `docs/manifest/20_literature_review.md` (rerun status note)
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section)
  - `docs/implementation/checklists/20_literature_review.md` (new checked rerun item)
  - `docs/implementation/00_status.md` (current packet snapshot)
- Next: continue active `M6` build packet and run prompt-12 again only on material literature/claim drift.

## 2026-02-09 (prompt-00 routing refresh after syncing prompt library to latest upstream)

- Synced prompt pack submodule to latest upstream commit:
  - `prompts` -> `63d6ac94e91b4e303caa895e394176b8d6c6fd15`
- Ran required prompt-pack bootstrap checks:
  - `python3 prompts/scripts/prompts_manifest.py --check`
  - `python3 prompts/scripts/system_integrity.py --mode prompt_pack`
- Rewrote routing artifact to the new prompt-00 contract:
  - updated `docs/implementation/reports/prompt_execution_plan.md` with cycle-stage inference, cadence assumptions, finalist betting table, ordered immediate prompt chain, deferred/not-now IDs, exploration IDs, and circuit-breaker/carryover rules.
- Synced status snapshot with the routing refresh:
  - updated `docs/implementation/00_status.md` with latest packet context and next-packet chain.
- Verification evidence:
  - `git -C prompts rev-parse HEAD`
  - `python3 prompts/scripts/prompts_manifest.py --check`
  - `python3 prompts/scripts/system_integrity.py --mode prompt_pack`
  - `rg -n "\\[ \\]" docs/implementation/checklists -S`
- Next: execute packet `M6` via `prompt-02 -> prompt-06 -> prompt-03`.

## 2026-02-09 (prompt-11 manual legacy-docs migration into Diataxis format)

- Executed `prompt-11-docs-diataxis-release` manually (no prompt-router selection) to migrate and retire legacy docs.
- Added new explanation pages carrying migrated legacy content:
  - `docs/explanation/system_overview.md`
  - `docs/explanation/data_pipeline.md`
  - `docs/explanation/scraping_architecture.md`
  - `docs/explanation/services_map.md`
  - `docs/explanation/agent_system.md`
  - `docs/explanation/model_architecture.md`
  - `docs/explanation/production_path.md`
- Updated docs entrypoints and migrated references:
  - `docs/INDEX.md`
  - `docs/explanation/architecture.md`
  - `README.md`
  - related implementation/manifest/report pages referencing legacy paths.
- Removed legacy files:
  - `docs/00_docs_index.md`
  - `docs/01_system_overview.md`
  - `docs/02_data_pipeline.md`
  - `docs/03_unified_scraping_architecture.md`
  - `docs/04_services_map.md`
  - `docs/05_agents_map.md`
  - `docs/06_agent_workflow.md`
  - `docs/07_model_architecture.md`
  - `docs/08_path_to_production.md`
- Verification evidence:
  - `rg -n "00_docs_index\\.md|01_system_overview\\.md|02_data_pipeline\\.md|03_unified_scraping_architecture\\.md|04_services_map\\.md|05_agents_map\\.md|06_agent_workflow\\.md|07_model_architecture\\.md|08_path_to_production\\.md" README.md docs -g "*.md"`
  - `python3 scripts/check_docs_sync.py --changed-file README.md --changed-file docs/INDEX.md --changed-file docs/explanation/architecture.md --changed-file docs/explanation/system_overview.md --changed-file docs/explanation/data_pipeline.md --changed-file docs/explanation/scraping_architecture.md --changed-file docs/explanation/services_map.md --changed-file docs/explanation/agent_system.md --changed-file docs/explanation/model_architecture.md --changed-file docs/explanation/production_path.md --changed-file docs/how_to/run_end_to_end.md --changed-file docs/manifest/20_literature_review.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/checklists/01_plan.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/reports/20_literature_review_log.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/implementation/reports/architecture_coherence_report.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md --changed-file docs/00_docs_index.md --changed-file docs/01_system_overview.md --changed-file docs/02_data_pipeline.md --changed-file docs/03_unified_scraping_architecture.md --changed-file docs/04_services_map.md --changed-file docs/05_agents_map.md --changed-file docs/06_agent_workflow.md --changed-file docs/07_model_architecture.md --changed-file docs/08_path_to_production.md`
  - `python3 scripts/check_command_map.py`
- Next: continue with open implementation bet `IB-06`.

## 2026-02-08 (prompt-11 manual contract packet for IB-05 artifact-feature mapping enforcement)

- Executed `prompt-11-docs-diataxis-release` manually (no prompt-router selection) to close `IB-05`.
- Implemented contract guard:
  - added `scripts/check_artifact_feature_contract.py` to fail when load-bearing artifact IDs are not mapped in alignment/governance docs.
  - added `tests/unit/docs/test_check_artifact_feature_contract.py` covering pass/fail scenarios.
  - wired CI docs guardrail step in `.github/workflows/ci.yml`:
    - `CMD-ARTIFACT-FEATURE-CONTRACT-CHECK`
- Synced command-map/docs surfaces:
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/11_ci.md`
  - `docs/manifest/10_testing.md`
- Closed governance outcomes:
  - `IB-05` in `docs/implementation/checklists/03_improvement_bets.md`
  - `O-01` in `docs/implementation/checklists/08_artifact_feature_alignment.md`
  - combined benchmark+artifact contract gate in `docs/implementation/checklists/02_milestones.md` (`IB-03`)
- Verification evidence:
  - `python3 scripts/check_artifact_feature_contract.py`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/docs/test_check_artifact_feature_contract.py -q`
  - `python3 scripts/check_docs_sync.py --changed-file scripts/check_artifact_feature_contract.py --changed-file tests/unit/docs/test_check_artifact_feature_contract.py --changed-file .github/workflows/ci.yml --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/manifest/11_ci.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
  - `python3 scripts/check_command_map.py`
- Next: execute `IB-06` packet for runtime source support/fallback status visibility.

## 2026-02-08 (prompt-03 manual closure packet for P1-F alignment gate surface)

- Executed `prompt-03-docs-sync-and-gap-reporter` manually (no prompt-router selection) to close `P1-F`.
- Closed milestone and alignment-surface governance:
  - marked `P1-F` complete in `docs/implementation/checklists/02_milestones.md`.
  - retained `docs/implementation/checklists/08_artifact_feature_alignment.md` and `docs/implementation/reports/artifact_feature_alignment.md` as checkable, milestone-referenced surfaces after `P1-E`.
- Verification evidence:
  - `test -f docs/implementation/checklists/08_artifact_feature_alignment.md && test -f docs/implementation/reports/artifact_feature_alignment.md`
  - `rg -n "C-04|P1-E|P1-F|artifact_feature_alignment" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/reports/artifact_feature_alignment.md docs/implementation/00_status.md docs/implementation/03_worklog.md`
- Next: route the next governance gap (`IB-05`) into an enforceable artifact-feature contract check.

## 2026-02-08 (prompt-02 manual trust packet for P1-E benchmark gate)

- Executed `prompt-02-app-development-playbook` manually (no prompt-router selection) to close `P1-E`.
- Implemented fusion-vs-tree benchmark gate:
  - added `src/ml/training/benchmark.py` with:
    - leak-safe time+geo split construction,
    - RF/XGBoost baseline training/evaluation,
    - fusion-service subset evaluation,
    - explicit gate thresholds and pass/fail reasons,
    - benchmark artifact outputs (`json` + `md`).
  - wired new CLI wrapper command in `src/interfaces/cli.py`:
    - `python3 -m src.interfaces.cli benchmark ...`
- Added/expanded targeted test coverage:
  - `tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py`
  - `tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py`
- Added dependency support for XGBoost:
  - `requirements.txt`
  - `pyproject.toml`
  - regenerated `requirements.lock`
- Generated benchmark artifacts:
  - `docs/implementation/reports/fusion_tree_benchmark.json`
  - `docs/implementation/reports/fusion_tree_benchmark.md`
- Synced docs and milestone/alignment state:
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/10_testing.md`
  - `docs/reference/cli.md`
  - `docs/implementation/checklists/02_milestones.md` (`P1-E` complete)
  - `docs/implementation/checklists/03_improvement_bets.md` (`IB-03` complete)
  - `docs/implementation/checklists/08_artifact_feature_alignment.md` (`C-04` complete)
  - `docs/implementation/reports/artifact_feature_alignment.md`
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py -q`
  - `python3 -m src.interfaces.cli benchmark --listing-type sale --label-source auto --geo-key city --val-split 0.1 --test-split 0.2 --split-seed 42 --max-fusion-eval 80 --min-test-rows 50 --fusion-min-coverage 0.6 --fusion-mae-ratio-threshold 1.2 --fusion-mape-ratio-threshold 1.2 --output-json docs/implementation/reports/fusion_tree_benchmark.json --output-md docs/implementation/reports/fusion_tree_benchmark.md`
  - `python3 -m src.ml.training.benchmark --max-fusion-eval 5 --output-json /tmp/fusion_tree_benchmark_smoke.json --output-md /tmp/fusion_tree_benchmark_smoke.md --fail-on-gate` (returns `2` when gate fails as designed)
- Note:
  - current benchmark artifact reports gate failure driven by `fusion_coverage_below_threshold` / `fusion_metrics_missing` in this dataset (fusion eval rejected most candidates due `hedonic_index_fallback_detected`).
- Next: execute `P1-F` alignment-gate packet.

## 2026-02-08 (prompt-02 manual trust packet for P1-D spatial diagnostics)

- Executed `prompt-02-app-development-playbook` manually (no prompt-router selection) to close `P1-D`.
- Implemented spatial residual diagnostics in calibration workflow:
  - added `build_spatial_residual_diagnostics` in `src/valuation/workflows/calibration.py`.
  - added optional output `--spatial-diagnostics-output` with configurable drift/outlier thresholds.
  - emitted segment-level warnings by `region_id`, `listing_type`, `price_band`, `horizon_months` with Moran/LISA proxy fields.
- Fixed CLI wrapper forwarding bug:
  - `src/interfaces/cli.py` now forwards non-preflight passthrough args in stable order.
- Added targeted unit coverage:
  - `tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py`
  - `tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py`
- Updated docs/triage surfaces:
  - `docs/manifest/07_observability.md`
  - `docs/manifest/09_runbook.md`
  - `docs/reference/cli.md`
  - `docs/reference/data_formats.md`
  - `docs/manifest/10_testing.md`
- Closed milestone/alignment outcomes:
  - `P1-D` set complete in `docs/implementation/checklists/02_milestones.md`.
  - `C-03` set complete in `docs/implementation/checklists/08_artifact_feature_alignment.md`.
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q`
  - `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --output <registry.json> --coverage-report-output <coverage.json> --coverage-min-samples 20 --coverage-floor 0.80 --spatial-diagnostics-output <spatial.json> --spatial-min-samples 20 --spatial-drift-threshold-pct 0.08 --spatial-outlier-rate-threshold 0.15 --spatial-outlier-zscore 2.5`
  - `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file src/valuation/services/conformal_calibrator.py --changed-file src/valuation/workflows/calibration.py --changed-file src/valuation/services/valuation_persister.py --changed-file tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py --changed-file tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py --changed-file tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py --changed-file tests/unit/valuation/test_valuation_persister__confidence_semantics.py --changed-file docs/manifest/07_observability.md --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/reference/cli.md --changed-file docs/reference/data_formats.md --changed-file docs/how_to/interpret_outputs.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
  - `python3 scripts/check_command_map.py`
- Next: execute `P1-E` benchmark gate packet.

## 2026-02-08 (prompt-02 manual trust packet for P0-F segmented coverage gate)

- Executed `prompt-02-app-development-playbook` manually (no prompt-router selection) to close trust-critical `P0-F`.
- Implemented segmented conformal coverage reporting:
  - fixed passthrough CLI forwarding in `src/interfaces/cli.py` so dash-prefixed flags for wrapped commands are preserved in order.
  - added `segmented_coverage_report` in `src/valuation/services/conformal_calibrator.py`.
  - added workflow output flags in `src/valuation/workflows/calibration.py` to emit a JSON coverage report with thresholds.
- Added targeted unit coverage:
  - `tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py`.
  - `tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py`.
- Updated docs/triage surfaces:
  - `docs/manifest/07_observability.md`
  - `docs/manifest/09_runbook.md`
  - `docs/reference/cli.md`
  - `docs/reference/data_formats.md`
  - `docs/manifest/10_testing.md`
- Closed milestone and alignment outcomes:
  - `P0-F` set complete in `docs/implementation/checklists/02_milestones.md`.
  - `C-02` set complete in `docs/implementation/checklists/08_artifact_feature_alignment.md`.
- Verification evidence:
  - `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --output <registry.json> --coverage-report-output <coverage.json> --coverage-min-samples 20 --coverage-floor 0.80`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q`
  - `python3 scripts/check_docs_sync.py --changed-file src/valuation/services/conformal_calibrator.py --changed-file src/valuation/workflows/calibration.py --changed-file tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py --changed-file src/valuation/services/valuation_persister.py --changed-file tests/unit/valuation/test_valuation_persister__confidence_semantics.py --changed-file docs/manifest/07_observability.md --changed-file docs/manifest/09_runbook.md --changed-file docs/manifest/10_testing.md --changed-file docs/reference/cli.md --changed-file docs/reference/data_formats.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/03_improvement_bets.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
  - `python3 scripts/check_command_map.py`
- Next: execute `P1-D` packet for spatial residual diagnostics and triage mapping.

## 2026-02-08 (prompt-02 manual trust packet for P0-E confidence semantics)

- Executed `prompt-02-app-development-playbook` manually (no prompt-router selection) to close the trust-critical `P0-E` milestone.
- Implemented persisted confidence derivation in `src/valuation/services/valuation_persister.py`:
  - removed static placeholder confidence,
  - derived confidence from interval uncertainty, calibration state, projection confidence, comp support, and risk penalties,
  - stored `confidence_components` in valuation evidence for auditability.
- Added targeted test coverage:
  - `tests/unit/valuation/test_valuation_persister__confidence_semantics.py`.
- Synced trust semantics docs/artifacts:
  - `docs/how_to/interpret_outputs.md`
  - `docs/manifest/10_testing.md`
  - `docs/implementation/checklists/08_artifact_feature_alignment.md`
  - `docs/implementation/reports/artifact_feature_alignment.md`
- Closed milestone outcome:
  - `P0-E` set complete in `docs/implementation/checklists/02_milestones.md`.
- Verification evidence:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q`
  - `rg -n "confidence_components|calibration_status|projection_component|volatility_penalty" src/valuation/services/valuation_persister.py docs/how_to/interpret_outputs.md`
  - `python3 scripts/check_docs_sync.py --changed-file src/valuation/services/valuation_persister.py --changed-file tests/unit/valuation/test_valuation_persister__confidence_semantics.py --changed-file docs/how_to/interpret_outputs.md --changed-file docs/manifest/10_testing.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/checklists/08_artifact_feature_alignment.md --changed-file docs/implementation/reports/artifact_feature_alignment.md --changed-file docs/manifest/03_decisions.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/03_worklog.md`
  - `python3 scripts/check_command_map.py`
- Next: execute trust-critical `P0-F` packet for segmented conformal coverage gating.

## 2026-02-08 (prompt-11 manual lockfile convergence packet for P1-C)

- Executed `prompt-11-docs-diataxis-release` manually (no prompt-router selection) as a bounded install-policy packet.
- Generated lockfile:
  - `requirements.lock` via `python3 -m piptools compile --resolver=backtracking --output-file requirements.lock requirements.txt`.
- Updated canonical install policy docs to lockfile-backed flow:
  - `README.md`
  - `docs/getting_started/installation.md`
  - `docs/manifest/02_tech_stack.md`
- Closed milestone outcome:
  - `P1-C` set complete in `docs/implementation/checklists/02_milestones.md`.
- Verification evidence:
  - `python3 -m piptools compile --resolver=backtracking --output-file requirements.lock requirements.txt`
  - `rg -n "requirements.lock|piptools|Poetry" README.md docs/getting_started/installation.md docs/manifest/02_tech_stack.md`
  - `python3 scripts/check_docs_sync.py --changed-file README.md --changed-file docs/getting_started/installation.md --changed-file docs/manifest/02_tech_stack.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/implementation/00_status.md`
  - `python3 scripts/check_command_map.py`
- Next: execute trust-critical `P0-E` packet to replace placeholder persisted confidence semantics with calibration-derived confidence.

## 2026-02-08 (prompt-02 manual hardening packet for P1-B preflight UX)

- Executed `prompt-02-app-development-playbook` manually (no prompt-router selection) to break rerun-loop churn and close an implementation milestone.
- Implemented top-level preflight help UX fix in `src/interfaces/cli.py`:
  - added explicit `preflight` argument surface (common freshness/caching flags),
  - preserved passthrough behavior for other wrapper commands.
- Synced docs to runtime behavior:
  - `README.md`
  - `docs/reference/cli.md`
  - `docs/troubleshooting.md`
  - `docs/manifest/09_runbook.md`
- Closed milestone outcome:
  - `P1-B` set complete in `docs/implementation/checklists/02_milestones.md`.
- Verification evidence:
  - `python3 -m src.interfaces.cli -h`
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file README.md --changed-file docs/reference/cli.md --changed-file docs/troubleshooting.md --changed-file docs/manifest/09_runbook.md --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md`
- Next: close `P1-C` (lockfile install policy) or move to trust-critical `P0-E`/`P0-F`.

## 2026-02-08 (prompt-07 repo audit refresh after prompt-12 post prompt-03 post prompt-14 packet)

- Executed packet 3 in router order: `prompt-07-repo-audit-checklist`.
- Refreshed `checkbox.md` with current rerun context and updated maintenance-risk wording.
- Verification evidence:
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m src.interfaces.cli prefect preflight --help` (fails due Prefect/Pydantic import mismatch in active environment)
  - `python3 scripts/check_command_map.py`
  - `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "P0-E|P0-F|P1-B|P1-C|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 4 (`prompt-13-research-paper-verification`) unless redirected.

## 2026-02-08 (prompt-12 literature validation after prompt-03 post prompt-14 packet)

- Executed packet 2 in router order: `prompt-12-research-literature-validation`.
- Execution mode: bounded revalidation rerun (no citation-set expansion).
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section)
  - `docs/implementation/checklists/20_literature_review.md` (new rerun checklist item)
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 3 (`prompt-07-repo-audit-checklist`) unless redirected.

## 2026-02-08 (prompt-03 alignment review gate after prompt-14 packet)

- Executed selected packet 1 from updated prompt library: `prompt-03-alignment-review-gate`.
- Refreshed alignment gate deliverables with current evidence:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Updated correction mapping to current open milestone outcomes (`P0-E`, `P0-F`, `P1-B`) and removed stale deferred-state findings from this gate.
- Verification evidence:
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "P0-E|P0-F|P1-B|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute router packet 2 (`prompt-12-research-literature-validation`) unless redirected.

## 2026-02-08 (prompt-14 improvement direction bet loop after prompt-lib refresh)

- Executed selected packet 1 from updated prompt library: `prompt-14-improvement-direction-bet-loop`.
- Added improvement-direction deliverables:
  - `docs/implementation/reports/improvement_directions.md`
  - `docs/implementation/checklists/03_improvement_bets.md`
- Updated milestones with improvement-bet routing:
  - added `IB-01`, `IB-02`, `IB-03` milestone outcomes,
  - added packet `M5` for prompt-14 completion.
- Verification evidence:
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
  - `rg -n "RandomForest|XGBoost|xgboost|sklearn\\.ensemble" src tests`
  - `rg -n "LISA|Moran|coverage by segment|segmented coverage" src tests docs`
- Next: execute the next router-selected packet after this bet planning pass (expected `prompt-07-repo-audit-checklist`).

## 2026-02-08 (prompt-15 artifact-feature alignment gate after prompt-lib refresh)

- Executed selected packet 1 from updated prompt library: `prompt-15-artifact-feature-alignment-gate`.
- Added artifact-feature gate deliverables:
  - `docs/implementation/checklists/08_artifact_feature_alignment.md`
  - `docs/implementation/reports/artifact_feature_alignment.md`
- Routed top artifact-backed outcomes into milestones:
  - added `P0-E`, `P0-F`, `P1-D`, `P1-E`, `P1-F` in `docs/implementation/checklists/02_milestones.md`,
  - added packet `M4`,
  - replaced stale research-deferred wording with current executed-state wording.
- Verification evidence:
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "confidence\\s*=\\s*0\\.85|placeholder logic" src/valuation/services/valuation_persister.py`
  - `rg -n "RandomForest|XGBoost|xgboost|sklearn\\.ensemble" src tests`
  - `rg -n "LISA|Moran|coverage by segment|segmented coverage" src tests docs`
- Next: execute the next router-selected packet after this gate (expected `prompt-14-improvement-direction-bet-loop`).

## 2026-02-08 (prompt-13 rerun after latest prompt-07 post prompt-12/03 sequence)

- Executed packet 4 in sequence: `prompt-13-research-paper-verification`.
- Revalidated paper verification artifacts and reproducibility commands; no claim-table expansion in this rerun.
- Verification evidence:
  - `python3 scripts/paper_generate_sanity_artifact.py`
  - `python3 scripts/verify_paper_contract.py`
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails due third-party plugin autoload)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (`12 passed`)
  - `python3 scripts/build_paper.py` (`paper/main.pdf` built)
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 1 (`prompt-03-alignment-review-gate`) in the current router order.

## 2026-02-08 (prompt-07 rerun after latest prompt-12 post prompt-03 post prompt-13 sequence)

- Executed packet 3 in sequence: `prompt-07-repo-audit-checklist`.
- Refreshed `checkbox.md` with current rerun context; P0/P1 priority set remains materially unchanged.
- Prefect CLI environment fragility remains reproducible (`python3 -m src.interfaces.cli prefect preflight --help` import mismatch).
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m src.interfaces.cli prefect preflight --help` (failure captured)
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 4 (`prompt-13-research-paper-verification`) as a bounded rerun.

## 2026-02-08 (prompt-12 rerun after latest prompt-03 post prompt-13 post prompt-07 sequence)

- Executed packet 2 in sequence: `prompt-12-research-literature-validation`.
- Execution mode: bounded revalidation rerun (no new sources or citation expansion).
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section)
  - `docs/implementation/checklists/20_literature_review.md` (new rerun checklist item)
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 3 (`prompt-07-repo-audit-checklist`).

## 2026-02-08 (prompt-03 rerun after latest prompt-13 post prompt-07 post prompt-12 sequence)

- Executed packet 1 in sequence: `prompt-03-alignment-review-gate`.
- Refreshed alignment artifacts with current rerun context:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Findings remain materially unchanged: objective alignment holds, with open trust risks centered on placeholder confidence semantics, source-support visibility, and top-level preflight usability.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "P1-B|P1-C|Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 2 (`prompt-12-research-literature-validation`) as a bounded rerun.

## 2026-02-08 (prompt-13 rerun after latest prompt-07 post prompt-12 sequence)

- Executed packet 4 in sequence: `prompt-13-research-paper-verification`.
- Revalidated paper verification artifacts and reproducibility commands; no claim-table expansion in this rerun.
- Verification evidence:
  - `python3 scripts/paper_generate_sanity_artifact.py`
  - `python3 scripts/verify_paper_contract.py`
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails due third-party plugin autoload)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (`12 passed`)
  - `python3 scripts/build_paper.py` (`paper/main.pdf` built)
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 1 (`prompt-03-alignment-review-gate`) in the current router order.

## 2026-02-08 (prompt-07 rerun after latest prompt-12 post prompt-13 packet-4 sequence)

- Executed packet 3 in sequence: `prompt-07-repo-audit-checklist`.
- Refreshed `checkbox.md` with current rerun context; P0/P1 priority set remains materially unchanged.
- Prefect CLI environment fragility remains reproducible (`python3 -m src.interfaces.cli prefect preflight --help` import mismatch).
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m src.interfaces.cli prefect preflight --help` (failure captured)
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 4 (`prompt-13-research-paper-verification`) as a bounded rerun.

## 2026-02-08 (prompt-12 rerun after latest prompt-03 post prompt-13 packet-4 refresh)

- Executed packet 2 in sequence: `prompt-12-research-literature-validation`.
- Execution mode: bounded revalidation rerun (no new sources or citation expansion).
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section)
  - `docs/implementation/checklists/20_literature_review.md` (new rerun checklist item)
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 3 (`prompt-07-repo-audit-checklist`).

## 2026-02-08 (prompt-03 rerun after latest prompt-13 packet-4 refresh)

- Executed packet 1 in sequence: `prompt-03-alignment-review-gate`.
- Refreshed alignment artifacts with current rerun context:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Findings remain materially unchanged: objective alignment holds, with open trust risks centered on placeholder confidence semantics, source-support visibility, and top-level preflight usability.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "P1-B|P1-C|Deferred / Not Now|Deferred / Not now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
  - `python3 scripts/build_paper.py`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 2 (`prompt-12-research-literature-validation`) as a bounded rerun.

## 2026-02-08 (prompt-13 rerun, packet-4 execution refresh)

- Executed packet 4 in sequence: `prompt-13-research-paper-verification`.
- Revalidated paper verification commands and fixed reproducible build drift in `paper/main.tex` (LaTeX-safe path rendering + citations).
- Verification evidence:
  - `python3 scripts/paper_generate_sanity_artifact.py`
  - `python3 scripts/verify_paper_contract.py`
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (failure captured from third-party plugin autoload)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (`12 passed`)
  - `python3 scripts/build_paper.py` (`paper/main.pdf` built)
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 1 (`prompt-03-alignment-review-gate`) in the current router order.

## 2026-02-08 (prompt-07 rerun after latest prompt-12)

- Executed packet 3 in sequence: `prompt-07-repo-audit-checklist`.
- Refreshed `checkbox.md` with current rerun context; P0/P1 priority set remains materially unchanged.
- Prefect CLI environment fragility remains reproducible (`python3 -m src.interfaces.cli prefect preflight --help` import mismatch).
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m src.interfaces.cli prefect preflight --help` (failure captured)
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "Deferred / Not Now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 4 (`prompt-13-research-paper-verification`) as a bounded rerun.

## 2026-02-08 (prompt-12 rerun after latest prompt-03)

- Executed packet 2 in sequence: `prompt-12-research-literature-validation`.
- Execution mode: bounded revalidation rerun (no new sources or citation expansion).
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section)
  - `docs/implementation/checklists/20_literature_review.md` (new rerun checklist item)
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 3 (`prompt-07-repo-audit-checklist`).

## 2026-02-08 (prompt-03 rerun after latest prompt-13)

- Executed packet 1 in sequence: `prompt-03-alignment-review-gate`.
- Refreshed alignment artifacts:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Findings remain materially unchanged: objective remains aligned with open trust risks centered on placeholder confidence semantics, source-support visibility, and CLI/deferred-routing drift.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "P1-B|P1-C|Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 2 (`prompt-12-research-literature-validation`) as a bounded rerun.

## 2026-02-08 (prompt-13 rerun after latest prompt-07)

- Executed packet 4 in sequence: `prompt-13-research-paper-verification`.
- Revalidated paper verification artifacts and updated reproducibility notes:
  - `paper/verification_log.md` (new rerun section)
  - `paper/README.md` (pytest plugin-autoload fallback command note)
- Verification evidence:
  - `python3 scripts/paper_generate_sanity_artifact.py`
  - `python3 scripts/verify_paper_contract.py`
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (fails due third-party pytest plugin autoload)
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` (`12 passed`)
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: router order loops back to packet 1 (`prompt-03-alignment-review-gate`).

## 2026-02-08 (prompt-07 rerun after latest prompt-12)

- Executed packet 3 in sequence: `prompt-07-repo-audit-checklist`.
- Refreshed `checkbox.md` with latest rerun context and revalidated the current P0/P1 outcome set.
- Captured fresh environment fragility evidence: `python3 -m src.interfaces.cli prefect preflight --help` currently fails due Prefect/Pydantic import mismatch in the active Python environment.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m src.interfaces.cli prefect preflight --help` (failure captured)
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "Deferred / Not Now|prompt-12|prompt-13|P1-B|P1-C" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 4 (`prompt-13-research-paper-verification`) as a bounded rerun.

## 2026-02-08 (prompt-12 rerun after latest prompt-03)

- Executed packet 2 in sequence: `prompt-12-research-literature-validation`.
- Execution mode: bounded revalidation rerun (no new sources or citation expansion).
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section)
  - `docs/implementation/checklists/20_literature_review.md` (new rerun checklist item)
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 3 (`prompt-07-repo-audit-checklist`).

## 2026-02-08 (prompt-03 alignment gate rerun after latest prompt-07)

- Executed the next packet in sequence: `prompt-03-alignment-review-gate`.
- Refreshed alignment artifacts:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Findings remain materially unchanged: objective is aligned, with open trust risks centered on placeholder confidence semantics, source-support visibility, and CLI help/deferred-routing drift.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence\\s*=\\s*0\\.85|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "P1-B|P1-C|Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: execute packet 2 (`prompt-12-research-literature-validation`) as a bounded rerun.

## 2026-02-08 (prompt-07 rerun after latest prompt-12)

- Executed the next packet in sequence: `prompt-07-repo-audit-checklist`.
- Updated `checkbox.md` with new rerun context after the latest prompt-12 pass; substantive risk priorities remain unchanged.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m src.interfaces.cli prefect preflight --help`
  - `python3 scripts/check_command_map.py`
  - `rg -n "placeholder logic|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `rg -n "Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- Next: continue with the next router-ordered packet.

## 2026-02-08 (prompt-12 rerun after latest prompt-03)

- Executed the next recommended packet in sequence: `prompt-12-research-literature-validation`.
- Execution mode: bounded revalidation rerun (no new sources added).
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section).
  - `docs/implementation/checklists/20_literature_review.md` (new rerun checklist item).
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- Next: continue with the next packet after this prompt-12 rerun.

## 2026-02-08 (prompt-03 alignment gate refresh after prompt-07)

- Re-ran `prompt-03-alignment-review-gate` after the repo audit refresh to confirm objective alignment.
- Refreshed alignment artifacts with current audit-driven risks:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Updated top corrective focus to:
  - replace placeholder confidence persistence semantics,
  - surface source support/fallback status in runtime outputs,
  - close preflight help + deferred-routing language drift.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `rg -n "placeholder logic|confidence" src/valuation/services/valuation_persister.py`
  - `rg -n "Currently returns empty data|TODO: Implement specific HTML parsing" src/listings/agents/processors/immowelt.py src/listings/agents/processors/realtor.py src/listings/agents/processors/redfin.py src/listings/agents/processors/seloger.py`
  - `python3 scripts/check_command_map.py`
  - `rg -n "P1-B|P1-C|Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- Next: schedule and execute `C-01`/`C-02`/`C-03` through a bounded prompt-02 hardening packet.

## 2026-02-08 (prompt-07 repo audit refresh after prompt-12 rerun)

- Executed the next recommended packet: `prompt-07-repo-audit-checklist`.
- Refreshed `checkbox.md` against current repo evidence and updated the prompt-00 handoff outcomes.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
- Next: rerun router and execute the next packet from the updated audit state.

## 2026-02-08 (prompt-12 rerun after alignment refresh)

- Executed `prompt-12-research-literature-validation` as the next router packet after the alignment refresh.
- Scope decision: bounded revalidation only (no citation expansion).
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (rerun section added).
- Verification evidence:
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- Next: follow the routing plan (currently `prompt-07-repo-audit-checklist`).

## 2026-02-08 (prompt-07 repo audit refresh after prompt-12 rerun)

- Executed the next recommended packet: `prompt-07-repo-audit-checklist`.
- Rewrote `checkbox.md` against current repo evidence (post CI/release/docs/research updates), preserving required prompt-07 structure.
- Key audit deltas versus prior snapshot:
  - release-discipline artifacts are now present and moved from missing -> partial/operational state,
  - dominant risks now center on confidence persistence placeholder logic, source support visibility, and top-level preflight UX,
  - Prompt-00 handoff now maps fresh P0/P1 outcomes and packet sequencing for milestones.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m src.interfaces.cli prefect preflight --help`
  - `python3 scripts/check_command_map.py`
  - `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/09_runbook.md`
  - `python3 -m pytest --markers`
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q`
- Next: rerun router and execute the next packet from updated audit state.

## 2026-02-08 (prompt-03 alignment gate refresh post-prompt-13)

- Re-ran `prompt-03-alignment-review-gate` after prompt-13 to confirm objective alignment and update corrective actions.
- Refreshed alignment artifacts:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Updated corrective focus to close `P1-B` (preflight UX), `P1-C` (lockfile install path), and refresh deferred routing language.
- Verification evidence:
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `rg -n "Deferred / Not Now|prompt-12|prompt-13" docs/implementation/checklists/02_milestones.md`
- Next: execute a small hardening packet to close `P1-B` and update deferred routing language.

## 2026-02-08 (prompt-13 research paper verification)

- Executed `prompt-13-research-paper-verification` to lock literature-backed claims to paper + code verification.
- Added paper and verification surfaces:
  - `paper/main.tex`
  - `paper/references.bib`
  - `paper/implementation_map.md`
  - `paper/verification_log.md`
  - `paper/README.md`
  - `paper/artifacts/sanity_case.json`
- Added verification tooling and tests:
  - `scripts/build_paper.py`
  - `scripts/verify_paper_contract.py`
  - `scripts/paper_generate_sanity_artifact.py`
  - `tests/unit/paper/test_paper_verification.py`
- Verification evidence:
  - `python3 scripts/paper_generate_sanity_artifact.py`
  - `python3 scripts/verify_paper_contract.py`
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live"`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Next: router recommends `prompt-03-alignment-review-gate` as the next packet.

## 2026-02-08 (prompt-12 rerun after prompt-03)

- Executed the next recommended packet from current routing order: `prompt-12-research-literature-validation`.
- Chosen execution mode: bounded revalidation rerun (no citation-set expansion) to keep scope small and avoid research-track drift.
- Updated artifacts:
  - `docs/implementation/reports/20_literature_review_log.md` (new rerun section)
  - `docs/implementation/checklists/20_literature_review.md` (rerun verification item)
- Verification evidence:
  - `python3 prompts/scripts/prompt_router.py select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate` (`OK: 14 artifacts`)
  - `rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md`
  - `rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
- Next: run Packet 3 (`prompt-07-repo-audit-checklist`) from the current execution plan.

## 2026-02-08 (prompt-03 alignment gate refresh)

- Re-ran `prompt-03-alignment-review-gate` as selected by the updated router output (`phase_5` / `cool_down`).
- Refreshed stale alignment artifacts with current evidence:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Updated findings now reflect current repo state:
  - observability/milestones/release baseline artifacts are present,
  - top open alignment risks are `P1-B` (preflight help UX), `P1-C` (lockfile-backed install policy), and stale deferred routing language.
- Verification evidence captured:
  - `python3 prompts/scripts/prompt_router.py select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 scripts/check_command_map.py`
  - `python3 -m pytest --markers`
  - `test -f docs/manifest/07_observability.md && test -f docs/implementation/checklists/02_milestones.md && test -f .github/workflows/ci.yml && test -f docs/reference/versioning_policy.md && test -f docs/implementation/checklists/06_release_readiness.md`
  - `rg -n "P1-B|P1-C|\\[ \\]" docs/implementation/checklists/02_milestones.md`
- Next: execute a small `prompt-02` hardening packet for `P1-B` + deferred-routing cleanup, then close `P1-C`.

## 2026-02-08 (prompt-12 literature validation)

- Executed `prompt-12-research-literature-validation` as the next unexecuted routed packet after release-discipline closure.
- Added literature packet deliverables:
  - `docs/manifest/20_literature_review.md`
  - `docs/implementation/reports/20_literature_review_log.md`
  - `docs/implementation/checklists/20_literature_review.md`
- Initialized artifact traceability store and captured load-bearing references:
  - `docs/artifacts/README.md`
  - `docs/artifacts/index.json` with 14 DOI/arXiv metadata entries.
- Curated sources cover the repo's key decision surfaces: hedonic/repeat-sales indexing, spatial diagnostics, quantile interval modeling, conformal calibration, and retrieval/attention methods.
- Synthesized project-facing outcomes:
  - keep comp/time-anchored quantile architecture,
  - require RF/XGBoost baselines,
  - add subgroup coverage diagnostics,
  - add spatial drift diagnostics before stronger confidence claims.
- Verification evidence:
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
  - `python3 prompts/scripts/web_artifacts.py --repo-root . init`
  - `python3 prompts/scripts/web_artifacts.py --repo-root . add-meta ...` (14 entries)
  - `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - `curl -Ls "https://api.crossref.org/works/<doi>"`
  - `curl -Ls "https://export.arxiv.org/api/query?id_list=<arxiv_id>"`
- Next: run `prompt-13-research-paper-verification`.

## 2026-02-08 (prompt-07 post-CI audit refresh)

- Executed `prompt-07-repo-audit-checklist` after CI baseline changes to refresh repo-level findings.
- Updated `checkbox.md` to reflect:
  - CI baseline and docs-sync guardrails now present.
  - observability/runbook/milestones artifacts now present.
  - remaining dominant gaps: release discipline artifacts, source coverage transparency, CLI preflight help UX.
- Prompt-00 handoff in `checkbox.md` now points next packet to `prompt-11-docs-diataxis-release`.
- Verification evidence used in this refresh:
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
  - `python3 scripts/check_command_map.py`
  - `python3 scripts/check_docs_sync.py --changed-file src/interfaces/cli.py --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/09_runbook.md`
  - `python3 -m src.interfaces.cli preflight --help`
- Next: run `prompt-11` release documentation packet.

## 2026-02-08 (prompt-02 packet 2)

- Executed Packet M2 for `prompt-02-app-development-playbook` (CI baseline + docs-sync guardrail).
- Added CI workflow:
  - `.github/workflows/ci.yml`
  - jobs: `docs-sync-guardrail`, `offline-quality-gates`
- Added CI integrity scripts:
  - `scripts/check_docs_sync.py` (requires status + milestones + manifest update on runtime/test/CI/config changes)
  - `scripts/check_command_map.py` (ensures `docs/manifest/11_ci.md` only references runbook command IDs)
- Updated command/documentation mapping:
  - `docs/manifest/09_runbook.md` with `CMD-DOCS-SYNC-GUARD` and `CMD-CI-COMMAND-MAP-CHECK`
  - `docs/manifest/11_ci.md` to reflect active workflow and required checks
  - `docs/manifest/10_testing.md` to reflect CI baseline status
- Updated milestone/epic/docs tracking:
  - `docs/implementation/checklists/02_milestones.md` marks Packet M2 complete
  - `docs/implementation/epics/epic_reliability_baseline.md` tasks marked complete
  - `docs/manifest/03_decisions.md` includes CI baseline ADR
- Verification evidence:
  - `python3 scripts/check_command_map.py`
  - `python3 scripts/check_docs_sync.py --changed-file .github/workflows/ci.yml --changed-file docs/implementation/00_status.md --changed-file docs/implementation/checklists/02_milestones.md --changed-file docs/manifest/11_ci.md`
  - `python3 -m src.interfaces.cli -h`
  - `python3 -m pytest --markers`
  - `python3 -m pytest --run-integration --run-e2e -m "not live"` (86 passed, 20 deselected)
- Next: rerun `prompt-00` to refresh prompt routing after CI baseline closure.

## 2026-02-08 (prompt-02 packet 1)

- Executed `prompt-02-app-development-playbook` as a bounded Packet 1 (`Standard` mode, appetite `small`).
- Added missing milestone and governance artifacts:
  - `docs/implementation/checklists/02_milestones.md`
  - `docs/implementation/reports/project_plan.md`
  - `docs/implementation/reports/assumptions_register.md`
  - `docs/implementation/reports/README.md`
  - `docs/implementation/epics/epic_reliability_baseline.md`
- Added missing manifest surfaces required for reliability gating:
  - `docs/manifest/02_tech_stack.md`
  - `docs/manifest/06_security.md`
  - `docs/manifest/07_observability.md`
  - `docs/manifest/08_deployment.md`
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/12_conventions.md`
- Promoted runbook to canonical command map source:
  - updated `docs/.prompt_system.yml` (`command_map_file`)
  - updated `docs/manifest/10_testing.md` and `docs/manifest/11_ci.md` to pointer-based mapping.
- Added prompt-02 decision records in `docs/manifest/03_decisions.md`.
- Updated docs navigation in `docs/INDEX.md`.
- Verification evidence captured:
  - `python3 -m src.interfaces.cli -h`
  - `python3 -m src.interfaces.cli preflight --help`
  - `python3 -m pytest --markers`
  - `rg -n "## Command Map|CMD-" docs/manifest/09_runbook.md docs/manifest/11_ci.md`
  - `rg -n "Logging Schema|golden signals|SLI|SLO|Debug Playbook|Objective metric mapping" docs/manifest/07_observability.md`
  - `test -f docs/implementation/checklists/02_milestones.md && test -f docs/implementation/reports/project_plan.md && test -f docs/implementation/reports/assumptions_register.md`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
- Note: router still prioritizes research prompts due repo research artifacts; `Not now` defers remain active until P0 CI baseline closes.
- Next: run Packet M2 to add `.github/workflows/ci.yml` and docs-sync CI guardrail, then rerun prompt routing.

## 2026-02-08 (prompt-00 routing)

- Executed `prompt-00-prompt-routing-plan` and regenerated routing artifacts.
- Command evidence:
  - `python3 prompts/scripts/prompt_router.py --root prompts registry --format json`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --output docs/implementation/reports/prompt_execution_plan.md`
- Router auto-selected research prompts due repo research signals; routing was objective-gated using `checkbox.md` Prompt-00 handoff.
- Committed immediate packet to `prompt-02-app-development-playbook` for P0 milestones + observability/CI gate outcomes.
- Deferred `prompt-11` until after P0, and explicitly deferred `prompt-12`/`prompt-13` per audit packeting guidance.
- Updated `docs/implementation/00_status.md` with Now/Next/Not now and verification trail.
- Next: execute `prompt-02` Packet 1 and create `docs/implementation/checklists/02_milestones.md`.

## 2026-02-08 (alignment gate)

- Executed `prompt-03-alignment-review-gate` and created:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Alignment verdict recorded as `ALIGNED_WITH_RISKS`.
- Required questions answered with repo evidence against `docs/manifest/00_overview.md#Core Objective`.
- Identified top 3 corrective actions:
  - C-01 milestone packet mapping (`02_milestones.md`)
  - C-02 observability metric governance (`07_observability.md`)
  - C-03 CI baseline and docs-sync guardrail
- Explicit next-packet mapping added to reference `docs/implementation/checklists/02_milestones.md`.
- Updated status snapshot in `docs/implementation/00_status.md` with commands and routing.
- Next: run `prompt-07-repo-audit-checklist` and convert audit outcomes into milestone packets.

## 2026-02-08

- Executed `prompt-04-architecture-coherence-loop` packet and created canonical architecture artifacts:
  - `docs/manifest/01_architecture.md`
  - `docs/manifest/04_api_contracts.md`
  - `docs/manifest/05_data_model.md`
  - `docs/implementation/checklists/00_architecture_coherence.md`
  - `docs/implementation/reports/architecture_coherence_report.md`
- Locked docs root mapping via `docs/.prompt_system.yml`.
- Updated docs navigation in `docs/INDEX.md` to include architecture checklist/report surfaces.
- Captured command evidence:
  - `python3 -m src.interfaces.cli -h`
  - `python3 -m src.platform.workflows.prefect_orchestration -h`
  - `python3 -m pytest --markers`
  - `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
- Coherence verdict: `GO_WITH_RISKS`.
- Remaining risks explicitly documented: no CI gate, missing release discipline docs, missing dedicated runbook command map page.
- Next: run `prompt-03` (alignment gate) then `prompt-07` (repo audit checklist) and convert outcomes into milestone planning.

## 2026-02-06

- Initialized test stabilization documentation system and captured current test runner/marker configuration.
- Phase 1 baseline runs completed:
  - Unit: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"` (62 passed)
  - Unit data contracts: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"` (9 passed)
  - Integration: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration` (19 passed)
  - E2E: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e` (1 passed)
- Note: warnings observed from `src/market/services/hedonic_index.py` about nanoseconds conversion; tests still pass.
- Phase 5 verification completed (0 flakes):
  - Unit: 3 consecutive green runs (62 passed each)
  - Unit data contracts: 3 consecutive green runs (9 passed each)
  - Integration: 1 green run (19 passed)
  - E2E: 1 green run (1 passed)
- Minor hardening attempt: `pytest.ini` addopts updated to include `-p no:langsmith.pytest_plugin` (LangSmith still appears in pytest's plugin list in this environment; tests remain stable). Documentation updated to clarify that plugin autoload may still occur and the suite remains green.
- Final report updated: `docs/implementation/reports/test_stabilization_final_report.md`.
- Next: (optional) decide whether `@pytest.mark.live` should remain opt-in only or be integrated into CI once a CI workflow exists.

## 2026-02-09 (prompt-03 alignment review gate refresh)

- Executed `prompt-03-alignment-review-gate` to refresh objective drift checks after reliability gates closed.
- Updated alignment artifacts:
  - `docs/implementation/checklists/07_alignment_review.md`
  - `docs/implementation/reports/alignment_review.md`
- Routed the next corrective packet:
  - Added Packet `M6` in `docs/implementation/checklists/02_milestones.md` (UI verification + source-status visibility).
- Verification evidence:
  - `rg -n "confidence = 0.85|placeholder confidence|confidence_components|calibration_status" src/valuation/services/valuation_persister.py docs/how_to/interpret_outputs.md`
  - `rg -n "source support|fallback|blocked|crawler status|source status" docs/crawler_status.md src/interfaces/dashboard/app.py src/interfaces/api/pipeline.py -S`
  - `rg -n "e2e|dashboard|Streamlit|ui verification" docs/implementation/checklists docs/implementation/reports README.md -S`
  - `rg -n "\[ \]" docs/implementation/checklists -S`
- Next: execute Packet `M6` (prompt-06 UI verification) and then close `O-04` assumption badges.

## 2026-03-10 (Figma-to-live alignment packet)

- Implemented backend and audit plumbing for the Figma redesign alignment pass.
- Added persisted product objects and APIs:
  - watchlists
  - saved searches
  - memos + memo export
  - comp reviews
  - command-center run history
- Added operational read APIs over runtime trust artifacts:
  - recent job runs
  - benchmark runs
  - coverage reports
  - data quality events
  - source contract runs
- Hardened `POST /valuations` so real insufficient-data cases return structured `422` responses instead of uncaught `500`s.
- Reduced dashboard startup coupling by switching dashboard service loading away from eager retriever initialization.
- Verified:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/application/test_workspace_service.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/application/test_reporting_service.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
  - `python3 -m compileall src/application src/adapters/http src/interfaces/dashboard/services`
- Captured the audit artifact in:
  - `docs/implementation/reports/figma_live_alignment_matrix.md`
- Live runtime findings recorded during verification:
  - successful real-data valuation for listing `3cddb9e0c75d`
  - structured `target_surface_area_required` response for listing `3fe641d70a322bf312591463cebc7bbe`
  - structured `insufficient_comps` response for listing `4zLGu`
  - seeded one real `preflight` job run through `/jobs/preflight`
  - `coverage_reports` populated; `benchmark_runs` still empty
