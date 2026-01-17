# Architecture Review: Unified Scraper Architecture

## Executive Summary
The current architecture is a **hybrid**:
1.  **Stealth Requests**: acts as a **Utility Patch**. It fixes a specific problem (TLS fingerprinting) but does not abstract the *decision* of how to scrape.
2.  **Agent Factory**: acts as a **Pattern**. It standardizes creation but leaves execution logic inside each agent.

## Is it a "Layer" or a "Patch"?
Honest Verdict: **It is currently more of a "Patch" (Utility Wrapper).**

While it standardizes *how* requests are made (stealthily), it does not abstract *scraping execution*.
- **Evidence**: In `immobiliare.py`, the agent itself decides:
  ```python
  if use_playwright:
      html = self._fetch_with_playwright(url)
  else:
      html = self.toolbox.fetch_html(url)
  ```
  This means every agent re-invents the "Browser vs Request" logic. A true **Scraping Layer** would hide this complexity.

## Proposed Evolution: The "Scraping Engine" (True Abstraction)
To move from "patch" to "layer", you need a `ScrapingEngine` that handles the *execution strategy* centrally.

### New Component: `ScrapingEngine`
Instead of agents calling `stealth_requests` directly, they would ask the engine for content.

```python
# Abstraction Interface
class ScrapingEngine:
    def fetch(self, url: str, strategy: Strategy = Strategy.HYBRID) -> str:
        """
        Centrally manages:
        1. Choice of Playwright vs Requests (based on strategy)
        2. Automatic retry with different methods (Requests -> fail -> Playwright)
        3. Proxy rotation
        4. Robots.txt compliance
        """
        pass

# Agent Code Becomes Clean
class IdealistaCrawler(BaseAgent):
    def run(self, payload):
        # agent doesn't care if it's curl_cffi or playwright
        html = self.engine.fetch(payload['url'], strategy=Strategy.STEALTH)
        return self.parse(html)
```

## Recommendation
1.  **Keep Current Patch**: reliable for now.
2.  **Build `ScrapingEngine`**: Step-by-step refactor to move `_fetch_with_playwright` logic out of agents and into `src/platform/engine.py`.
