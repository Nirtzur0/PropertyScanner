# Installation

## Prerequisites

- Python 3.10+
- `pip`
- Playwright browser binaries (required for `html_browser` crawler sources)

## Install (pip + venv)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.lock
python3 -m playwright install
```

## Lockfile Policy

```bash
python3 -m pip install pip-tools
python3 -m piptools compile --resolver=backtracking --output-file requirements.lock requirements.txt
```

Use `requirements.lock` for installs. Treat `requirements.txt` as the editable input list and refresh the lockfile when dependency constraints change.

## Verify Installation

```bash
python3 -m src.interfaces.cli -h
python3 -m pytest --markers
```

You should see:
- CLI command list including `preflight`, `market-data`, `build-index`, `dashboard`, and `agent`.
- Pytest marker list including `integration`, `e2e`, and `live`.

## Platform Notes

- Default runtime is local-first and SQLite-backed (`data/listings.db`).
- Docker compose is optional for dashboard/testing workflows (`docker-compose.yml`).

## Common Install Issues

- Missing browser binaries:
  - Symptom: crawler/dashboard paths that require browser automation fail.
  - Fix: run `python3 -m playwright install`.
- Optional plugin noise in pytest output:
  - Symptom: extra plugin warnings during test discovery.
  - Fix: this is expected in some environments; the project uses explicit marker gating.
