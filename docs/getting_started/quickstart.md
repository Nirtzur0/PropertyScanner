# Quickstart

Outcome: run the project locally, validate the command surface, and open the React workbench.

## 1) Setup Environment

Follow [Installation](./installation.md) first.

## 2) Confirm Core Commands

```bash
python3 -m src.interfaces.cli -h
python3 -m src.interfaces.cli preflight --help
```

Checkpoint: you can see the top-level command list and preflight wrapper help output.

## 3) Run Offline Quality Gate (recommended)

```bash
python3 -m pytest --run-integration --run-e2e -m "not live"
```

Checkpoint: tests complete green for offline suites.

## 4) Launch The App

```bash
python3 -m src.interfaces.cli api --host 127.0.0.1 --port 8001
```

Open: `http://127.0.0.1:8001/workbench`

The JSON API is available under `http://127.0.0.1:8001/api/v1/...`.
Legacy Streamlit remains available only as a deprecated operator surface:

```bash
python3 -m src.interfaces.cli legacy-dashboard --skip-preflight
```

## 5) Optional Full Refresh

If you have required data inputs (for example transactions file) and want a full refresh:

```bash
python3 -m src.interfaces.cli preflight --skip-transactions
```

Then reload the React workbench.

## Next

- Learn the full workflow: [Run End-to-End](../how_to/run_end_to_end.md)
- Learn output semantics: [Interpret Outputs](../how_to/interpret_outputs.md)
- Explore command details: [CLI Reference](../reference/cli.md)
