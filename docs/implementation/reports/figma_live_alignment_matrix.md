# Figma-to-Live Alignment Matrix

Date: 2026-03-10

Figma source of truth:
- File key: `In3GpOiXHDFAwGWIUkC9lP`
- Workbench: `6:2`
- Listing Detail: `7:2`
- Comp Workbench: `8:2`
- Memo + Watchlists: `9:2`
- Pipeline + Source Health: `10:2`
- Command Center: `11:2`

Runtime evidence used:
- live API on `http://127.0.0.1:8001`
- live dashboard on `http://127.0.0.1:8501`
- repo UI verification loop: `tests/e2e/ui/test_dashboard_ui_verification_loop.py`

Status vocabulary:
- `implemented`: backed by live API/runtime and no placeholder dependency
- `partial`: some live contract exists, but route/UI parity or full behavior is missing
- `blocked-by-data`: surface exists but truthful population is limited by current runtime data
- `missing`: no live surface or contract

| Figma screen | Feature | Live surface | Real data source | Status | Fix owner | Blocking dependency |
| --- | --- | --- | --- | --- | --- | --- |
| `6:2` Workbench | listing corpus and ranking inputs | `GET /listings`, Streamlit deal flow | `listings` table | implemented | UI | none |
| `6:2` Workbench | map and table sync | Streamlit map + table | listing `location.lat/lon` | partial | UI | multi-route redesign not implemented |
| `6:2` Workbench | explainable ranking | Streamlit reasons/intel summary | persisted valuations + listing signals | partial | UI | ranking logic not yet surfaced like Figma |
| `6:2` Workbench | saved views | `GET/POST /saved-searches` | `saved_searches` table | partial | UI | no live route in dashboard |
| `6:2` Workbench | watchlist actions | `GET/POST /watchlists` | `watchlists` table | partial | UI | no live route in dashboard |
| `6:2` Workbench | persistent job tray | `GET /job-runs` | `job_runs` table | partial | UI | no visible tray in dashboard |
| `6:2` Workbench | notification center | pipeline/source badges only | `pipeline-status`, `sources` | partial | UI | dedicated notification surface missing |
| `7:2` Listing Detail | canonical dossier | `GET /listings/{id}` | `listings` table | implemented | UI | no dedicated route yet |
| `7:2` Listing Detail | fair value summary | `POST /valuations` | comparable baseline valuation | implemented | UI | no dedicated route yet |
| `7:2` Listing Detail | insufficiency handling | `POST /valuations` returns `422` structured detail | valuation service errors | implemented | Backend/UI | none |
| `7:2` Listing Detail | evidence ladder | valuation evidence payload | baseline comps/evidence | partial | UI | Figma-grade evidence layout missing |
| `7:2` Listing Detail | source provenance and activity | `GET /source-contract-runs`, `GET /data-quality-events` | `source_contract_runs`, `data_quality_events` | partial | UI | listing-scoped provenance timeline missing |
| `7:2` Listing Detail | memo hooks | `GET/POST /memos`, `POST /memos/{id}/export` | `memos` table | partial | UI | no listing detail route |
| `8:2` Comp Workbench | comp review persistence | `GET/POST /comp-reviews` | `comp_reviews` table | implemented | UI | dedicated workbench route missing |
| `8:2` Comp Workbench | pin/reject/override actions | `POST /comp-reviews` | selected/rejected/override fields | implemented | UI | no live review interface |
| `8:2` Comp Workbench | valuation impact visibility | valuation + comp review can coexist | `valuations`, `comp_reviews` | partial | Backend/UI | no derived adjusted-value view yet |
| `9:2` Memo + Watchlists | memo list/detail | `GET/POST /memos`, `GET /memos/{id}` | `memos` table | implemented | UI | no route in dashboard |
| `9:2` Memo + Watchlists | memo export | `POST /memos/{id}/export` | memo sections/assumptions/risks | implemented | UI | export is API-only today |
| `9:2` Memo + Watchlists | watchlist board | `GET/POST /watchlists` | `watchlists` table | implemented | UI | live route missing |
| `9:2` Memo + Watchlists | saved searches | `GET/POST /saved-searches` | `saved_searches` table | implemented | UI | live route missing |
| `10:2` Pipeline + Source Health | source capability board | `GET /sources`, `GET /source-contract-runs` | source audits | implemented | UI | none |
| `10:2` Pipeline + Source Health | data quality event stream | `GET /data-quality-events` | `data_quality_events` | implemented | UI | none |
| `10:2` Pipeline + Source Health | recent jobs | `GET /job-runs` | `job_runs` | implemented | UI | none |
| `10:2` Pipeline + Source Health | benchmark gate report | `GET /benchmarks` | `benchmark_runs` | blocked-by-data | Ops/Backend | live DB has `0` benchmark runs |
| `10:2` Pipeline + Source Health | coverage report | `GET /coverage-reports` | `coverage_reports` | implemented | UI | none |
| `10:2` Pipeline + Source Health | truthful support labels | `GET /sources`, `GET /pipeline-status` | source/model readiness | implemented | UI | none |
| `11:2` Command Center | advisory run history | `GET /command-center/runs` | `agent_runs` | implemented | UI | none |
| `11:2` Command Center | explicit action confirmation | existing Streamlit approval loop | agent plan review | partial | UI | dedicated route missing |
| `11:2` Command Center | message history | run summary only | `agent_runs.summary`, `agent_runs.plan` | partial | Backend/UI | message-level persistence absent |

## Observed runtime constraints

- Live API now returns structured valuation insufficiency instead of `500`:
  - `target_surface_area_required`
  - `insufficient_comps`
- Live DB-backed operational data exists:
  - `coverage_reports=4`
  - `source_contract_runs=40`
  - `data_quality_events=94`
- Live DB still lacks some truth surfaces expected by the design:
  - `job_runs=1`
  - `benchmark_runs=0`
- Source trust remains weak in the real DB:
  - `supported=0`
  - `degraded=1`
  - `blocked=11`
  - `experimental=8`

## Immediate follow-up defects

1. Build actual routes/views for watchlists, saved searches, memos, comp workbench, and pipeline surfaces instead of leaving the new contracts API-only.
2. Add listing-scoped provenance aggregation so Listing Detail can render the Figma activity rail truthfully.
3. Persist command-center messages if the Figma conversation/history panel stays in scope.
4. Generate at least one benchmark run in the live DB before claiming the benchmark gate panel is populated.
