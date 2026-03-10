# Verification Log (Prompt-13)

## 0. Rerun log (2026-02-09, manual prompt-13 execution)
- Trigger: explicit user-requested `prompt-13` run.
- Scope decision: bounded verification rerun (no model/paper claim expansion) while active build packet `M6` remains the primary objective path.
- Command outcomes:
  - `python3 scripts/paper_generate_sanity_artifact.py` -> passed (`paper/artifacts/sanity_case.json` regenerated).
  - `python3 scripts/verify_paper_contract.py` -> passed.
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` -> failed in active environment due third-party `langsmith` pytest plugin autoload error (`ForwardRef._evaluate ... recursive_guard`).
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` -> passed (`12 passed`).
  - `python3 scripts/build_paper.py` -> passed; produced `paper/main.pdf`.
- Change policy:
  - no claim-table or implementation-map changes in this rerun,
  - verification evidence refreshed and plugin autoload fragility retained as an environment constraint.

## 0. Rerun log (2026-02-08, packet-4 execution refresh after latest prompt-07 post prompt-12/03 sequence)
- Trigger: executed as packet 4 in the current sequence after the latest `prompt-07-repo-audit-checklist` rerun.
- Scope decision: bounded revalidation rerun (no model/paper claim expansion).
- Command outcomes:
  - `python3 scripts/paper_generate_sanity_artifact.py` -> passed (`paper/artifacts/sanity_case.json` regenerated).
  - `python3 scripts/verify_paper_contract.py` -> passed.
  - `python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` -> failed in active environment due third-party `langsmith` pytest plugin autoload error (`ForwardRef._evaluate ... recursive_guard`).
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/paper -m "not integration and not e2e and not live" -q` -> passed (`12 passed`).
  - `python3 scripts/build_paper.py` -> passed; produced `paper/main.pdf`.
- Change policy:
  - no claim-table or mapping changes in this rerun,
  - `paper/main.tex` corrected for reproducible LaTeX build (`\texttt{...}` paths with escaped underscores and in-text citations),
  - verification evidence refreshed and environment plugin fragility retained as a known local constraint.

## 1. Scope, regimes, and constraints
- Scope: residential valuation using comp-based retrieval + hedonic normalization + log-residual quantile modeling.
- Regimes: sparse and drifting markets, local-first SQLite runtime, time-safe comps.
- Constraints: optional multimodal signals, anti-bot constrained data sources, limited sold labels.
- Appetite: medium
- Packet state: downhill

## 2. Research questions (Now)
1. When does comp-anchored residual modeling outperform direct price prediction in sparse markets?
2. What index-normalization assumptions are required to avoid time drift bias?
3. Which uncertainty method provides defensible interval guarantees under finite samples?
4. How should semantic retrieval be constrained by structure/geo filters?
5. Which baselines must remain in the validation suite before model changes are trusted?

## 3. Search log and inclusion/exclusion criteria
- Source of truth: `docs/manifest/20_literature_review.md` and `docs/implementation/reports/20_literature_review_log.md`.
- Inclusion: primary sources with DOI/arXiv and direct relevance to comp modeling, indices, quantiles, or conformal calibration.
- Exclusion: sources without stable identifiers or unrelated to valuation correctness.

## 4. Canonical references (subset)
- Rosen1974: hedonic decomposition for attribute pricing.
- BaileyMuthNourse1963: repeat-sales index construction.
- CaseShiller1987: city-scale index methodology.
- KoenkerBassett1978: quantile regression framework.
- RomanoPattersonCandes2019: conformalized quantile regression.
- BarberEtAl2021: jackknife+ intervals.

## 5. Artifact traceability map

| Artifact ID | Source/Citation key | Used for | Notes |
| --- | --- | --- | --- |
| `lit-rosen-1974` | Rosen1974 | Hedonic attribute pricing assumption | Metadata-only artifact in `docs/artifacts/index.json`. |
| `lit-bailey-muth-nourse-1963` | BaileyMuthNourse1963 | Time normalization rationale | Metadata-only artifact. |
| `lit-case-shiller-1987` | CaseShiller1987 | Index construction evidence | Metadata-only artifact. |
| `lit-koenker-bassett-1978` | KoenkerBassett1978 | Quantile loss/interval framing | Metadata-only artifact. |
| `lit-cqr-2019` | RomanoPattersonCandes2019 | Conformal calibration | Metadata-only artifact. |
| `lit-jackknifeplus-2021` | BarberEtAl2021 | Fallback interval guarantee | Metadata-only artifact. |

## 6. Key claims table

| Claim | Source | Assumptions | Evidence | Confidence | Traceability | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| Time-normalized comp pricing reduces market-drift bias. | BaileyMuthNourse1963, CaseShiller1987 | Indices are reliable and timely. | Empirical index construction. | High | Literature | `test_time_adjustment_factor_exact` |
| Robust MAD-filtered baseline reduces comp outlier influence. | Rosen1974 | Comps are representative after filtering. | Economic modeling practice. | Medium | Verified by tests | `test_robust_baseline_filters_outliers` |
| Log-residual quantiles can be reconstructed into price quantiles. | RomanoPattersonCandes2019 | Residuals are modeled around a stable baseline. | Statistical method. | High | Verified by tests | `test_log_residual_quantile_reconstruction` |
| Income value is bounded by configured adjustment caps. | Internal design | Configured cap is respected. | Implementation property. | High | Verified by tests | `test_income_value_bounds` |
| Interval monotonicity is enforced after calibration. | KoenkerBassett1978 | Quantile ordering is required for validity. | Statistical constraints. | High | Verified by tests | `test_enforce_monotonicity_sorted` |
| Conformal calibration improves marginal coverage but not conditional coverage. | BarberEtAl2021, AngelopoulosBates2021 | Exchangeability and stable distribution. | Theoretical guarantees. | High | Literature | TODO(segment_coverage_tests) |

## 7. Competing viewpoints / contradictions
- Repeat-sales indices reduce composition bias, but can overweight frequently traded stock. Use segmented reporting and fallbacks where coverage is thin.
- Conformal methods give marginal guarantees; conditional coverage requires segmented monitoring.

## 8. Decisions for this project
- Keep comp-anchored log-residual quantile modeling with strict time-normalization.
- Require baseline comparisons (RF/XGBoost) before major model changes.
- Add segmented coverage reporting as a follow-on to this packet.

## 9. Verification plan coverage summary
- Verified by tests: time adjustment, MAD baseline filtering, log-residual reconstruction, income bounds, monotonic quantiles, uncertainty calculation.
- Literature-only: conformal coverage guarantees and hedonic theory assumptions.
- TODO: segmented coverage and end-to-end accuracy benchmarks.

## 10. Not now
- End-to-end accuracy benchmarks with full dataset coverage.
- Automated coverage dashboards by region/type.
