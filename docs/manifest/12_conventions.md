# Conventions

## Repository Layout

- `src/interfaces/`: user-facing interfaces (CLI, dashboard, Python API).
- `src/platform/`: config, persistence, migrations, orchestration utilities.
- `src/listings/`, `src/market/`, `src/valuation/`, `src/ml/`: domain workflows/services.
- `tests/`: unit/integration/e2e/live markers with explicit gating.
- `docs/manifest/`: architecture/policy/reference.
- `docs/implementation/`: status/checklists/reports/worklog.

## Coding and Boundary Rules

- Prefer extending existing modules before introducing new abstractions.
- Keep public boundaries typed and explicit (`src/platform/domain/schema.py`).
- Treat CLI/API/workflow boundaries as contracts; document changes in `docs/manifest/04_api_contracts.md`.
- Keep one canonical command map in `docs/manifest/09_runbook.md`.

## Config and Environment

- Configuration is Hydra-composed from `config/app.yaml` and includes.
- Runtime-specific paths should be configured through environment variables, not hardcoded absolute paths.

## Testing and Gating

- Default suite is deterministic and offline; integration/e2e/live are opt-in by marker flags.
- Any runtime behavior change must update:
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/10_testing.md` and/or `docs/manifest/11_ci.md`
  - `docs/implementation/00_status.md`

## Docs Update Discipline

- `docs/manifest/*`: what/why references.
- `docs/implementation/*`: packet execution evidence.
- Significant build-vs-buy and architecture deviations are recorded in `docs/manifest/03_decisions.md`.

## Naming and Documentation Style

- Use descriptive, stable names for commands and checklist IDs.
- Checklist items are outcome-based and include acceptance + verification commands.
- Prefer linking to canonical docs instead of duplicating large tables.
