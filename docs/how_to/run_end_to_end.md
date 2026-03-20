# How-To: Run End-to-End

This recipe runs the current local-first workflow from package/API verification to the React workbench and downstream valuation artifacts.

## 1) Verify command surface

```bash
python3 -m src.interfaces.cli -h
```

## 2) Seed or refresh local data

For the deterministic local demo path:

```bash
python3 -m src.interfaces.cli seed-sample-data
make smoke-api
```

For a broader local refresh:

```bash
python3 -m src.interfaces.cli preflight --skip-transactions
```

If you need full transaction ingest, provide a valid transactions path and remove `--skip-transactions`.

## 3) Run explicit workflow stages (optional, targeted)

```bash
python3 -m src.interfaces.cli market-data
python3 -m src.interfaces.cli build-index --listing-type sale
python3 -m src.interfaces.cli train-pipeline --epochs 50
python3 -m src.interfaces.cli backfill --listing-type sale --max-age-days 7
```

## 4) Open the primary app surface

```bash
property-scanner api --host 127.0.0.1 --port 8001
```

Open:

- React workbench: `http://127.0.0.1:8001/workbench`
- JSON API: `http://127.0.0.1:8001/api/v1/...`

Legacy Streamlit remains available only as a deprecated operator surface:

```bash
python3 -m src.interfaces.cli legacy-dashboard --skip-preflight
```

## 5) Validate outputs

- Artifact reference: [Data Formats](../reference/data_formats.md)
- Output interpretation: [Interpret Outputs](./interpret_outputs.md)
- Pipeline architecture/details: [Data And Training Pipeline](../explanation/data_pipeline.md)
- Reliability checks: [Troubleshooting](../troubleshooting.md)

## Optional: run the same repo-owned checks as the local gate

```bash
make test-offline
make test-integration
make test-e2e
```
