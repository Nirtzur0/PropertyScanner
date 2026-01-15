import requests
import json
import logging
import structlog
from typing import Dict, Any, Optional

logger = structlog.get_logger()

class DescriptionAnalyst:
    """
    Analyzes property descriptions using a local LLM (Ollama) to:
    1. Extract structural features (missing fields).
    2. Assess sentiment/value (critical analysis).
    """
    
    def __init__(self, model_name: str = "llama3:latest", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.generate_endpoint = f"{base_url}/api/generate"
        
    def analyze(self, description: str) -> Dict[str, Any]:
        """
        Analyze the description and return structred data.
        """
        if not description or len(description) < 50:
            return {}

        prompt = f"""You are a cynical Real Estate Investment Analyst. Your job is to ignore marketing fluff and assess financial value/risk.
Description: "{description}"

Analyze the text and extract the following in strict JSON format:

1. **Facts**: Extract boolean/int flags.
2. **Drivers**:
   - `positive_drivers`: List of features that DIRECTLY increase rent/sale price (e.g. "terrace", "elevator", "recently_renovated", "exterior").
   - `negative_drivers`: List of red flags or costs (e.g. "no_elevator", "interior_apartment", "needs_reform", "squatters").
3. **Sentiment**: `investor_sentiment` (float in [-1.0, 1.0]).
   - Rating based on ROI potential, NOT how "nice" the description sounds.
   - -1.0 = severe red flags / toxic asset (legal issues, ruins).
   -  0.0 = neutral, standard market listing.
   - +1.0 = exceptional opportunity / clearly undervalued.
   - Use values inside the range; prefer 1 decimal precision.

Output JSON ONLY:
{{
  "facts": {{
    "has_elevator": bool,
    "has_pool": bool,
    "has_garage": bool,
    "renovation_needed": bool,
    "floor": int or null
  }},
  "financial_analysis": {{
    "positive_drivers": ["string"],
    "negative_drivers": ["string"],
    "investor_sentiment": float,
    "summary": "Compact risk/reward assessment (max 15 words)"
  }},
  "extraction": {{
    "city_or_district": "string or null"
  }}
}}
"""
        
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json" # Ollama JSON mode
            }
            
            response = requests.post(self.generate_endpoint, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                content = data.get("response", "")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Fallback structural repair if needed, but JSON mode usually works
                    logger.warning("llm_json_parse_error", content=content)
                    return {}
            else:
                logger.warning("ollama_request_failed", status=response.status_code, body=response.text)
                return {}
                
        except Exception as e:
            logger.error("description_analysis_failed", error=str(e))
            return {}
