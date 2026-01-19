# Crawler Health & Status Report

**Date:** 2026-01-19
**Subject:** Final Global Migration Status & Blocking Analysis

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
