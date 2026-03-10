# Crawler Health & Status Report

## Runtime Evidence Update (2026-03-10)

- Runtime source labels now prefer recent persisted `source_contract_runs` evidence and fall back to this document only when no recent run evidence exists.
- Current live packet evidence on the default local stack:
  - `pisos`, `imovirtual_pt`, and `rightmove_uk` passed live smoke with canonical source IDs and persisted crawl metrics.
  - `zoopla_uk` remains block-prone and should be treated as success-or-explicit-block.
  - `idealista`, `immobiliare_it`, and `onthemarket_uk` currently surface explicit `policy_blocked:*` outcomes under conservative compliance semantics instead of pretending to be crawler regressions.
- The matrix below remains useful as operator guidance, but it is no longer the primary runtime source of truth.

**Date:** 2026-01-19
**Subject:** Final Global Migration Status & Blocking Analysis
**Runtime Label Sync:** 2026-02-09 (`M6 / C-02`)

## Overview

This document summarizes the results of the comprehensive global scraper migration effort. We have evaluated and attempted to migrate key property portals across Europe and the USA.

**Key Finding:** Enterprise-grade anti-bot protection (DataDome, Akamai) is ubiquitous among major real estate portals. Standard browser automation without residential proxies is effectively blocked in 75% of the target markets.

## Verification Methodology

Tests were conducted using:
1.  **Browser Identity**: Headless Chrome controlled via **PyDoll** (Chrome DevTools Protocol).
2.  **Stealth**: `prefer_browser=True` and `maximize_stealth=True` enabled in `ScrapeClient` to simulate human headers and TLS fingerprints.
3.  **Network**: Standard datacenter IP range (no residential proxies).

**Verification Standard**: A "Blocked" status indicates that the site detected and rejected the automated browser session despite these stealth measures.

## Migration Status Matrix

| Crawler | Country | Status | Verification Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Imovirtual** | Portugal | ✅ **Operational** | Passing | - Successfully migrated to `ScrapeClient`.<br>- Normalizer handles JSON-LD (fixed `@graph` parsing) and DOM fallback.<br>- Integration tests passing with real network calls. |
| **OnTheMarket** | UK | ✅ **Operational** | Passing | - Migrated to `ScrapeClient`.<br>- Normalizer extracts structured data from `dataLayer`.<br>- Validated with live integration tests handling rate limits. |
| **Pisos.com** | Spain | ✅ **Operational** | Passing | - Reference implementation. Working correctly. |
| **Realtor** | USA | ❌ **Blocked** | Failing | - **FATAL**: Blocked (likely DataDome/Cloudflare). |
| **Redfin** | USA | ❌ **Blocked** | Failing | - **FATAL**: Blocked (Fingerprinting). |
| **Homes.com** | USA | ❌ **Blocked** | Failing | - **FATAL**: Blocked (Rate Limit/Access Denied). |
| **Casa.it** | Italy | ❌ **Blocked** | Failing | - **FATAL**: Blocked by **DataDome**.<br>- Listing content hidden behind challenge page. |
| **Immobiliare** | Italy | ❌ **Blocked** | Failing | - **FATAL**: Blocked by **DataDome**.<br>- Integration test failed. |
| **Idealista** | Spain | ❌ **Blocked** | Failing | - **FATAL**: Blocked by **DataDome**.<br>- Integration test failed. |
| **SeLoger** | France | ❌ **Blocked** | Failing | - **FATAL**: Blocked by **DataDome**.<br>- Integration test failed. |
| **Immowelt** | Germany | ❌ **Blocked** | Failing | - **FATAL**: Blocked by **DataDome**.<br>- Integration test failed. |
| **Funda** | Netherlands | ❌ **Blocked** | Failing | - **FATAL**: Blocked by **Akamai/reCAPTCHA**.<br>- Browser execution intercepted. |
| **Rightmove** | UK | ✅ **Operational** | Passing | - Successfully fetched valid content.<br>- Stealth bypass effective. |
| **Zoopla** | UK | ✅ **Operational** | Passing | - Successfully fetched valid content.<br>- Stealth bypass effective. |
| **Sreality** | Czechia | ✅ **Operational** | Passing | - Successfully fetched valid content. |
| **Daft.ie** | Ireland | ❌ **Blocked** | Failing | - **FATAL**: Blocked by CAPTCHA/DataDome. |
| **Pararius** | Netherlands | ❌ **Blocked** | Failing | - **FATAL**: Blocked by CAPTCHA. |
| **Otodom** | Poland | ❌ **Blocked** | Failing | - **FATAL**: Blocked by CAPTCHA/Cloudflare. |

## Runtime Source-Support Labels

`src/interfaces/api/pipeline.py` and `src/interfaces/dashboard/app.py` now expose runtime source labels based on `config/sources.yaml` plus this status matrix:

- `supported`: source is enabled and mapped to `Operational` in this report.
- `blocked`: source is mapped to `Blocked` in this report.
- `fallback`: source is disabled, unverified, or missing explicit operational evidence.

Runtime payload shape:
- `source_support.summary`: counts for `supported`, `blocked`, `fallback`.
- `source_support.sources[*].runtime_label`: per-source label surfaced in dashboard status panels.
- `assumption_badges[*]`: artifact-backed runtime caveat badges (`status`, `artifact_ids`, `summary`, `guide_path`) consumed by API/dashboard trust views.

Operator note:
- runtime labels now prefer recent persisted crawl evidence; review this document when there is no recent source-contract evidence or when you need manual blocking context.

## Detailed Blocking Analysis

### 1. DataDome Targets (Europe + Some US)
These sites share the same protection mechanism.
- **Symptom**: The browser receives a 200 OK or 403 Forbidden, but the HTML body is replaced by a challenge script (`<script src="https://js.datadome.co/tags.js">`) or a CAPTCHA iframe.
- **Impact**: Zero data extraction possible.
- **Remediation**: Requires high-quality **Residential Rotating Proxies** and potentially advanced fingerprinting evasion.

### 2. Akamai / reCAPTCHA Targets (Funda)
- **Symptom**: Request is intercepted by an Akamai edge worker presenting a "Verification" page.

### 3. US Specifics (Realtor, Redfin, Homes)
- **Symptom**: Aggressive IP blocking, fingerprinting (Redfin), and strict rate limits (Homes).
- **Impact**: Similar to DataDome, these require residential infrastructure.

## Conclusion & Next Steps

The code migration is complete for all targets that are technically feasible with the current infrastructure. The logic for the blocked crawlers (Normalizers, Integration Tests) has been prepared or stubbed, but they cannot operate until the underlying blocking issue is addressed via infrastructure upgrades.

**Recommendation:**
1.  **Infrastructure Upgrade**: Procure residential proxy access if these markets are critical.
2.  **Focus**: Rely on Imovirtual, OnTheMarket, and Pisos.com for current data streams.
