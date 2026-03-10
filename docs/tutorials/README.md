# Tutorial: Local End-to-End Reliability Pass

Outcome: validate that your workspace can run the core local workflow and produce interpretable outputs.

## Step 1: Inspect command surface

```bash
python3 -m src.interfaces.cli -h
```

You should see commands including `preflight`, `market-data`, `build-index`, `train-pipeline`, and `backfill`.

## Step 2: Validate test marker gating

```bash
python3 -m pytest --markers
```

You should see markers `integration`, `e2e`, and `live`.

## Step 3: Run offline quality gate

```bash
python3 -m pytest --run-integration --run-e2e -m "not live"
```

Checkpoint:
- Offline suites pass.
- Any warnings are visible and can be reviewed in test output.

## Step 4: Run preflight refresh

```bash
python3 -m src.interfaces.cli preflight --skip-transactions
```

Checkpoint:
- Pipeline runs complete without manual DB repairs.
- Artifacts in `data/` and `models/` are available.

## Step 5: Inspect outputs

- Data model and artifacts: [Data Formats](../reference/data_formats.md)
- Output semantics and sanity checks: [Interpret Outputs](../how_to/interpret_outputs.md)

## Common Tutorial Failure Points

- Browser dependencies missing for crawler sources.
- Source reliability variability due anti-bot protections.
- Transactions ingest assumptions if `transactions.csv` is not present.

Use [Troubleshooting](../troubleshooting.md) for symptom-based fixes.
