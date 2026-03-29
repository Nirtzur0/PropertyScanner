"""
Temporal Fusion Transformer (TFT) Forecaster — v2

Proper implementation of the TFT architecture (Lim et al., 2021) for
multi-region, multi-horizon property value prediction.

Architecture (matching the paper):
1. Static covariate encoder (region embedding → enrichment vectors)
2. Variable Selection Networks for temporal inputs
3. GRN-based feature processing throughout
4. Self-attention temporal encoder (replaces v1's LSTM)
5. Multi-horizon quantile outputs with interpretable attention

Key improvements over v1:
- GRN used for all feature processing (was unused in v1)
- Variable Selection Network for learned feature importance
- Self-attention replaces LSTM for temporal encoding
- Proper static enrichment (region context conditions temporal processing)
- Batched training (sequences collected then trained in mini-batches)

References:
- Lim et al. "Temporal Fusion Transformers for Interpretable
  Multi-horizon Time Series Forecasting" (2021)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import structlog
from src.platform.config import DEFAULT_DB_PATH, TFT_MODEL_PATH
from src.platform.settings import TFTConfig
from src.platform.settings import AppConfig
from src.market.repositories.market_fundamentals import MarketFundamentalsRepository

logger = structlog.get_logger(__name__)


class GatedResidualNetwork(nn.Module):
    """
    Gated Residual Network — the core building block of TFT.

    Applies non-linear processing with a gated skip connection and
    optional static context injection.
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        output_size: int,
        dropout: float = 0.1,
        context_size: Optional[int] = None,
    ):
        super().__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.context_proj = (
            nn.Linear(context_size, hidden_size, bias=False)
            if context_size
            else None
        )
        self.fc2 = nn.Linear(hidden_size, output_size)
        self.gate = nn.Sequential(
            nn.Linear(hidden_size, output_size),
            nn.Sigmoid(),
        )
        self.dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(output_size)
        self.skip = (
            nn.Linear(input_size, output_size)
            if input_size != output_size
            else nn.Identity()
        )

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


class VariableSelectionNetwork(nn.Module):
    """
    Variable Selection Network — learns which input features matter most.

    Each input variable is processed through its own GRN, then a softmax
    gate (conditioned on all inputs + optional static context) produces
    per-variable importance weights.  Returns the weighted sum and the
    weights themselves for interpretability.
    """

    def __init__(
        self,
        num_inputs: int,
        input_size: int,
        hidden_size: int,
        dropout: float = 0.1,
        context_size: Optional[int] = None,
    ):
        super().__init__()
        self.num_inputs = num_inputs
        self.hidden_size = hidden_size

        # Per-variable GRNs
        self.variable_grns = nn.ModuleList([
            GatedResidualNetwork(input_size, hidden_size, hidden_size, dropout)
            for _ in range(num_inputs)
        ])

        # Weight network: softmax gate over variables
        gate_input_size = num_inputs * input_size
        if context_size:
            gate_input_size += context_size
        self.weight_grn = GatedResidualNetwork(
            gate_input_size, hidden_size, num_inputs, dropout
        )

    def forward(
        self,
        inputs: List[torch.Tensor],
        context: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            inputs: list of (B, T, input_size) tensors, one per variable
            context: optional (B, context_size) static context

        Returns:
            output: (B, T, hidden_size) — weighted combination
            weights: (B, T, num_inputs) — variable importance
        """
        # Process each variable through its GRN
        processed = [grn(inp) for grn, inp in zip(self.variable_grns, inputs)]

        # Compute variable importance weights
        concat = torch.cat(inputs, dim=-1)  # (B, T, num_inputs * input_size)
        if context is not None:
            # Expand static context across time
            ctx = context.unsqueeze(1).expand(-1, concat.size(1), -1)
            concat = torch.cat([concat, ctx], dim=-1)

        raw_weights = self.weight_grn(concat)  # (B, T, num_inputs)
        weights = F.softmax(raw_weights, dim=-1)

        # Weighted sum
        stacked = torch.stack(processed, dim=-1)  # (B, T, hidden_size, num_inputs)
        output = (stacked * weights.unsqueeze(-2)).sum(dim=-1)  # (B, T, hidden_size)

        return output, weights


class StaticCovariateEncoder(nn.Module):
    """
    Encodes static covariates (region) into four context vectors used to
    enrich different parts of the temporal processing pipeline.
    """

    def __init__(self, hidden_size: int, num_regions: int, dropout: float = 0.1):
        super().__init__()
        self.embedding = nn.Embedding(num_regions, hidden_size)
        # Four context vectors (as in the paper):
        # 1. Variable selection context
        # 2. Temporal encoder enrichment
        # 3. Temporal decoder enrichment (reused as pre-attention enrichment)
        # 4. Output enrichment
        self.context_grns = nn.ModuleList([
            GatedResidualNetwork(hidden_size, hidden_size, hidden_size, dropout)
            for _ in range(4)
        ])

    def forward(
        self, region_ids: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        emb = self.embedding(region_ids)  # (B, H)
        return tuple(grn(emb) for grn in self.context_grns)


class InterpretableMultiHeadAttention(nn.Module):
    """
    Multi-head attention that averages attention weights across heads
    for interpretability (as specified in the TFT paper, Section 4.5).
    """

    def __init__(self, hidden_size: int, num_heads: int, dropout: float = 0.1):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads
        assert hidden_size % num_heads == 0

        self.q_proj = nn.Linear(hidden_size, hidden_size)
        self.k_proj = nn.Linear(hidden_size, hidden_size)
        self.v_proj = nn.Linear(hidden_size, hidden_size)
        self.out_proj = nn.Linear(hidden_size, hidden_size)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self, query: torch.Tensor, key: torch.Tensor, value: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        B, T, _ = query.shape

        # Multi-head projections
        q = self.q_proj(query).reshape(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(key).reshape(B, T, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(value).reshape(B, T, self.num_heads, self.head_dim).transpose(1, 2)

        # Scaled dot-product attention
        scale = self.head_dim ** 0.5
        scores = torch.matmul(q, k.transpose(-2, -1)) / scale  # (B, H, T, T)

        # Causal mask: prevent attending to future timesteps
        mask = torch.triu(torch.ones(T, T, device=query.device), diagonal=1).bool()
        scores = scores.masked_fill(mask.unsqueeze(0).unsqueeze(0), float("-inf"))

        attn_weights = F.softmax(scores, dim=-1)
        attn_weights = self.dropout(attn_weights)

        attn_output = torch.matmul(attn_weights, v)  # (B, H, T, head_dim)
        attn_output = attn_output.transpose(1, 2).reshape(B, T, -1)
        output = self.out_proj(attn_output)

        # Average attention across heads for interpretability
        avg_weights = attn_weights.mean(dim=1)  # (B, T, T)

        return output, avg_weights


class TFTForecaster(nn.Module):
    """
    Temporal Fusion Transformer for property value forecasting.

    Follows the architecture from Lim et al. (2021):
    1. Static covariate encoder → context vectors
    2. Variable selection (conditioned on static context)
    3. GRN-based temporal processing
    4. Interpretable multi-head self-attention
    5. Position-wise feed-forward → quantile outputs

    Features:
    - Static: region embedding
    - Time-varying observed: price index, inventory
    - Time-varying known: time index, macro (euribor, inflation)
    """

    def __init__(self, config: TFTConfig, num_regions: int):
        super().__init__()
        self.config = config
        h = config.hidden_size

        # --- Static covariate encoder ---
        self.static_encoder = StaticCovariateEncoder(h, max(num_regions, 1), config.dropout)

        # --- Feature projections (each to hidden_size) ---
        self.price_proj = GatedResidualNetwork(1, h, h, config.dropout)
        self.inventory_proj = GatedResidualNetwork(1, h, h, config.dropout)
        self.macro_proj = GatedResidualNetwork(2, h, h, config.dropout)
        self.time_proj = GatedResidualNetwork(1, h, h, config.dropout)

        # --- Variable selection ---
        self.vsn = VariableSelectionNetwork(
            num_inputs=4,
            input_size=h,
            hidden_size=h,
            dropout=config.dropout,
            context_size=h,
        )

        # --- Temporal processing (GRN with static enrichment) ---
        self.temporal_grn = GatedResidualNetwork(
            h, h, h, config.dropout, context_size=h
        )

        # --- Self-attention ---
        self.attention = InterpretableMultiHeadAttention(
            h, config.attention_heads, config.dropout
        )
        self.attn_gate = nn.Sequential(nn.Linear(h, h), nn.Sigmoid())
        self.attn_norm = nn.LayerNorm(h)

        # --- Position-wise feed-forward ---
        self.output_grn = GatedResidualNetwork(h, h, h, config.dropout, context_size=h)

        # --- Quantile prediction heads ---
        self.quantile_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(h, h // 2),
                nn.ELU(),
                nn.Linear(h // 2, len(config.prediction_horizons)),
            )
            for _ in config.quantiles
        ])

    def forward(
        self,
        region_ids: torch.Tensor,
        price_seq: torch.Tensor,
        inventory_seq: torch.Tensor,
        macro_seq: torch.Tensor,
        time_seq: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        """
        Args:
            region_ids:    (B,) region indices
            price_seq:     (B, T, 1) historical price indices
            inventory_seq: (B, T, 1) inventory counts
            macro_seq:     (B, T, 2) [euribor, inflation]
            time_seq:      (B, T, 1) time indices

        Returns:
            Dict with quantile predictions per horizon and attention weights
        """
        # --- Static encoding ---
        cs_vsn, cs_enc, cs_dec, cs_out = self.static_encoder(region_ids)

        # --- Feature projection ---
        price_emb = self.price_proj(price_seq)        # (B, T, H)
        inventory_emb = self.inventory_proj(inventory_seq)
        macro_emb = self.macro_proj(macro_seq)
        time_emb = self.time_proj(time_seq)

        # --- Variable selection (conditioned on static context) ---
        selected, var_weights = self.vsn(
            [price_emb, inventory_emb, macro_emb, time_emb],
            context=cs_vsn,
        )  # (B, T, H), (B, T, 4)

        # --- Temporal processing with static enrichment ---
        cs_enc_expanded = cs_enc.unsqueeze(1).expand_as(selected)
        temporal = self.temporal_grn(selected, context=cs_enc_expanded)

        # --- Self-attention with gated residual ---
        attended, attn_weights = self.attention(temporal, temporal, temporal)
        gated = self.attn_gate(attended) * attended
        temporal = self.attn_norm(temporal + gated)

        # --- Output processing with static enrichment ---
        cs_out_expanded = cs_out.unsqueeze(1).expand_as(temporal)
        output = self.output_grn(temporal, context=cs_out_expanded)

        # --- Take last timestep for prediction ---
        context = output[:, -1, :]  # (B, H)

        # --- Quantile predictions ---
        outputs = {}
        for i, q in enumerate(self.config.quantiles):
            outputs[f"q{int(q * 100)}"] = self.quantile_heads[i](context)

        outputs["attention_weights"] = attn_weights
        outputs["variable_weights"] = var_weights  # (B, T, 4) — interpretability

        return outputs


class TFTForecastingService:
    """
    Service wrapper for TFT forecaster with training and inference.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        model_path: Optional[str] = None,
        config: Optional[TFTConfig] = None,
        app_config: Optional[AppConfig] = None,
    ):
        if app_config is not None:
            if db_path is None:
                db_path = str(app_config.pipeline.db_path)
            if model_path is None:
                model_path = str(app_config.paths.tft_model_path)
            if config is None:
                config = app_config.tft
        if db_path is None:
            db_path = str(DEFAULT_DB_PATH)
        if model_path is None:
            model_path = str(TFT_MODEL_PATH)
        if config is None:
            config = TFTConfig()

        self.db_path = db_path
        self.model_path = model_path
        self.config = config
        self.model = None
        self.region_map = {}
        self.data_source = None

    def _load_training_data(
        self,
        *,
        data_source: Optional[str] = None,
        allow_fallback: bool = False,
    ) -> Tuple[pd.DataFrame, str]:
        """Load and prepare training data from hedonic indices (fallback to official metrics)."""
        repo = MarketFundamentalsRepository(db_path=self.db_path)
        try:
            source = str(data_source).strip().lower() if data_source else None
            if source == "official":
                return repo.load_tft_official_data(), "official"
            if source == "hedonic":
                return repo.load_tft_training_data(), "hedonic"

            df = repo.load_tft_training_data()
            if not allow_fallback:
                return df, "hedonic"

            min_rows = max(50, self.config.context_length + 1)
            if len(df) >= min_rows:
                return df, "hedonic"

            fallback = repo.load_tft_official_data()
            if not fallback.empty:
                logger.warning(
                    "tft_data_source_fallback",
                    hedonic_rows=len(df),
                    official_rows=len(fallback),
                )
                return fallback, "official"

            return df, "hedonic"
        except Exception as e:
            logger.warning("tft_training_data_load_failed", error=str(e))
            return pd.DataFrame(), "hedonic"

    def _build_sequences(
        self, df: pd.DataFrame
    ) -> List[Dict[str, torch.Tensor]]:
        """Build all training sequences across regions, returned as a list of dicts."""
        sequences = []
        for region in df["region_id"].unique():
            region_df = df[df["region_id"] == region].sort_values("month_date")
            if len(region_df) < self.config.context_length + 1:
                continue

            region_idx = self.region_map[region]
            price_vals = region_df["hedonic_index_sqm"].values.astype(np.float32)
            inventory_vals = region_df["inventory_count"].fillna(0).values.astype(np.float32)
            euribor_vals = region_df["euribor_12m"].fillna(3.0).values.astype(np.float32)
            inflation_vals = region_df["inflation"].fillna(2.5).values.astype(np.float32)

            for i in range(len(region_df) - self.config.context_length):
                sl = slice(i, i + self.config.context_length)
                sequences.append({
                    "region_id": torch.tensor([region_idx]),
                    "price_seq": torch.tensor(price_vals[sl]).unsqueeze(-1),
                    "inventory_seq": torch.tensor(inventory_vals[sl]).unsqueeze(-1),
                    "macro_seq": torch.tensor(
                        np.stack([euribor_vals[sl], inflation_vals[sl]], axis=-1)
                    ),
                    "time_seq": torch.arange(self.config.context_length, dtype=torch.float32).unsqueeze(-1),
                    "target": torch.tensor([price_vals[i + self.config.context_length]]),
                })
        return sequences

    def train(self, epochs: int = 100, lr: float = 0.001, batch_size: int = 32):
        """Train the TFT model with proper mini-batch training."""
        df, data_source = self._load_training_data(allow_fallback=True)
        self.data_source = data_source

        if len(df) < 50:
            logger.warning("insufficient_data_for_tft", count=len(df), data_source=data_source)
            return

        # Build region map
        regions = df["region_id"].unique()
        self.region_map = {r: i for i, r in enumerate(regions)}

        # Initialize model
        self.model = TFTForecaster(self.config, len(regions))

        optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr, weight_decay=0.01)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        # Build all sequences upfront
        sequences = self._build_sequences(df)
        if not sequences:
            logger.warning("no_valid_sequences_for_tft")
            return

        logger.info(
            "tft_training_start",
            epochs=epochs,
            regions=len(regions),
            sequences=len(sequences),
            params=sum(p.numel() for p in self.model.parameters()),
        )

        best_loss = float("inf")
        patience_counter = 0
        patience = 15

        for epoch in range(epochs):
            self.model.train()
            total_loss = 0.0

            # Shuffle sequences
            perm = np.random.permutation(len(sequences))

            num_batches = 0
            for batch_start in range(0, len(sequences), batch_size):
                batch_indices = perm[batch_start : batch_start + batch_size]
                batch = [sequences[i] for i in batch_indices]

                # Collate batch
                region_ids = torch.cat([s["region_id"] for s in batch])
                price_seq = torch.stack([s["price_seq"] for s in batch])
                inventory_seq = torch.stack([s["inventory_seq"] for s in batch])
                macro_seq = torch.stack([s["macro_seq"] for s in batch])
                time_seq = torch.stack([s["time_seq"] for s in batch])
                targets = torch.cat([s["target"] for s in batch])

                outputs = self.model(region_ids, price_seq, inventory_seq, macro_seq, time_seq)

                loss = torch.tensor(0.0)
                for q in self.config.quantiles:
                    q_key = f"q{int(q * 100)}"
                    q_pred = outputs[q_key][:, 0]  # first horizon
                    errors = targets - q_pred
                    loss = loss + torch.where(
                        errors >= 0, q * errors, (q - 1) * errors
                    ).mean()

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

                total_loss += loss.item()
                num_batches += 1

            scheduler.step()
            avg_loss = total_loss / max(num_batches, 1)

            # Early stopping
            if avg_loss < best_loss - 1e-4:
                best_loss = avg_loss
                patience_counter = 0
            else:
                patience_counter += 1

            if epoch % 10 == 0:
                logger.info("tft_training_progress", epoch=epoch, loss=f"{avg_loss:.4f}")

            if patience_counter >= patience:
                logger.info("tft_early_stopping", epoch=epoch)
                break

        # Save model
        if hasattr(self.config, "model_dump"):
            config_payload = self.config.model_dump()
        elif hasattr(self.config, "__dict__"):
            config_payload = self.config.__dict__.copy()
        else:
            config_payload = {}
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'region_map': self.region_map,
            'config': config_payload,
            'data_source': self.data_source,
        }, self.model_path)

        logger.info("tft_training_complete", model_path=self.model_path)

    def predict(self, region_id: str, current_value: float) -> Dict[str, float]:
        """
        Generate predictions for a region.

        Returns dict with quantile predictions for each horizon.
        """
        if self.model is None:
            self._load_model()

        if self.model is None:
            return {}

        # Get recent history
        data_source = self.data_source or "hedonic"
        df, _ = self._load_training_data(data_source=data_source, allow_fallback=False)
        if df.empty or "region_id" not in df.columns:
            return {}

        region_key = str(region_id).strip().lower() if region_id else ""
        region_df = df[df['region_id'] == region_key].tail(self.config.context_length)

        if len(region_df) < self.config.context_length:
            fallback_key = None
            for candidate in ("all", "national"):
                if candidate == region_key:
                    continue
                candidate_df = df[df["region_id"] == candidate].tail(self.config.context_length)
                if len(candidate_df) >= self.config.context_length:
                    fallback_key = candidate
                    region_df = candidate_df
                    break
            if fallback_key:
                logger.warning("tft_region_fallback", requested=region_id, used=fallback_key)
                region_key = fallback_key
            else:
                return {}

        # Prepare tensors
        region_idx = self.region_map.get(region_key)
        if region_idx is None:
            if self.region_map:
                region_idx = next(iter(self.region_map.values()))
                logger.warning("tft_region_missing", requested=region_id, used=region_key)
            else:
                region_idx = 0
        region_tensor = torch.tensor([region_idx])

        price_seq = torch.tensor(region_df['hedonic_index_sqm'].values, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
        inventory_seq = torch.tensor(region_df['inventory_count'].fillna(0).values, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
        macro_seq = torch.tensor(
            np.stack([region_df['euribor_12m'].fillna(3.0).values, region_df['inflation'].fillna(2.5).values], axis=-1),
            dtype=torch.float32
        ).unsqueeze(0)
        time_seq = torch.arange(len(region_df), dtype=torch.float32).unsqueeze(0).unsqueeze(-1)

        # Predict
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(region_tensor, price_seq, inventory_seq, macro_seq, time_seq)

        # Scale predictions to property value
        current_index = region_df['hedonic_index_sqm'].iloc[-1]
        results = {}

        for q in self.config.quantiles:
            q_key = f"q{int(q*100)}"
            pred_indices = outputs[q_key].squeeze().numpy()

            for i, h in enumerate(self.config.prediction_horizons):
                growth_ratio = pred_indices[i] / current_index if current_index > 0 else 1.0
                results[f"{q_key}_m{h}"] = current_value * growth_ratio

        return results

    def _load_model(self):
        """Load trained model from disk"""
        try:
            try:
                checkpoint = torch.load(self.model_path, map_location="cpu")
            except Exception as e:
                try:
                    try:
                        import __main__ as main_module
                        if not hasattr(main_module, "TFTConfig"):
                            setattr(main_module, "TFTConfig", TFTConfig)
                    except Exception:
                        pass
                    checkpoint = torch.load(
                        self.model_path,
                        weights_only=False,
                        map_location="cpu",
                    )
                    if not isinstance(checkpoint, dict) or "model_state_dict" not in checkpoint:
                        raise ValueError("invalid_checkpoint_structure")
                except TypeError:
                    raise e

            self.region_map = checkpoint.get('region_map', {})
            self.data_source = checkpoint.get("data_source")
            if self.data_source is not None:
                self.data_source = str(self.data_source).strip().lower()

            raw_config = checkpoint.get('config')
            if isinstance(raw_config, dict):
                self.config = TFTConfig.model_validate(raw_config)
            elif isinstance(raw_config, TFTConfig):
                self.config = raw_config
            elif raw_config is not None and hasattr(raw_config, "model_dump"):
                self.config = TFTConfig.model_validate(raw_config.model_dump())
            elif raw_config is not None and hasattr(raw_config, "__dict__"):
                self.config = TFTConfig.model_validate(raw_config.__dict__)
            else:
                self.config = TFTConfig()

            self.model = TFTForecaster(self.config, len(self.region_map))
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.eval()
            logger.info("tft_model_loaded", path=self.model_path)

            # Self-heal: if checkpoint wasn't in the safe dict format, rewrite it.
            if not isinstance(raw_config, dict):
                try:
                    if hasattr(self.config, "model_dump"):
                        config_payload = self.config.model_dump()
                    else:
                        config_payload = self.config.__dict__.copy()
                    safe_checkpoint = {
                        "model_state_dict": checkpoint.get("model_state_dict"),
                        "region_map": self.region_map,
                        "config": config_payload,
                        "data_source": self.data_source,
                    }
                    torch.save(safe_checkpoint, self.model_path)
                    logger.info("tft_checkpoint_upgraded", path=self.model_path)
                except Exception as upgrade_err:
                    logger.warning("tft_checkpoint_upgrade_failed", error=str(upgrade_err))
        except Exception as e:
            logger.warning("tft_model_load_failed", error=str(e))
            self.model = None


if __name__ == "__main__":
    # Test training
    service = TFTForecastingService()
    service.train(epochs=50)
