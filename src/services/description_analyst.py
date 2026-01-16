import json
from typing import Any, Dict, Optional

import requests
import structlog

from src.core.settings import DescriptionAnalystConfig
from src.utils.config import load_app_config

logger = structlog.get_logger()

class DescriptionAnalyst:
    """
    Analyzes property descriptions using a local LLM (Ollama) to:
    1. Extract structural features (missing fields).
    2. Assess sentiment/value (critical analysis).
    """
    
    def __init__(
        self,
        config: Optional[DescriptionAnalystConfig] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        if config is None:
            try:
                config = load_app_config().description_analyst
            except Exception:
                config = DescriptionAnalystConfig()
        self.config = config
        self.model_name = model_name or config.model_name
        self.base_url = base_url or config.base_url
        self.generate_endpoint = f\"{self.base_url}/api/generate\"
        self.timeout_seconds = config.timeout_seconds
        self.min_description_length = config.min_description_length
        
    def analyze(self, description: str) -> Dict[str, Any]:
        """
        Analyze the description and return structred data.
        """
        if not description or len(description) < self.min_description_length:
            return {}

        prompt = f"""You are a skeptical Real Estate Investment Analyst. Ignore marketing fluff and extract investable signals,
with a focus on separating luxury from fixer-upper listings.

The description can be in English/Spanish/Italian/French/Portuguese; normalize outputs to English keys.
Use only explicit evidence. If a detail is not stated or strongly implied, set it to null/false and lower confidence.

Luxury signals (examples): premium materials (marble, hardwood, natural stone), designer finishes, high-end appliances/brands,
concierge/doorman, penthouse, private lift, panoramic views, large terraces, smart home, bespoke cabinetry.
Fixer-upper signals (examples): "to renovate/reform", "original condition", "needs updating", structural damage,
damp/mold, outdated installations, missing utilities, occupied/okupas, legal issues.
Standard: move-in ready without premium cues.

Extract in strict JSON ONLY (no markdown), matching this schema:
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
  }},
  "condition_assessment": {{
    "overall_condition": "renovated/good/fair/needs_work/unknown",
    "finish_quality": "luxury/standard/basic/unknown",
    "renovation_scope": "none/cosmetic/partial/full/unknown",
    "luxury_vs_fixer": "luxury/standard/fixer_upper/unknown",
    "confidence": float
  }}
}}

Rules:
- overall_condition: renovated=recent updates; good=well kept; fair=dated but livable; needs_work=explicit repairs.
- finish_quality: luxury=high-end materials/brands/amenities; basic=low-end finishes; standard otherwise.
- renovation_scope: none=move-in ready; cosmetic=paint/fixtures; partial=kitchen/bath; full=gut/structural.
- luxury_vs_fixer: luxury only if finish_quality=luxury and overall_condition in {{renovated,good}}; fixer_upper if
  overall_condition=needs_work or renovation_scope=full; otherwise standard.
- confidence is 0.0 to 1.0 and lower it when signals are weak.
- Set renovation_needed true only if evidence of needed renovation/repairs is explicit or strongly implied; otherwise false.
- investor_sentiment must be in [-1.0, 1.0] based on ROI potential (not marketing tone).
- Use 1 decimal for investor_sentiment and 2 decimals for confidence when possible.
Description: "{description}"
"""
        
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json" # Ollama JSON mode
            }
            
            response = requests.post(
                self.generate_endpoint,
                json=payload,
                timeout=self.timeout_seconds,
            )
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
