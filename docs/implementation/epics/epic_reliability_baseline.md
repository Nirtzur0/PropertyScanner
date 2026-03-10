# Epic: Reliability Baseline and Execution Governance

## Epic Goal

Create a verifiable reliability baseline so future implementation work stays aligned with the core objective.

## Scope

- milestone packetization and acceptance tracking
- observability and runbook command-map canonicalization
- CI gate mapping for deterministic offline suites

## User Story Slice

- As a maintainer, I can identify exactly what must pass before new features are added.
- As a contributor, I can run canonical commands and understand where CI should point.
- As an analyst user, I can trust that output claims are backed by measurable signals.

## Tasks

- [x] Task E1-T1: create and maintain `docs/implementation/checklists/02_milestones.md`.
  - AC: P0/P1/P2 outcomes include owner/effort/verify commands.
  - Tests: N/A (docs task)
  - Edge cases: stale packet references after prompt rerouting.
- [x] Task E1-T2: maintain canonical command map in `docs/manifest/09_runbook.md` and pointer mapping in `docs/manifest/11_ci.md`.
  - AC: CI doc contains `CMD-*` references only; no duplicated command tables.
  - Tests: grep command id cross-reference.
  - Edge cases: renamed commands without updated IDs.
- [x] Task E1-T3: establish observability gate in `docs/manifest/07_observability.md`.
  - AC: includes log schema, golden signals, SLI/SLO, and triage playbook.
  - Tests: section presence checks.
  - Edge cases: objective metric changes not reflected in SLI table.

## Files in Scope

- `docs/implementation/checklists/02_milestones.md`
- `docs/manifest/07_observability.md`
- `docs/manifest/09_runbook.md`
- `docs/manifest/11_ci.md`
- `docs/implementation/00_status.md`
- `docs/implementation/03_worklog.md`
