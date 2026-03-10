# Observability

## Scope

This manifest defines observability and reliability gates for critical workflows.

Critical workflows:
- preflight orchestration
- unified crawl + listing persistence
- market/index/training/backfill pipeline steps
- calibration refresh + segmented coverage reporting
- dashboard startup path
- agent run execution

## Logging Schema (Required Fields)

Each critical workflow log event should include:
- `ts`: ISO timestamp
- `run_id`: pipeline/agent run identifier
- `workflow`: canonical workflow name (for example `preflight`, `build_index`)
- `step`: step/task name
- `status`: `running|success|failed|skipped`
- `duration_ms`: elapsed duration when terminal
- `component`: module/service owner
- `error_type`: normalized failure class when failed
- `error_message`: redacted message

Redaction policy:
- never log API keys, auth headers, session cookies, or full PII payloads
- mask secrets in exception payloads before persistence
- log structured failure reason codes over raw stacktrace dumps in user-facing surfaces

## Metrics and Tracing Plan

Signal sources currently available:
- `pipeline_runs` table (`src/platform/pipeline/repositories/pipeline_runs.py`)
- `agent_runs` table (`src/agentic/memory.py`)
- CLI/flow command exit status

Metric plan by workflow:
- `preflight`:
  - latency: total preflight duration
  - errors: failed/timeout runs by day
  - traffic: runs per day
- `unified_crawl`:
  - traffic: listings processed per run
  - errors: source-level extraction failures
  - saturation: queue/backlog size proxy from pending stale state
- `build_index`:
  - latency: index build duration
  - errors: metadata/model mismatch incidents
- `backfill`:
  - traffic: listings evaluated per run
  - errors: `insufficient_comps` ratio
- `calibration`:
  - traffic: calibration samples ingested per run
  - quality: segmented coverage by `region_id`, `listing_type`, `price_band`, `horizon_months`
  - errors: segments below coverage threshold after min-sample gate
  - diagnostics: spatial residual drift/outlier warnings (Moran/LISA proxy fields) by segment
- `agent`:
  - latency: run duration
  - errors: failed tool/run ratio
  - traffic: queries per day
- `llm/vlm enrichment`:
  - errors: ChatMock/OpenAI-compatible request failures by `provider`, `api_base`, and `model`
  - quality: explicit `vlm_backend_request_failed` / `fusion_vlm_failed` counts when vision is unsupported
  - drift: backend changes between configured text and vision routes
- `dashboard status`:
  - quality: `source_support.summary` counts for `supported`, `blocked`, `fallback`
  - drift: sources moving from `supported` -> `fallback` or `blocked`
  - guidance link integrity: `source_support.doc_path` points to `docs/crawler_status.md`

Tracing plan:
- use `run_id` as trace spine across CLI/API/workflow logs and DB run tables
- add per-step correlation fields in persisted metadata where absent

## Golden Signals Dashboards

Required dashboard families:
- `latency`: preflight/build-index/backfill/agent p95 + max duration
- `traffic`: pipeline run counts, listing throughput, agent query volume
- `errors`: failed run counts by workflow + top reason codes
- `saturation`: stale-artifact backlog, retry counts, queue pressure proxies

## SLI/SLO and Alert Routing

### Objective metric mapping

| Objective metric (`docs/manifest/00_overview.md`) | SLI | Initial SLO | Alert routing |
| --- | --- | --- | --- |
| Time-to-first-dashboard <= 30 minutes | setup-to-dashboard duration | 95% <= 30m weekly | Sev-2 if breached 2 consecutive days |
| Offline suites remain green | pass rate for unit+integration+e2e offline suites | 100% on protected branch | Sev-1 on first failure |
| Preflight->dashboard happy path works without DB manual fixes | successful preflight+dashboard launch ratio | >= 98% weekly | Sev-2 if < 98% |
| Runtime source trust is explicit in dashboard/API status surfaces | ratio of status payloads containing `source_support.summary` and per-source `runtime_label` | 100% on protected branch | Sev-2 on first regression |
| Runtime assumption caveats are explicit in dashboard/API status surfaces | ratio of status payloads containing non-empty `assumption_badges` with `artifact_ids` | 100% on protected branch | Sev-2 on first regression |
| Valuation outputs persist with provenance | share of persisted valuations with run metadata/evidence | >= 99% | Sev-2 if < 99% |
| Segmented conformal coverage remains within floor | share of evaluated segments meeting coverage floor (`region_id`, `listing_type`, `price_band`, `horizon`) | >= 90% of evaluated segments pass (`min_samples >= 20`, floor `0.80`) | Sev-2 if breached in two consecutive calibration runs |
| Spatial residual drift/outlier warnings remain bounded | share of evaluated spatial segments in warning state (`warn_drift`, `warn_outlier`, `warn_drift_outlier`) | <= 20% warned segments (`min_samples >= 20`) | Sev-2 if breached in two consecutive diagnostics runs |

Severity routing:
- Sev-1: correctness gate failure (tests/contract regression) -> immediate maintainer action
- Sev-2: reliability/objective degradation -> same-day triage
- Sev-3: intermittent/non-critical warnings -> backlog item in next packet

## Debug Playbook (Common Incidents)

- Incident: preflight fails or stalls
  - Triage:
    - `python3 -m src.interfaces.cli preflight --help`
    - `python3 -m src.interfaces.cli prefect preflight --help`
- Incident: data contracts fail
  - Triage:
    - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"`
- Incident: offline integration or e2e instability
  - Triage:
    - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration`
    - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e`
- Incident: command-map drift
  - Triage:
    - `rg -n "CMD-" docs/manifest/09_runbook.md docs/manifest/11_ci.md`
- Incident: source-support labels missing or inconsistent in runtime surfaces
  - Triage:
    - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_pipeline_api__source_support.py -q`
    - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_pipeline_status__shows_source_support_labels -q`
    - `rg -n "supported|blocked|fallback|source_support|assumption_badges|artifact_ids" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py docs/crawler_status.md -S`
- Incident: ChatMock/OpenAI-compatible backend rejects text or vision requests
  - Triage:
    - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/platform/test_llm__chatmock_routing.py tests/unit/listings/services/test_description_analyst__chatmock.py tests/unit/listings/services/test_vlm__chatmock.py -q`
    - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q`
    - `rg -n "litellm_completion_failed|description_analysis_failed|vlm_backend_request_failed|fusion_vlm_failed" src/listings src/platform -S`
    - verify `config/llm.yaml`, `config/description_analyst.yaml`, and `config/vlm.yaml` point to the intended `api_base` and model names
- Incident: segmented conformal coverage gate fails
  - Triage:
    - `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --coverage-report-output data/calibration_coverage.json --coverage-min-samples 20 --coverage-floor 0.80`
    - Inspect failed segments (`status = fail`) by `region_id`, `listing_type`, `price_band`, and `horizon_months`.
- Incident: spatial residual drift/outlier warnings spike
  - Triage:
    - `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --spatial-diagnostics-output data/spatial_residual_diagnostics.json --spatial-min-samples 20 --spatial-drift-threshold-pct 0.08 --spatial-outlier-rate-threshold 0.15 --spatial-outlier-zscore 2.5`
    - Inspect warned segments (`status` starts with `warn_`) and prioritize persistent warnings by `region_id`, `listing_type`, `price_band`, and `horizon_months`.

## Milestone Gate

Before closing the current P0 packet:
- `docs/manifest/07_observability.md` exists and maps objective metrics to measurable signals.
- `docs/manifest/11_ci.md` references command IDs from `docs/manifest/09_runbook.md`.
- `docs/implementation/checklists/02_milestones.md` includes observability acceptance checks.
