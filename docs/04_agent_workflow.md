# Agent Workflow

This document explains the autonomous agent system that powers data collection and normalization.

## Agent Architecture

The system uses a **LangGraph** workflow (`src/cognitive/graph.py`) to orchestrate the actions of specialized agents. This graph-based approach allows for conditional routing and a "Supervisor" LLM that decides the next best action based on the current state.

```mermaid
graph TD
    Supervisor["Supervisor (LLM)"]
    
    subgraph "Worker Nodes"
        Crawl["Crawl Node"]
        Norm["Normalize Node"]
        Enrich["Enrich Node"]
        Filter["Filter Node"]
        Eval["Evaluate Node"]
    end

    Report["Report Node"]

    Supervisor -->|Decision| Crawl
    Supervisor -->|Decision| Norm
    Supervisor -->|Decision| Enrich
    Supervisor -->|Decision| Filter
    Supervisor -->|Decision| Eval
    Supervisor -->|Decision| Report
    
    Crawl --> Supervisor
    Norm --> Supervisor
    Enrich --> Supervisor
    Filter --> Supervisor
    Eval --> Supervisor
    
    Report --> END
```

### The Supervisor Pattern
Instead of a rigid linear pipeline, the **Supervisor** (an LLM) inspects the `AgentState` (e.g., "Have we crawled data? Is it normalized?") and dynamically routes execution to the appropriate worker node.

**Typical Flow**: `Crawl -> Normalize -> Enrich -> Filter -> Evaluate -> Report`

## Agent Examples

### 1. `PisosCrawlerAgent`
- **Goal**: Navigate pagination and listing pages on *pisos.com*.
- **Strategy**: 
    - Respects `robots.txt` and rate limits.
    - Uses randomized User-Agents.
    - extracting JSON-LD structured data when available, falling back to CSS selectors.

### 2. `PisosNormalizerAgent`
- **Goal**: Convert disparate field names into our `CanonicalListing` Pydantic model.
- **Transforms**:
    - `"3 habs"` $\rightarrow$ `bedrooms=3`
    - `"planta 4"` $\rightarrow$ `floor=4`
    - `"250.000 €"` $\rightarrow$ `price=250000.0`, `currency="EUR"`

## Future Expansion
The architecture allows plugging in new agents easily:
- `IdealistaCrawlerAgent`
- `FotocasaCrawlerAgent`
- `NewsAgent` (for macro data)

Each new source only requires a matched pair of **Crawler** and **Processor**; the rest of the pipeline (Storage, Enrichment, Valuation) remains unchanged.
