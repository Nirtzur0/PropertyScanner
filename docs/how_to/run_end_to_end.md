# How-To: Run End-to-End

This recipe runs the local-first workflow from preflight to valuation artifacts.

## 1) Verify command surface

```bash
python3 -m src.interfaces.cli -h
```

## 2) Run preflight orchestration

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

## 4) Open dashboard

```bash
python3 -m src.interfaces.cli dashboard --skip-preflight
```

## 5) Validate outputs

- Artifact reference: [Data Formats](../reference/data_formats.md)
- Output interpretation: [Interpret Outputs](./interpret_outputs.md)
- Pipeline architecture/details: [Data And Training Pipeline](../explanation/data_pipeline.md)
- Reliability checks: [Troubleshooting](../troubleshooting.md)

## Optional: run same checks as CI offline gate

```bash
python3 -m pytest --run-integration --run-e2e -m "not live"
```
