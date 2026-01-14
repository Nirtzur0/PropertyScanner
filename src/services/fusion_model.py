"""
Fusion Model: The "Brain" that reasons over multimodal data.
Uses Cross-Attention between target listing and comparable listings.
"""
import os
import json
import structlog
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

logger = structlog.get_logger()

# PyTorch imports (lazy for optional dependency)
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("pytorch_not_available", msg="Fusion model disabled. Install with: pip install torch")


@dataclass
class FusionOutput:
    """Output from the fusion model."""
    price_quantiles: Dict[str, float]  # {"0.1": val, "0.5": val, "0.9": val}
    rent_quantiles: Dict[str, float]
    time_to_sell_quantiles: Optional[Dict[str, float]] = None
    attention_weights: Optional[np.ndarray] = None  # For interpretability


if TORCH_AVAILABLE:
    class TabularMLP(nn.Module):
        """Simple MLP for tabular features."""
        def __init__(self, input_dim: int, hidden_dim: int = 64, output_dim: int = 128):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim, output_dim),
                nn.LayerNorm(output_dim)
            )
            
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.net(x)


    class PropertyFusionModel(nn.Module):
        """
        Cross-Attention Fusion Model for property valuation.
        
        Architecture:
        1. Project all modalities to shared dimension
        2. Target listing = Query
        3. Comparable listings = Keys and Values
        4. Cross-attention to aggregate information from comps
        5. Quantile prediction heads
        """
        def __init__(
            self,
            tabular_dim: int = 11,
            text_dim: int = 384,
            image_dim: int = 512,
            hidden_dim: int = 64,  # Reduced from 256 for smaller model
            num_heads: int = 2,    # Reduced from 4
            num_quantiles: int = 3  # 0.1, 0.5, 0.9
        ):
            super().__init__()
            
            self.hidden_dim = hidden_dim
            self.num_quantiles = num_quantiles
            
            # Modality Projectors (simplified)
            self.tab_proj = nn.Sequential(
                nn.Linear(tabular_dim, hidden_dim),
                nn.ReLU(),
                nn.LayerNorm(hidden_dim)
            )
            self.text_proj = nn.Linear(text_dim, hidden_dim)
            # Note: image_proj kept for compatibility but VLM text is primary
            self.image_proj = nn.Linear(image_dim, hidden_dim)
            
            # Modality fusion (simplified)
            self.modality_fusion = nn.Sequential(
                nn.Linear(hidden_dim * 3, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.LayerNorm(hidden_dim)
            )
            
            # Cross-Attention: Target attends to Comps
            self.cross_attention = nn.MultiheadAttention(
                embed_dim=hidden_dim,
                num_heads=num_heads,
                dropout=0.2,
                batch_first=True
            )
            
            # Post-attention processing (simplified)
            self.post_attn = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2)
            )
            
            # Prediction Heads (Quantile Regression)
            self.price_head = nn.Linear(hidden_dim, num_quantiles)
            self.rent_head = nn.Linear(hidden_dim, num_quantiles)
            self.time_head = nn.Linear(hidden_dim, num_quantiles)
            
            # Uncertainty head (predicts interval width)
            self.uncertainty_head = nn.Linear(hidden_dim, 1)

        def _encode_listing(
            self,
            tab: torch.Tensor,
            text: torch.Tensor,
            image: Optional[torch.Tensor] = None
        ) -> torch.Tensor:
            """Encode a single listing from all modalities."""
            # Project each modality
            tab_emb = self.tab_proj(tab)
            text_emb = self.text_proj(text)
            
            if image is not None:
                image_emb = self.image_proj(image)
            else:
                # Zero vector for missing images
                image_emb = torch.zeros_like(text_emb)
                
            # Concat and fuse
            combined = torch.cat([tab_emb, text_emb, image_emb], dim=-1)
            fused = self.modality_fusion(combined)
            
            return fused

        def forward(
            self,
            target_tab: torch.Tensor,
            target_text: torch.Tensor,
            target_image: Optional[torch.Tensor],
            comp_tab: torch.Tensor,
            comp_text: torch.Tensor,
            comp_image: Optional[torch.Tensor],

            comp_prices: torch.Tensor,
            return_attention: bool = False,
            comp_doms: Optional[torch.Tensor] = None
        ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
            """
            Forward pass with retrieval-augmented reasoning.
            
            The model predicts RESIDUALS relative to the attention-weighted comp prices,
            which anchors predictions to the actual market values of comparables.
            
            Args:
                target_*: Target listing features (batch_size, feature_dim)
                comp_*: Comp features (batch_size, num_comps, feature_dim)
                comp_prices: Actual prices of comps (batch_size, num_comps)
                return_attention: Whether to return attention weights
                
            Returns:
                price_quantiles: (batch_size, 3) - actual price predictions
                rent_quantiles: (batch_size, 3)
                time_quantiles: (batch_size, 3)
                attention_weights: Optional (batch_size, num_comps)
            """
            batch_size = target_tab.shape[0]
            num_comps = comp_tab.shape[1]
            
            # Encode target listing
            target_emb = self._encode_listing(target_tab, target_text, target_image)
            target_emb = target_emb.unsqueeze(1)  # (B, 1, D)
            
            # Encode all comps
            comp_embs = []
            for i in range(num_comps):
                comp_i = self._encode_listing(
                    comp_tab[:, i],
                    comp_text[:, i],
                    comp_image[:, i] if comp_image is not None else None
                )
                comp_embs.append(comp_i)
            comp_emb = torch.stack(comp_embs, dim=1)  # (B, K, D)
            
            # Cross-attention: Target queries the Comps
            attn_out, attn_weights = self.cross_attention(
                query=target_emb,
                key=comp_emb,
                value=comp_emb,
                need_weights=True
            )
            attn_weights = attn_weights.squeeze(1)  # (B, K)
            
            # Compute attention-weighted comp price as anchor
            # This gives us a baseline prediction based on similar comps
            price_anchor = (attn_weights * comp_prices).sum(dim=-1, keepdim=True)  # (B, 1)
            price_std = comp_prices.std(dim=-1, keepdim=True).clamp(min=1000)  # (B, 1)
            
            # Residual connection
            reasoned = target_emb + attn_out
            reasoned = self.post_attn(reasoned.squeeze(1))  # (B, D)
            
            # Predict RESIDUALS (adjustments) as fraction of price std
            price_residuals = self.price_head(reasoned)  # (B, 3)
            
            # Final price = anchor + (residual * std)
            # This ensures predictions are in the right scale
            price_q = price_anchor + price_residuals * price_std
            
            # Rent prediction: ~0.4% of price per month (European average)
            rent_base = price_anchor * 0.004
            rent_residuals = self.rent_head(reasoned)
            rent_std = rent_base * 0.2  # 20% variation
            rent_q = rent_base + rent_residuals * rent_std
            
            # Time to sell (days) - base depends on market velocity
            # If we know the DOM of comps, we use their average as the baseline
            if comp_doms is not None and len(comp_doms) > 0:
                 # Calculate mean of valid DOMs (ignore -1 or None if passed as tensor)
                 # Here assuming comp_doms is a tensor of shape (B, K)
                 # Simplified: take the mean of the anchor price concept but for time
                 time_base = comp_doms.mean(dim=-1, keepdim=True).clamp(min=10.0) # (B, 1)
            else:
                 time_base = torch.full_like(price_anchor, 90.0)
            
            time_residuals = self.time_head(reasoned)
            time_q = time_base + time_residuals * 30.0  # +/- 30 days adjustment
            
            if return_attention:
                return price_q, rent_q, time_q, attn_weights
            return price_q, rent_q, time_q, None


    class QuantileLoss(nn.Module):
        """Pinball loss for quantile regression."""
        def __init__(self, quantiles: List[float] = [0.1, 0.5, 0.9]):
            super().__init__()
            self.quantiles = quantiles
            
        def forward(self, predictions: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
            """
            Compute pinball loss.
            
            Args:
                predictions: (batch_size, num_quantiles)
                targets: (batch_size,) - actual values
                
            Returns:
                scalar loss
            """
            targets = targets.unsqueeze(-1)  # (B, 1)
            errors = targets - predictions  # (B, Q)
            
            losses = []
            for i, q in enumerate(self.quantiles):
                error = errors[:, i]
                loss = torch.where(
                    error >= 0,
                    q * error,
                    (q - 1) * error
                )
                losses.append(loss.mean())
                
            return sum(losses) / len(losses)


class FusionModelService:
    """
    Service wrapper for the Fusion Model.
    Handles loading, inference, and model management.
    """
    def __init__(
        self,
        model_path: str = "models/fusion_model.pt",
        config_path: str = "models/fusion_config.json"
    ):
        self.model_path = model_path
        self.config_path = config_path
        self.model = None
        self.config = {}
        self.device = "cpu"
        
        if TORCH_AVAILABLE:
            self._load_or_init()

    def _load_or_init(self):
        """Load existing model or initialize a new one."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError("fusion_config_missing")

        with open(self.config_path, "r") as f:
            self.config = json.load(f)

        required = {"tabular_dim", "text_dim", "image_dim", "hidden_dim", "num_heads"}
        missing = required.difference(self.config.keys())
        if missing:
            raise ValueError("fusion_config_incomplete")

        self.model = PropertyFusionModel(
            tabular_dim=self.config["tabular_dim"],
            text_dim=self.config["text_dim"],
            image_dim=self.config["image_dim"],
            hidden_dim=self.config["hidden_dim"],
            num_heads=self.config["num_heads"]
        )
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError("fusion_model_missing")

        self.model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
        logger.info("fusion_model_loaded", path=self.model_path)
            
        self.model.eval()

    def predict(
        self,
        target_text_embedding: np.ndarray,
        target_tabular_features: np.ndarray,
        target_image_embedding: Optional[np.ndarray],
        comp_text_embeddings: List[np.ndarray],
        comp_tabular_features: List[np.ndarray],
        comp_image_embeddings: List[np.ndarray],

        comp_prices: List[float],
        comp_doms: List[float] = None # Added inputs
    ) -> FusionOutput:
        """
        Make predictions for a target listing.
        
        Args:
            target_text_embedding: Text embedding (384D)
            target_tabular_features: Tabular features (8D)
            target_image_embedding: Optional image embedding (512D)
            comp_text_embeddings: List of comp text embeddings
            comp_tabular_features: List of comp tabular features
            comp_image_embeddings: List of comp image embeddings
            comp_prices: Actual prices of comparables
            
        Returns:
            FusionOutput with quantile predictions
        """
        if not TORCH_AVAILABLE or self.model is None:
            raise RuntimeError("fusion_model_unavailable")

        if not comp_text_embeddings or not comp_tabular_features or not comp_prices:
            raise ValueError("missing_comps_for_fusion")

        if len(comp_text_embeddings) != len(comp_tabular_features) or len(comp_text_embeddings) != len(comp_prices):
            raise ValueError("mismatched_comp_inputs")
        if comp_image_embeddings and len(comp_image_embeddings) != len(comp_text_embeddings):
            raise ValueError("mismatched_comp_image_inputs")
        
        # Prepare target tensors
        target_tab = torch.from_numpy(target_tabular_features).unsqueeze(0).float()
        target_text = torch.from_numpy(target_text_embedding).unsqueeze(0).float()
        target_image = None
        if target_image_embedding is not None:
            target_image = torch.from_numpy(target_image_embedding).unsqueeze(0).float()
        
        # Prepare comp tensors
        num_comps = min(len(comp_text_embeddings), 10)
        if num_comps == 0:
            raise ValueError("missing_comps_for_fusion")
            
        comp_tab = torch.stack([
            torch.from_numpy(f).float() for f in comp_tabular_features[:num_comps]
        ]).unsqueeze(0)
        comp_text = torch.stack([
            torch.from_numpy(e).float() for e in comp_text_embeddings[:num_comps]
        ]).unsqueeze(0)
        
        comp_image = None
        if comp_image_embeddings and any(x is not None for x in comp_image_embeddings):
            # Handle potentially mixed None/Array list
            valid_emb = np.zeros(self.config.get("image_dim", 512))
            clean_list = []
            for item in comp_image_embeddings[:num_comps]:
                if item is not None:
                    clean_list.append(torch.from_numpy(item).float())
                    valid_emb = item # Keep for shape
                else:
                    # Pad with zeros if missing
                    dim = valid_emb.shape[0] if hasattr(valid_emb, 'shape') else 512
                    clean_list.append(torch.zeros(dim).float())
            comp_image = torch.stack(clean_list).unsqueeze(0)

        comp_prices_t = torch.tensor([comp_prices[:num_comps]])
        
        # Prepare DOMs
        comp_doms_t = None
        if comp_doms:
            # Handle potentially fewer comps
            valid_doms = comp_doms[:num_comps]
            if not valid_doms: valid_doms = [90.0]
            comp_doms_t = torch.tensor([valid_doms]).float() # (1, K)

        with torch.no_grad():
            price_q, rent_q, time_q, attn = self.model(
                target_tab, target_text, target_image,
                comp_tab, comp_text, comp_image,
                comp_prices_t,
                return_attention=True,
                comp_doms=comp_doms_t
            )
        
        return FusionOutput(
            price_quantiles={
                "0.1": float(price_q[0, 0]),
                "0.5": float(price_q[0, 1]),
                "0.9": float(price_q[0, 2])
            },
            rent_quantiles={
                "0.1": float(rent_q[0, 0]),
                "0.5": float(rent_q[0, 1]),
                "0.9": float(rent_q[0, 2])
            },
            time_to_sell_quantiles={
                "0.1": float(time_q[0, 0]),
                "0.5": float(time_q[0, 1]),
                "0.9": float(time_q[0, 2])
            },
            attention_weights=attn.numpy() if attn is not None else None
        )

    def save(self):
        """Save model and config."""
        if not TORCH_AVAILABLE or self.model is None:
            return
            
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        torch.save(self.model.state_dict(), self.model_path)
        
        with open(self.config_path, "w") as f:
            json.dump(self.config, f)
            
        logger.info("fusion_model_saved", path=self.model_path)
