# Decisions

This file records durable engineering decisions.

## 2026-02-06: Pytest Marker Taxonomy + Gating

- Decision: Standardize test selection via markers and explicit opt-in flags.
- Markers:
  - `integration`: offline integration tests (SQLite/filesystem), no live network.
  - `e2e`: end-to-end tests (offline, minimal mocks).
  - `live`: real network/browser tests, always opt-in.
  - `network`: hits the network.
  - `slow`: long-running tests.
- Gating:
  - Default `pytest` run skips `integration`, `e2e`, and `live` unless explicitly enabled.
  - Enable via CLI flags: `--run-integration`, `--run-e2e`, `--run-live` or env vars `RUN_INTEGRATION=1`, `RUN_E2E=1`, `RUN_LIVE=1`.

Rationale: keep the default suite deterministic and fast; make boundary tests explicit and easy to run.

## 2026-02-06: Mitigate Third-Party Pytest Plugin Interference

- Decision: Prefer a repo-controlled test environment and keep tests robust against extra pytest plugins being present.
- Mechanism:
  - Primary: run tests via the project venv (`venv/bin/python -m pytest`), as documented in `docs/manifest/10_testing.md`.
  - Best-effort hardening:
    - `pytest.ini` includes `addopts` entries intended to disable the LangSmith pytest plugin.
    - `sitecustomize.py` exists as an optional hook to set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, but note: in this Python 3.12 environment `sitecustomize.py` is not auto-imported at interpreter startup (so this hook may not take effect).
  - If plugin autoload becomes a real problem in some environment, prefer explicitly setting `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` in that environment and then enabling only the needed plugins.

Rationale: ensure repository tests run in a stable, repo-controlled environment.

## 2026-02-06: Make `src` Import-Safe via Lazy Exports

- Decision: avoid importing heavy/optional runtime dependencies (notably Prefect) at `import src` time.
- Mechanism:
  - `src/__init__.py` exports `PipelineAPI` lazily via `__getattr__`.

Rationale: tests and submodules should be importable without pulling in orchestration dependencies.
