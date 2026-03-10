# Project Plan

## Current Cycle Snapshot

- Stage: `bet` (Packet 1 under `prompt-02-app-development-playbook`)
- Appetite: `small`
- State: `downhill`

Objective re-anchor:
- Objective: build a local-first property intelligence workflow with reproducible valuation outputs and trustworthy operations.
- This step advances objective by: adding milestone scheduling and observability/CI gate definitions required to keep implementation aligned.
- Risks of misalignment: research-track prompts and release polish can distract from P0 reliability gates.

## Problem and Scope

The project has working pipelines and architecture docs, but P0 operational governance is incomplete:
- no milestone packet checklist
- no observability manifest and runbook command-map canonicalization
- no CI gate mapping
- source coverage reliability boundaries are under-documented versus anti-bot/portal constraints

Scope for this packet:
- establish planning and reliability docs needed before additional feature work
- do not change runtime behavior or refactor pipeline code

## Users and Workflows (Current Focus)

- Maintainer: needs deterministic milestones and acceptance signals.
- Contributor: needs a canonical command map and CI mapping.
- Analyst/new user: benefits indirectly from reliability gates and clearer run/debug steps.

## Assumptions

Tracked in `docs/implementation/reports/assumptions_register.md`.

## Rabbit Holes (Explicitly Avoided Now)

- full release documentation refresh (`prompt-11` packet)
- research-paper track (`prompt-12`/`prompt-13`)
- DB backend migration (SQLite -> Postgres as default)
- source-unblocking implementation work against anti-bot providers (track as planned constraint, not this packet)

## No-gos for This Packet

- no broad code refactors
- no runtime behavior changes without dedicated checklist items
- no CI provider lock-in decision beyond baseline mapping

## Milestone and Epic Mapping

- Milestones checklist: `docs/implementation/checklists/02_milestones.md`
- Epic for this packet: `docs/implementation/epics/epic_reliability_baseline.md`

## Deliverables Completed in This Packet

- Added missing manifest pages:
  - `docs/manifest/02_tech_stack.md`
  - `docs/manifest/06_security.md`
  - `docs/manifest/07_observability.md`
  - `docs/manifest/08_deployment.md`
  - `docs/manifest/09_runbook.md`
  - `docs/manifest/12_conventions.md`
- Added implementation planning artifacts:
  - `docs/implementation/checklists/02_milestones.md`
  - `docs/implementation/reports/assumptions_register.md`
  - `docs/implementation/reports/README.md`
  - `docs/implementation/epics/epic_reliability_baseline.md`
- Added CI baseline implementation:
  - `.github/workflows/ci.yml`
  - `scripts/check_docs_sync.py`
  - `scripts/check_command_map.py`

## Next Packet Preview

- Re-run `prompt-00` routing after CI baseline merge to confirm next bounded packet.
- Start P1 release-discipline packet (`prompt-11`) and implement:
  - `CHANGELOG.md`
  - `docs/reference/versioning_policy.md`
  - `docs/implementation/checklists/06_release_readiness.md`
