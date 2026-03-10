# How-To: Interpret Outputs

## Core Output Surfaces

- Database: `data/listings.db`
- Vector index: `data/vector_index.lancedb`
- Vector metadata: `data/vector_metadata.json`
- Model artifacts: `models/`

## What success looks like

- Workflow commands complete without exceptions.
- Offline suites pass.
- Listings and valuations are present in storage.
- Run metadata exists for orchestration and agent flows.

## Key entities to interpret

- Listing contract: `CanonicalListing` (`src/platform/domain/schema.py`)
- Valuation output: `DealAnalysis` + `EvidencePack` (`src/platform/domain/schema.py`)
- Persistence tables: `listings`, `valuations`, `agent_runs` (`src/platform/domain/models.py`)

## Confidence and evidence semantics

- `fair_value_estimate` is model-estimated fair value.
- `fair_value_uncertainty_pct` is uncertainty width, not guarantee.
- persisted `valuations.confidence_score` is a composite derived from:
  - interval uncertainty (`fair_value_uncertainty_pct`)
  - calibration state (`evidence.calibration_status`)
  - projection confidence surfaces (`projections[*].confidence_score`)
  - comp support depth (`evidence.top_comps`)
  - risk penalties (volatility and index disagreement)
- confidence derivation components are stored in `valuations.evidence.confidence_components` for auditability.
- `evidence.top_comps` contains comparable support records.
- `calibration_status` and fallback flags indicate confidence quality and fallback paths.
- `evidence.calibration_fallback_reason` explains why bootstrap fallback was used when `calibration_status = bootstrap`.
- `evidence.calibration_diagnostics` stores the numeric trigger state (`n_samples`, `min_samples`, `coverage_rate`, `coverage_floor`, `horizon_months`).

## Runtime assumption badges

- `PipelineAPI.pipeline_status()` now includes `assumption_badges` for runtime trust interpretation in API/dashboard status surfaces.
- Badge fields:
  - `id`: stable badge identifier
  - `status`: `ok`, `caution`, or `gap`
  - `artifact_ids`: load-bearing literature links from `docs/artifacts/index.json`
  - `summary`: operator-facing caveat text
  - `guide_path`: doc path for deeper context
- Current badges cover:
  - source coverage caveat (`lit-case-shiller-1988`)
  - conformal coverage caveat (`lit-conformal-tutorial-2021`)
  - explicit bootstrap fallback policy for weak-regime segments (`lit-jackknifeplus-2021`)
  - open land/structure decomposition diagnostics (`lit-deng-gyourko-wu-2012`)

## Sanity checks

- Run reliability gate:

```bash
python3 -m pytest --run-integration --run-e2e -m "not live"
```

- Validate command-map and CI mapping consistency:

```bash
python3 scripts/check_command_map.py
```

## Common interpretation pitfalls

- Treating fallback-heavy source outputs as equivalent to fully normalized sources.
- Interpreting confidence as certainty.
- Ignoring freshness/staleness effects when preflight is skipped.
