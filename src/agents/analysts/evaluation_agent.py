"""
Evaluation Agent: The "Brain" of the Property Scanner.
Orchestrates multimodal encoding, retrieval, and fusion for property valuation.
"""
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from dataclasses import dataclass

from src.agents.base import BaseAgent, AgentResponse
from src.core.domain.schema import CanonicalListing, CompListing
import numpy as np

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
    evaluated_at: datetime = Field(default_factory=datetime.now)
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
        
        # Lazy imports to avoid slow startup
        self._retriever = None
        self._encoder = None
        self._retriever = None
        self._encoder = None
        self._tab_encoder = None
        self._vision_encoder = None
        self._fusion = None
        self._enable_vision = enable_vision

    def _ensure_loaded(self):
        """Lazy load components."""
        if self._retriever is None:
            from src.services.retrieval import CompRetriever
            self._retriever = CompRetriever()
            
        if self._encoder is None:
            from src.services.encoders import TextEncoder
            self._encoder = TextEncoder()
            
        if self._tab_encoder is None:
            from src.services.encoders import TabularEncoder
            self._tab_encoder = TabularEncoder()
            
        if self._vision_encoder is None and self._enable_vision:
            try:
                from src.services.encoders import VisionEncoder
                self._vision_encoder = VisionEncoder()
            except ImportError:
                logger.warning("vision_encoder_import_failed")
            
        if self._fusion is None:
            from src.services.fusion_model import FusionModelService
            self._fusion = FusionModelService()

    def _extract_features(self, item: Any) -> Dict[str, float]:
        """Extract tabular features from Listing or CompListing."""
        features = {}
        
        # Handle CanonicalListing
        if hasattr(item, 'property_type'):
            features['bedrooms'] = float(item.bedrooms or 0)
            features['bathrooms'] = float(item.bathrooms or 0)
            features['surface_area_sqm'] = float(item.surface_area_sqm or 0)
            features['floor'] = float(item.floor or 0)
            if item.location:
                features['lat'] = float(item.location.lat)
                features['lon'] = float(item.location.lon)
            
            # Derived
            if item.price and item.surface_area_sqm:
                features['price_per_sqm'] = item.price / item.surface_area_sqm
        
        # Handle CompListing
        elif hasattr(item, 'features'):
            # CompListing features are already a flat dict usually
            # But we might need to map them if names differ
            features['bedrooms'] = float(item.features.get('bedrooms', 0))
            features['bathrooms'] = float(item.features.get('bathrooms', 0))
            features['surface_area_sqm'] = float(item.features.get('sqm', 0)) # Note 'sqm' key from CompRetriever
            features['lat'] = float(item.features.get('lat', 0))
            features['lon'] = float(item.features.get('lon', 0))
            
            if item.price and features['surface_area_sqm']:
                features['price_per_sqm'] = item.price / features['surface_area_sqm']
                
        return features

    def _compute_deal_score(
        self,
        ask_price: float,
        fair_value_q50: float,
        fair_value_q10: float,
        fair_value_q90: float,
        rent_q50: float,
        missing_fields: int,
        weights: ScoringWeights
    ) -> tuple:
        """
        Compute deal score from predictions.
        
        Returns:
            (score, breakdown)
        """
        # Undervaluation: How much below median fair value
        undervaluation = (fair_value_q50 - ask_price) / ask_price if ask_price > 0 else 0
        
        # Yield proxy: Annual rent / price
        yield_proxy = (12 * rent_q50) / ask_price if ask_price > 0 else 0
        
        # Uncertainty penalty: Wide intervals = uncertain
        interval_width = (fair_value_q90 - fair_value_q10) / fair_value_q50 if fair_value_q50 > 0 else 1.0
        uncertainty_penalty = max(0, (interval_width - 0.2) * 2)  # Penalty above 20% width
        
        # Data quality penalty
        data_quality_penalty = missing_fields * 0.05
        
        # Weighted combination
        raw_score = (
            weights.undervaluation * undervaluation +
            weights.yield_proxy * yield_proxy -
            weights.uncertainty_penalty * uncertainty_penalty -
            weights.data_quality_penalty * data_quality_penalty
        )
        
        # Sigmoid normalization to [0, 1]
        import math
        score = 1.0 / (1.0 + math.exp(-5 * (raw_score - 0.05)))
        score = max(0.0, min(1.0, score))
        
        breakdown = ScoreBreakdown(
            undervaluation=undervaluation,
            yield_proxy=yield_proxy,
            uncertainty_penalty=uncertainty_penalty,
            data_quality_penalty=data_quality_penalty
        )
        
        return score, breakdown

    def _generate_thesis(
        self,
        score: float,
        fair_value_q50: float,
        ask_price: float,
        interval_width: float
    ) -> str:
        """Generate human-readable investment thesis."""
        delta_pct = ((fair_value_q50 - ask_price) / ask_price) * 100 if ask_price > 0 else 0
        
        if score >= 0.8:
            verdict = "Strong Buy Signal"
        elif score >= 0.6:
            verdict = "Potential Opportunity"
        elif score >= 0.4:
            verdict = "Fair Value"
        else:
            verdict = "Overpriced / High Risk"
            
        confidence = "High" if interval_width < 0.15 else ("Medium" if interval_width < 0.30 else "Low")
        
        return (
            f"{verdict}. Fair value estimate: {fair_value_q50:,.0f}€ "
            f"({delta_pct:+.1f}% vs ask). Confidence: {confidence}."
        )

    def _get_image_embedding(self, listing: Any) -> Optional[np.ndarray]:
        """Get or compute image embedding."""
        if not self._vision_encoder:
            return None
            
        # Check cache (schema update required listing.image_embeddings)
        if hasattr(listing, 'image_embeddings') and listing.image_embeddings:
            # Return mean of cached embeddings
            return np.mean(listing.image_embeddings, axis=0)
            
        # Compute if local paths exist (development mode)
        # In production this would fetch from URL or use pre-computed
        if hasattr(listing, 'image_urls') and listing.image_urls:
             # Basic placeholder: if URLs are local file paths
             local_paths = [u for u in listing.image_urls if os.path.exists(str(u))]
             if local_paths:
                 return self._vision_encoder.encode_images(local_paths)
                 
        return None

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        """
        Perform full evaluation of a listing.
        """
        self._ensure_loaded()
        listing = request.listing
        
        # 1. Retrieve comparables
        if request.forced_comps:
            comps = request.forced_comps
        else:
            comps = self._retriever.retrieve_comps(
                target=listing,
                k=request.num_comps,
                max_radius_km=request.geo_radius_km
            )
        
        # 2. Encode target
        # Mix VLM description if available
        desc = listing.description or ""
        if listing.vlm_description:
            desc = f"{desc} \nVision Context: {listing.vlm_description}"
            
        text = f"{listing.title or ''} {desc}"
        target_emb = self._encoder.encode_single(text)
        target_feats = self._extract_features(listing)
        target_tab = self._tab_encoder.encode(target_feats)
        target_img = self._get_image_embedding(listing)
        
        # 3. Encode comps and get prices
        comp_embeddings = []
        comp_tabulars = []
        comp_images = []
        comp_prices = []
        
        for c in comps:
            # Note: In production, we'd cache embeddings
            comp_emb = self._encoder.encode_single(str(c.id))
            comp_feats = self._extract_features(c)
            comp_tab = self._tab_encoder.encode(comp_feats)
            comp_img = self._get_image_embedding(c) # Usually None for comps unless cached
            
            comp_embeddings.append(comp_emb)
            comp_tabulars.append(comp_tab)
            comp_images.append(comp_img)
            comp_prices.append(c.price)
        
        # 4. Fusion model prediction
        fusion_output = self._fusion.predict(
            target_text_embedding=target_emb,
            target_tabular_features=target_tab,
            target_image_embedding=target_img,
            comp_text_embeddings=comp_embeddings,
            comp_tabular_features=comp_tabulars,
            comp_image_embeddings=comp_images,
            comp_prices=comp_prices
        )
        
        # Extract quantiles
        fv_q = fusion_output.price_quantiles
        rent_q = fusion_output.rent_quantiles
        
        # 5. Compute deal score
        missing_fields = sum([
            listing.bedrooms is None,
            listing.surface_area_sqm is None,
            0 if listing.location else 1,
            len(listing.image_urls or []) == 0
        ])
        
        # Resolve strategy
        strategy_name = request.strategy
        strategy = PRESET_STRATEGIES.get(strategy_name, PRESET_STRATEGIES["balanced"])
        
        score, breakdown = self._compute_deal_score(
            ask_price=listing.price,
            fair_value_q50=fv_q.get("0.5", listing.price),
            fair_value_q10=fv_q.get("0.1", listing.price * 0.9),
            fair_value_q90=fv_q.get("0.9", listing.price * 1.1),
            rent_q50=rent_q.get("0.5", listing.price * 0.004),
            missing_fields=missing_fields,
            weights=strategy.weights
        )
        
        # 6. Generate thesis
        interval_width = (fv_q.get("0.9", 0) - fv_q.get("0.1", 0)) / fv_q.get("0.5", 1) if fv_q.get("0.5") else 0.2
        thesis = self._generate_thesis(
            score=score,
            fair_value_q50=fv_q.get("0.5", listing.price),
            ask_price=listing.price,
            interval_width=interval_width
        )
        
        # 7. Build evidence
        evidence = Evidence(
            top_comps=[
                {
                    "id": c.id,
                    "price": c.price,
                    "similarity": c.similarity_score,
                    "snapshot_id": c.snapshot_id
                }
                for c in comps[:5]
            ],
            attention_weights=fusion_output.attention_weights.tolist() if fusion_output.attention_weights is not None else None,
            citations=[c.snapshot_id for c in comps if c.snapshot_id]
        )
        
        # 8. Flags
        flags = {
            "missing_images": len(listing.image_urls or []) == 0,
            "no_location": listing.location is None,
            "few_comps": len(comps) < 3,
            "high_uncertainty": interval_width > 0.30
        }
        
        return EvaluationResult(
            listing_id=listing.id,
            fair_value_quantiles=fv_q,
            rent_predicted_quantiles=rent_q,
            deal_score=score,
            score_breakdown=breakdown,
            investment_thesis=thesis,
            evidence=evidence,
            flags=flags,
            strategy_used=strategy_name
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
