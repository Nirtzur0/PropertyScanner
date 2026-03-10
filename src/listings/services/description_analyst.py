import json
from typing import Any, Dict, Optional

import structlog

from src.platform.settings import DescriptionAnalystConfig
from src.platform.utils.llm import complete_with_fallback

logger = structlog.get_logger()


class DescriptionAnalyst:
    """
    Analyzes property descriptions using an OpenAI-compatible chat backend to:
    1. Extract structural features (missing fields).
    2. Assess sentiment/value (critical analysis).
    """

    def __init__(
        self,
        config: Optional[DescriptionAnalystConfig] = None,
        model_name: Optional[str] = None,
        api_base: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        if config is None:
            config = DescriptionAnalystConfig()
        self.config = config
        self.provider = config.provider
        resolved_model = model_name or config.model_name
        if self.provider == "ollama" and resolved_model and not resolved_model.startswith("ollama/"):
            resolved_model = f"ollama/{resolved_model}"
        self.model_name = resolved_model
        self.api_base = api_base or base_url or config.api_base
        self.api_key_env = config.api_key_env
        self.timeout_seconds = config.timeout_seconds
        self.min_description_length = config.min_description_length

    def analyze(self, description: str) -> Dict[str, Any]:
        """
        Analyze the description and return structured data.
        """
        if not description or len(description) < self.min_description_length:
            return {}

        prompt = f"""You are a skeptical Real Estate Investment Analyst. Ignore marketing fluff and extract investable signals.
Focus on CAPEX, yield, liquidity, legal/occupancy risk, and durable value drivers, with a clear separation between
luxury, standard, and fixer-upper listings.

The description can be in English/Spanish/Italian/French/Portuguese; normalize outputs to English keys.
Use only explicit evidence. If not stated or strongly implied, use false/null/"unknown".
Use snake_case for list items.

Common terms to map (examples):
- "sin ascensor"/"no elevator" -> has_elevator=false; "ascensor"/"elevator" -> true
- "exterior"/"interior" -> unit_position
- "bajo"/"ground floor" -> floor=0
- "atico"/"penthouse" -> property_type="penthouse"
- "para reformar"/"to renovate"/"da ristrutturare" -> renovation_needed=true
- "a estrenar"/"new build"/"nuovo" -> is_new_build=true, overall_condition=renovated
- "ocupado"/"alquilado"/"okupas" -> occupancy flags
- "VPO"/"vivienda protegida" -> has_vpo_restriction=true
- "licencia turistica" -> has_tourist_license=true

Extract strict JSON ONLY (no markdown), matching this schema:
{{
  "facts": {{
    "has_elevator": bool,
    "has_pool": bool,
    "has_garage": bool,
    "has_parking": bool,
    "has_terrace": bool,
    "has_balcony": bool,
    "has_garden": bool,
    "has_storage_room": bool,
    "has_air_conditioning": bool,
    "has_heating": bool,
    "has_doorman": bool,
    "has_security_system": bool,
    "has_accessibility": bool,
    "is_furnished": bool,
    "is_new_build": bool,
    "is_renovated": bool,
    "renovation_needed": bool,
    "is_occupied": bool,
    "has_tenant": bool,
    "has_squatters": bool,
    "has_vpo_restriction": bool,
    "has_tourist_license": bool,
    "floor": int or null,
    "unit_position": "exterior/interior/corner/unknown",
    "orientation": "north/south/east/west/dual/unknown",
    "natural_light": "poor/ok/good/excellent/unknown"
  }},
  "financial_analysis": {{
    "positive_drivers": ["string"],
    "negative_drivers": ["string"],
    "capex_risks": ["string"],
    "deal_breakers": ["string"],
    "liquidity_outlook": "high/medium/low/unknown",
    "investor_sentiment": float,
    "summary": "Compact risk/reward assessment (max 15 words)"
  }},
  "extraction": {{
    "city_or_district": "string or null",
    "neighborhood": "string or null",
    "property_type": "apartment/house/duplex/penthouse/studio/land/unknown",
    "language_hint": "en/es/it/fr/pt/other/unknown"
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
- renovation_needed: true only if explicit repair/renovation need is stated or strongly implied; otherwise false.
- luxury_vs_fixer: luxury only if finish_quality=luxury and overall_condition in {{renovated,good}}; fixer_upper if
  overall_condition=needs_work or renovation_scope=full; otherwise standard.
- liquidity_outlook: low if legal/occupancy constraints or heavy CAPEX are mentioned; high if clean, renovated, and easy-to-sell.
- confidence is 0.0 to 1.0 and lower it when signals are weak.
- investor_sentiment must be in [-1.0, 1.0] based on ROI potential (not marketing tone).
- Use 1 decimal for investor_sentiment and 2 decimals for confidence when possible.
Description: "{description}"
"""

        try:
            response = complete_with_fallback(
                models=[self.model_name],
                messages=[
                    {
                        "role": "system",
                        "content": "Return strict JSON only. Do not wrap the response in markdown.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=900,
                timeout_seconds=self.timeout_seconds,
                api_base=self.api_base,
                api_key_env=self.api_key_env,
                response_format=(None if self.provider == "ollama" else {"type": "json_object"}),
            )
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                logger.warning("llm_json_parse_error", model=response.model, content=response.content)
                return {}

        except Exception as exc:
            logger.error(
                "description_analysis_failed",
                provider=self.provider,
                api_base=self.api_base,
                model=self.model_name,
                error=str(exc),
            )
            return {}
