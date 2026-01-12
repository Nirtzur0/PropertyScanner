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

        prompt = f"""You are a strict, cynical real estate investor. Analyze this property description.
Description: "{description}"

Task:
1. Extract FACTS (boolean/int) if present: has_elevator, has_pool, has_garage, renovation_needed, floor_number (int).
2. Determine SENTIMENT score (-1.0 to 1.0): 
   - -1.0 = Terrible deal, major red flags, "needs work".
   - 0.0 = Neutral, factual listing.
   - 1.0 = Incredible opportunity, "must see", purely positive.
   Be CRITICAL. Marketing fluff should not boost the score much.
3. specific_features: List of key strings e.g. ["sea_view", "high_ceilings"].

Output ONLY valid JSON:
{{
  "facts": {{
    "has_elevator": bool,
    "has_pool": bool,
    "has_garage": bool,
    "renovation_needed": bool,
    "floor": int or null
  }},
  "sentiment_score": float,
  "summary": "Short critical assessment"
}}
"""
        
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json" # Ollama JSON mode
            }
            
            response = requests.post(self.generate_endpoint, json=payload, timeout=30)
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
