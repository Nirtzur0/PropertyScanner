# Artifact-Feature Alignment Report

## Overview

- Prompt: `prompt-15-artifact-feature-alignment-gate`
- Date: 2026-02-09
- Artifact store: `docs/artifacts/index.json` (`14` artifacts, validated)
- Alignment verdict: `ALIGNED_WITH_GAPS`
- Summary: post-`M8` decision packet, retriever ablation and decomposition-risk decisions are explicit, and fallback interval policy is now mapped; remaining open items are the operational follow-ons (`C-11`, `C-12`).

## Artifact Inventory Summary

| Artifact ID | Role | Affected feature area |
| --- | --- | --- |
| `lit-rosen-1974` | Hedonic pricing foundation | Comp baseline + feature-driven valuation |
| `lit-bailey-muth-nourse-1963` | Repeat-sales index method | Time normalization and index adjustment |
| `lit-case-shiller-1987` | City-scale repeat-sales practice | Time adjustment policy and market index usage |
| `lit-case-shiller-1988` | Market persistence/staleness risk | Temporal filtering and stale-comp safeguards |
| `lit-deng-gyourko-wu-2012` | Measurement caveat (land vs structure) | Index interpretation and diagnostics |
| `lit-anselin-1995` | Spatial non-stationarity diagnostics | Spatial drift/outlier monitoring |
| `lit-koenker-bassett-1978` | Quantile regression framing | p10/p50/p90 prediction surfaces |
| `lit-breiman-2001` | Tabular baseline requirement | Baseline model benchmark harness |
| `lit-xgboost-2016` | Strong boosted baseline requirement | Baseline model benchmark harness |
| `lit-attention-2017` | Target-conditioned attention weighting | Cross-attention fusion model |
| `lit-sbert-2019` | Semantic embedding retrieval | Retriever model/index metadata lock |
| `lit-cqr-2019` | Conformalized quantile calibration | Conformal calibration workflow |
| `lit-jackknifeplus-2021` | Distribution-free interval fallback | Fallback interval strategy |
| `lit-conformal-tutorial-2021` | Marginal vs conditional coverage caveat | Coverage reporting + confidence semantics |

## Artifact-to-Feature Matrix

| Artifact ID | Expected implication | Current feature/test coverage | Status (Supported/Partial/Missing/Misaligned) | Evidence paths |
| --- | --- | --- | --- | --- |
| `lit-rosen-1974` | Hedonic assumptions should anchor comp-based valuation behavior. | Robust comp baseline and residual architecture are implemented and tested. | Supported | `src/valuation/services/valuation.py`, `docs/explanation/model_architecture.md`, `tests/unit/paper/test_paper_verification.py` |
| `lit-bailey-muth-nourse-1963` | Repeat-sales indexing should inform time adjustment. | Hedonic/index adjustment is implemented and covered by deterministic tests. | Supported | `src/market/services/hedonic_index.py`, `src/ml/dataset.py`, `tests/unit/paper/test_paper_verification.py` |
| `lit-case-shiller-1987` | City-scale index use should be operational in valuation workflow. | Market/index tables and adjustment path are integrated in training/inference pipeline. | Supported | `docs/manifest/05_data_model.md`, `src/ml/dataset.py`, `src/valuation/services/forecasting.py` |
| `lit-case-shiller-1988` | Stale/inefficient market behavior should drive strict temporal handling and source-trust signaling. | Temporal leakage controls are in place, runtime source labels are surfaced in API/dashboard, and live-browser trust evidence is captured against the real Streamlit runtime. | Supported | `src/valuation/services/retrieval.py`, `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`, `tests/live/ui/test_dashboard_live_browser__source_support.py` |
| `lit-deng-gyourko-wu-2012` | Measurement decomposition caveats should be visible in diagnostics. | Decomposition-risk decision packet now exists with explicit segment-sample and MAE-gap thresholds; runtime diagnostics remain intentionally gated pending sufficient land samples. | Partial | `docs/implementation/reports/retriever_ablation_report.json`, `docs/manifest/20_literature_review.md`, `docs/implementation/checklists/08_artifact_feature_alignment.md` |
| `lit-anselin-1995` | Spatial drift/outlier diagnostics should be tracked operationally. | Spatial residual diagnostics are emitted from calibration workflow with drift/outlier warning states and runbook triage mapping. | Supported | `src/valuation/workflows/calibration.py`, `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md` |
| `lit-koenker-bassett-1978` | Quantile-first prediction should remain first-class. | Quantile outputs and uncertainty formula are implemented and tested. | Supported | `src/valuation/services/valuation.py`, `docs/explanation/model_architecture.md`, `tests/unit/paper/test_paper_verification.py` |
| `lit-breiman-2001` | Tree baselines should be benchmarked against fusion model. | Benchmark harness includes RandomForest baseline under time+geo split with explicit gate thresholds and report artifacts. | Supported | `src/ml/training/benchmark.py`, `docs/implementation/reports/fusion_tree_benchmark.json`, `docs/implementation/checklists/02_milestones.md` |
| `lit-xgboost-2016` | XGBoost baseline should exist in validation harness. | Benchmark harness includes XGBoost baseline with gate participation and benchmark report output. | Supported | `src/ml/training/benchmark.py`, `requirements.lock`, `docs/implementation/reports/fusion_tree_benchmark.md` |
| `lit-attention-2017` | Cross-attention should be implemented with inspectable evidence. | Multihead cross-attention model and attention weights are implemented and surfaced. | Supported | `src/ml/services/fusion_model.py`, `src/valuation/services/valuation.py`, `docs/explanation/model_architecture.md` |
| `lit-sbert-2019` | Semantic retrieval should enforce model/index metadata consistency. | Retriever uses SentenceTransformer with strict metadata/version/fingerprint checks. | Supported | `src/valuation/services/retrieval.py`, `docs/manifest/05_data_model.md`, `docs/reference/configuration.md` |
| `lit-cqr-2019` | Conformalized quantile calibration should be available in workflow. | Conformal calibrator/workflow emits segmented coverage report outputs with explicit threshold metadata. | Supported | `src/valuation/services/conformal_calibrator.py`, `src/valuation/workflows/calibration.py`, `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md` |
| `lit-jackknifeplus-2021` | Fallback interval strategy should be explicit for weak-regime settings. | Runtime interval policy now switches to wider bootstrap fallback intervals for unseen, under-sampled, or under-covered segments, and runbook/docs explain the trigger thresholds. | Supported | `docs/manifest/20_literature_review.md`, `docs/manifest/09_runbook.md`, `src/valuation/services/conformal_calibrator.py`, `src/valuation/services/valuation.py` |
| `lit-conformal-tutorial-2021` | Conditional coverage caveats should be visible in confidence semantics. | Persisted confidence is composite/traceable from diagnostics and segmented coverage reporting is emitted with thresholded pass/fail states. | Supported | `docs/manifest/20_literature_review.md`, `src/valuation/services/valuation_persister.py`, `src/valuation/workflows/calibration.py`, `docs/how_to/interpret_outputs.md` |

## Top Corrective Outcomes (3-7)

| Outcome | Owner | Effort | Acceptance signal | Prompt-chain recommendation |
| --- | --- | --- | --- | --- |
| C-08: Run retriever ablation + embedding-drift decision packet (`O-02`) [Closed 2026-02-09]. | maintainer | M | Reproducible ablation report documents keep/simplify decision thresholds for semantic retrieval (`decision = simplify`). | `prompt-15` -> `prompt-02` -> `prompt-09` -> `prompt-03` |
| C-09: Add decomposition diagnostics bet for land/structure measurement risk (`O-03`) [Closed 2026-02-09]. | maintainer | M | Decision packet now includes decomposition thresholds and sample-floor gate (`decision = keep_gap_visible` when sample floor is not met). | `prompt-15` -> `prompt-14` -> `prompt-02` -> `prompt-03` |
| C-10: Define fallback interval strategy for weak-regime segments (`lit-jackknifeplus-2021`) [Closed 2026-03-10]. | maintainer | S | Runbook and runtime policy specify when to switch to fallback intervals under low-sample/coverage-risk regimes. | `prompt-02` -> `prompt-03` |

## Top Opportunity Outcomes (3-7)

| Outcome | Owner | Effort | Acceptance signal | Prompt-chain recommendation |
| --- | --- | --- | --- | --- |
| O-02: Run retriever ablation packet (geo-only vs geo+structure vs geo+semantic) and track drift [Closed 2026-02-09]. | maintainer | M | Periodic ablation report now exists with keep/simplify decision threshold for semantic retrieval complexity. | `prompt-14` -> `prompt-02` -> `prompt-09` |
| O-03: Add measurement-risk bet for land/structure decomposition diagnostics [Closed 2026-02-09]. | maintainer | M | Decomposition decision note now exists with explicit sample-floor and MAE-gap thresholds. | `prompt-12` -> `prompt-14` -> `prompt-02` |
| O-05: Close fixture-only verification gap with live-browser trust evidence [Closed 2026-02-09]. | maintainer | S | Prompt-06 report/checklist include live-session proof for source-label rendering under real dashboard runtime. | `prompt-15` -> `prompt-06` -> `prompt-03` |
| O-01: Artifact-feature mapping contract check is operational and CI-enforced. | contributor | S | Docs-check script validates artifact IDs are mapped in alignment report/checklist/milestones and runs in CI docs guardrail. | `prompt-02` -> `prompt-11` |

## Milestone Routing Summary

- Previously closed and retained: `C-01`, `C-02`, `C-03`, `C-04`, `C-05`, `C-06`, `C-07`, `C-08`, `C-09`, `O-01`, `O-02`, `O-03`, `O-04`, and `O-05`.
- Active remaining corrective outcomes: `C-11` and `C-12` only.
- Follow-on routing: run `prompt-03` to close `M9` routing evidence, then decide whether `C-11` or `C-12` should be the next small packet.
