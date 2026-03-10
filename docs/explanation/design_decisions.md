# Design Decisions

Canonical ADR-style decisions live in `docs/manifest/03_decisions.md`.

## Key Decisions (Current)

- Local-first runtime and SQLite system-of-record for developer-friendly operation.
- Prompt-system docs workflow with manifest and implementation tracking separation.
- Canonical command-map source moved to `docs/manifest/09_runbook.md`.
- CI baseline with docs-sync and command-map integrity checks.

## Why these decisions

- Keep the system operable by a single maintainer while preserving auditability.
- Prevent docs/code drift as workflows evolve.
- Enforce deterministic offline reliability before release hardening.

## Alternatives repeatedly deferred

- Full migration to Postgres as default runtime.
- Research-track expansion before release-discipline closure.
- Release automation beyond current CI baseline.
