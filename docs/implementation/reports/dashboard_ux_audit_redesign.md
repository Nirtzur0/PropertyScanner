# V3 implementation update (2026-03-11)

- The live product has since been pruned beyond this original V2 audit packet.
- Current route truth is now:
  - primary nav: `Workbench`, `Decisions`, `Pipeline`
  - `Decisions` tabs: `Watchlists`, `Memos`
  - `/command-center` no longer exists as a product surface and now redirects to `/pipeline`
  - `/pipeline` now leads with `GET /api/v1/pipeline/trust-summary`
  - analyst interaction instrumentation now persists through `POST /api/v1/ui-events`
- The repo-owned design source under `design/figma_redesign/*` has been updated to match the V3 prune.
- Figma re-sync is only partially complete for V3:
  - new workbench V3 import: `35:2`
  - remaining V3 imports are blocked until the Figma MCP seat/tool-call limit resets

# 1. Executive verdict

Property Scanner already had the beginnings of a premium analytical product language, but the live React product was not yet behaving like a coherent decision tool. The old state over-indexed on showing listings and under-indexed on showing readiness, degraded trust, missing data, and the next correct workflow step. The result was visually promising but operationally misleading.

The redesign direction is to keep the warm editorial system, keep map-first exploration, and become much stricter about hierarchy:

- `Workbench` leads with `actionable`, `degraded`, `needs data`, and `next drill-down`.
- `Listing detail` becomes a real dossier instead of a generic detail card.
- `Comp review` becomes a controlled analyst surface instead of a placeholder.
- `Decision memory` is merged into one hub instead of splitting watchlists and memos.
- `Pipeline` becomes the product trust surface.
- `Command Center` stays read-mostly and explicit about what is not yet persisted.

Canonical targets:

- React routes: `/workbench`, `/listings/:listingId`, `/comp-reviews/:listingId`, `/watchlists`, `/pipeline`, `/command-center`
- Redirect: `/memos -> /watchlists?tab=memos`
- Figma file: `In3GpOiXHDFAwGWIUkC9lP`
- Repo-tracked design source: `design/figma_redesign/*`

# 2. What is working

- The visual language was already stronger than a typical builder-made dashboard. The warm stone palette, serif hierarchy, and restrained editorial tone are worth preserving.
- The map-first workbench concept is correct for this product. Geography is part of the thinking model, not decoration.
- The backend already had real primitives for watchlists, saved searches, memos, comp reviews, data-quality events, coverage reports, and source contract runs.
- The pipeline/source-trust domain model was already richer than the UI exposed.
- Existing Figma nodes `6:2` to `11:2` established a good direction for a premium multi-surface product rather than a single overloaded dashboard.

# 3. What is not working

- The first-use experience was weak. The live product did not immediately answer whether the current corpus was actually actionable.
- Watchlists and memos were split into separate primary-nav destinations even though they are both decision-memory surfaces.
- Listing detail was too generic. It did not behave like a dossier with evidence, provenance, source health, and explicit missing-data states.
- Comp review was not a workbench. It was effectively persistence without a meaningful analyst workflow.
- Pipeline information existed, but the screen hierarchy did not frame it as a trust gate before downstream decision-making.
- Command Center risked implying a conversational product that the persistence model does not currently support.

# 4. UX/UI anti-patterns found

- Showing a dense listing surface without foregrounding readiness is an anti-pattern for an operational intelligence product.
- Splitting `Watchlists` and `Memos` at top-level nav creates duplicate decision-memory surfaces.
- Treating missing valuation support as a secondary note instead of a first-class state increases false confidence.
- Generic detail cards hide the actual reasons a user should trust or distrust a listing.
- Placeholder comp-review UI encourages a multi-surface workflow without giving users one real place to make the decision.
- Command-center history without durable message persistence would be fake memory.

# 5. Information design critique

- The old structure mixed exploration, decision memory, and operations too loosely.
- The product needed a cleaner distinction between:
  - overview and triage,
  - dossier and investigation,
  - decision memory,
  - operational trust,
  - guarded advisory context.
- The main IA decision is now:
  - `Workbench`
  - `Decisions`
  - `Pipeline`
  - `Command Center`
- `Memos` should not remain a separate primary destination. They are one mode inside `Decisions`.

# 6. Dashboard/data-presentation critique

- The product was under-aggregated. Too much of the burden sat on raw listings rather than summary states.
- The first viewport needed to answer:
  - how many listings are actionable,
  - how many are degraded,
  - how many still need data,
  - which listing should be reviewed next.
- Tables were useful, but the product leaned too hard on them as the primary comprehension layer.
- Source health, valuation availability, and comp sufficiency needed to be elevated above raw listing volume.
- Alerts and trust events belonged closer to decision workflows, not as disconnected operational trivia.

# 7. Redesign principles

- Overview first, detail on demand.
- Trust before optimism.
- Elegant aggregation before raw listing volume.
- Fewer surfaces, each with a clearer job.
- Strong visual hierarchy with calm density.
- Explicit degraded and missing-data states.
- One reusable component system across workbench, dossier, decisions, pipeline, and command center.
- Desktop-first with honest mobile/tablet scope.

# 8. Proposed new information architecture

- `Workbench`
  - Truth strip
  - Lens builder
  - Map module
  - Review queue
  - Selection basket
  - Active dossier rail
- `Listing dossier`
  - Value moment
  - Source health
  - Media ribbon
  - Evidence ladder
  - Market context
  - Provenance and activity
  - Decision hooks
- `Comp workbench`
  - Candidate pool
  - Pinned/rejected sets
  - Adjustment matrix
  - Delta preview
  - Override log
  - Publish-to-memo gate
- `Decisions`
  - Watchlists
  - Saved searches
  - Memos
  - Alerts
- `Pipeline`
  - Job deck
  - Source capability board
  - Benchmark gate
  - Coverage report
  - Quality-event stream
- `Command Center`
  - Briefing
  - Suggested action
  - Confirmation drawer
  - Recent execution context

# 9. Proposed screen set

- `Workbench` overview: `/workbench`
- `Listing dossier`: `/listings/:listingId`
- `Comp workbench`: `/comp-reviews/:listingId`
- `Decision hub`: `/watchlists`
- `Memo deep-link redirect`: `/memos -> /watchlists?tab=memos`
- `Pipeline trust surface`: `/pipeline`
- `Command Center`: `/command-center`
- Tablet/mobile triage views:
  - workbench summary,
  - decision review,
  - pipeline monitoring

# 10. Proposed component system

- App shell with primary nav and status tray
- Truth strip / KPI strip
- Lens builder
- Map card with legend and hover card
- Review queue cards
- Selection basket table
- Active dossier rail
- Source health card
- Media ribbon
- Evidence ladder card
- Provenance timeline
- Decision tabs
- Candidate comp table
- Adjustment cards
- Delta preview cards
- Guardrail/confirmation drawer
- Explicit empty/loading/error/degraded cards

# 11. Interaction model

- Filtering updates the workbench lens and keeps map, queue, and basket synchronized.
- Multi-select remains shift/meta-click based in the workbench.
- Dossier drill-down is explicit from the workbench rail or basket.
- Comp-review save creates a persisted draft review record; it is not ephemeral local state only.
- Memo publication stays explicit from comp review or workbench.
- Decision hub uses tabs instead of fragmenting primary navigation.
- Command Center requires explicit review acknowledgement before any future mutation workflow.

# 12. Visual design direction

- Typography:
  - `Fraunces` for product-level hierarchy and value moments
  - `IBM Plex Sans` for interface copy
  - `IBM Plex Mono` for operational/status language
- Color roles:
  - calm canvas and surface neutrals for the base
  - dark slate/teal for instrument zones
  - terracotta for actions and emphasis
  - amber for degraded/caution
  - green for trusted/healthy states
  - red for blocked/error
- Density:
  - information-dense but never flat
  - cards should still read as grouped modules, not spreadsheet fragments
- Motion:
  - keep restrained panel transitions and map/table synchronization

# 13. States and edge cases

- Every major screen must render:
  - loading
  - empty
  - degraded
  - error
- Major cases now surfaced explicitly:
  - missing required valuation fields
  - insufficient comps
  - missing imagery
  - missing description
  - stale or degraded source health
  - no benchmark runs
  - no coverage report
  - no advisory history
- Command Center intentionally does not fake chat history when no message persistence exists.

# 14. Accessibility review

- Preserve high-contrast typography and clear semantic color roles.
- Status is never color-only; labels remain visible.
- Buttons and nav chips keep consistent shapes and hover/focus affordances.
- Dense table surfaces still keep readable column spacing.
- Responsive scope is explicit instead of pretending full desktop parity on mobile.
- Map remains supplemental to the truth strip and basket, so the first-use experience does not rely only on spatial interpretation.

# 15. Figma file structure recommendation

- Keep existing file `In3GpOiXHDFAwGWIUkC9lP`.
- Preserve existing nodes `6:2` to `11:2`.
- The synced V2 captures now exist in the same file as top-level nodes:
  - `26:2` `00 Foundations`
  - `27:2` `10 Workbench V2`
  - `28:2` `11 Listing Dossier V2`
  - `29:2` `12 Comp Workbench V2`
  - `30:2` `13 Decision Hub V2`
  - `31:2` `14 Pipeline Trust Surface V2`
  - `34:2` `15 Command Center V2`
- Repo-tracked source remains `design/figma_redesign`.
- Figma MCP sync completed on 2026-03-11 into file `In3GpOiXHDFAwGWIUkC9lP`; the import preserved legacy nodes `6:2` to `11:2` and landed the V2 designs as top-level nodes rather than a separate page set.

# 16. Implementation-aware handoff for Codex

## Screen contracts

### Workbench

- Purpose: triage the corpus truthfully before the user drills into any listing.
- User goal: know what is actionable, what is degraded, and what to review next.
- Main content blocks:
  - truth strip
  - lens builder
  - review queue
  - map
  - selection basket
  - active dossier rail
- Primary actions:
  - save basket to decisions
  - draft memo
  - start comp review
  - run valuation
  - open dossier
- States:
  - no actionable listings
  - degraded-heavy corpus
  - empty lens
- Data dependencies:
  - `GET /api/v1/workbench/explore`
  - `GET /api/v1/workbench/layers`
  - `GET /api/v1/workbench/listings/{listingId}/context`
- Reusable components:
  - truth strip
  - queue card
  - basket table
  - dossier rail

### Listing dossier

- Purpose: turn a listing into an evidence-backed decision object.
- User goal: understand value, trust, provenance, and next action without stitching data together mentally.
- Main content blocks:
  - value moment
  - source health
  - media ribbon
  - evidence ladder
  - market context
  - provenance and activity
  - decision hooks
- Primary actions:
  - run valuation
  - open comp review
  - open decisions
- States:
  - no valuation evidence
  - missing imagery
  - degraded source
- Data dependencies:
  - `GET /api/v1/workbench/listings/{listingId}/context`
- Reusable components:
  - source health card
  - evidence ladder
  - provenance timeline
  - data-gap cards

### Comp workbench

- Purpose: give analysts one real place to curate comps and record overrides.
- User goal: retain/reject comps, capture assumptions, and publish to memo with guardrails.
- Main content blocks:
  - candidate pool
  - adjustment matrix
  - delta preview
  - override log
  - memo publication gate
- Primary actions:
  - pin comp
  - reject comp
  - save review
  - publish to memo
- States:
  - no candidate pool because the listing lacks valuation prerequisites
  - insufficient retained comps
- Data dependencies:
  - `GET /api/v1/comp-reviews/{listingId}/workspace`
  - `POST /api/v1/comp-reviews`
  - `POST /api/v1/memos`
- Reusable components:
  - comp candidate table
  - adjustment cards
  - guardrail cards

### Decision hub

- Purpose: unify watchlists, searches, memo outputs, and alerts.
- User goal: manage decision memory in one place.
- Main content blocks:
  - watchlist board
  - saved search list
  - memo queue
  - trust alerts
- Primary actions:
  - switch tab
  - export memo
  - open originating workflow
- States:
  - no watchlists
  - no memos
  - no alerts
- Data dependencies:
  - `GET /api/v1/watchlists`
  - `GET /api/v1/saved-searches`
  - `GET /api/v1/memos`
  - `GET /api/v1/data-quality-events`
- Reusable components:
  - tab strip
  - list card
  - export panel

### Pipeline trust surface

- Purpose: show whether downstream decision screens should be trusted.
- User goal: inspect jobs, source health, benchmarks, coverage, and quality events quickly.
- Main content blocks:
  - truth strip
  - job deck
  - source capability board
  - benchmark gate
  - coverage report
  - quality stream
- Primary actions:
  - inspect recent run context
  - review degraded sources
- States:
  - no benchmark runs
  - no coverage data
  - no jobs
- Data dependencies:
  - `GET /api/v1/pipeline-status`
  - `GET /api/v1/sources`
  - `GET /api/v1/job-runs`
  - `GET /api/v1/benchmarks`
  - `GET /api/v1/coverage-reports`
  - `GET /api/v1/data-quality-events`
  - `GET /api/v1/source-contract-runs`

### Command Center

- Purpose: keep advisory context truthful and guarded.
- User goal: review briefing context and understand what still requires operator approval.
- Main content blocks:
  - briefing list
  - suggested action card
  - confirmation drawer
  - recent execution list
- Primary actions:
  - review
  - acknowledge readiness for operator handoff
- States:
  - no advisory runs
  - no persisted action queue
- Data dependencies:
  - `GET /api/v1/command-center/runs`
  - `GET /api/v1/job-runs`
  - `GET /api/v1/pipeline-status`

## Route structure

- `/workbench`
- `/listings/:listingId`
- `/comp-reviews/:listingId`
- `/watchlists`
- `/watchlists?tab=watchlists|searches|memos|alerts`
- `/memos -> /watchlists?tab=memos`
- `/pipeline`
- `/command-center`

## Component hierarchy

- `AppChrome`
  - `StatusTray`
  - `GlobalNav`
  - route screens
- `WorkbenchPage`
  - `OverviewStrip`
  - `WorkbenchMap`
  - `QueueCard`
  - `SelectionBasket`
  - `ActiveDossierRail`
- `ListingPage`
  - `ValueMoment`
  - `SourceHealthCard`
  - `MediaRibbon`
  - `EvidenceLadder`
  - `ProvenanceTimeline`
- `CompReviewPage`
  - `CandidatePoolTable`
  - `AdjustmentMatrix`
  - `DeltaPreview`
  - `OverrideLog`
- `DecisionsPage`
  - `DecisionTabs`
  - `MemoExportCard`
- `PipelinePage`
  - `JobDeck`
  - `SourceCapabilityBoard`
  - `BenchmarkGateCard`
  - `CoverageList`
  - `QualityStream`
- `CommandCenterPage`
  - `BriefingList`
  - `SuggestedActionCard`
  - `ConfirmationDrawer`

## Design-system foundation

- Token source:
  - `frontend/src/index.css`
  - `frontend/src/styles.css`
  - `design/figma_redesign/styles.css`
- Core tokens already in use:
  - `--bg`, `--surface`, `--surface-dark`, `--text`, `--accent`, `--teal`, `--gold`, `--green`, `--red`
  - radii: `12 / 18 / 24 / 32`
  - shadow tiers: `shadow`, `shadow-tight`

# 17. Prioritized roadmap

1. Fix hierarchy first.
   Result: users immediately understand readiness, degradation, and next steps.

2. Keep `Decisions` merged.
   Result: fewer duplicated surfaces, stronger information scent, better memo/watchlist coherence.

3. Preserve dossier parity.
   Result: listing pages stop being generic detail cards and become actual decision surfaces.

4. Keep comp review as a real workbench.
   Result: analysts can make and persist judgment in one place instead of bouncing between placeholder routes.

5. Treat pipeline as a trust gate.
   Result: downstream UI stops implying confidence when upstream data quality is poor.

6. Keep command-center persistence honest.
   Result: the UI does not claim chat/memory behavior the backend does not support.
