# Runbook

## Command Map

This is the canonical command map for local operation and CI pointers.

| ID | Purpose | Command | Source |
| --- | --- | --- | --- |
| `CMD-CLI-HELP` | Inspect primary CLI surface | `python3 -m src.interfaces.cli -h` | `src/interfaces/cli.py` |
| `CMD-PREFLIGHT` | Run canonical freshness orchestration | `python3 -m src.interfaces.cli preflight` | `src/interfaces/cli.py` |
| `CMD-PREFLIGHT-HELP` | Inspect preflight command behavior | `python3 -m src.interfaces.cli preflight --help` | `src/interfaces/cli.py` |
| `CMD-PREFECT-PREFLIGHT-HELP` | Inspect wrapped Prefect preflight options | `python3 -m src.interfaces.cli prefect preflight --help` | `src/platform/workflows/prefect_orchestration.py` |
| `CMD-DASHBOARD` | Launch Streamlit dashboard | `python3 -m src.interfaces.cli dashboard` | `src/interfaces/cli.py` |
| `CMD-DASHBOARD-HELP` | Inspect dashboard command behavior | `python3 -m src.interfaces.cli dashboard --help` | `src/interfaces/cli.py` |
| `CMD-DASHBOARD-SKIP-PREFLIGHT` | Launch dashboard without preflight refresh | `python3 -m src.interfaces.cli dashboard --skip-preflight` | `src/interfaces/cli.py` |
| `CMD-MARKET-DATA` | Build market/registry artifacts | `python3 -m src.interfaces.cli market-data` | `src/interfaces/cli.py` |
| `CMD-BUILD-INDEX` | Build vector retrieval index | `python3 -m src.interfaces.cli build-index --listing-type sale` | `src/interfaces/cli.py` |
| `CMD-TRAIN` | Train fusion model | `python3 -m src.interfaces.cli train --epochs 50` | `src/interfaces/cli.py` |
| `CMD-FUSION-TREE-BENCHMARK` | Benchmark fusion against RF/XGBoost baselines under time+geo split | `python3 -m src.interfaces.cli benchmark --listing-type sale --geo-key city --max-fusion-eval 80 --output-json docs/implementation/reports/fusion_tree_benchmark.json --output-md docs/implementation/reports/fusion_tree_benchmark.md` | `src/ml/training/benchmark.py` |
| `CMD-RETRIEVER-ABLATION` | Run retrieval ablation packet (`geo-only` vs `geo+structure` vs `geo+structure+semantic`) and emit decision report | `python3 -m src.interfaces.cli retriever-ablation --listing-type sale --max-targets 80 --num-comps 5 --output-json docs/implementation/reports/retriever_ablation_report.json --output-md docs/implementation/reports/retriever_ablation_report.md` | `src/ml/training/retriever_ablation.py` |
| `CMD-BACKFILL` | Persist valuation snapshots | `python3 -m src.interfaces.cli backfill --listing-type sale --max-age-days 7` | `src/interfaces/cli.py` |
| `CMD-CALIBRATION-COVERAGE` | Build stratified calibrators and emit segmented coverage report | `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --coverage-report-output data/calibration_coverage.json --coverage-min-samples 20 --coverage-floor 0.80` | `src/valuation/workflows/calibration.py` |
| `CMD-SPATIAL-RESIDUAL-DIAGNOSTICS` | Emit spatial drift/outlier diagnostics (Moran/LISA proxy fields) | `python3 -m src.interfaces.cli calibrators --input <samples.jsonl> --spatial-diagnostics-output data/spatial_residual_diagnostics.json --spatial-min-samples 20 --spatial-drift-threshold-pct 0.08 --spatial-outlier-rate-threshold 0.15 --spatial-outlier-zscore 2.5` | `src/valuation/workflows/calibration.py` |
| `CMD-MIGRATE` | Apply DB migrations | `python3 -m src.interfaces.cli migrate` | `src/interfaces/cli.py` |
| `CMD-TEST-MARKERS` | List pytest markers and gating flags | `python3 -m pytest --markers` | `pytest.ini`, `tests/conftest.py` |
| `CMD-TEST-UNIT` | Run deterministic unit suite | `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"` | `pytest.ini`, `tests/` |
| `CMD-TEST-INTEGRATION` | Run offline integration suite | `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration` | `tests/integration/` |
| `CMD-TEST-E2E` | Run offline e2e suite | `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e` | `tests/e2e/` |
| `CMD-TEST-E2E-UI` | Run dashboard UI verification loop (fixture-backed Streamlit AppTest) | `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` | `tests/e2e/ui/test_dashboard_ui_verification_loop.py`, `src/interfaces/dashboard/app.py` |
| `CMD-TEST-LIVE-UI` | Run live-browser dashboard trust verification (real Streamlit server + Playwright) | `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q` | `tests/live/ui/test_dashboard_live_browser__source_support.py`, `src/interfaces/cli.py`, `src/interfaces/dashboard/app.py` |
| `CMD-TEST-OFFLINE-ALL` | Run full offline gate | `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration --run-e2e -m "not live"` | `pytest.ini`, `tests/` |
| `CMD-DOCS-SYNC-GUARD` | Enforce docs updates for runtime/test/CI changes | `python3 scripts/check_docs_sync.py --base <base_sha> --head <head_sha>` | `scripts/check_docs_sync.py` |
| `CMD-CI-COMMAND-MAP-CHECK` | Verify CI docs reference valid runbook IDs | `python3 scripts/check_command_map.py` | `scripts/check_command_map.py` |
| `CMD-ARTIFACT-FEATURE-CONTRACT-CHECK` | Ensure load-bearing artifact IDs remain mapped to feature/test outcomes | `python3 scripts/check_artifact_feature_contract.py` | `scripts/check_artifact_feature_contract.py` |

## Environment Variables (Key)

- `PROPERTY_SCANNER_DATA_DIR`
- `PROPERTY_SCANNER_MODELS_DIR`
- `PROPERTY_SCANNER_DB_PATH`
- `PROPERTY_SCANNER_DB_URL`
- `PROPERTY_SCANNER_VECTOR_INDEX_PATH`
- `PROPERTY_SCANNER_VECTOR_METADATA_PATH`
- `RUN_INTEGRATION`
- `RUN_E2E`
- `RUN_LIVE`

Source: `config/paths.yaml`, `tests/conftest.py`.

## Triage Playbook

### Pipeline orchestration issue

1. Confirm CLI and preflight surfaces:
   - `CMD-CLI-HELP`
   - `CMD-PREFLIGHT-HELP`
2. Inspect wrapped Prefect command surface:
   - `CMD-PREFECT-PREFLIGHT-HELP`

### Offline test regression

1. Inspect marker configuration:
   - `CMD-TEST-MARKERS`
2. Re-run deterministic suites in order:
   - `CMD-TEST-UNIT`
   - `CMD-TEST-INTEGRATION`
   - `CMD-TEST-E2E`

### Dashboard launch issue

1. Verify preflight behavior and launch path:
   - `CMD-PREFLIGHT`
   - `CMD-DASHBOARD`
2. Run deterministic UI flow checks:
   - `CMD-TEST-E2E-UI`
3. Run live-browser trust verification when source-label rendering evidence is required:
   - `CMD-TEST-LIVE-UI`

### Segmented coverage gate failure

1. Recompute stratified calibrators and emit coverage report:
   - `CMD-CALIBRATION-COVERAGE`
2. Inspect failing rows in report output (`status = fail`) and triage by:
   - `region_id`
   - `listing_type`
   - `price_band`
   - `horizon_months`

### Fallback interval policy for weak-regime segments

1. Primary interval mode remains segmented conformal calibration.
2. Runtime switches to wider bootstrap fallback intervals when any of these are true for a `(region_id, listing_type, price_band, horizon_months)` segment:
   - segment is unseen in the calibrator registry,
   - `n_samples < 20`,
   - `coverage_rate < coverage_floor` where the default floor is `target_coverage - 0.05` and currently resolves to `0.80` for `alpha = 0.10`.
3. Triage bootstrap-heavy runs by inspecting:
   - `valuations.evidence.calibration_status`
   - `valuations.evidence.calibration_fallback_reason`
   - `valuations.evidence.calibration_diagnostics`
4. If fallback reason is `insufficient_samples` or `unseen_segment`, prioritize data collection for the affected segment before treating intervals as stable.
5. If fallback reason is `coverage_below_floor`, treat the segment as a calibration drift warning and rerun `CMD-CALIBRATION-COVERAGE` before trusting confidence-sensitive decisions.

### Spatial drift/outlier warning

1. Emit spatial residual diagnostics:
   - `CMD-SPATIAL-RESIDUAL-DIAGNOSTICS`
2. Inspect warned rows (`status` starts with `warn_`) and triage by:
   - `region_id`
   - `listing_type`
   - `price_band`
   - `horizon_months`
3. Prioritize segments where `drift_flag` or `outlier_flag` persist across consecutive runs.

### Fusion benchmark gate failure

1. Re-run benchmark artifact generation:
   - `CMD-FUSION-TREE-BENCHMARK`
2. Inspect gate reasons and fusion coverage fields in:
   - `docs/implementation/reports/fusion_tree_benchmark.json`
3. If `fusion_coverage_below_threshold` dominates, triage listing quality for:
   - missing geolocation (`lat`/`lon`)
   - hedonic index fallback errors

### Retriever ablation / decomposition decision packet

1. Re-run retrieval ablations:
   - `CMD-RETRIEVER-ABLATION`
2. Inspect decision payloads in:
   - `docs/implementation/reports/retriever_ablation_report.json`
3. Route based on decision:
   - if semantic decision is `keep`: retain semantic retrieval complexity and schedule drift monitoring.
   - if semantic decision is `simplify`: prioritize simplification packet for semantic retrieval path.
   - if decomposition status is `insufficient_segment_samples` or `warn_mae_gap`: keep decomposition gap visible and prioritize diagnostics packet.

### Docs/CI guardrail issue

1. Validate docs-sync logic with explicit changed files:
   - `CMD-DOCS-SYNC-GUARD`
2. Validate CI command-ID references:
   - `CMD-CI-COMMAND-MAP-CHECK`
3. Validate artifact-feature mapping contract:
   - `CMD-ARTIFACT-FEATURE-CONTRACT-CHECK`

## Known Operational Footguns

- `preflight --help` now exposes common flags; full flow-level options still live under `CMD-PREFECT-PREFLIGHT-HELP`.
- Dashboard launch runs preflight by default unless `--skip-preflight` is passed.
- Compose worker command semantics require explicit query/area args and are not a persistent worker role yet.
- Spatial diagnostics currently expose Moran/LISA proxy signals, not full adjacency-matrix inference.
- Bootstrap fallback intervals are intentionally wider and lower-trust than calibrated intervals; `bootstrap` is an explicit caution state, not a calibrated success state.
