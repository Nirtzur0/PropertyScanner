"""
Evaluation Agent: The "Brain" of the Property Scanner.
Orchestrates multimodal encoding, retrieval, and fusion for property valuation.
"""
import math
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from src.platform.agents.base import BaseAgent, AgentResponse
from src.platform.domain.schema import CanonicalListing, CompListing
from src.platform.utils.time import utcnow

logger = structlog.get_logger()


# ============ Schemas ============

class EvaluationRequest(BaseModel):
    """Input to the evaluation agent."""
    listing: CanonicalListing
    forced_comps: Optional[List[CompListing]] = None
    num_comps: int = 10
    geo_radius_km: float = 5.0
    strategy: str = "balanced"


class ScoreBreakdown(BaseModel):
    """Breakdown of how the deal score was computed."""
    undervaluation: float = Field(description="How much below fair value")
    yield_proxy: float = Field(description="Estimated rental yield")
    uncertainty_penalty: float = Field(description="Penalty for high uncertainty")
    data_quality_penalty: float = Field(description="Penalty for missing data")


class Evidence(BaseModel):
    """Evidence pack for explainability."""
    top_comps: List[Dict[str, Any]] = Field(default_factory=list)
    attention_weights: Optional[List[float]] = None
    feature_importance: Optional[Dict[str, float]] = None
    citations: List[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    """Output from the evaluation agent."""
    listing_id: str
    
    # Distributional estimates
    fair_value_quantiles: Dict[str, float]  # {"0.1": val, "0.5": val, "0.9": val}
    rent_predicted_quantiles: Dict[str, float]
    
    # Decision support
    deal_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: ScoreBreakdown
    investment_thesis: str
    
    # Explainability
    evidence: Evidence
    
    # Flags
    flags: Dict[str, bool] = Field(default_factory=dict)
    
    # Metadata
    model_version: str = "fusion_v1"
    evaluated_at: datetime = Field(default_factory=utcnow)
    strategy_used: str = "balanced"

class ScoringWeights(BaseModel):
    """Weights for the deal scoring algorithm."""
    undervaluation: float = 1.0
    yield_proxy: float = 0.5
    uncertainty_penalty: float = 0.3
    data_quality_penalty: float = 0.2

class ScoringStrategy(BaseModel):
    """Defines a persona/strategy for evaluating deals."""
    name: str
    description: str
    weights: ScoringWeights

# Preset Strategies
PRESET_STRATEGIES = {
    "balanced": ScoringStrategy(
        name="balanced",
        description="Balanced approach between value and reliability.",
        weights=ScoringWeights()
    ),
    "bargain_hunter": ScoringStrategy(
        name="bargain_hunter",
        description="Aggressively seeks undervalued properties, tolerant of updates needed.",
        weights=ScoringWeights(
            undervaluation=2.0,
            yield_proxy=0.2,
            uncertainty_penalty=0.1,
            data_quality_penalty=0.1
        )
    ),
    "cash_flow_investor": ScoringStrategy(
        name="cash_flow_investor",
        description="Optimizes for rental yield and immediate income (Airbnb/Rental).",
        weights=ScoringWeights(
            undervaluation=0.5,
            yield_proxy=2.0,
            uncertainty_penalty=0.5, # Dislike risk/vacancy
            data_quality_penalty=0.3
        )
    ),
    "safe_bet": ScoringStrategy(
        name="safe_bet",
        description="Prioritizes certainty and high data quality.",
        weights=ScoringWeights(
            undervaluation=0.8,
            yield_proxy=0.4,
            uncertainty_penalty=1.0,
            data_quality_penalty=1.0
        )
    )
}


# ============ Agent ============

class EvaluationAgent(BaseAgent):
    """
    The AI Brain for property valuation.
    
    Pipeline:
    1. Encode target listing (multimodal)
    2. Retrieve comparable listings
    3. Fuse information via cross-attention
    4. Predict value distributions
    5. Compute deal score
    6. Generate evidence pack
    """
    
    def __init__(self, enable_vision: bool = False):
        super().__init__(name="EvaluationAgent")

        # Lazy-load valuation pipeline
        self._storage = None
        self._valuation = None
        self._enable_vision = enable_vision

    def _ensure_loaded(self):
        """Lazy load components."""
        if self._storage is None:
            from src.platform.storage import StorageService
            self._storage = StorageService()

        if self._valuation is None:
            from src.valuation.services.valuation import ValuationService
            self._valuation = ValuationService(self._storage)

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        """
        Perform full evaluation of a listing.
        """
        listing = request.listing
        direct_fusion_ready = all(
            hasattr(self, attr) and getattr(self, attr) is not None
            for attr in ("_fusion", "_encoder", "_tab_encoder")
        )
        if not direct_fusion_ready:
            self._ensure_loaded()

        if request.forced_comps:
            raise ValueError("forced_comps_not_supported")

        analysis = None
        if self._valuation is not None:
            config = self._valuation.config
            orig_k = config.K_model
            orig_radius = config.max_distance_km
            try:
                if request.num_comps:
                    config.K_model = request.num_comps
                if request.geo_radius_km:
                    config.max_distance_km = request.geo_radius_km

                analysis = self._valuation.evaluate_deal(listing)
            except Exception as exc:
                logger.warning("valuation_fallback", error=str(exc), listing_id=listing.id)
            finally:
                config.K_model = orig_k
                config.max_distance_km = orig_radius

        if analysis is None and direct_fusion_ready:
            fusion_out = self._fusion.predict(
                target_text_embedding=self._encoder.encode_single(listing.title or ""),
                target_tabular_features=self._tab_encoder.encode({}),
                target_image_embedding=None,
                comp_text_embeddings=[],
                comp_tabular_features=[],
                comp_image_embeddings=[],
                comp_prices=[],
            )

            fv_q = {
                "0.1": float(fusion_out.price_quantiles.get("0.1", 0.0)),
                "0.5": float(fusion_out.price_quantiles.get("0.5", 0.0)),
                "0.9": float(fusion_out.price_quantiles.get("0.9", 0.0)),
            }
            rent_mid = float(fusion_out.rent_quantiles.get("0.5", 0.0))
            rent_q = {
                "0.1": float(fusion_out.rent_quantiles.get("0.1", rent_mid * 0.9)),
                "0.5": rent_mid,
                "0.9": float(fusion_out.rent_quantiles.get("0.9", rent_mid * 1.1)),
            }

            fair_value = fv_q["0.5"]
            if fair_value <= 0:
                raise ValueError("invalid_fair_value")
            if not listing.price or listing.price <= 0:
                raise ValueError("invalid_listing_price")

            uncertainty = 0.0
            if fv_q["0.5"] > 0:
                uncertainty = (fv_q["0.9"] - fv_q["0.1"]) / (2 * fv_q["0.5"])

            missing_fields = sum([
                listing.bedrooms is None,
                listing.surface_area_sqm is None,
                0 if listing.location else 1,
                len(listing.image_urls or []) == 0,
            ])

            strategy = PRESET_STRATEGIES.get(request.strategy, PRESET_STRATEGIES["balanced"])
            undervaluation = (fair_value - listing.price) / listing.price
            yield_proxy = (rent_mid * 12 / fair_value) if fair_value > 0 else 0.0
            raw_score = (
                strategy.weights.undervaluation * undervaluation
                + strategy.weights.yield_proxy * (yield_proxy / 0.05)
                - strategy.weights.uncertainty_penalty * uncertainty
                - strategy.weights.data_quality_penalty * (missing_fields * 0.05)
            )
            deal_score = max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(raw_score)))

            breakdown = ScoreBreakdown(
                undervaluation=undervaluation,
                yield_proxy=yield_proxy,
                uncertainty_penalty=uncertainty,
                data_quality_penalty=missing_fields * 0.05,
            )

            return EvaluationResult(
                listing_id=listing.id,
                fair_value_quantiles=fv_q,
                rent_predicted_quantiles=rent_q,
                deal_score=deal_score,
                score_breakdown=breakdown,
                investment_thesis="Fusion-only valuation (fallback path).",
                evidence=Evidence(),
                flags={"valuation_fallback": True},
                strategy_used=request.strategy,
            )

        if analysis is None:
            raise ValueError("valuation_failed")

        if analysis.fair_value_estimate <= 0:
            raise ValueError("invalid_fair_value")
        if analysis.fair_value_uncertainty_pct < 0:
            raise ValueError("invalid_uncertainty")

        fv_q = {
            "0.1": analysis.fair_value_estimate * (1 - analysis.fair_value_uncertainty_pct),
            "0.5": analysis.fair_value_estimate,
            "0.9": analysis.fair_value_estimate * (1 + analysis.fair_value_uncertainty_pct),
        }

        if analysis.rental_yield_estimate is None:
            raise ValueError("missing_rental_yield")

        rent_est = analysis.rental_yield_estimate * analysis.fair_value_estimate / 1200
        if rent_est <= 0:
            raise ValueError("invalid_rent_estimate")

        if not analysis.rent_projections:
            raise ValueError("missing_rent_projections")

        rent_proj = min(analysis.rent_projections, key=lambda p: p.months_future)
        if rent_proj.predicted_value <= 0:
            raise ValueError("invalid_rent_projection")

        rent_spread = (
            rent_proj.confidence_interval_high - rent_proj.confidence_interval_low
        ) / (2 * rent_proj.predicted_value)
        if rent_spread < 0:
            raise ValueError("invalid_rent_projection_interval")

        rent_q = {
            "0.1": rent_est * (1 - rent_spread),
            "0.5": rent_est,
            "0.9": rent_est * (1 + rent_spread),
        }

        # Score breakdown for explainability only (deal_score comes from valuation)
        missing_fields = sum([
            listing.bedrooms is None,
            listing.surface_area_sqm is None,
            0 if listing.location else 1,
            len(listing.image_urls or []) == 0
        ])

        if not listing.price or listing.price <= 0:
            raise ValueError("invalid_listing_price")

        breakdown = ScoreBreakdown(
            undervaluation=(analysis.fair_value_estimate - listing.price) / listing.price,
            yield_proxy=analysis.rental_yield_estimate,
            uncertainty_penalty=analysis.fair_value_uncertainty_pct,
            data_quality_penalty=missing_fields * 0.05
        )

        evidence = Evidence(
            top_comps=[
                {
                    "id": c.id,
                    "price": c.adj_price,
                    "similarity": c.similarity_score,
                    "url": c.url
                }
                for c in (analysis.evidence.top_comps if analysis.evidence else [])[:5]
            ],
            attention_weights=[
                c.attention_weight for c in (analysis.evidence.top_comps if analysis.evidence else [])
            ] or None,
            citations=[
                c.url for c in (analysis.evidence.top_comps if analysis.evidence else []) if c.url
            ]
        )

        flags = {flag: True for flag in analysis.flags}
        
        return EvaluationResult(
            listing_id=listing.id,
            fair_value_quantiles=fv_q,
            rent_predicted_quantiles=rent_q,
            deal_score=analysis.deal_score,
            score_breakdown=breakdown,
            investment_thesis=analysis.investment_thesis or "",
            evidence=evidence,
            flags=flags,
            strategy_used=request.strategy
        )

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """BaseAgent interface."""
        try:
            # Parse request
            if "listing" in input_payload:
                listing = input_payload["listing"]
                if isinstance(listing, dict):
                    listing = CanonicalListing(**listing)
            else:
                return AgentResponse(status="failure", data=None, errors=["No listing provided"])
            
            request = EvaluationRequest(
                listing=listing,
                num_comps=input_payload.get("num_comps", 10),
                geo_radius_km=input_payload.get("geo_radius_km", 5.0),
                strategy=input_payload.get("strategy", "balanced")
            )
            
            result = self.evaluate(request)
            
            return AgentResponse(
                status="success",
                data=result.model_dump(),
                errors=[]
            )
            
        except Exception as e:
            logger.error("evaluation_failed", error=str(e))
            return AgentResponse(status="failure", data=None, errors=[str(e)])
