"""
Fusion Model v2: Comp-Aware Multimodal Transformer (CAMT)

Predicts property fair value by reasoning over comparable listings using
cross-attention with learned modality gating and relative comp encoding.

Architecture:
1. GRN-based modality projectors (tab, text, image)
2. Gated modality fusion (learned per-modality importance)
3. Relative comp encoding (target-comp feature differences)
4. Stacked cross-attention layers with residual connections
5. Shared trunk → task-specific quantile prediction heads

Key improvements over v1:
- Gated fusion replaces naive concat (learns modality importance)
- Relative features encode target-comp relationships, not just raw features
- Stacked attention enables deeper comp reasoning
- GRN blocks throughout for better gradient flow and gating
- Batched comp encoding (no per-comp loop)
"""
import os
import json
import structlog
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from src.platform.config import FUSION_MODEL_PATH, FUSION_CONFIG_PATH

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

    class GatedResidualNetwork(nn.Module):
        """
        GRN building block (Lim et al., 2021).

        Applies ELU non-linearity, optional context injection, gated skip
        connection, and layer normalization.  Used throughout the model for
        feature processing — replaces plain Linear+ReLU blocks.
        """

        def __init__(
            self,
            input_dim: int,
            hidden_dim: int,
            output_dim: int,
            dropout: float = 0.1,
            context_dim: Optional[int] = None,
        ):
            super().__init__()
            self.fc1 = nn.Linear(input_dim, hidden_dim)
            self.context_proj = (
                nn.Linear(context_dim, hidden_dim, bias=False)
                if context_dim
                else None
            )
            self.fc2 = nn.Linear(hidden_dim, output_dim)
            self.gate = nn.Sequential(
                nn.Linear(hidden_dim, output_dim),
                nn.Sigmoid(),
            )
            self.skip = (
                nn.Linear(input_dim, output_dim)
                if input_dim != output_dim
                else nn.Identity()
            )
            self.layer_norm = nn.LayerNorm(output_dim)
            self.dropout = nn.Dropout(dropout)

        def forward(
            self, x: torch.Tensor, context: Optional[torch.Tensor] = None
        ) -> torch.Tensor:
            hidden = F.elu(self.fc1(x))
            if self.context_proj is not None and context is not None:
                hidden = hidden + self.context_proj(context)
            hidden = self.dropout(hidden)
            output = self.fc2(hidden)
            gate = self.gate(hidden)
            return self.layer_norm(gate * output + self.skip(x))


    class GatedModalityFusion(nn.Module):
        """
        Learns per-modality importance gates instead of naive concatenation.

        Given M modality embeddings each of dimension D, produces a single
        D-dimensional fused embedding where each modality's contribution is
        controlled by a learned softmax gate conditioned on all modalities.
        """

        def __init__(self, hidden_dim: int, num_modalities: int = 3, dropout: float = 0.1):
            super().__init__()
            self.num_modalities = num_modalities
            self.gate_network = nn.Sequential(
                nn.Linear(hidden_dim * num_modalities, hidden_dim),
                nn.ELU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, num_modalities),
                nn.Softmax(dim=-1),
            )
            self.output_grn = GatedResidualNetwork(
                hidden_dim, hidden_dim, hidden_dim, dropout
            )

        def forward(self, modalities: List[torch.Tensor]) -> torch.Tensor:
            """
            Args:
                modalities: list of (B, D) or (B, K, D) tensors — one per modality.
            Returns:
                Fused tensor of same shape as individual modalities.
            """
            concat = torch.cat(modalities, dim=-1)  # (..., D*M)
            gates = self.gate_network(concat)  # (..., M)
            stacked = torch.stack(modalities, dim=-1)  # (..., D, M)
            fused = (stacked * gates.unsqueeze(-2)).sum(dim=-1)  # (..., D)
            return self.output_grn(fused)


    class RelativeCompEncoder(nn.Module):
        """
        Encodes the *relationship* between target and each comp, not just the
        comp in isolation.

        Computes element-wise differences of z-scored tabular features between
        target and comp, projects them, and combines with the comp's fused
        embedding via a GRN.  This gives the attention mechanism explicit
        relational context (e.g. "this comp is larger", "this comp is farther
        away").
        """

        def __init__(self, tabular_dim: int, hidden_dim: int, dropout: float = 0.1):
            super().__init__()
            self.diff_proj = nn.Sequential(
                nn.Linear(tabular_dim, hidden_dim),
                nn.ELU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim),
            )
            self.combine = GatedResidualNetwork(
                hidden_dim * 2, hidden_dim, hidden_dim, dropout
            )

        def forward(
            self,
            comp_emb: torch.Tensor,
            target_tab: torch.Tensor,
            comp_tab: torch.Tensor,
        ) -> torch.Tensor:
            """
            Args:
                comp_emb:   (B, K, D) — fused comp embeddings
                target_tab: (B, T) — target tabular features (z-scored)
                comp_tab:   (B, K, T) — comp tabular features (z-scored)
            Returns:
                (B, K, D) — relation-enriched comp embeddings
            """
            # Element-wise difference: how does each comp compare to the target?
            target_expanded = target_tab.unsqueeze(1).expand_as(comp_tab)  # (B, K, T)
            diff = target_expanded - comp_tab  # (B, K, T)
            diff_emb = self.diff_proj(diff)  # (B, K, D)

            combined = torch.cat([comp_emb, diff_emb], dim=-1)  # (B, K, 2D)
            B, K, _ = combined.shape
            out = self.combine(combined.reshape(B * K, -1))
            return out.reshape(B, K, -1)


    class CrossAttentionLayer(nn.Module):
        """Single cross-attention layer with pre-norm and residual."""

        def __init__(self, hidden_dim: int, num_heads: int, dropout: float = 0.1):
            super().__init__()
            self.norm_q = nn.LayerNorm(hidden_dim)
            self.norm_kv = nn.LayerNorm(hidden_dim)
            self.attn = nn.MultiheadAttention(
                embed_dim=hidden_dim,
                num_heads=num_heads,
                dropout=dropout,
                batch_first=True,
            )
            self.ff = GatedResidualNetwork(hidden_dim, hidden_dim * 2, hidden_dim, dropout)

        def forward(
            self,
            query: torch.Tensor,
            key_value: torch.Tensor,
            need_weights: bool = False,
        ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
            q = self.norm_q(query)
            kv = self.norm_kv(key_value)
            attn_out, attn_weights = self.attn(
                query=q, key=kv, value=kv, need_weights=need_weights
            )
            x = query + attn_out  # residual
            x = self.ff(x)  # feed-forward with gating
            return x, attn_weights


    class PropertyFusionModel(nn.Module):
        """
        Comp-Aware Multimodal Transformer for property valuation.

        Architecture:
        1. GRN-based modality projectors → hidden_dim per modality
        2. Gated modality fusion → single embedding per listing
        3. Relative comp encoder → relation-aware comp embeddings
        4. Stacked cross-attention (target queries comps)
        5. Shared trunk → quantile prediction heads

        Predictions are RESIDUALS relative to attention-weighted comp prices,
        anchoring outputs to actual market values.
        """

        def __init__(
            self,
            tabular_dim: int = 11,
            text_dim: int = 384,
            image_dim: int = 512,
            hidden_dim: int = 128,
            num_heads: int = 4,
            num_quantiles: int = 3,
            num_attention_layers: int = 2,
            dropout: float = 0.15,
        ):
            super().__init__()

            self.hidden_dim = hidden_dim
            self.num_quantiles = num_quantiles
            self.tabular_dim = tabular_dim

            # --- Modality projectors (GRN-based) ---
            self.tab_proj = GatedResidualNetwork(tabular_dim, hidden_dim, hidden_dim, dropout)
            self.text_proj = GatedResidualNetwork(text_dim, hidden_dim, hidden_dim, dropout)
            self.image_proj = GatedResidualNetwork(image_dim, hidden_dim, hidden_dim, dropout)

            # --- Gated modality fusion ---
            self.modality_fusion = GatedModalityFusion(hidden_dim, num_modalities=3, dropout=dropout)

            # --- Relative comp encoder ---
            self.rel_comp_encoder = RelativeCompEncoder(tabular_dim, hidden_dim, dropout)

            # --- Stacked cross-attention ---
            self.cross_attention_layers = nn.ModuleList([
                CrossAttentionLayer(hidden_dim, num_heads, dropout)
                for _ in range(num_attention_layers)
            ])

            # --- Shared trunk ---
            self.trunk = GatedResidualNetwork(hidden_dim, hidden_dim * 2, hidden_dim, dropout)

            # --- Task-specific prediction heads ---
            self.price_head = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ELU(),
                nn.Linear(hidden_dim // 2, num_quantiles),
            )
            self.rent_head = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ELU(),
                nn.Linear(hidden_dim // 2, num_quantiles),
            )
            self.time_head = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ELU(),
                nn.Linear(hidden_dim // 2, num_quantiles),
            )
            self.uncertainty_head = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 4),
                nn.ELU(),
                nn.Linear(hidden_dim // 4, 1),
                nn.Softplus(),
            )

        def _encode_modalities(
            self,
            tab: torch.Tensor,
            text: torch.Tensor,
            image: Optional[torch.Tensor] = None,
        ) -> torch.Tensor:
            """
            Encode a listing (or batch of listings) from all modalities.

            Args:
                tab:   (*, tabular_dim)
                text:  (*, text_dim)
                image: (*, image_dim) or None
            Returns:
                (*, hidden_dim) fused embedding
            """
            tab_emb = self.tab_proj(tab)
            text_emb = self.text_proj(text)
            image_emb = (
                self.image_proj(image)
                if image is not None
                else torch.zeros_like(tab_emb)
            )
            return self.modality_fusion([tab_emb, text_emb, image_emb])

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
            comp_doms: Optional[torch.Tensor] = None,
            output_mode: str = "price",
        ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
            """
            Forward pass with retrieval-augmented reasoning.

            Predicts RESIDUALS relative to attention-weighted comp prices.

            Args:
                target_*:  Target listing features — (B, feature_dim)
                comp_*:    Comp features — (B, K, feature_dim)
                comp_prices: Actual prices of comps — (B, K)
                return_attention: Return attention weights for interpretability
                comp_doms: Days on market per comp — (B, K) or None
                output_mode: "price" for absolute prices, "residual" for raw residuals

            Returns:
                price_quantiles: (B, 3)
                rent_quantiles:  (B, 3)
                time_quantiles:  (B, 3)
                attention_weights: (B, K) or None
            """
            batch_size = target_tab.shape[0]
            num_comps = comp_tab.shape[1]

            # --- Encode target ---
            target_emb = self._encode_modalities(
                target_tab, target_text, target_image
            )  # (B, D)
            target_emb = target_emb.unsqueeze(1)  # (B, 1, D)

            # --- Encode comps (batched, no loop) ---
            B, K, _ = comp_tab.shape
            comp_tab_flat = comp_tab.reshape(B * K, -1)
            comp_text_flat = comp_text.reshape(B * K, -1)
            comp_image_flat = (
                comp_image.reshape(B * K, -1) if comp_image is not None else None
            )
            comp_emb_flat = self._encode_modalities(
                comp_tab_flat, comp_text_flat, comp_image_flat
            )  # (B*K, D)
            comp_emb = comp_emb_flat.reshape(B, K, -1)  # (B, K, D)

            # --- Relative comp encoding ---
            comp_emb = self.rel_comp_encoder(comp_emb, target_tab, comp_tab)

            # --- Stacked cross-attention ---
            attn_weights = None
            x = target_emb
            for i, layer in enumerate(self.cross_attention_layers):
                need_w = return_attention and (i == len(self.cross_attention_layers) - 1)
                x, w = layer(x, comp_emb, need_weights=need_w)
                if w is not None:
                    attn_weights = w.squeeze(1)  # (B, K)

            # --- Shared trunk ---
            reasoned = self.trunk(x.squeeze(1))  # (B, D)

            # --- Price prediction (residual) ---
            price_residuals = self.price_head(reasoned)  # (B, 3)

            # Attention-weighted comp price anchor
            if attn_weights is None:
                # If we didn't collect weights, compute them from last layer
                with torch.no_grad():
                    _, w = self.cross_attention_layers[-1](
                        self.trunk(x.squeeze(1)).unsqueeze(1),
                        comp_emb,
                        need_weights=True,
                    )
                    anchor_weights = w.squeeze(1)
            else:
                anchor_weights = attn_weights

            price_anchor = (anchor_weights * comp_prices).sum(dim=-1, keepdim=True)

            if output_mode == "residual":
                price_q = price_residuals
            else:
                price_std = comp_prices.std(dim=-1, keepdim=True).clamp(min=1000)
                price_q = price_anchor + price_residuals * price_std

            # --- Rent prediction ---
            rent_residuals = self.rent_head(reasoned)  # (B, 3)
            rent_base = price_anchor * 0.004
            rent_std = rent_base.abs() * 0.3
            rent_q = rent_base + rent_residuals * rent_std

            # --- Time to sell prediction ---
            time_residuals = self.time_head(reasoned)
            if comp_doms is not None and comp_doms.numel() > 0:
                time_base = comp_doms.mean(dim=-1, keepdim=True).clamp(min=10.0)
            else:
                time_base = torch.full_like(price_anchor, 90.0)
            time_q = time_base + time_residuals * 30.0

            if return_attention:
                return price_q, rent_q, time_q, anchor_weights
            return price_q, rent_q, time_q, None


    class QuantileLoss(nn.Module):
        """
        Pinball loss for quantile regression.

        Supports optional per-sample weights and monotonicity regularization
        to discourage quantile crossing (q10 > q50 or q50 > q90).
        """

        def __init__(
            self,
            quantiles: List[float] = [0.1, 0.5, 0.9],
            crossing_penalty: float = 0.1,
        ):
            super().__init__()
            self.quantiles = quantiles
            self.crossing_penalty = crossing_penalty

        def forward(
            self,
            predictions: torch.Tensor,
            targets: torch.Tensor,
            weights: Optional[torch.Tensor] = None,
        ) -> torch.Tensor:
            """
            Args:
                predictions: (B, Q)
                targets: (B,)
                weights: (B,) optional per-sample weights
            Returns:
                scalar loss
            """
            targets = targets.unsqueeze(-1)  # (B, 1)
            errors = targets - predictions  # (B, Q)

            losses = []
            for i, q in enumerate(self.quantiles):
                error = errors[:, i]
                loss = torch.where(error >= 0, q * error, (q - 1) * error)
                if weights is not None:
                    loss = loss * weights
                losses.append(loss.mean())

            total = sum(losses) / len(losses)

            # Monotonicity regularization: penalize quantile crossing
            if self.crossing_penalty > 0 and len(self.quantiles) >= 2:
                for i in range(len(self.quantiles) - 1):
                    crossing = F.relu(predictions[:, i] - predictions[:, i + 1])
                    total = total + self.crossing_penalty * crossing.mean()

            return total


class FusionModelService:
    """
    Service wrapper for the Fusion Model.
    Handles loading, inference, and model management.
    """
    def __init__(
        self,
        model_path: str = str(FUSION_MODEL_PATH),
        config_path: str = str(FUSION_CONFIG_PATH)
    ):
        self.model_path = model_path
        self.config_path = config_path
        self.model = None
        self.config = {}
        self.device = "cpu"

        # Load config even when torch is unavailable so downstream services can
        # still read `target_mode` / retriever metadata and fall back cleanly.
        self._load_config()

        if TORCH_AVAILABLE:
            self._try_load_model()

    def _load_config(self) -> None:
        if not os.path.exists(self.config_path):
            logger.warning("fusion_config_missing", path=self.config_path)
            self.config = {}
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception as exc:
            logger.warning("fusion_config_load_failed", path=self.config_path, error=str(exc))
            self.config = {}

    def _try_load_model(self) -> None:
        """Best-effort model load. Missing artifacts should not crash the app."""
        if not self.config:
            return

        try:
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
        except Exception as exc:
            logger.warning("torch_thread_config_failed", error=str(exc))

        required = {"tabular_dim", "text_dim", "image_dim", "hidden_dim", "num_heads"}
        missing = required.difference(self.config.keys())
        if missing:
            logger.warning("fusion_config_incomplete", missing=sorted(missing))
            return

        self.model = PropertyFusionModel(
            tabular_dim=self.config["tabular_dim"],
            text_dim=self.config["text_dim"],
            image_dim=self.config["image_dim"],
            hidden_dim=self.config["hidden_dim"],
            num_heads=self.config["num_heads"],
            num_attention_layers=self.config.get("num_attention_layers", 2),
            dropout=self.config.get("dropout", 0.15),
        )

        if not os.path.exists(self.model_path):
            logger.warning("fusion_model_missing", path=self.model_path)
            self.model = None
            return

        try:
            self.model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
            logger.info("fusion_model_loaded", path=self.model_path)
        except Exception as exc:
            logger.warning("fusion_model_load_failed", path=self.model_path, error=str(exc))
            self.model = None
            return

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
        comp_doms: List[float] = None,
        output_mode: str = "price"
    ) -> FusionOutput:
        """
        Make predictions for a target listing.

        Args:
            target_text_embedding: Text embedding (384D)
            target_tabular_features: Tabular features (11D)
            target_image_embedding: Optional image embedding (512D)
            comp_text_embeddings: List of comp text embeddings
            comp_tabular_features: List of comp tabular features
            comp_image_embeddings: List of comp image embeddings
            comp_prices: Actual prices of comparables
            comp_doms: Days on market per comp
            output_mode: "price" or "residual"

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
            valid_emb = np.zeros(self.config.get("image_dim", 512))
            clean_list = []
            for item in comp_image_embeddings[:num_comps]:
                if item is not None:
                    clean_list.append(torch.from_numpy(item).float())
                    valid_emb = item
                else:
                    dim = valid_emb.shape[0] if hasattr(valid_emb, 'shape') else 512
                    clean_list.append(torch.zeros(dim).float())
            comp_image = torch.stack(clean_list).unsqueeze(0)

        comp_prices_t = torch.tensor([comp_prices[:num_comps]])

        # Prepare DOMs
        comp_doms_t = None
        if comp_doms:
            valid_doms = comp_doms[:num_comps]
            if not valid_doms:
                valid_doms = [90.0]
            comp_doms_t = torch.tensor([valid_doms]).float()

        with torch.no_grad():
            price_q, rent_q, time_q, attn = self.model(
                target_tab, target_text, target_image,
                comp_tab, comp_text, comp_image,
                comp_prices_t,
                return_attention=True,
                comp_doms=comp_doms_t,
                output_mode=output_mode
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
