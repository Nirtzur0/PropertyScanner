# Repository Audit Checklist (Prompt-07)
Date: 2026-02-08 (post prompt-12 rerun after prompt-03 post prompt-14 packet, packet-3 execution refresh)

Rerun context: repeated prompt-07 pass after bounded prompt-12 rerun in the latest packet sequence; trust/usability priorities remain materially unchanged, and Prefect CLI environment fragility remains reproducible (`pydantic`/`prefect` import mismatch).

### Project Intent vs Reality
- [x] What the project claims to be: a local-first property intelligence workflow for discovery, valuation, and decision support through CLI/API/dashboard (evidence: `README.md`, `docs/manifest/00_overview.md`).
- [x] What it actually provides: unified crawl + market/index/train/backfill flows, plus persisted artifacts and run metadata (evidence: `src/listings/workflows/unified_crawl.py`, `src/platform/workflows/prefect_orchestration.py`, `src/platform/domain/models.py`, `data/`, `models/`).
- [x] What it actually provides: engineering controls and docs baseline (architecture/contracts/data model, observability/runbook/CI, milestones/status/worklog) (evidence: `docs/manifest/01_architecture.md`, `docs/manifest/04_api_contracts.md`, `docs/manifest/05_data_model.md`, `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md`, `docs/manifest/11_ci.md`, `docs/implementation/checklists/02_milestones.md`).
- [ ] Top 3 alignment risk 1: top-level `preflight` help remains a passthrough and can mislead users about available options (evidence: `python3 -m src.interfaces.cli preflight --help`, `src/interfaces/cli.py`).
- [ ] Top 3 alignment risk 2: persisted valuation confidence still uses placeholder logic, which can overstate certainty (evidence: `src/valuation/services/valuation_persister.py`).
- [ ] Top 3 alignment risk 3: source coverage remains constrained by anti-bot + fallback-only normalizers for several markets (evidence: `docs/crawler_status.md`, `src/listings/agents/processors/immowelt.py`, `src/listings/agents/processors/realtor.py`, `src/listings/agents/processors/redfin.py`, `src/listings/agents/processors/seloger.py`).

### Logic / Algorithm Alignment & Output Quality
- [x] Core logic entry points are identifiable and consistent: CLI, API, dashboard, Prefect orchestration, and agent orchestrator (evidence: `src/interfaces/cli.py`, `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`, `src/platform/workflows/prefect_orchestration.py`, `src/agentic/orchestrator.py`).
- [ ] Algorithm/logic alignment mismatch: CLI `preflight` command advertises the right workflow but does not expose actionable top-level options directly (evidence: `python3 -m src.interfaces.cli preflight --help` vs `python3 -m src.interfaces.cli prefect preflight --help`).
- [ ] Algorithm/logic alignment mismatch: valuation confidence score is static/heuristic instead of model-backed calibration evidence (evidence: `src/valuation/services/valuation_persister.py:41`).
- [x] Output schema and semantics are documented and implemented across DB/domain/docs (evidence: `docs/manifest/05_data_model.md`, `docs/reference/data_formats.md`, `src/platform/domain/schema.py`, `src/platform/domain/models.py`).
- [x] Correctness signals exist across tests, CI gates, docs-sync guardrails, and paper verification tests (evidence: `pytest.ini`, `tests/conftest.py`, `.github/workflows/ci.yml`, `scripts/check_docs_sync.py`, `scripts/check_command_map.py`, `tests/unit/paper/test_paper_verification.py`).
- [ ] Completeness gap: source-specific parsing completeness is uneven; fallback paths mask unsupported coverage in some sources (evidence: `src/listings/agents/processors/*.py`, `docs/crawler_status.md`).
- [x] Interpretability baseline is present via user-facing interpretation docs + runbook + troubleshooting (evidence: `docs/how_to/interpret_outputs.md`, `docs/manifest/09_runbook.md`, `docs/troubleshooting.md`).

### User Journeys (Happy Paths)
- [x] New user: what works today -> installation/quickstart/how-to/tutorial/reference paths exist and link to runnable commands (evidence: `docs/INDEX.md`, `docs/getting_started/installation.md`, `docs/getting_started/quickstart.md`, `docs/how_to/run_end_to_end.md`).
- [ ] New user: what is missing or fragile -> no top-level license/contributing policy and dual install surfaces without lockfile guidance increase uncertainty (evidence: missing `LICENSE`, missing `CONTRIBUTING.md`, `README.md`, `pyproject.toml`, `requirements.txt`).
- [ ] New user: concrete next step -> outcome: onboarding trust metadata and single recommended install path are explicit (target: `LICENSE`, `CONTRIBUTING.md`, `README.md`, `docs/manifest/02_tech_stack.md`).

- [x] Power user: what works today -> full flow commands, runbook IDs, observability/CI mappings, and release workflow references exist (evidence: `docs/manifest/09_runbook.md`, `docs/manifest/07_observability.md`, `docs/manifest/11_ci.md`, `docs/reference/release_workflow.md`).
- [ ] Power user: what is missing or fragile -> source reliability and coverage status are still mostly docs-driven, not surfaced strongly at runtime outputs (evidence: `docs/crawler_status.md`, `config/sources.yaml`).
- [ ] Power user: concrete next step -> outcome: runtime surfaces clearly annotate source support/blocked/fallback status for executed runs (target: pipeline status payload + dashboard status panels + docs pointer updates).

- [x] Contributor: what works today -> milestone-driven workflow, status/worklog discipline, CI docs-sync and offline quality gates are in place (evidence: `docs/implementation/checklists/02_milestones.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`, `.github/workflows/ci.yml`).
- [ ] Contributor: what is missing or fragile -> dependency locking and release automation remain partial, compose worker role is ambiguous, and Prefect CLI path currently fails in active environment due dependency mismatch (evidence: missing lockfile, `docs/reference/release_workflow.md`, `docker-compose.yml`, `src/interfaces/agent.py`, `python3 -m src.interfaces.cli prefect preflight --help` traceback).
- [ ] Contributor: concrete next step -> outcome: lockfile-backed install policy + clear worker/runtime roles and tag workflow are documented and enforced (target: `docs/manifest/02_tech_stack.md`, `docs/reference/release_workflow.md`, compose/runtime docs).

### Missing “Product” Pieces
- [ ] Installation story -> **Partial**.
  - Evidence: quickstart/install exist (`docs/getting_started/*`, `README.md`) but two package surfaces (`requirements.txt`, Poetry) remain without a lockfile-backed default.
- [ ] “Hello world” / minimal reproducible example -> **Partial**.
  - Evidence: end-to-end recipe exists (`docs/how_to/run_end_to_end.md`), but a single canonical smoke command with expected output snapshot is not highlighted.
- [ ] Config/story coherence -> **Partial**.
  - Evidence: Hydra config and references are documented (`config/app.yaml`, `docs/reference/configuration.md`), but source reliability caveats span multiple docs (`docs/crawler_status.md`, `README.md`).
- [ ] Reproducibility -> **Partial**.
  - Evidence: CI offline gates and paper verification tests exist (`.github/workflows/ci.yml`, `tests/unit/paper/test_paper_verification.py`) but dependency locking policy is still open and active env import mismatch can break Prefect flows (`python3 -m src.interfaces.cli prefect preflight --help`).
- [ ] Observability -> **Partial**.
  - Evidence: observability manifesto and SLI/SLO mapping exist (`docs/manifest/07_observability.md`), but dashboard/alert ownership and run-validated telemetry proof are not yet tracked as completed outcomes.
- [x] Output validation -> **Solid**.
  - Evidence: data contract/e2e tests plus paper contract checks exist (`tests/e2e/data_contracts/test_end_to_end_output_sanity.py`, `scripts/verify_paper_contract.py`, `tests/unit/paper/test_paper_verification.py`).
- [x] Documentation structure -> **Solid**.
  - Evidence: canonical docs index and Diataxis surfaces exist (`docs/INDEX.md`, `docs/getting_started/`, `docs/how_to/`, `docs/reference/`, `docs/explanation/`).
- [x] Testing strategy -> **Solid**.
  - Evidence: marker taxonomy + gated CI + troubleshooting paths (`pytest.ini`, `tests/conftest.py`, `.github/workflows/ci.yml`, `docs/manifest/10_testing.md`).
- [ ] Packaging/release -> **Partial**.
  - Evidence: release artifacts exist (`CHANGELOG.md`, `docs/reference/versioning_policy.md`, `docs/implementation/checklists/06_release_readiness.md`, `docs/how_to/upgrade_notes_template.md`) but tag/publish automation remains TODO (`docs/reference/release_workflow.md`).
- [ ] Security/safety basics -> **Partial**.
  - Evidence: security baseline doc exists (`docs/manifest/06_security.md`) but no CI security automation workflow is present.
- [ ] Dependency/tooling stack coherence -> **Partial**.
  - Evidence: stack is documented (`docs/manifest/02_tech_stack.md`) but no lockfile and duplicated dependency declarations remain (`pyproject.toml`, `requirements.txt`).
- [x] Dependency inventory.
  - Evidence: core libraries are explicit in dependency files and mapped to real modules (`pyproject.toml`, `requirements.txt`, `src/`).
  - Key examples: Hydra (config), SQLAlchemy (DB), Prefect (orchestration), LanceDB + Sentence Transformers (retrieval), Streamlit (UI), LangGraph/LangChain/LiteLLM (agent), Pytest (verification).
- [ ] Category map.
  - packaging/locking=Partial, config+secrets=Partial, logging=Partial, retries/timeouts=Partial, validation/contracts=Solid, testing=Solid, lint+types+format=Partial, CI/release=Partial, reproducibility=Partial, orchestration=Solid, DB+migrations=Partial, serialization/file formats=Solid, concurrency=Partial, observability=Partial, security automation=Missing.
  - Evidence: `pyproject.toml`, `requirements.txt`, `docs/manifest/02_tech_stack.md`, `docs/manifest/06_security.md`, `docs/manifest/07_observability.md`, `.github/workflows/ci.yml`.
- [ ] Bespoke vs buy.
  - Evidence: custom compliance/migration/runtime tooling is justified (`src/platform/utils/compliance.py`, `src/platform/migrations.py`), but dependency locking and release automation should align to standard boring workflows before more bespoke tooling.
- [ ] Packaging/release remediation outcomes (required because status is Partial).
  - Add outcome: tag/release workflow mapping is executable and automated (target: `.github/workflows/release.yml`, `docs/reference/release_workflow.md`).
  - Add outcome: release readiness checklist links to concrete tag/publish verification commands (target: `docs/implementation/checklists/06_release_readiness.md`).
- [ ] Observability remediation outcomes (required because status is Partial).
  - Add outcome: run-validated signal collection evidence for defined SLI/SLO metrics is tracked per release packet (target: `docs/manifest/07_observability.md`, `docs/implementation/00_status.md`).
  - Add outcome: alert ownership + triage routing is codified with command IDs (target: `docs/manifest/09_runbook.md`, `docs/manifest/07_observability.md`).

### Architecture & Boundaries
- [x] Clear separation of concerns: interfaces/workflows/domain/services remain modular and documented (evidence: `src/interfaces/*`, `src/platform/*`, `src/listings/*`, `src/market/*`, `src/valuation/*`, `docs/manifest/01_architecture.md`).
- [ ] Coupling point that will cause pain: top-level CLI wrappers mask deep flow flags, forcing users into secondary command paths for key options (evidence: `src/interfaces/cli.py`).
- [ ] Coupling point that will cause pain: compose worker service command is not a stable long-running worker role and can confuse deployment assumptions (evidence: `docker-compose.yml`, `src/interfaces/agent.py`).
- [ ] Missing boundary: calibrated model confidence semantics are not bounded by explicit persistence contract checks in valuation write path (evidence: `src/valuation/services/valuation_persister.py`, `paper/verification_log.md`).
- [x] Architecture diagram drift summary: architecture docs align with code at high level; biggest drift is runtime support transparency and CLI usability boundaries, not core module layout (evidence: `docs/manifest/01_architecture.md`, `docs/crawler_status.md`, `src/interfaces/cli.py`).
- [ ] High-impact recommendation 1: outcome -> CLI `preflight` top-level help exposes actionable options directly (owner: maintainer, effort: S).
- [ ] High-impact recommendation 2: outcome -> valuation confidence persistence uses calibrated evidence-derived score instead of placeholder heuristic (owner: maintainer, effort: M).
- [ ] High-impact recommendation 3: outcome -> source support states are emitted at runtime and linked in user-facing outputs (owner: maintainer, effort: M).
- [ ] High-impact recommendation 4: outcome -> lockfile-backed install path is canonical and enforced in CI/docs (owner: maintainer, effort: S).
- [ ] High-impact recommendation 5: outcome -> release tag/publish automation closes manual release gap (owner: maintainer, effort: M).

### UI/UX (If Applicable)
- [x] UI surface and launch path are clear: Streamlit dashboard via CLI or compose (evidence: `src/interfaces/dashboard/app.py`, `README.md`, `docker-compose.yml`).
- [x] UX-to-logic alignment is mostly strong: dashboard and CLI share pipeline/API surfaces (evidence: `src/interfaces/dashboard/services/*`, `src/interfaces/api/pipeline.py`, `src/interfaces/cli.py`).
- [ ] Output presentation gap: calibrated confidence semantics are not yet consistently explained as persisted behavior vs model evidence in user-facing surfaces (evidence: `src/valuation/services/valuation_persister.py`, `docs/how_to/interpret_outputs.md`).
- [ ] UX footgun: dashboard defaults to preflight unless `--skip-preflight`, which can trigger unexpected startup latency/side effects (evidence: `src/interfaces/cli.py`, `README.md`, `docs/troubleshooting.md`).
- [ ] UX footgun: compose `worker` service command does not match a persistent queue-worker mental model (evidence: `docker-compose.yml`, `src/interfaces/agent.py`).

### Consistency & Maintenance Risks
- [ ] Dead/unused entrypoint risk: compose worker role semantics are ambiguous and likely underused as currently declared (evidence: `docker-compose.yml`, `src/interfaces/agent.py`).
- [ ] Conflicting docs vs code risk: legacy index (`docs/00_docs_index.md`) and canonical index (`docs/INDEX.md`) coexist and can split navigation authority if not governed.
- [ ] Duplicate config/dependency risk: `requirements.txt` and Poetry metadata coexist without lockfile parity.
- [ ] “Works on my machine” risk: some runbook/testing docs still embed absolute local paths (evidence: `docs/manifest/09_runbook.md`, `docs/manifest/10_testing.md`).
- [ ] Runtime dependency drift risk: Prefect entrypoint import fails in active environment due `pydantic`/`pydantic_settings` mismatch, indicating environment contract drift (evidence: `python3 -m src.interfaces.cli prefect preflight --help` traceback).
- [ ] Hidden prerequisite risk: browser tooling and anti-bot constraints remain required context for successful crawl workflows (evidence: `README.md`, `docs/crawler_status.md`).
- [ ] Packet-loop risk: router primary recommendation still resets to `prompt-03`, so packet sequence progress depends on manual next-packet discipline (evidence: `docs/implementation/reports/prompt_execution_plan.md`).
- [ ] Most important maintenance risk summary: output trust can be undermined by placeholder confidence persistence + partial source support visibility, even though CI/docs/testing baselines are now materially stronger.

### Prioritized Next Steps
- [ ] **P0 outcome:** persisted confidence is evidence-backed and no longer placeholder-derived in valuation writes (owner: maintainer, effort: M, evidence: `src/valuation/services/valuation_persister.py`, `paper/verification_log.md`).
- [ ] **P0 outcome:** runtime/source support status is surfaced in user-facing outputs so unsupported/fallback markets are explicit (owner: maintainer, effort: M, evidence: `docs/crawler_status.md`, `config/sources.yaml`, `src/listings/agents/processors/*`).
- [ ] **P1 outcome:** top-level preflight CLI help is actionable and mirrors practical operator options (owner: maintainer, effort: S, evidence: `src/interfaces/cli.py`, current help output).
- [ ] **P1 outcome:** dependency/install strategy converges to one lockfile-backed path with docs+CI alignment (owner: maintainer, effort: S, evidence: `pyproject.toml`, `requirements.txt`, missing lockfile).
- [ ] **P1 outcome:** release workflow includes automated tag/publish path and references release readiness checklist (owner: maintainer, effort: M, evidence: `docs/reference/release_workflow.md`).
- [ ] **P2 outcome:** docs navigation is fully canonicalized and legacy index role is explicitly scoped (owner: contributor, effort: S, evidence: `docs/INDEX.md`, `docs/00_docs_index.md`).
- [ ] **P2 outcome:** contributor and license metadata are added at repo root for governance clarity (owner: maintainer, effort: S, evidence: missing `LICENSE`, missing `CONTRIBUTING.md`).

### Prompt-00 Handoff (Required)
- [ ] **Top P0 outcomes to copy into `docs/implementation/checklists/02_milestones.md`**
  - Outcome A: valuation confidence persistence becomes calibration-evidence-backed.
  - Target files/areas: `src/valuation/services/valuation_persister.py`, `src/valuation/services/calibration.py`, `docs/how_to/interpret_outputs.md`.
  - Acceptance signal: no placeholder confidence logic remains; persisted confidence can be traced to calibration outputs with tests.
  - Suggested phase: `Phase 3.5`.
  - Outcome B: source support/runtime status is explicit in execution surfaces.
  - Target files/areas: `config/sources.yaml`, pipeline status/reporting layer, dashboard status UI, `docs/crawler_status.md`.
  - Acceptance signal: run outputs clearly label supported/blocked/fallback source states.
  - Suggested phase: `Phase 3.5`.
- [ ] **Top P1 outcomes to copy into `docs/implementation/checklists/02_milestones.md`**
  - Outcome C: top-level preflight help exposes concrete options.
  - Target files/areas: `src/interfaces/cli.py`, `README.md`, `docs/manifest/09_runbook.md`, `docs/reference/cli.md`.
  - Acceptance signal: `python3 -m src.interfaces.cli preflight --help` lists actionable options (not only passthrough args).
  - Suggested phase: `Phase 3`.
  - Outcome D: lockfile-backed install path becomes canonical.
  - Target files/areas: dependency lockfile, `README.md`, `docs/manifest/02_tech_stack.md`, CI install step notes.
  - Acceptance signal: one default install path is documented and reproducible in CI/local checks.
  - Suggested phase: `Phase 4`.
  - Outcome E: release automation is defined.
  - Target files/areas: `.github/workflows/release.yml` (or equivalent), `docs/reference/release_workflow.md`, `docs/implementation/checklists/06_release_readiness.md`.
  - Acceptance signal: release workflow doc includes automated tag/publish path with verification steps.
  - Suggested phase: `Phase 5`.
- [ ] **Architecture drift outcomes to copy into `docs/implementation/checklists/00_architecture_coherence.md` (if used)**
  - Drift 1: CLI wrapper boundary hides preflight options at primary interface.
  - Drift 2: output-confidence semantics in persistence layer are weaker than intended model-confidence story.
  - Drift 3: source support boundaries are documented but not consistently surfaced at runtime.
- [ ] **Packaging/release outcomes to implement via `prompt-11-docs-diataxis-release.md` release discipline artifacts**
  - Keep current release docs and add automated release pipeline mapping (tag/publish/notes) plus ownership.
- [ ] **Observability/reliability outcomes to implement via `prompt-02-app-development-playbook.md` Observability & Reliability Gate**
  - Add run-validated evidence for SLI/SLO instrumentation and alert routing ownership tied to runbook command IDs.
- [ ] **Recommended execution packeting**
  - First packet (1-5 items): C (CLI preflight help) + D (lockfile/install policy).
  - Second packet: A (confidence persistence correctness) + B (source support runtime visibility).
  - Explicit defer items: new research-track expansion (`prompt-12`, `prompt-13`) and broad UI polish until these trust/reliability outcomes close.
