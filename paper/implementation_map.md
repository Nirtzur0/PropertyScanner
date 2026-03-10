# Paper to Code Implementation Map

This map links paper labels to concrete code entrypoints. It is validated by
`scripts/verify_paper_contract.py` and used by unit tests under
`tests/unit/paper/`.

| Paper | Code | Find | Tests | Notes |
| --- | --- | --- | --- | --- |
| `eq:time_adjust` | `src/market/services/hedonic_index.py` | `def compute_adjustment_factor` | `tests/unit/paper/test_paper_verification.py::test_time_adjustment_factor_exact` | Time index ratio and clamping behavior. |
| `eq:baseline_mad` | `src/valuation/services/valuation.py` | `def _robust_comp_baseline` | `tests/unit/paper/test_paper_verification.py::test_robust_baseline_filters_outliers` | MAD-filtered weighted median. |
| `eq:price_quantile` | `src/valuation/services/valuation.py` | `np.exp(baseline_log + r10)` | `tests/unit/paper/test_paper_verification.py::test_log_residual_quantile_reconstruction` | Residuals converted to price quantiles. |
| `eq:income_value` | `src/valuation/services/valuation.py` | `income_value = (rent_est * 12) / (market_yield / 100.0)` | `tests/unit/paper/test_paper_verification.py::test_income_value_bounds` | Income blend bounded by configured caps. |
| `eq:area_adjust` | `src/valuation/services/valuation.py` | `area_adjustment = float(max(-cap, min(cap, area_adjustment)))` | `tests/unit/paper/test_paper_verification.py::test_area_adjustment_cap` | Area adjustment cap and scaling. |
| `eq:uncertainty` | `src/valuation/services/valuation.py` | `uncertainty = (q90 - q10) / (2 * q50)` | `tests/unit/paper/test_paper_verification.py::test_uncertainty_half_width` | Uncertainty half-width calculation. |
| `sec:verification` | `tests/unit/paper/test_paper_verification.py` | `sanity_case.json` | `tests/unit/paper/test_paper_verification.py::test_regression_sanity_case` | Regression anchor for deterministic inputs. |
| `sec:assumptions` | `paper/verification_log.md` | `## 1. Scope, regimes, and constraints` | `tests/unit/paper/test_paper_verification.py::test_contract_labels_present` | Assumptions are tracked and scoped. |
