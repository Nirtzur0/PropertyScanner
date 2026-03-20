# Prompt Execution Plan

- Generated: `2026-03-11`
- Prompt pack source: `prompts` submodule @ `63d6ac94e91b4e303caa895e394176b8d6c6fd15`
- Target repo: `/Users/nirtzur/Documents/projects/property_scanner`
- Objective anchor: `docs/manifest/00_overview.md#Core Objective`

## Current Route

- Active route: `Dashboard V3 simplification -> contract support -> partial Figma resync -> UI verification`
- Active packet: `dashboard V3 prune`
- Evidence:
  - canonical product surface is now the FastAPI-served React workbench, not the deprecated Streamlit dashboard
  - the follow-up V3 packet prunes the live IA to three primary destinations and removes Command Center as a product surface
  - lightweight backend support now exists for `GET /api/v1/pipeline/trust-summary` and `POST /api/v1/ui-events`
  - repo-owned HTML prototypes were updated for V3, but the second Figma MCP sync pass is only partially complete because the seat/tool-call limit re-blocked the import after the new Workbench capture

## Inferred Cycle Stage + Key Signals

- Inferred cycle stage: `Build`
- Legacy phase signal: `phase_3`
- Reasoning:
  - Current alignment gate says `ALIGNED_WITH_RISKS` and routes to implementation packet `M6` (`docs/implementation/checklists/07_alignment_review.md`).
  - Active milestone has one medium implementation packet open: `M6` (`docs/implementation/checklists/02_milestones.md`).
  - Open improvement bet is implementation-facing (`IB-06`) and mapped to runtime/UI surfaces (`docs/implementation/checklists/03_improvement_bets.md`).
  - Release packet remains open but is downstream of current reliability/trust packet (`docs/implementation/checklists/06_release_readiness.md`).
  - Core objective and docs system are already established (`docs/manifest/00_overview.md`, `docs/.prompt_system.yml`).

## Cadence Assumption

- `build_window`: `6 weeks`
- `cooldown_window`: `2 weeks`
- Why this default holds: no repo evidence currently indicates a different cadence policy, and this packet is a bounded reliability/trust slice rather than a new shaping cycle.

## Finalist Betting Table

| Prompt ID | Why now | Appetite | Decision |
| --- | --- | --- | --- |
| `prompt-02-app-development-playbook` | `M10` follow-through requires code + docs execution across the pruned IA, trust-summary contract, and instrumentation surfaces. | `medium` | `Immediate #1` |
| `prompt-06-ui-e2e-verification-loop` | The V3 prune needs browser evidence for the reduced nav, command-center redirect, and simplified Decisions/Pipeline flows. | `medium` | `Immediate #2` |
| `prompt-03-alignment-review-gate` | Needed immediately after the V3 prune to confirm Figma/live drift and record the MCP sync blocker truthfully. | `small` | `Immediate #3` |
| `prompt-15-artifact-feature-alignment-gate` | `O-04` (assumption badges) is open but should follow `M6` runtime/UI trust baseline. | `small` | `Deferred / Not now` |
| `prompt-11-docs-diataxis-release` | Release-readiness checklist is open, but should not preempt active build packet risks. | `small` | `Deferred / Not now` |
| `prompt-10-tests-stabilization-loop` | Use only if `M6` introduces failing/flaky tests; no current failure signal requires it first. | `small` | `Deferred / Conditional` |
| `prompt-14-improvement-direction-bet-loop` | Re-bet directions after `M6` closes to avoid planning on stale runtime/UI assumptions. | `small` | `Exploration later` |

## Selected Immediate Prompt IDs (Ordered)

1. `prompt-02-app-development-playbook`
2. `prompt-06-ui-e2e-verification-loop`
3. `prompt-03-alignment-review-gate`

### Why now + dependencies + expected deliverables

1. `prompt-02-app-development-playbook`
   - Why now: execute the V3 simplification packet against the React product and keep milestone/status/worklog synchronized.
   - Dependencies: `charter-prompt-system.md`, `charter-app-implementation-system.md`, `charter-docs-system.md`, `guardrails-repo-change.md`
   - Expected deliverables for this packet: `docs/implementation/reports/dashboard_ux_audit_redesign.md`, React route/UI updates under `frontend/src/*`, trust-summary + UI-event contracts, design-source updates under `design/figma_redesign/*`, milestone/status/worklog sync, and route/data-contract verification
2. `prompt-06-ui-e2e-verification-loop`
   - Why now: verify the pruned React routes, command-center redirect, slimmer Decisions surface, and pipeline trust summary with browser-level evidence.
   - Dependencies: `charter-prompt-system.md`, `charter-docs-system.md`, `charter-test-system.md`, `guardrails-repo-change.md`
   - Expected deliverables: route-level React UI smoke coverage and verification references in planning/status docs
3. `prompt-03-alignment-review-gate`
   - Why now: verify that the new IA, route map, and partial V3 Figma sync state are explicit instead of implied.
   - Dependencies: `charter-prompt-system.md`, `charter-docs-system.md`, `guardrails-repo-change.md`
   - Expected deliverables: refreshed alignment matrix, decision log, and checkpoint docs

## Deferred / Not Now Prompt IDs

- `prompt-15-artifact-feature-alignment-gate` (run after `M6`; targeted for `O-04`)
- `prompt-11-docs-diataxis-release` (run after reliability/trust packet closes)
- `prompt-10-tests-stabilization-loop` (trigger only on actual failure/flakiness evidence)

## Exploration Prompt IDs

- `prompt-14-improvement-direction-bet-loop`
- `prompt-09-tests-refactor-suite`
- `prompt-04-architecture-coherence-loop`

## Packet Sizing, Appetite, Scope-Cut Order

- Packet size rule: `1-5` checklist items per run; keep one active packet.
- Active packet appetite: `medium` (`M6`).
- Scope-cut order if behind:
  1. Cut assumption-badge surfacing (`O-04`) from this packet and defer to `prompt-15`.
  2. Cut non-critical/secondary UI routes from E2E scope; keep only core dashboard smoke flows.
  3. Cut UI polish and visual cleanup not required for trust/readiness outcomes.

## Circuit-Breaker + Carryover Rules

- Circuit-breakers (stop and re-shape instead of extending time):
  - If source-status surfacing requires broad churn (> about 30 files or architecture rewrite), stop and create a reshaped smaller bet.
  - If UI test harness cannot run with repo-native commands, stop after command-map evidence and re-bet setup hardening first.
  - If new failures remain `uphill` after one bounded stabilization pass, route a dedicated `prompt-10` packet.
- Carryover disposition: unfinished work does not auto-carry; return to shaping/routing (`prompt-00`) with explicit `Now` vs `Not now`.

## Betting Summary

- Bet: close packet `M6` (runtime source-support visibility + UI verification baseline).
- Appetite: `medium`
- Expected impact: improve trust/operability of core dashboard workflow and reduce objective-drift risk.
- No-gos:
  - no unrelated UI redesign/polish packet,
  - no release-readiness expansion before `M6`,
  - no broad refactors beyond the packet acceptance signals.
- Owner type: `maintainer`
