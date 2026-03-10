# Literature Review Log (Prompt-12)

## 2026-02-09 rerun (manual prompt-12 execution)

- Trigger: explicit user-requested `prompt-12` run.
- Scope decision: bounded revalidation-only rerun (no citation expansion) to keep focus on active build packet `M6`.
- Result:
  - artifact store remains valid (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - required review section and key-claims table remain intact in `docs/manifest/20_literature_review.md`,
  - bibliography/identifier table remains intact in this log.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required.

## 2026-02-08 rerun (after prompt-03 alignment gate post prompt-14 packet)

- Trigger: executed as packet 2 in the routing sequence after finishing the latest `prompt-03-alignment-review-gate` run.
- Scope decision: bounded revalidation-only rerun (no citation expansion) to keep focus on open trust/usability delivery.
- Result:
  - artifact store remains valid (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - required review sections and claims table remain intact in `docs/manifest/20_literature_review.md`,
  - bibliography/identifier table remains intact in this log.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required.

## 2026-02-08 rerun (after latest prompt-03 post prompt-13 post prompt-07 sequence)

- Trigger: executed as packet 2 in the current routing sequence after completing the latest prompt-03 rerun.
- Scope decision: bounded revalidation-only rerun (no citation expansion) to preserve current trust/usability execution focus.
- Result:
  - artifact store remains valid (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - review section structure and key-claims table remain intact in `docs/manifest/20_literature_review.md`,
  - bibliography/identifier table remains intact in this log.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required.

## 2026-02-08 rerun (after latest prompt-03 post prompt-13 packet-4 refresh)

- Trigger: executed as packet 2 in the current routing sequence after completing the latest prompt-03 rerun.
- Scope decision: bounded revalidation-only rerun (no citation expansion) to preserve current trust/usability execution focus.
- Result:
  - artifact store remains valid (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - review section structure and key-claims table remain intact in `docs/manifest/20_literature_review.md`,
  - bibliography/identifier table remains intact in this log.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required.

## 2026-02-08 rerun (after latest prompt-03 post-prompt-13)

- Trigger: executed as packet 2 in the current routing sequence after completing the latest prompt-03 rerun (following prompt-13).
- Scope decision: bounded revalidation-only rerun (no citation expansion) to preserve current trust/usability execution focus.
- Result:
  - artifact store remains valid (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - review section structure and key-claims table remain intact in `docs/manifest/20_literature_review.md`,
  - bibliography/identifier table remains intact in this log.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required.

## 2026-02-08 rerun (after latest prompt-03)

- Trigger: executed as packet 2 in the current routing sequence after completing the latest `prompt-03-alignment-review-gate` rerun.
- Scope decision: bounded revalidation-only rerun (no citation expansion) to preserve trust-risk execution focus.
- Result:
  - artifact store remains valid (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - review section structure and key-claims table remain intact in `docs/manifest/20_literature_review.md`,
  - bibliography/identifier table remains intact in this log.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required.

## 2026-02-08 rerun (after prompt-03 trust-risk refresh)

- Trigger: executed as the next recommended packet after `prompt-03-alignment-review-gate`.
- Scope decision: bounded revalidation-only rerun (no citation expansion) to keep focus on near-term implementation packets.
- Result:
  - artifact store remains valid (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - review structure and key-claims table remain intact in `docs/manifest/20_literature_review.md`,
  - bibliography/identifier table remains intact in this log.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required.

## 2026-02-08 rerun (post alignment refresh)

- Trigger: executed as the next router packet after a prompt-03 alignment refresh.
- Scope decision: revalidation-only refresh (no citation expansion) to keep this packet bounded and avoid research drift.
- Result:
  - verified review/log/checklist structure remains intact,
  - revalidated artifact index consistency (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - confirmed no claim-table changes required in `docs/manifest/20_literature_review.md`.

## 2026-02-08 rerun (router packet execution)

- Trigger: executed as Packet 2 from `docs/implementation/reports/prompt_execution_plan.md` after completing `prompt-03`.
- Scope decision: revalidation-only refresh (no expansion of citation set) to keep this packet bounded and avoid unplanned research drift.
- Result:
  - reviewed canonical review/log/checklist structure for completeness,
  - revalidated artifact index consistency (`python3 prompts/scripts/web_artifacts.py --repo-root . validate` -> `OK: 14 artifacts`),
  - confirmed all load-bearing cited sources in this packet still map to artifact IDs.
- Change policy:
  - no source additions/removals in this rerun,
  - no claim-table deltas required in `docs/manifest/20_literature_review.md`.

## Inferred topic and scope
- Inferred topic from repo objective and valuation docs: evidence-grounded AVM design for comp-based property valuation with uncertainty calibration.
- Primary repo grounding used:
  - `docs/manifest/00_overview.md`
  - `docs/explanation/model_architecture.md`
  - `src/valuation/services/valuation.py`
  - `src/market/services/hedonic_index.py`

## Search queries and where searched

### Round 1: repository-first scoping
- Command: `rg -n "paper|research|literature|doi|arxiv|hedonic|valuation|index" docs src -S`
- Goal: locate existing project assumptions, data/model boundaries, and missing evidence links.

### Round 2: DOI validation (Crossref API)
- Where searched: `https://api.crossref.org`
- Query pattern:
  - `curl -Ls "https://api.crossref.org/works/<doi>"`
- DOIs checked:
  - `10.1086/260169`
  - `10.1080/01621459.1963.10480679`
  - `10.3386/w2393`
  - `10.3386/w2506`
  - `10.3386/w18403`
  - `10.1111/j.1538-4632.1995.tb00338.x`
  - `10.2307/1913643`
  - `10.1023/A:1010933404324`
  - `10.1145/2939672.2939785`
  - `10.1214/20-AOS1965`

### Round 3: arXiv metadata validation
- Where searched: `https://export.arxiv.org/api/query`
- Query pattern:
  - `curl -Ls "https://export.arxiv.org/api/query?id_list=<arxiv_id>"`
- IDs checked:
  - `1706.03762`
  - `1908.10084`
  - `1905.03222`
  - `1905.02928`
  - `2107.07511`

## Inclusion and exclusion criteria
- Inclusion:
  - Primary sources with stable identifiers (DOI or arXiv ID).
  - Direct relevance to at least one load-bearing project decision: comp construction, time normalization, quantile modeling, uncertainty calibration, spatial diagnostics, or retrieval architecture.
  - Methods that can be falsified in repo-local benchmarks/tests.
- Exclusion:
  - Source lacks stable identifier or has unclear publication provenance.
  - Topic is adjacent but not load-bearing for this repo packet (e.g., privacy-preserving synthetic data publication workflows).
  - Mostly implementation tips/blog-level material without primary evidence.

## Sources considered but excluded
- `10.1111/j.1467-985X.2008.00574.x` (JRSS A): strong paper, but off-topic for this packet (data confidentiality release methods rather than valuation modeling).
- OpenReview entries from broad "house price prediction" search with weak reproducibility detail and no clear external validity regime for this repo.
- General web pages/blog tutorials without stable DOI/arXiv identifiers.

## Included source bibliography (curated)

| Key | Authors | Year | Identifier | Type | Artifact ID |
| --- | --- | --- | --- | --- | --- |
| Rosen1974 | Sherwin Rosen | 1974 | DOI `10.1086/260169` | Journal article | `lit-rosen-1974` |
| BaileyMuthNourse1963 | M.J. Bailey, R.F. Muth, H.O. Nourse | 1963 | DOI `10.1080/01621459.1963.10480679` | Journal article | `lit-bailey-muth-nourse-1963` |
| CaseShiller1987 | Karl Case, Robert Shiller | 1987 | DOI `10.3386/w2393` | NBER report | `lit-case-shiller-1987` |
| CaseShiller1988 | Karl Case, Robert Shiller | 1988 | DOI `10.3386/w2506` | NBER report | `lit-case-shiller-1988` |
| DengGyourkoWu2012 | Yongheng Deng, Joseph Gyourko, Jing Wu | 2012 | DOI `10.3386/w18403` | NBER report | `lit-deng-gyourko-wu-2012` |
| Anselin1995 | Luc Anselin | 1995 | DOI `10.1111/j.1538-4632.1995.tb00338.x` | Journal article | `lit-anselin-1995` |
| KoenkerBassett1978 | Roger Koenker, Gilbert Bassett | 1978 | DOI `10.2307/1913643` | Journal article | `lit-koenker-bassett-1978` |
| Breiman2001 | Leo Breiman | 2001 | DOI `10.1023/A:1010933404324` | Journal article | `lit-breiman-2001` |
| ChenGuestrin2016 | Tianqi Chen, Carlos Guestrin | 2016 | DOI `10.1145/2939672.2939785` | Conference paper | `lit-xgboost-2016` |
| Vaswani2017 | Ashish Vaswani et al. | 2017 | arXiv `1706.03762` | Preprint | `lit-attention-2017` |
| ReimersGurevych2019 | Nils Reimers, Iryna Gurevych | 2019 | arXiv `1908.10084` | Preprint | `lit-sbert-2019` |
| RomanoPattersonCandes2019 | Yaniv Romano, Evan Patterson, Emmanuel Candes | 2019 | arXiv `1905.03222` | Preprint | `lit-cqr-2019` |
| BarberEtAl2021 | R.F. Barber, E.J. Candes, A. Ramdas, R.J. Tibshirani | 2021 | DOI `10.1214/20-AOS1965` | Journal article | `lit-jackknifeplus-2021` |
| AngelopoulosBates2021 | Anastasios Angelopoulos, Stephen Bates | 2021 | arXiv `2107.07511` | Preprint | `lit-conformal-tutorial-2021` |

## Per-source claim extraction notes
- **Rosen1974** (`lit-rosen-1974`)
  - Claim: market prices reflect bundles of implicit attribute prices.
  - Assumption signal: feature completeness matters for unbiased valuation.
- **BaileyMuthNourse1963** (`lit-bailey-muth-nourse-1963`)
  - Claim: repeat-sales regression reduces compositional drift in index construction.
  - Assumption signal: repeat transactions must be high-quality matches.
- **CaseShiller1987** (`lit-case-shiller-1987`)
  - Claim: city-level repeat-sales indices are operationally tractable and informative.
  - Assumption signal: local market heterogeneity still requires segmentation.
- **CaseShiller1988** (`lit-case-shiller-1988`)
  - Claim: persistence/inefficiency exists in single-family housing markets.
  - Assumption signal: stale comps need explicit time handling.
- **DengGyourkoWu2012** (`lit-deng-gyourko-wu-2012`)
  - Claim: land-price and structure-price decomposition materially affects measured dynamics.
  - Assumption signal: single scalar index can hide structural shifts.
- **Anselin1995** (`lit-anselin-1995`)
  - Claim: local spatial statistics detect non-stationarity and outliers missed globally.
  - Assumption signal: neighborhood definition influences diagnostics.
- **KoenkerBassett1978** (`lit-koenker-bassett-1978`)
  - Claim: quantile targets provide richer conditional distribution modeling than mean-only models.
  - Assumption signal: heteroskedastic behavior is expected and should be modeled.
- **Breiman2001** (`lit-breiman-2001`)
  - Claim: random forests are robust baselines on structured feature sets.
  - Assumption signal: baseline benchmarking is required before complex model claims.
- **ChenGuestrin2016** (`lit-xgboost-2016`)
  - Claim: boosted trees efficiently capture high-order tabular interactions.
  - Assumption signal: split hygiene (time/geo) is critical to avoid leakage.
- **Vaswani2017** (`lit-attention-2017`)
  - Claim: attention gives target-conditioned weighting over candidate context points.
  - Assumption signal: data scale and regularization affect stability.
- **ReimersGurevych2019** (`lit-sbert-2019`)
  - Claim: sentence embeddings improve retrieval relevance.
  - Assumption signal: embedding drift/domain shift can degrade comp quality.
- **RomanoPattersonCandes2019** (`lit-cqr-2019`)
  - Claim: CQR recovers calibrated intervals while using flexible quantile regressors.
  - Assumption signal: exchangeability is load-bearing.
- **BarberEtAl2021** (`lit-jackknifeplus-2021`)
  - Claim: jackknife+ gives model-agnostic predictive interval guarantees.
  - Assumption signal: interval width may increase in unstable/noisy regimes.
- **AngelopoulosBates2021** (`lit-conformal-tutorial-2021`)
  - Claim: practical conformal deployment must distinguish marginal from conditional guarantees.
  - Assumption signal: subgroup monitoring is mandatory.

## Artifact traceability map

| Source/Citation | Artifact ID | Usage in review | Notes |
| --- | --- | --- | --- |
| Rosen (1974), DOI `10.1086/260169` | `lit-rosen-1974` | Hedonic theory basis for feature-driven pricing assumptions | Metadata-only artifact |
| Bailey et al. (1963), DOI `10.1080/01621459.1963.10480679` | `lit-bailey-muth-nourse-1963` | Repeat-sales/time normalization rationale | Metadata-only artifact |
| Case and Shiller (1987), DOI `10.3386/w2393` | `lit-case-shiller-1987` | City-scale index construction evidence | Metadata-only artifact |
| Case and Shiller (1988), DOI `10.3386/w2506` | `lit-case-shiller-1988` | Market persistence and stale-comp risk | Metadata-only artifact |
| Deng et al. (2012), DOI `10.3386/w18403` | `lit-deng-gyourko-wu-2012` | Measurement pitfall notes for indices | Metadata-only artifact |
| Anselin (1995), DOI `10.1111/j.1538-4632.1995.tb00338.x` | `lit-anselin-1995` | Spatial non-stationarity diagnostics recommendation | Metadata-only artifact |
| Koenker and Bassett (1978), DOI `10.2307/1913643` | `lit-koenker-bassett-1978` | Quantile-loss and interval framing support | Metadata-only artifact |
| Breiman (2001), DOI `10.1023/A:1010933404324` | `lit-breiman-2001` | Tree baseline requirement | Metadata-only artifact |
| Chen and Guestrin (2016), DOI `10.1145/2939672.2939785` | `lit-xgboost-2016` | Boosted-tree baseline requirement | Metadata-only artifact |
| Vaswani et al. (2017), arXiv `1706.03762` | `lit-attention-2017` | Attention-based comp weighting rationale | Metadata-only artifact |
| Reimers and Gurevych (2019), arXiv `1908.10084` | `lit-sbert-2019` | Semantic retrieval and metadata-locking rationale | Metadata-only artifact |
| Romano et al. (2019), arXiv `1905.03222` | `lit-cqr-2019` | CQR calibration recommendation | Metadata-only artifact |
| Barber et al. (2021), DOI `10.1214/20-AOS1965` | `lit-jackknifeplus-2021` | Fallback conformal interval strategy | Metadata-only artifact |
| Angelopoulos and Bates (2021), arXiv `2107.07511` | `lit-conformal-tutorial-2021` | Marginal-vs-conditional coverage caveat | Metadata-only artifact |

## Reproducibility commands used in this packet
- `python3 prompts/scripts/web_artifacts.py --repo-root . init`
- `python3 prompts/scripts/web_artifacts.py --repo-root . add-meta ...` (14 source entries)
- `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
- `curl -Ls "https://api.crossref.org/works/<doi>"`
- `curl -Ls "https://export.arxiv.org/api/query?id_list=<arxiv_id>"`
