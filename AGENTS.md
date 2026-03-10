# AGENTS.md (Prompt Library Bootstrap)

Use this file in the **target repository root** (the parent folder of the prompt-pack directory) so coding agents can execute this prompt library correctly.

## 1) First-Run Bootstrap (Required)
1. Set `PROMPT_PACK_DIR` to the folder that contains this library (`PROMPTS.md`, `prompt-00-prompt-routing-plan.md`, `scripts/`).
2. Validate the prompt library before execution:
   - `python3 <prompt_pack_dir>/scripts/prompts_manifest.py --check`
   - `python3 <prompt_pack_dir>/scripts/system_integrity.py --mode prompt_pack`
3. Generate the routing plan with `prompt-00-prompt-routing-plan.md`:
   - infer cycle stage from repo state, select immediate/deferred/exploration prompt IDs, and write `docs/implementation/reports/prompt_execution_plan.md`.
4. Open the selected `prompt-<NN>-*.md` and load every file listed in its `dependencies:` front matter before coding.

## 2) Prompt Library Map (What To Use)
- `prompt-00`: route/select next prompt packet from repo state.
- `prompt-01`: turn rough requirements into PRD + measurable acceptance criteria.
- `prompt-02`: end-to-end app development playbook (docs-first, production-quality).
- `prompt-03`: objective drift/alignment review gate.
- `prompt-04`: architecture coherence loop (arc42 + C4 style).
- `prompt-05`: README onboarding quickstart refresh.
- `prompt-06`: UI E2E verification loop.
- `prompt-07`: repo audit checklist and prioritized findings.
- `prompt-08`: dashboard/data explorer implementation.
- `prompt-09`: test refactor and suite hardening.
- `prompt-10`: test stabilization and flaky/failing test recovery.
- `prompt-11`: docs + Diataxis + release-readiness pass.
- `prompt-12`: literature/research validation sweep.
- `prompt-13`: research-paper implementation + verification.
- `prompt-14`: discover missing/weak improvement directions and turn them into milestone-ready bets.
- `prompt-15`: align features/milestones with artifact evidence and derive corrective opportunities.

For lifecycle routing and sequencing, use `<prompt_pack_dir>/PROMPTS.md` as canonical guidance.

## 3) Non-Negotiable Operating Rules
- Repo truth only: do not invent commands, features, schemas, datasets, or status.
- Commands must be repo-sourced (`Makefile`, scripts, package tasks, CI configs, etc.).
- Minimal diff by default; avoid repo-wide churn unless explicitly requested.
- Deliverables are written to the **target repo**, not into `<prompt_pack_dir>/`.
- Keep one active work packet at a time (recommended packet size: 1-5 checklist items).
- Re-anchor each packet to `DOCS_ROOT/manifest/00_overview.md#Core Objective`.
- If `Core Objective` is missing, create/update it before major planning/implementation.
- Update `docs/implementation/00_status.md` and `docs/implementation/03_worklog.md` at each coherent checkpoint.
- Use web browsing only when needed (or required by prompt metadata), and ground load-bearing external sources per `charter-artifacts-system.md`.

## 4) Docs System Contract
- If the active prompt depends on `charter-docs-system.md`, detect/lock `DOCS_ROOT` first.
- Ensure `DOCS_ROOT/.prompt_system.yml` exists before writing docs.
- Prefer links over duplicated policy text; shared policy lives in prompt-pack charters.

## 5) Completion Discipline
- Stop when required deliverables exist and verification checks are run (or explicitly marked blocked).
- If runtime/context limits are hit, hand off with:
  - completed vs remaining checklist items
  - exact next commands
  - blockers/risks and open assumptions
