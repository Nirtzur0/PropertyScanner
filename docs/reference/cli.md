# CLI Reference

Primary entrypoint:

```bash
property-scanner --help
```

Repo-owned command surface:

```bash
make build-package
make test-offline
make test-integration
make test-e2e
make smoke-api
```

The CLI is a wrapper over module entrypoints in `src/interfaces/cli.py`. `property-scanner` is the supported console entrypoint; `python3 -m src.interfaces.cli` remains compatible.

## Commands

| Command | Delegates to | Notes |
| --- | --- | --- |
| `market-data` | `src.platform.workflows.prefect_orchestration` | Prefect market-data flow |
| `build-index` | `src.platform.workflows.prefect_orchestration` | Prefect vector index flow |
| `train` | `src.ml.training.train` | Fusion training module wrapper; sale runs fail fast with explicit closed-sale readiness diagnostics |
| `benchmark` | `src.ml.training.benchmark` | Fusion-vs-tree benchmark; sale runs fail fast with explicit closed-sale readiness diagnostics |
| `backfill` | `src.platform.workflows.prefect_orchestration` | Prefect valuation backfill flow |
| `transactions` | `src.platform.workflows.prefect_orchestration` | Prefect transactions flow |
| `api` | `uvicorn src.adapters.http.app:app` | Serves the React workbench and `/api/v1/...` JSON endpoints |
| `dashboard` | Deprecated Streamlit launcher | Kept as a legacy alias during migration |
| `legacy-dashboard` | Deprecated Streamlit launcher | `--skip-preflight` avoids automatic preflight |
| `agent` | `src.interfaces.agent` | Requires query and at least one area |
| `calibrators` | `src.valuation.workflows.calibration` | Calibration workflow wrapper (supports segmented coverage report output) |
| `clean-data` | `src.platform.workflows.prefect_orchestration maintenance --clean` | Data cleanup path |
| `preflight` | `src.platform.workflows.prefect_orchestration preflight` | Canonical freshness orchestration with top-level common flags |
| `prefect` | `src.platform.workflows.prefect_orchestration` | Use for detailed flow flags |
| `unified-crawl` | `src.listings.workflows.unified_crawl` | Source crawl wrapper |
| `sidecar-crawl` | `src.listings.scraping.sidecar` | Writes/invokes the Node/TypeScript crawl sidecar contract |
| `migrate` | `src.platform.migrations` | DB schema migrations |
| `train-pipeline` | `src.platform.workflows.prefect_orchestration` | VLM + fusion training flow |
| `caption-images` | `src.platform.workflows.prefect_orchestration maintenance --vlm` | VLM captioning path |
| `audit-serving-data` | application reporting service | Scans current listings and records serving-eligibility issues into `data_quality_events` |
| `seed-sample-data` | application sample-data seeder | Seeds a small local `pisos` dataset for smoke tests and first-run demos |

## Getting detailed flags

`preflight` now exposes common freshness/caching flags at top-level help:

```bash
property-scanner preflight --help
```

For full Prefect flow-level arguments, use:

```bash
python3 -m src.interfaces.cli prefect preflight --help
python3 -m src.interfaces.cli prefect market-data --help
python3 -m src.interfaces.cli prefect build-index --help
```

Calibrator workflow example with segmented coverage output:

```bash
python3 -m src.interfaces.cli calibrators \
  --input "<samples.jsonl>" \
  --coverage-report-output data/calibration_coverage.json \
  --coverage-min-samples 20 \
  --coverage-floor 0.80

python3 -m src.interfaces.cli calibrators \
  --input "<samples.jsonl>" \
  --spatial-diagnostics-output data/spatial_residual_diagnostics.json \
  --spatial-min-samples 20 \
  --spatial-drift-threshold-pct 0.08 \
  --spatial-outlier-rate-threshold 0.15 \
  --spatial-outlier-zscore 2.5

python3 -m src.listings.scraping.sidecar \
  --source-id pisos \
  --start-url "https://example.com/search" \
  --write-only
```

If you need the calibration module's native argparse help text:

```bash
python3 -m src.valuation.workflows.calibration --help
python3 -m src.ml.training.train --help
python3 -m src.ml.training.benchmark --help
python3 -m src.listings.scraping.sidecar --help
```

## Exit behavior

- CLI returns delegated module exit code.
- Unknown command fails with parser error.

## Supported local slice

- `pisos` is the documented supported end-to-end local slice for this packet.
- `rightmove_uk`, `zoopla_uk`, `imovirtual_pt`, `onthemarket_uk`, and `sreality_cz` should be treated as experimental unless fresh runtime evidence upgrades them.
- `realtor_us`, `redfin_us`, `seloger_fr`, and `immowelt_de` now have deterministic normalizers but require proxy-backed browser configuration for live crawling.
- blocked portals remain blocked, and proxy-required portals now fail explicitly rather than silently degrading to fake success.
