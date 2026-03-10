# Data Model

This document describes entities, stores, and lineage used by runtime scenarios in `docs/manifest/01_architecture.md`.

## Storage Surfaces

| Surface | Type | Default Location | Purpose | Evidence |
| --- | --- | --- | --- | --- |
| Operational DB | SQLite | `data/listings.db` | system of record for listings, valuations, indices, runs | `src/platform/config.py`, `src/platform/domain/models.py`, `src/platform/migrations.py` |
| Seen URLs DB | SQLite | `data/unified_seen_urls.sqlite3` | crawl dedupe state per source/mode | `src/listings/workflows/unified_crawl.py` |
| Legacy/general seen DB | SQLite | `data/seen_urls.sqlite3` | configurable seen-url storage path | `src/platform/config.py` |
| Vector index | LanceDB | `data/vector_index.lancedb` | semantic comp retrieval index | `src/platform/config.py`, `src/valuation/workflows/indexing.py` |
| Vector metadata | JSON | `data/vector_metadata.json` | index model/policy/fingerprint metadata | `src/valuation/services/retrieval.py` |
| Model artifacts | Files | `models/*` | fusion model, config, calibration, forecast model | `src/platform/config.py`, `src/platform/settings.py` |
| Snapshots | Files | `data/snapshots/` | crawled raw/snapshot artifacts | `src/platform/config.py` |

## Relational Entities

### Core ORM tables

| Table | Key Columns | Description | Evidence |
| --- | --- | --- | --- |
| `listings` | `id`, `source_id`, `external_id`, `url`, `price`, `listing_type`, `status`, geo + enrichment fields | canonical listing entity used by all workflows | `src/platform/domain/models.py` |
| `valuations` | `id`, `listing_id`, `model_version`, `fair_value`, ranges, `evidence` | historical valuation snapshots per listing | `src/platform/domain/models.py` |
| `agent_runs` | `id`, `query`, `strategy`, `plan`, counters, `ui_blocks` | persisted memory for agent runs | `src/platform/domain/models.py`, `src/agentic/memory.py` |

### Migrated/derived tables

| Table | Key Dimensions | Description | Evidence |
| --- | --- | --- | --- |
| `market_indices` | `region_id`, `month_date` | market price/rent/inventory/liquidity metrics | `src/platform/migrations.py` |
| `macro_indicators` | `date` | macroeconomic indicators | `src/platform/migrations.py` |
| `macro_scenarios` | `date`, `scenario_name` | scenario forecasts and source trace | `src/platform/migrations.py` |
| `hedonic_indices` | `region_id`, `month_date` | hedonic index outputs and diagnostics | `src/platform/migrations.py` |
| `area_intelligence` | `area_id` | sentiment/development signals + source URLs | `src/platform/migrations.py` |
| `official_metrics` | `provider_id`, `region_id`, `period_date`, `metric` | unified official provider metrics | `src/platform/migrations.py` |
| `pipeline_runs` | `run_id`, `step_name`, `status`, time fields | workflow execution telemetry | `src/platform/pipeline/repositories/pipeline_runs.py`, `src/platform/migrations.py` |

## Domain Schema Contracts

| Model | Role | Evidence |
| --- | --- | --- |
| `RawListing` | pre-normalization crawler payload | `src/platform/domain/schema.py` |
| `CanonicalListing` | normalized listing contract across services | `src/platform/domain/schema.py` |
| `DealAnalysis` | valuation and decision output | `src/platform/domain/schema.py` |
| `EvidencePack` + `CompEvidence` | valuation interpretability payload | `src/platform/domain/schema.py` |
| `ValuationProjection` | forward horizon projection unit | `src/platform/domain/schema.py` |

## Data Lineage by Runtime Flow

### Preflight flow lineage

1. `PipelineStateService` inspects listings/index/model freshness.
2. Stale or missing conditions trigger workflow steps.
3. Steps write data into DB tables and artifacts.
4. `pipeline_runs` records status and metadata.

Evidence: `src/platform/pipeline/state.py`, `src/platform/workflows/prefect_orchestration.py`, `src/platform/pipeline/repositories/pipeline_runs.py`.

### Crawl to listing lineage

1. Crawlers produce raw records.
2. Normalization maps to `CanonicalListing`.
3. Quality gate filters invalid entries.
4. Persistence writes to `listings`.
5. Seen-url store marks processed URLs.

Evidence: `src/listings/workflows/unified_crawl.py`, `src/listings/services/quality_gate.py`, `src/listings/services/listing_persistence.py`.

### Valuation lineage

1. Candidate listing is loaded from `listings`.
2. Retriever reads vector index + metadata and returns comps.
3. Valuation service computes estimates/evidence.
4. Persister writes snapshot into `valuations`.

Evidence: `src/interfaces/api/pipeline.py`, `src/valuation/services/retrieval.py`, `src/valuation/services/valuation.py`, `src/valuation/services/valuation_persister.py`.

## Invariants

- `listings.id` remains stable primary key for cross-flow joins.
- `valuations.listing_id` references existing listing ids.
- Run telemetry is append/transition based (`running` -> terminal status) in `pipeline_runs`.
- Retriever metadata must remain aligned with embedding model and index fingerprint.
- Listing type semantics (`sale`/`rent`) remain normalized across ingestion and valuation paths.

## Known Gaps and Drift Risks

- `pipeline_runs` table creation appears in both migrations and repository bootstrap; behavior is compatible but duplicated.
- Docker compose includes PostgreSQL while default runtime persists to SQLite; docs and contributor expectations must keep this explicit.
- No formal schema migration version table yet; migrations are idempotent best effort.

Evidence: `src/platform/migrations.py`, `src/platform/pipeline/repositories/pipeline_runs.py`, `docker-compose.yml`, `src/platform/config.py`.
