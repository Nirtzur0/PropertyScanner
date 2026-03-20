# API and Boundary Contracts

This document defines interface contracts used by the architecture in `docs/manifest/01_architecture.md`.

## Contract Index

- CLI contracts: `CLI-*`
- Python API contracts: `API-*`
- Workflow orchestration contracts: `FLOW-*`
- Agentic contracts: `AGENT-*`
- Persistence/run-event contracts: `EVENT-*`

## CLI Contracts

| Contract ID | Entry Command | Boundary | Contract (Inputs -> Outputs) | Evidence |
| --- | --- | --- | --- | --- |
| `CLI-01` | `python3 -m src.interfaces.cli preflight [args]` | User -> orchestrator | CLI args -> Prefect `preflight_flow` result dict and refreshed artifacts | `src/interfaces/cli.py`, `src/platform/workflows/prefect_orchestration.py` |
| `CLI-02` | `python3 -m src.interfaces.cli market-data [args]` | User -> market workflow | CLI args -> market tables/official metrics updates | `src/interfaces/cli.py`, `src/market/workflows/market_data.py` |
| `CLI-03` | `python3 -m src.interfaces.cli build-index [args]` | User -> retrieval index workflow | CLI args -> indexed count + LanceDB/metadata update | `src/interfaces/cli.py`, `src/valuation/workflows/indexing.py` |
| `CLI-04` | `python3 -m src.interfaces.cli train [args]` | User -> training workflow | CLI args -> model artifacts under `models/` | `src/interfaces/cli.py`, `src/ml/training/train.py` |
| `CLI-05` | `python3 -m src.interfaces.cli backfill [args]` | User -> valuation workflow | CLI args -> persisted valuation rows (`valuations`) | `src/interfaces/cli.py`, `src/valuation/workflows/backfill.py` |
| `CLI-06` | `python3 -m src.interfaces.cli dashboard [--skip-preflight]` | User -> dashboard | optional preflight + Streamlit UI on port 8501 | `src/interfaces/cli.py`, `src/interfaces/dashboard/app.py` |
| `CLI-07` | `python3 -m src.interfaces.cli agent "<query>" "<area>"` | User -> agentic orchestration | query/areas -> final report + evaluations + run memory | `src/interfaces/cli.py`, `src/interfaces/agent.py`, `src/agentic/orchestrator.py` |

## Python API Contracts (`PipelineAPI`)

| Contract ID | Method | Input Contract | Output Contract | Evidence |
| --- | --- | --- | --- | --- |
| `API-01` | `PipelineAPI.preflight(**kwargs)` | optional policy/path kwargs | dict with preflight state/steps | `src/interfaces/api/pipeline.py`, `src/platform/workflows/prefect_orchestration.py` |
| `API-02` | `PipelineAPI.crawl_backfill(...)` | source/url/listing args + flags | `List[Dict[str, Any]]` crawl result payloads | `src/interfaces/api/pipeline.py`, `src/listings/workflows/unified_crawl.py` |
| `API-03` | `PipelineAPI.build_market_data(**kwargs)` | optional db/workflow flags | side-effect workflow completion (None) | `src/interfaces/api/pipeline.py`, `src/market/workflows/market_data.py` |
| `API-04` | `PipelineAPI.build_vector_index(**kwargs)` | db/index parameters | integer indexed count | `src/interfaces/api/pipeline.py`, `src/valuation/workflows/indexing.py` |
| `API-05` | `PipelineAPI.train_model(**kwargs)` | training kwargs | list/dict training payload | `src/interfaces/api/pipeline.py`, `src/ml/training/train.py` |
| `API-06` | `PipelineAPI.evaluate_listing(...)` | `CanonicalListing`/`DBListing`/dict | `DealAnalysis` | `src/interfaces/api/pipeline.py`, `src/platform/domain/schema.py`, `src/valuation/services/valuation.py` |
| `API-07` | `PipelineAPI.evaluate_listing_id(id, ...)` | listing id | `DealAnalysis` | `src/interfaces/api/pipeline.py` |
| `API-08` | `PipelineAPI.source_support_summary(...)` | optional crawler-status path override | source-level `supported|blocked|experimental` labels + counts | `src/interfaces/api/pipeline.py`, `docs/crawler_status.md`, `config/sources.yaml` |
| `API-09` | `PipelineAPI.pipeline_status(...)` | optional crawler-status path override | pipeline freshness snapshot + `source_support` + `assumption_badges` payloads | `src/interfaces/api/pipeline.py`, `src/platform/pipeline/state.py`, `src/interfaces/dashboard/services/loaders.py` |
| `API-10` | `PipelineAPI.assumption_badges(...)` | normalized `source_support` payload | artifact-backed assumption badges (`id`, `label`, `status`, `artifact_ids`, `summary`, `guide_path`) | `src/interfaces/api/pipeline.py`, `docs/implementation/checklists/08_artifact_feature_alignment.md`, `docs/implementation/reports/artifact_feature_alignment.md` |
| `API-11` | `ReportingService.pipeline_trust_summary()` | none | aggregated analyst trust digest (`freshness`, `source_summary`, `top_blockers`, `benchmark_gate`, `jobs_summary`, `latest_quality_events`, `details_available`) | `src/application/reporting.py`, `src/application/pipeline.py`, `src/adapters/http/app.py` |
| `API-12` | `ReportingService.record_ui_event(payload)` | `event_name`, `route`, optional subject fields, context, `occurred_at` | accepted event id + status | `src/application/reporting.py`, `src/adapters/http/app.py`, `src/adapters/http/schemas.py` |

## Workflow Orchestration Contracts (Prefect)

| Contract ID | Flow | Input Contract | Output Contract | Evidence |
| --- | --- | --- | --- | --- |
| `FLOW-01` | `preflight_flow` | refresh policy + step skip flags | dict: `initial_state`, `steps`, `final_state` | `src/platform/workflows/prefect_orchestration.py` |
| `FLOW-02` | `market_data_flow` | db/skip flags + optional transactions | dict with status markers (`market_data`, `transactions`) | `src/platform/workflows/prefect_orchestration.py` |
| `FLOW-03` | `build_index_flow` | db/index/model args | dict with indexed result payload | `src/platform/workflows/prefect_orchestration.py` |
| `FLOW-04` | `training_flow` | epochs/device/VLM args | dict summarizing `vlm` and `train` statuses | `src/platform/workflows/prefect_orchestration.py` |
| `FLOW-05` | `valuation_backfill_flow` | db/city/type/age filters | dict: processed count | `src/platform/workflows/prefect_orchestration.py` |
| `FLOW-06` | `transactions_flow` | file path + defaults | dict with ingestion result | `src/platform/workflows/prefect_orchestration.py` |

## Agentic Contracts

| Contract ID | Boundary | Input Contract | Output Contract | Evidence |
| --- | --- | --- | --- | --- |
| `AGENT-01` | `CognitiveOrchestrator.run` | `query`, non-empty `areas`, optional `plan`, `strategy` | dict including `final_report`, `evaluations`, `messages`, `run_id`, optional `error` | `src/agentic/orchestrator.py` |
| `AGENT-02` | Agent memory persistence | run payload fields (`query`, `plan`, counts, ids) | row in `agent_runs` table | `src/agentic/memory.py`, `src/platform/domain/models.py` |
| `AGENT-03` | Agent tool boundary | typed tool inputs (`CrawlInput`, `EvaluateInput`, etc.) | tool-specific structured payload for graph nodes | `src/agentic/tools.py` |

## Persistence and Event Contracts

| Contract ID | Surface | Contract | Evidence |
| --- | --- | --- | --- |
| `EVENT-01` | `pipeline_runs` | `(run_id, run_type, step_name, status, started_at, completed_at, metadata)` | `src/platform/pipeline/repositories/pipeline_runs.py` |
| `EVENT-02` | `agent_runs` | persisted cognitive run summary and trace pointers | `src/platform/domain/models.py`, `src/agentic/memory.py` |
| `EVENT-03` | `valuations` | valuation snapshot tied to listing id + model version + evidence JSON | `src/platform/domain/models.py`, `src/valuation/services/valuation_persister.py` |
| `EVENT-04` | `ui_events` | persisted analyst interaction events (`event_name`, `route`, `subject_type`, `subject_id`, `context`, `occurred_at`) | `src/platform/domain/models.py`, `src/platform/migrations.py`, `src/application/reporting.py` |

## Domain Data Contracts

- `CanonicalListing` is the normalized listing boundary across listings/valuation interfaces.
- `DealAnalysis` is the output boundary for valuation and agentic explanation.
- `EvidencePack` and `CompEvidence` define interpretable valuation evidence payloads.

Evidence: `src/platform/domain/schema.py`.

## Failure and Compatibility Contracts

- `CognitiveOrchestrator.run` requires `areas`; missing areas raise `ValueError("areas_required")`.
- Retrieval strict mode can reject stale/mismatched metadata (`retrieval_model_mismatch`, version mismatch).
- Backfill/valuation workflows skip failed listings and continue remaining workload.
- CLI surface is passthrough-based; command naming changes must preserve module map compatibility.

Evidence: `src/agentic/orchestrator.py`, `src/valuation/services/retrieval.py`, `src/valuation/workflows/backfill.py`, `src/interfaces/cli.py`.
