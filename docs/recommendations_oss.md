# Open Source Recommendations for Property Scanner

This document outlines high-impact open-source libraries and tools that could enhance the `property_scanner` project. Recommendations are categorized by domain and impact.

---

## 1. Orchestration & Observability (High Impact)
**Current State**: Prefect flows handle orchestration and retries; preflight/maintenance run via the CLI.

### **Prefect** (or Dagster)
*   **Why**: Your pipeline involves complex dependencies (Scrape -> Normalize -> Fuse -> Augment). Prefect allows you to define these as flows with automatic retries, caching (don't re-scrape if done), and a local UI to debug failures.
*   **Fit**: "Code as workflows" philosophy fits your Python-heavy codebase perfectly.
*   **Migration**: Prefect flows wrap existing workflow steps; `pipeline_runs` still captures per-step metadata.
*   **Status**: Implemented via `src/platform/workflows/prefect_orchestration.py` (use `python3 -m src.interfaces.cli preflight` or `python3 -m src.interfaces.cli prefect preflight`).

### **Pydantic Settings** (already likely used, but explicit usage)
*   **Why**: Ensure strict validation of all `AppConfig` via `.env` files. Hydra is great for composition, but Pydantic Settings handles environment variable overrides cleaner for production.

---

## 2. Data Engineering & Analytics (Medium Impact)
**Current State**: Pandas + DuckDB + SQLite.

### **dbt (Data Build Tool) with dbt-duckdb**
*   **Why**: Currently, transformations (e.g., calculating hedonic indices, cleaning prices) likely live in Python functions. `dbt` moves this to modular SQL models.
*   **Benefit**: Lineage graphs, automatic documentation, and data quality tests (`not null`, `unique`) on your database tables.
*   **Fit**: Excellent integration with DuckDB for local analytics.

### **Polars**
*   **Why**: If your property dataset grows >1M rows, Pandas will slow down. Polars is a Rust-backed DataFrame library that is 10-50x faster and memory efficient.
*   **Fit**: Drop-in replacement for many Pandas operations, especially for the "Market Evaluation" aggregation steps.
*   **Status**: Optional backend via `dataframe.backend: polars` (defaults to pandas).

### **LanceDB**
*   **Why**: You use `faiss-cpu`. LanceDB is a modern, embedded vector database (runs in-process like SQLite) that is optimized for multi-modal data (images + text).
*   **Benefit**: Easier management than raw FAISS indices. Native storage of the embeddings alongside the metadata.
*   **Fit**: Perfect for your VLM/Image-search features.
*   **Status**: Optional backend via `valuation.retriever_backend: lancedb` and `valuation.retriever_lancedb_path`.

---

## 3. LLM & Agents (High Efficiency)
**Current State**: LangChain + LangGraph.

### **LiteLLM**
*   **Why**: You are using `langchain-openai`. LiteLLM provides a standardized interface to ANY model (OpenAI, Anthropic, Ollama, Azure) using the OpenAI format.
*   **Benefit**: Switch between `gpt-4o` and a local `llama3` via config without changing code. Robust cost tracking and fallback logic (e.g., "Use Local Llama, if fail -> GPT-4").
*   **Status**: Implemented via `src/platform/utils/llm.py`; configure `llm.models` in `config/llm.yaml`.

### **Instructor**
*   **Why**: LangChain's Pydantic extraction can be verbose. `Instructor` is a lightweight library that patches the OpenAI/LiteLLM client to return simple Pydantic objects.
*   **Fit**: Ideal for the `Normalizer` agents extracting structured data from HTML.
*   **Status**: Implemented as an LLM fallback normalizer (enable via `llm.normalizer_enabled: true`).

---

## 4. Scraping & Browser (Optimization)
**Current State**: Playwright + Pydoll (Custom CDP).

### **Crawl4AI**
*   **Why**: An emerging competitor to generic Playwright scripts. It's optimized for LLM extraction, turning HTML into Markdown efficiently with cleaner separation of main content.
*   **Fit**: Could replace part of the `ScrapeClient` logic for "general" sites, though your Pydoll implementation is specialized and likely better for the "Stealth" requirement.

### **Browserbase (Managed)**
*   **Why**: If you scale beyond local machine capabilities, managing headless chromes is painful. Browserbase provides serverless browsers with stealth baked in.
*   **Note**: Not OSS, but relevant for scaling. For OSS alternative, self-hosting **Browserless** via Docker.

---

## 5. UI/UX (Dashboard)
**Current State**: Streamlit.

### **Streamlit-AgGrid**
*   **Why**: Streamlit's native dataframe is limited. AgGrid allows sorting, filtering, and **editing** cells directly in the grid (e.g., manually verifying a listing).
*   **Fit**: High value for the "Deal Flow" review page.

### **Reflex (formerly Pynecone)**
*   **Why**: If you hit the wall with Streamlit's "rerun everything on click" model. Reflex compiles Python to a React Single Page App (SPA).
*   **Fit**: Long-term consideration if the dashboard becomes a complex application.

---

## Recommended Action Plan

1.  **Immediate Win**: **LiteLLM** is integrated; adjust `config/llm.yaml` to change model priorities.
2.  **Stability Win**: Use **Prefect** flows for `crawl_backfill` and `market-data` to get visibility into crashes and scheduled runs.
3.  **Data Win**: Migrate Vector Search to **LanceDB**. Simplifies the VLM embedding persistence.
