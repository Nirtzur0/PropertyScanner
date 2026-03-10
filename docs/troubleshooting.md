# Troubleshooting

## Quick Diagnostics

Run these first:

```bash
python3 -m src.interfaces.cli -h
python3 -m pytest --markers
python3 scripts/check_command_map.py
```

## Symptom -> Cause -> Fix

### Need advanced preflight flags beyond top-level help

- Likely cause: top-level `preflight` exposes common flags, while full flow-level options live under the Prefect module.
- Fix:

```bash
python3 -m src.interfaces.cli preflight --help
python3 -m src.interfaces.cli prefect preflight --help
```

### Dashboard startup is slow or performs unexpected refresh

- Likely cause: dashboard command runs preflight by default.
- Fix:

```bash
python3 -m src.interfaces.cli dashboard --skip-preflight
```

### CI/docs sync check fails on runtime changes

- Likely cause: required docs were not updated with code/test/CI/config changes.
- Fix: update these docs in the same change set:
  - `docs/implementation/00_status.md`
  - `docs/implementation/checklists/02_milestones.md`
  - one of `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md`, `docs/manifest/10_testing.md`, `docs/manifest/11_ci.md`

### Crawler results are sparse or inconsistent

- Likely cause: portal anti-bot behavior or fallback-only source normalizers.
- Fix:
  - review `docs/crawler_status.md`
  - verify source `enabled` status in `config/sources.yaml`
  - start with known-supported sources before expanding scope

### Offline tests fail unexpectedly

- Likely cause: environment differences, dependency drift, or local artifact state.
- Fix:

```bash
python3 -m pytest --run-integration --run-e2e -m "not live"
```

If failures persist, compare against current CI command mapping in `docs/manifest/11_ci.md`.
