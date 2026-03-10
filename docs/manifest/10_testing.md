# Testing

## Test Runner

- Runner: `pytest`
- Preferred invocation: use the project venv Python:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest`

Note: in this environment, pytest may auto-load third-party plugins installed in the venv (for example `langsmith`). The suite should remain stable even when those plugins are present.

## Markers and Gating

Markers are declared in `pytest.ini` and applied via `tests/conftest.py`.

- `integration`: offline integration tests (SQLite/filesystem), no live network.
- `e2e`: end-to-end tests (offline, minimal mocks).
- `live`: real network/browser tests, always opt-in.
- `network`: hits the network.
- `slow`: long-running tests.

Default run behavior:
- `integration`, `e2e`, and `live` are skipped unless explicitly enabled.

Enable opt-in suites:
- Integration: `--run-integration` or `RUN_INTEGRATION=1`
- E2E: `--run-e2e` or `RUN_E2E=1`
- Live: `--run-live` or `RUN_LIVE=1`

## Canonical Command Map Pointer

Canonical commands are maintained in:
- `docs/manifest/09_runbook.md` (`## Command Map`)

Testing-focused command IDs:
- `CMD-TEST-MARKERS`
- `CMD-TEST-UNIT`
- `CMD-TEST-INTEGRATION`
- `CMD-TEST-E2E`
- `CMD-TEST-OFFLINE-ALL`
- `CMD-FUSION-TREE-BENCHMARK`
- `CMD-RETRIEVER-ABLATION`

## Trust-Critical Coverage

- Confidence persistence semantics are covered by:
  - `tests/unit/valuation/test_valuation_persister__confidence_semantics.py`
- Dashboard stale-cache rendering semantics are covered by:
  - `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`
- Segmented coverage reporting semantics are covered by:
  - `tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py`
- Spatial residual diagnostics semantics are covered by:
  - `tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py`
- Fusion-vs-tree benchmark gate semantics are covered by:
  - `tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py`
  - `tests/unit/ml/test_retriever_ablation_workflow__decisions.py`
- ChatMock/OpenAI-compatible routing and fallback semantics are covered by:
  - `tests/unit/platform/test_llm__chatmock_routing.py`
  - `tests/unit/listings/services/test_description_analyst__chatmock.py`
  - `tests/unit/listings/services/test_vlm__chatmock.py`
  - `tests/integration/listings/test_feature_fusion__chatmock_paths.py`
- Targeted run:
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py tests/unit/valuation/test_valuation_persister__confidence_semantics.py tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py tests/unit/ml/test_retriever_ablation_workflow__decisions.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py tests/unit/platform/test_llm__chatmock_routing.py tests/unit/listings/services/test_description_analyst__chatmock.py tests/unit/listings/services/test_vlm__chatmock.py -q`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q`
  - `python3 -m src.interfaces.cli benchmark --listing-type sale --geo-key city --max-fusion-eval 80 --output-json docs/implementation/reports/fusion_tree_benchmark.json --output-md docs/implementation/reports/fusion_tree_benchmark.md`
  - `python3 -m src.interfaces.cli retriever-ablation --listing-type sale --max-targets 80 --num-comps 5 --output-json docs/implementation/reports/retriever_ablation_report.json --output-md docs/implementation/reports/retriever_ablation_report.md`

## Environment Needs

- Unit: no external services; uses local fixtures and `tmp_path`.
- Integration: local SQLite + filesystem only.
- E2E: local SQLite + fixture HTML + filesystem only.
- Live: real network and may require Playwright/Pydoll browsers depending on crawler configuration.

## Current Gaps

- CI baseline exists in `.github/workflows/ci.yml`; monitor duration/stability and tighten cache/install strategy if needed.
- Docs integrity now validates command-map references and artifact-feature mapping contract invariants; broader link checks remain follow-up.
