# Figma-to-Live Alignment Matrix

Date: 2026-03-11

Figma source of truth:

- File key: `In3GpOiXHDFAwGWIUkC9lP`
- Existing preserved legacy nodes:
  - Workbench: `6:2`
  - Listing Detail: `7:2`
  - Comp Workbench: `8:2`
  - Memo + Watchlists: `9:2`
  - Pipeline + Source Health: `10:2`
  - Command Center: `11:2`
- Synced V2 nodes:
  - Foundations: `26:2`
  - Workbench: `27:2`
  - Listing Dossier: `28:2`
  - Comp Workbench: `29:2`
  - Decision Hub: `30:2`
  - Pipeline Trust Surface: `31:2`
  - Command Center: `34:2`
- V3 sync progress:
  - Workbench V3: `35:2`
  - Remaining V3 pages: blocked pending a Figma MCP seat/tool-call reset
- Repo-owned V3 design source:
  - `design/figma_redesign/index.html`
  - `design/figma_redesign/workbench.html`
  - `design/figma_redesign/listing-detail.html`
  - `design/figma_redesign/comp-workbench.html`
  - `design/figma_redesign/memo-watchlists.html`
  - `design/figma_redesign/pipeline-health.html`
  - `design/figma_redesign/command-center.html`

Figma sync note:

- On 2026-03-11 the repo-owned V2 prototypes were synced into the existing file via Figma MCP `existingFile` capture.
- The sync preserved legacy nodes `6:2` through `11:2`.
- MCP imported the V2 designs as top-level nodes in the file rather than a distinct page set.
- `34:2` is the canonical command-center capture after the copy-alignment recapture; `32:2` and `33:2` remain as superseded imports.
- A follow-up V3 sync started on 2026-03-11 and successfully imported the new workbench as `35:2`.
- The next attempted V3 listing-dossier capture (`e64f3b34-5370-4f10-a959-b9a951a8743a`) was blocked when Figma MCP returned the same seat/tool-call-limit error again, so the remaining V3 pages are still pending sync.

Runtime evidence used:

- FastAPI + React workbench on local runtime
- API contract verification in `tests/unit/adapters/http/test_fastapi_local_api.py`
- React route smoke in `tests/e2e/ui/test_react_dashboard_routes.py`

Status vocabulary:

- `implemented`: live route and backing contract exist
- `partial`: route exists, but part of the intended Figma behavior is still deferred
- `blocked-by-data`: route exists, but truthful population depends on runtime data not always present
- `deferred`: intentionally not in current scope

| Figma screen | V3 target | React route | Real data source | Status | V3 target closure | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `35:2` Workbench | truth strip, compact default lens, shortlist, basket, slim dossier rail | `/workbench` | `GET /api/v1/workbench/explore`, `GET /api/v1/workbench/layers`, `GET /api/v1/workbench/listings/{id}/context`, `POST /api/v1/ui-events` | implemented | closed | V3 workbench is the only fully re-synced Figma page from this pass |
| `28:2` Listing Dossier | trust-first dossier with merged trust/provenance and lighter market context | `/listings/:listingId` | `GET /api/v1/workbench/listings/{id}/context`, `POST /api/v1/ui-events` | implemented | open in Figma | live route matches V3 behavior, but the shared Figma file still points at the older V2 capture until MCP sync resumes |
| `29:2` Comp Workbench | candidate pool, top summary impact, disclosed override history | `/comp-reviews/:listingId` | `GET /api/v1/comp-reviews/{id}/workspace`, `POST /api/v1/comp-reviews`, `POST /api/v1/memos`, `POST /api/v1/ui-events` | implemented | open in Figma | live route reflects V3 simplification; Figma still needs the refreshed import |
| `30:2` Decision Hub | watchlists + memos only | `/watchlists` | `GET /api/v1/watchlists`, `GET /api/v1/memos` | implemented | open in Figma | `/memos` redirects to the memo tab; saved searches stay near the workbench lens instead of this route |
| `31:2` Pipeline Trust Surface | freshness, top blockers, source summary, benchmark gate, lower-level ops behind disclosure | `/pipeline` | `GET /api/v1/pipeline/trust-summary`, `GET /api/v1/coverage-reports`, `GET /api/v1/source-contract-runs`, `POST /api/v1/ui-events` | implemented | open in Figma | live page now uses the aggregate trust-summary contract and tracks blocker openings |
| `34:2` Command Center V2 | superseded legacy V2 advisory surface | `/command-center` | redirect -> `/pipeline`, `POST /api/v1/ui-events` | deferred | superseded | V3 removes this destination; repo-owned `design/figma_redesign/command-center.html` is now a deprecation frame but the refreshed capture is blocked by MCP limits |

## Route closure summary

- Closed:
  - workbench hierarchy
  - dossier parity
  - comp-review workspace
  - decision-hub simplification
  - pipeline trust surface + aggregate API
  - command-center route removal with compatibility redirect
- Partial:
  - V3 Figma re-sync beyond workbench
- Deferred:
  - full mobile parity for map and comp-review desktop workflows
  - physical cleanup of superseded imported Figma nodes

## Remaining gaps

1. Resume the V3 Figma sync for listing dossier, comp workbench, decisions, pipeline, and the command-center removal frame once the Figma seat/tool-call limit resets.
2. Add richer benchmark population in the live DB if the benchmark gate needs example-filled states in demos.
3. Optionally clean up or regroup superseded imports (`32:2`, `33:2`, older V2 captures) inside Figma if file hygiene matters.
