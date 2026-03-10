# Literature Review and Claim Validation (Prompt-12)

_Rerun status (2026-02-09): artifact index and claim/bibliography structures revalidated; no source or claim-table deltas in this packet._

## 1. Problem statement
Property Scanner currently implements a comp-anchored valuation pipeline (retrieval -> time normalization -> robust baseline -> residual quantile model -> optional conformal calibration). The load-bearing research question is whether this architecture is justified for noisy, thinly traded, spatially heterogeneous housing markets, and which assumptions must be enforced so the produced intervals remain decision-useful.

The project-level objective is practical: improve buy/hold/skip decision quality without pretending to provide official appraisal certainty. This review therefore focuses on methods that produce auditable assumptions, robust baselines, and uncertainty estimates that can be falsified with local backtests.

## 2. Scope and regimes
- Domain scope: residential property valuation with listing-level features, comparable sales/rents, and monthly market indices.
- Regimes in scope: low-to-medium data density by micro-market, non-stationary markets, sparse sold labels, mixed feature quality.
- Regimes out of scope: full-census appraisal systems, macro policy forecasting, pure image-only valuation.
- Target application: local-first AVM support for analyst triage and evidence-based scenario analysis.
- Constraints from repo reality: SQLite local store, optional LLM/VLM components, anti-bot data collection constraints, no guaranteed live source coverage.

Active research question cluster (Now):
- In sparse and drifting markets, when is comp-anchored residual modeling more reliable than direct price prediction?
- Which index-construction assumptions are required for time normalization to avoid spurious trend effects?
- What uncertainty methods provide practical finite-sample guarantees for valuation intervals?
- How much should semantic retrieval influence comp selection relative to geo/structure filters?
- Which baseline models should remain mandatory to detect overfitting in neural fusion components?

## 3. Canonical references
- **Rosen (1974)**, DOI: `10.1086/260169` (`lit-rosen-1974`): establishes hedonic decomposition as the theoretical basis for attribute-priced housing value.
- **Bailey, Muth, Nourse (1963)**, DOI: `10.1080/01621459.1963.10480679` (`lit-bailey-muth-nourse-1963`): foundational repeat-sales index construction for housing price dynamics.
- **Case, Shiller (1987)**, DOI: `10.3386/w2393` (`lit-case-shiller-1987`): practical repeat-sales indexing at city scale.
- **Case, Shiller (1988)**, DOI: `10.3386/w2506` (`lit-case-shiller-1988`): documents inefficiency/persistence in single-family markets, relevant to stale comps.
- **Deng, Gyourko, Wu (2012)**, DOI: `10.3386/w18403` (`lit-deng-gyourko-wu-2012`): highlights land-vs-structure decomposition and measurement pitfalls in fast-changing markets.
- **Anselin (1995)**, DOI: `10.1111/j.1538-4632.1995.tb00338.x` (`lit-anselin-1995`): local spatial diagnostics for neighborhood-level non-stationarity.
- **Koenker, Bassett (1978)**, DOI: `10.2307/1913643` (`lit-koenker-bassett-1978`): quantile regression framing for interval-aware prediction.
- **Breiman (2001)**, DOI: `10.1023/A:1010933404324` (`lit-breiman-2001`): strong tabular baseline family for non-linear effects and interactions.
- **Chen, Guestrin (2016)**, DOI: `10.1145/2939672.2939785` (`lit-xgboost-2016`): scalable boosted trees for high-signal structured features.
- **Vaswani et al. (2017)**, arXiv: `1706.03762` (`lit-attention-2017`): attention formulation used by target-vs-comps weighting logic.
- **Reimers, Gurevych (2019)**, arXiv: `1908.10084` (`lit-sbert-2019`): sentence embeddings for semantic retrieval among candidate comparables.
- **Romano, Patterson, Candes (2019)**, arXiv: `1905.03222` (`lit-cqr-2019`): conformalized quantile regression for calibrated interval construction.
- **Barber et al. (2021)**, DOI: `10.1214/20-AOS1965` (`lit-jackknifeplus-2021`): model-agnostic predictive interval guarantees.
- **Angelopoulos, Bates (2021)**, arXiv: `2107.07511` (`lit-conformal-tutorial-2021`): practical assumptions/caveats for deployment of distribution-free uncertainty.

## 4. Key claims

| Claim | Source | Assumptions | Evidence | Confidence | Implications |
| --- | --- | --- | --- | --- | --- |
| Housing price can be decomposed into implicit prices of attributes and location. | Rosen (1974) | Competitive market approximation, observed characteristic set is informative. | Economic theory + econometric treatment. | High | Keep explicit feature engineering and avoid black-box-only valuation paths. |
| Repeat-sales indices reduce compositional bias when tracking market movement over time. | Bailey et al. (1963); Case and Shiller (1987) | Repeat transactions are representative enough; transaction matching quality is high. | Empirical index construction. | High | Continue time normalization before comp aggregation; log fallback cases. |
| Single-family markets show persistence/inefficiency, so stale comps can mislead if not time-adjusted. | Case and Shiller (1988) | Observed serial dependence reflects partial inefficiency and lagged adjustment. | Empirical market tests. | Medium-High | Keep strict comp date filtering and document freshness effects in valuation evidence. |
| Land and structure should be separated conceptually in fast-moving markets to avoid index misreadings. | Deng et al. (2012) | Adequate proxies for land intensity and structure quality. | Empirical measurement study. | Medium | Track land/structure proxies where available; avoid single-index overreliance. |
| Local spatial diagnostics identify neighborhood non-stationarity and outliers that global models hide. | Anselin (1995) | Spatial neighborhood graph is sensible for the city/region. | Statistical methodology + simulations/applications. | High | Add local spatial diagnostics to observability and confidence warning logic. |
| Quantile regression is better aligned with valuation intervals than mean-only regression. | Koenker and Bassett (1978) | Conditional quantiles are identifiable with available features. | Statistical theory + estimation framework. | High | Keep p10/p50/p90 as first-class outputs and train/evaluate pinball losses. |
| Tree ensembles are strong, low-friction tabular baselines and catch non-linear interactions. | Breiman (2001); Chen and Guestrin (2016) | Sufficient tabular signal and leak-free splitting. | Broad empirical evidence. | High | Require RF/XGBoost baseline comparisons before claiming neural-fusion gains. |
| Attention supports target-conditioned weighting of comparables, not just fixed-distance averaging. | Vaswani et al. (2017) | Enough samples to estimate attention weights robustly. | Architecture-level empirical success. | Medium | Keep cross-attention as optional enhancement, but audit attribution stability. |
| Sentence embeddings improve semantic similarity search beyond lexical matching. | Reimers and Gurevych (2019) | Listing text quality is adequate; embedding drift is managed. | Retrieval benchmark evidence. | Medium-High | Maintain retriever metadata locking and periodic embedding drift checks. |
| Conformalized quantile regression can recover finite-sample marginal coverage with quantile models. | Romano et al. (2019) | Exchangeability between calibration and deployment distributions. | Statistical guarantee + experiments. | High | Keep conformal calibration as a post-model stage and report realized coverage by segment. |
| Jackknife+ offers model-agnostic interval validity under weak assumptions but can widen intervals. | Barber et al. (2021) | Stable learner and suitable resampling regime. | Theoretical guarantees + empirical checks. | High | Use as fallback calibration strategy where CQR assumptions are weak or data is small. |
| Conformal guarantees are usually marginal, not conditional; subgroup undercoverage must be monitored explicitly. | Angelopoulos and Bates (2021) | Deployment distributions can shift across segments/time. | Tutorial synthesis + examples. | High | Add subgroup coverage dashboards (region/type/price-band) before trusting global coverage. |

## 5. Competing viewpoints / contradictions
- **Classical hedonic vs modern ML:** hedonic models maximize interpretability and economic structure, while boosted/neural models may improve point accuracy under rich features. Decision: keep econometric anchors and require ML gains to beat them on leak-safe time+geo backtests.
- **Repeat-sales vs cross-sectional methods:** repeat-sales control composition but can bias toward frequently traded stock; cross-sectional methods use more listings but can be confounded by quality mix shifts. Decision: use both signals and surface disagreement as a risk flag.
- **Conformal validity claims:** conformal methods guarantee marginal coverage under exchangeability, but coverage may fail in specific neighborhoods or price bands. Decision: enforce segmented coverage checks before production confidence claims.
- **Semantic retrieval vs structural filters:** embedding similarity can retrieve semantically similar but structurally mismatched comps. Decision: keep geo/size/type hard constraints ahead of semantic ranking.

## 6. What this means for this project
Recommended modeling and validation decisions:
- **Build/keep:** comp-anchored log-residual quantile design with explicit time normalization and hard structural comp filters (`docs/explanation/model_architecture.md`, `src/valuation/services/valuation.py`).
- **Build now:** benchmark harness adding `RandomForest` and `XGBoost` baselines against current fusion residual model under time+geo splits (Breiman 2001, Chen and Guestrin 2016).
- **Build now:** subgroup coverage report for conformal intervals by `region_id`, listing type, and price band (Romano et al. 2019, Barber et al. 2021, Angelopoulos and Bates 2021).
- **Build now:** runtime fallback policy that keeps segmented conformal as primary and switches to wider bootstrap intervals for unseen, under-sampled, or under-covered segments.
- **Build now:** spatial drift diagnostics (local Moran/LISA-style checks) integrated into observability docs and valuation warning outputs (Anselin 1995).
- **Avoid:** claiming conditional coverage or market-efficiency assumptions without segmented empirical evidence.
- **Avoid:** replacing comp/time anchors with end-to-end neural price prediction until baseline and leakage tests are passed.

Open questions and falsification triggers:
- If tree baselines outperform fusion model on strict out-of-time splits, current multimodal complexity is not justified.
- If subgroup interval coverage drops materially below target despite calibration, conformal configuration is mis-specified for deployment regime.
- If retrieval ablations show minimal gain from text embeddings, retrieval stack should be simplified.
- If bootstrap fallback dominates a segment because sample floors or coverage floors are repeatedly missed, that segment should not be treated as calibration-ready.

## 7. Proposed validation checklist
- [ ] Add rolling-window backtests with time+geo holdouts and compare MAE/MedAE/pinball for fusion vs RF/XGBoost.
- [ ] Add interval metrics: empirical coverage, conditional coverage by segment, and interval width-cost tradeoff.
- [x] Add retriever ablations: geo-only, geo+structure, geo+structure+semantic; measure lift and failure modes.
  - Evidence: `docs/implementation/reports/retriever_ablation_report.md` (`semantic` decision currently `simplify` at configured thresholds).
- [x] Add decomposition diagnostics decision packet with explicit segment sample/MAE-gap thresholds.
  - Evidence: `docs/implementation/reports/retriever_ablation_report.json` (`decomposition_diagnostics.status = insufficient_segment_samples`, decision `keep_gap_visible`).
- [ ] Add index-dependency stress tests: evaluate valuations under missing/lagged index scenarios.
- [ ] Add spatial residual diagnostics (hotspot/outlier detection) and wire alerts to runbook triage.
- [ ] Add explicit acceptance thresholds before enabling any higher-complexity model path by default.
