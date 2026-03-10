# Architecture Coherence Report

Generated for packet: `prompt-04-architecture-coherence-loop`  
Date: 2026-02-08

## 1. Current architecture snapshot (lean profile status)

- Architecture baseline now exists in `docs/manifest/01_architecture.md` with required sections:
  - scope/constraints/quality scenarios
  - C4-1 context
  - C4-2 containers
  - C4-3 components (high-risk areas)
  - runtime scenarios
  - deployment/trust boundaries
  - cross-cutting concepts
  - risks/technical debt
- Contract and data model pages were added:
  - `docs/manifest/04_api_contracts.md`
  - `docs/manifest/05_data_model.md`
- Coherence tracking checklist created:
  - `docs/implementation/checklists/00_architecture_coherence.md`

## 2. Diagram-to-repo mapping table (element -> path -> status)

| Element | Evidence Path(s) | Status |
| --- | --- | --- |
| CLI entrypoint container | `src/interfaces/cli.py` | mapped |
| Dashboard container | `src/interfaces/dashboard/app.py` | mapped |
| Python API container | `src/interfaces/api/pipeline.py` | mapped |
| Prefect orchestration container | `src/platform/workflows/prefect_orchestration.py` | mapped |
| Pipeline freshness/state component | `src/platform/pipeline/state.py` | mapped |
| Unified crawl container | `src/listings/workflows/unified_crawl.py` | mapped |
| Market workflow container | `src/market/workflows/market_data.py` | mapped |
| Valuation workflow container | `src/valuation/workflows/backfill.py`, `src/valuation/services/valuation.py` | mapped |
| Retrieval/index component | `src/valuation/workflows/indexing.py`, `src/valuation/services/retrieval.py` | mapped |
| Training container | `src/ml/training/train.py` | mapped |
| Agentic orchestration container | `src/agentic/orchestrator.py`, `src/agentic/graph.py` | mapped |
| Operational DB store | `src/platform/domain/models.py`, `src/platform/migrations.py` | mapped |
| Run telemetry store | `src/platform/pipeline/repositories/pipeline_runs.py`, `src/agentic/memory.py` | mapped |
| Optional Docker deployment | `Dockerfile`, `docker-compose.yml` | mapped |

## 3. Key mismatches, decisions, and open risks

### Key mismatches / drift

- Architecture artifacts were missing from manifest tree before this packet; now resolved.
- `docs/INDEX.md` did not point to architecture coherence outputs; now resolved.
- Remaining drift:
  - CI workflow absent.
  - Release discipline docs absent.
  - Dedicated runbook/command-map page (`docs/manifest/09_runbook.md`) absent.

### Decisions taken

- Canonical architecture source-of-truth is now `docs/manifest/01_architecture.md`.
- Existing narrative docs (for example `docs/explanation/system_overview.md`) remain valid as supplemental context, not canonical architecture control docs.
- Readiness verdict for this packet: `GO_WITH_RISKS`.

### Open risks

- R1: No CI validation for architecture/docs drift.
- R2: Docker/Postgres optional path may diverge from SQLite-first defaults.
- R3: Retriever metadata/index mismatch can affect valuation confidence when artifacts are stale.

## 4. Verification command evidence (with source paths)

- `python3 -m src.interfaces.cli -h`
  - Result: pass; canonical command surface is available.
  - Source path: `src/interfaces/cli.py`
- `python3 -m src.platform.workflows.prefect_orchestration -h`
  - Result: pass; flow commands are exposed (`preflight`, `market-data`, `build-index`, `train-pipeline`, `backfill`, etc.).
  - Source path: `src/platform/workflows/prefect_orchestration.py`
- `python3 -m pytest --markers`
  - Result: pass; marker taxonomy visible and aligned with testing docs.
  - Source paths: `pytest.ini`, `tests/conftest.py`, `docs/manifest/10_testing.md`
- `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
  - Result: pass; prompt-04 no longer blocked by missing architecture artifacts.
  - Source path: `prompts/scripts/prompt_router.py`

## 5. Readiness verdict and rationale

Verdict: `GO_WITH_RISKS`

Rationale:

- GO because:
  - Required architecture/coherence deliverables now exist and are internally linked.
  - C4/runtime/deployment coverage is present with real evidence paths.
  - Contract and data-model docs align with implemented interfaces/stores.
- WITH_RISKS because:
  - CI/release discipline and dedicated runbook artifacts remain incomplete.
  - Runtime reliability still depends on local/manual enforcement for many checks.

## 6. Now next actions and Not now deferred items

### Now (next packet recommendations)

1. Run `prompt-03-alignment-review-gate` and produce:
   - `docs/implementation/checklists/07_alignment_review.md`
   - `docs/implementation/reports/alignment_review.md`
2. Run `prompt-07-repo-audit-checklist` and produce `checkbox.md` with milestone-ready P0/P1 outcomes.
3. Fold top P0 outcomes into `docs/implementation/checklists/02_milestones.md` in the next planning packet.

### Not now

- CI workflow creation and docs-update guardrail.
- Release discipline docs (`CHANGELOG.md`, versioning policy, release checklist).
- Dedicated command-map/runbook page (`docs/manifest/09_runbook.md`).
