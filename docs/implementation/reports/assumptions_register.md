# Assumptions Register

| ID | Assumption | Impact | Status | Owner | Evidence / Decision Note | Target stage |
| --- | --- | --- | --- | --- | --- | --- |
| `A-001` | SQLite default runtime remains sufficient for current local-first objective and test scope. | high | accepted | maintainer | Accepted for current milestone; reassess during release hardening and CI scale checks. Date: 2026-02-08. | cool_down |
| `A-002` | Existing run tables (`pipeline_runs`, `agent_runs`) are enough to bootstrap observability SLI definitions. | high | validated | maintainer | Confirmed by schema and repositories (`src/platform/pipeline/repositories/pipeline_runs.py`, `src/agentic/memory.py`). | build |
| `A-003` | Research artifacts in repo are out-of-scope for current objective packet and can be deferred safely. | medium | accepted | maintainer | Explicit defer in `checkbox.md` and `docs/implementation/reports/prompt_execution_plan.md`. Date: 2026-02-08. | bet |
| `A-004` | CI provider choice can be deferred while command-map IDs and required checks are defined now. | medium | accepted | maintainer | CI absent in repo; mapped checks in `docs/manifest/11_ci.md` for future wiring. Date: 2026-02-08. | build |
| `A-005` | Dashboard preflight side-effects are acceptable for now if runbook clarifies behavior. | low | accepted | maintainer | Behavior documented in runbook + README; UX refinement scheduled as P1/P2. Date: 2026-02-08. | cool_down |
