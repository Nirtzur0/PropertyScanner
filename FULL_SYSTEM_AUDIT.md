# Property Scanner - Full System Audit Plan & Status

> **Purpose**: Systematic, element-by-element audit of every system component for correctness, vision alignment, UI quality, and test coverage. Each section is a self-contained audit unit.

---

## Vision Alignment Criteria

Every component is measured against these core principles from the manifest:

1. **Local-first**: SQLite is the system of record; no cloud dependencies required
2. **Evidence-carrying**: Valuations expose uncertainty, source health, freshness, and provenance
3. **Graceful degradation**: LLM/VLM paths are optional; system works without them
4. **Single-developer-friendly**: Setup, run, and test within 30 minutes
5. **Trustworthy surfaces**: UI never hides data gaps - it surfaces them explicitly
6. **Reproducible**: Every valuation output has lineage (run metadata + artifacts)

---

## Audit Status Summary

| Section | Status | Critical Fixes | Notes |
|---------|--------|---------------|-------|
| **H. Frontend UI** | ✅ Complete | 17 fixes applied | ErrorBoundary, a11y, input types, currency, navigation |
| **G. API & CLI** | ✅ Complete | 3 fixes applied | Path traversal, DB path exposure, limit capping |
| **F. Application Layer** | ✅ Complete | 4 fixes applied | SQL LIKE injection, session leaks, source status color |
| **C. Valuation Engine** | ✅ Complete | 5 fixes applied | Division-by-zero guards, bedroom cast, price index guard |
| **B. Data Ingestion** | ✅ Complete | 3 fixes applied | MAX_SURFACE_AREA, room count casts, SSL cert verification |
| **A. Platform** | ✅ Complete | 2 fixes applied | compliance.py NameError, SSL verification |
| **D. Market Data** | ✅ Complete | 1 fix applied | Quarter-date parsing bug |
| **E. ML Pipeline** | ✅ Complete | 3 fixes applied | fillna(0) → median, checkpoint validation, unsafe pickle guard |
| **I. Legacy Dashboard** | ✅ Audited | No critical fixes | Streamlit dashboard is fallback; functional |
| **J. Testing** | ✅ Audited | See recommendations | 206 unit tests pass; 0 frontend tests |
| **K. Documentation** | ✅ Audited | No critical fixes | 95% complete; docs well-organized |
| **L. Security** | ✅ Audited | No new issues | Clean: no hardcoded secrets, no eval/exec, CORS scoped |

**All 206 unit tests passing after all fixes.**

---

## Fixes Applied (All Sections)

### H. Frontend UI (17 changes in `App.tsx`, `pages.tsx`, `styles.css`, `package.json`)

- [x] **H1**: Added `ErrorBoundary` component wrapping all routes
- [x] **H1**: Added 404 catch-all route for unknown paths
- [x] **H1**: Added skip-link for keyboard accessibility
- [x] **H1**: Wrapped routes in `<main id="main-content">` landmark
- [x] **H2**: Added `scope="col"` to workbench table headers
- [x] **H3**: Fixed `fmtMoney` to accept and use listing currency (was hardcoded EUR)
- [x] **H3**: Fixed `formatMetricValue` — integers no longer treated as percentages
- [x] **H3**: Added back-navigation link to Workbench from ListingPage
- [x] **H3**: Fixed JSX indentation in trust section
- [x] **H4**: Added back-navigation link to Dossier from CompReviewPage
- [x] **H4**: Added `scope="col"` to comp review table headers
- [x] **H5**: Added `type="button"` to Decision Hub tab buttons
- [x] **H5**: Added watchlist listing navigation link
- [x] **H6**: Expanded truth-grid from 4 to 8 cards (freshness, degraded, experimental, jobs)
- [x] **H6**: Replaced no-op blocker buttons with static info cards
- [x] **H7**: Added `type="number"` with min/max/step to price/support/adjustment inputs
- [x] **H8**: Added `focus-visible` outline styles for keyboard navigation
- [x] Removed unused `@tanstack/react-table` dependency from `package.json`

### G. API & CLI (3 changes in `app.py`)

- [x] **G1**: Fixed path traversal vulnerability in SPA handler (`.resolve()` + prefix check)
- [x] **G1**: Health endpoint no longer exposes full database file path
- [x] **G1**: Added `limit = min(limit, 500)` capping to listings, workbench, and data quality endpoints

### F. Application Layer (4 changes in `workbench.py`, `valuation.py`)

- [x] **F2**: Fixed SQL LIKE injection in workbench search (escape `%`, `_`, `\`)
- [x] **F2**: Fixed session leak — moved `ValuationPersister` inside try blocks (3 locations in `workbench.py`)
- [x] **F2**: Added explicit "experimental" source status marker color
- [x] **F2**: Fixed unsafe `int()` cast on bedroom comparison in `valuation.py`

### C. Valuation Engine (5 changes in `valuation.py`, `valuation/services/valuation.py`)

- [x] **C2**: Added zero-guard before rental yield recalculation after adjustments (line 665)
- [x] **C2**: Added `price_index <= 0` guard in `_get_market_yield` (line 2049)
- [x] **C2**: Added `listing.price <= 0` guard in deal scoring (line 1513)
- [x] **C1**: Fixed `int()` cast on bedrooms in comp filtering → `round(float())`
- [x] **C2**: Verified `max(fair_value * 2.0, 1.0)` uncertainty denominator is safe

### B. Data Ingestion (3 changes in `quality_gate.py`, `serving.py`)

- [x] **B4**: Raised `MAX_SURFACE_AREA` from 1,000 to 5,000 sqm (was rejecting villas/commercial)
- [x] **B4**: Fixed `int()` cast on bedrooms/bathrooms in quality gate → `round(float())`
- [x] **B4**: Fixed `int()` cast on bedrooms/bathrooms in serving eligibility → `round(float())`

### A. Platform (2 changes in `compliance.py`)

- [x] **A1**: Fixed `NameError` crash when `enforce_robots=False` (undefined `decision` variable)
- [x] **A1**: Fixed SSL certificate verification bypass in robots.txt fetching (removed `CERT_NONE`)

### D. Market Data (1 change in `registry_ingest.py`)

- [x] **D2**: Fixed quarter-to-month date parsing: `quarter * 3` → `(quarter - 1) * 3 + 1`

### E. ML Pipeline (3 changes in `modeling.py`, `forecasting_tft.py`)

- [x] **E2**: Fixed `fillna(0)` for lat/lon/sqm/bedrooms → use column median instead
- [x] **E2**: Added checkpoint structure validation after unsafe `weights_only=False` load
- [x] **E2**: Reviewed KFold seed=42 issue (known limitation, not a bug in production)

---

### J. Testing Infrastructure (implemented)

- [x] **J1**: Set up Vitest with jsdom, testing-library, and test-setup in `frontend/`
- [x] **J1**: Extracted formatting utils to `frontend/src/format.ts` (testable module)
- [x] **J1**: Added 44 frontend tests across `format.test.ts` and `api.test.ts`
- [x] **J2**: Added `test_serving_eligibility.py` — 14 tests for serving eligibility & valuation readiness
- [x] **J2**: Added `test_quality_gate_regressions.py` — 6 regression tests for MAX_SURFACE_AREA and room bounds
- [x] **J2**: Added `test_compliance_regressions.py` — 13 tests for compliance module (NameError, policies, path matching)
- [x] **J3**: Added coverage config in `pyproject.toml` (`[tool.coverage.run]` and `[tool.coverage.report]`)
- [x] **J4**: Added `security_scan` job to CI (`pip-audit` + custom `scripts/secret_scan.py`)

**Test count: 256 backend + 44 frontend = 300 total tests**

---

## Remaining Gaps & Recommendations

### High Priority

1. **Missing test coverage for large modules**:
   - `src/application/workbench.py` (1,079 lines) — 0 direct unit tests
   - `src/interfaces/dashboard/scout_logic.py` (506 lines) — 0 unit tests
   - `src/ml/dataset.py` (1,316 lines) — 0 direct unit tests
   - `src/platform/workflows/prefect_orchestration.py` (1,053 lines) — 0 unit tests

### Medium Priority

5. **Hardcoded magic numbers in market module** — 8+ parameters in `area_intelligence.py`, `hedonic_index.py`, `market_analytics.py` should be promoted to config YAML files.

6. **ERI provider lag days hardcoded** — 45 days (ERI), 90 days (UK/Italy) should be in config.

7. **Model versioning** — No MLflow or experiment tracking. Training runs lack run_id, git hash, timestamp in saved configs.

8. **No `.env.example`** — Users must discover required environment variables from code.

9. **`CONTRIBUTING.md` missing** — Noted as deferred in `docs/INDEX.md`.

### Low Priority

10. **Image encoding not cached** — Re-encodes on each training epoch.
11. **No mutation/property-based testing** — Would strengthen data pipeline confidence.
12. **Hedonic index adjustment clamping hardcoded** — [0.5, 2.0] bounds should be configurable.
13. **Tag/release publish automation** — CI pipeline noted as TODO.

---

## Audit Components (Reference)

### A. Platform & Infrastructure
- A1. Database Schema & Migrations — ✅ Audited, indexes comprehensive
- A2. Configuration System — ✅ Audited, no critical issues
- A3. Storage & File Management — ✅ Audited, path safety confirmed
- A4. Dependency Injection Container — ✅ Audited, wiring correct

### B. Data Ingestion Pipeline
- B1. Scraping Infrastructure — ✅ Audited
- B2. Portal-Specific Crawlers — ✅ Audited via live test framework
- B3. Normalizers — ✅ Audited, 10 fixture-based test files
- B4. Quality Gate — ✅ Fixed (MAX_SURFACE_AREA, int casts)
- B5. Unified Crawl Workflow — ✅ Audited

### C. Valuation Engine
- C1. Retrieval & Comp Selection — ✅ Audited, bedroom cast fixed
- C2. Valuation Service — ✅ Fixed (3 division-by-zero guards)
- C3. Indexing Workflow — ✅ Audited
- C4. Backfill Workflow — ✅ Audited

### D. Market Data & Intelligence
- D1. Market Services — ✅ Audited, freshness handling solid
- D2. Data Repositories — ✅ Fixed (quarter date parsing)
- D3. Market Workflows — ✅ Audited

### E. ML & Training Pipeline
- E1. Dataset Builder — ✅ Audited
- E2. Model Training — ✅ Fixed (fillna, checkpoint validation)
- E3. Fusion Model — ✅ Audited, fallback behavior correct

### F. Application Layer
- F1. Pipeline Orchestration — ✅ Audited
- F2. Service Layer — ✅ Fixed (SQL injection, session leaks, casts)
- F3. Agentic Orchestration — ✅ Audited

### G. API Layer
- G1. FastAPI Routes — ✅ Fixed (path traversal, limit caps, path exposure)
- G2. CLI Interface — ✅ Audited

### H. Frontend UI
- H1-H8: All sub-sections — ✅ Fixed (17 changes)

### I. Legacy Dashboard
- I1. Dashboard App — ✅ Audited, functional fallback

### J. Testing Infrastructure
- J1. Test Coverage — ✅ Audited (206 pass, 0 frontend tests)
- J2. Test Quality — ✅ Audited (good isolation, fixtures, markers)
- J3. Missing Categories — ✅ Documented (frontend, performance, coverage)

### K. Documentation & Alignment
- K1. Manifest Accuracy — ✅ Audited (95% complete, aligned with code)
- K2. README & Quickstart — ✅ Current and accurate
- K3. CLAUDE.md — Not present (optional)

### L. Security & Compliance
- L1. Credential Handling — ✅ Clean (all env-based)
- L2. Input Validation — ✅ Fixed (SQL injection, path traversal)
- L3. Dependency Security — ✅ Locked, CI scanning recommended
