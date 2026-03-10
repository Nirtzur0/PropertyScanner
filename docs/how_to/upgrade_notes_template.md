# Upgrade Notes Template

Copy this template for each release requiring user-visible migration notes.

## Release

- Version: `vX.Y.Z`
- Date: `YYYY-MM-DD`
- Owner: `<name>`

## Summary

- What changed in one paragraph.

## Breaking Changes

- [ ] None
- [ ] Documented below

If breaking changes exist, list each with:
- Impacted surface (CLI/config/data format/API)
- Old behavior
- New behavior
- Required user action

## Migration Steps

1. Backup current local artifacts (`data/`, `models/`) if needed.
2. Update dependencies and environment.
3. Apply required config or command changes.
4. Run validation commands.

Validation commands:

```bash
python3 -m src.interfaces.cli -h
python3 -m pytest --run-integration --run-e2e -m "not live"
python3 scripts/check_command_map.py
```

## Rollback Plan

- Exact rollback trigger(s).
- Exact rollback command(s) and file reversions.

## Observability and Verification

- Which SLI/SLO or runbook checks prove success.
- Any expected warning/noise that is safe to ignore.

## Follow-ups

- Deferred cleanups and owner.
