"""
Training Loop for PropertyFusionModel.
Implements quantile regression with early stopping and checkpointing.
"""
import os
import json
import structlog
import numpy as np
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

from src.services.fusion_model import PropertyFusionModel, QuantileLoss, TORCH_AVAILABLE
from src.core.config import DEFAULT_DB_PATH, VECTOR_INDEX_PATH, VECTOR_METADATA_PATH, MODELS_DIR
from src.training.dataset import create_dataloaders

logger = structlog.get_logger()


class Trainer:
    """
    Trainer for PropertyFusionModel.
    """
    def __init__(
        self,
        model: nn.Module,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader] = None,
        lr: float = 1e-4,
        weight_decay: float = 0.01,
        device: str = "cpu",
        checkpoint_dir: str = str(MODELS_DIR)
    ):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.device = device
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Optimizer
        self.optimizer = optim.AdamW(
            model.parameters(),
            lr=lr,
            weight_decay=weight_decay
        )
        
        # Loss
        self.criterion = QuantileLoss(quantiles=[0.1, 0.5, 0.9])
        
        # Tracking
        self.train_losses = []
        self.val_losses = []
        self.best_val_loss = float('inf')
        self.epochs_without_improvement = 0
        
    def train_epoch(self) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0.0
        num_batches = 0
        
        for batch in self.train_loader:
            # Move to device
            target_text = batch["target_text"].to(self.device)
            target_tab = batch["target_tab"].to(self.device)
            target_price = batch["target_price"].to(self.device)
            comp_text = batch["comp_text"].to(self.device)
            comp_tab = batch["comp_tab"].to(self.device)
            comp_prices = batch["comp_prices"].to(self.device)
            label_weight = batch.get("label_weight")
            if label_weight is not None:
                label_weight = label_weight.to(self.device)
            
            # Forward pass
            self.optimizer.zero_grad()
            
            price_q, rent_q, time_q, _ = self.model(
                target_tab=target_tab,
                target_text=target_text,
                target_image=None,
                comp_tab=comp_tab,
                comp_text=comp_text,
                comp_image=None,
                comp_prices=comp_prices,
                output_mode="residual"
            )
            
            # Compute loss (only on price for now)
            loss = self.criterion(price_q, target_price, weights=label_weight)
            
            # Backward pass
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        return total_loss / max(num_batches, 1)
    
    @torch.no_grad()
    def validate(self) -> Tuple[float, Dict[str, float]]:
        """Validate on val set with metrics."""
        return self.evaluate_loader(self.val_loader)

    @torch.no_grad()
    def evaluate_loader(self, loader: Optional[DataLoader]) -> Tuple[float, Dict[str, float]]:
        """Evaluate on a given loader with metrics."""
        if not loader:
            return 0.0, {}

        self.model.eval()
        total_loss = 0.0
        all_predictions = []
        all_targets = []
        num_batches = 0

        for batch in loader:
            target_text = batch["target_text"].to(self.device)
            target_tab = batch["target_tab"].to(self.device)
            target_price = batch["target_price"].to(self.device)
            comp_text = batch["comp_text"].to(self.device)
            comp_tab = batch["comp_tab"].to(self.device)
            comp_prices = batch["comp_prices"].to(self.device)
            baseline_price = batch.get("baseline_price")
            target_price_adj = batch.get("target_price_adj")
            label_weight = batch.get("label_weight")
            if baseline_price is not None:
                baseline_price = baseline_price.to(self.device)
            if target_price_adj is not None:
                target_price_adj = target_price_adj.to(self.device)
            if label_weight is not None:
                label_weight = label_weight.to(self.device)
            
            price_q, _, _, _ = self.model(
                target_tab=target_tab,
                target_text=target_text,
                target_image=None,
                comp_tab=comp_tab,
                comp_text=comp_text,
                comp_image=None,
                comp_prices=comp_prices,
                output_mode="residual"
            )
            
            loss = self.criterion(price_q, target_price, weights=label_weight)
            total_loss += loss.item()
            num_batches += 1
            
            # Collect predictions (median = quantile 0.5)
            if baseline_price is not None and target_price_adj is not None:
                baseline_log = torch.log(baseline_price.clamp(min=1.0))
                pred_log = baseline_log + price_q[:, 1]
                pred_price = torch.exp(pred_log)
                all_predictions.extend(pred_price.cpu().numpy())
                all_targets.extend(target_price_adj.cpu().numpy())
        
        avg_loss = total_loss / max(num_batches, 1)
        
        # Compute metrics
        predictions = np.array(all_predictions)
        targets = np.array(all_targets)

        if predictions.size == 0 or targets.size == 0:
            return avg_loss, {}
        
        mae = np.mean(np.abs(predictions - targets))
        mape = np.mean(np.abs((predictions - targets) / np.maximum(targets, 1))) * 100
        median_error = np.median(np.abs(predictions - targets))
        
        metrics = {
            "mae": mae,
            "mape": mape,
            "median_error": median_error
        }
        
        return avg_loss, metrics
    
    def save_checkpoint(self, epoch: int, is_best: bool = False):
        """Save model checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
            "best_val_loss": self.best_val_loss
        }
        
        # Save latest
        torch.save(checkpoint, self.checkpoint_dir / "checkpoint_latest.pt")
        
        # Save best
        if is_best:
            torch.save(self.model.state_dict(), self.checkpoint_dir / "fusion_model.pt")
            logger.info("best_model_saved", epoch=epoch, val_loss=self.best_val_loss)
    
    
    def train(
        self,
        epochs: int = 100,
        patience: int = 10,
        min_delta: float = 1e-4,
        fold_idx: int = 0
    ) -> Dict[str, Any]:
        """
        Full training loop with early stopping.
        """
        logger.info("training_started", fold=fold_idx, epochs=epochs, patience=patience)
        
        best_metrics = {}
        
        for epoch in range(epochs):
            # Train
            train_loss = self.train_epoch()
            self.train_losses.append(train_loss)
            
            # Validate with metrics
            if self.val_loader:
                val_loss, metrics = self.validate()
            else:
                val_loss = train_loss
                metrics = {}
            self.val_losses.append(val_loss)
            
            # Check improvement
            is_best = False
            if val_loss < self.best_val_loss - min_delta:
                self.best_val_loss = val_loss
                self.epochs_without_improvement = 0
                is_best = True
                best_metrics = metrics
            else:
                self.epochs_without_improvement += 1
            
            # Save checkpoint
            self.save_checkpoint(epoch, is_best)
            
            # Log progress with metrics
            # Format loss in thousands (K) for readability
            log_data = {
                "fold": fold_idx,
                "epoch": epoch + 1,
                "loss": f"{train_loss/1000:.1f}k",
                "val_loss": f"{val_loss/1000:.1f}k",
                "best": is_best
            }
            if metrics:
                log_data["mape"] = f"{metrics.get('mape', 0):.1f}%"
                log_data["mae"] = f"€{metrics.get('mae', 0):,.0f}"
            
            # Only log every 5 epochs or if best to reduce noise
            if is_best or (epoch + 1) % 5 == 0:
                logger.info("epoch_completed", **log_data)
            
            # Early stopping
            if self.epochs_without_improvement >= patience:
                logger.info("early_stopping", fold=fold_idx, epoch=epoch + 1)
                break
        
        return {
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
            "best_val_loss": self.best_val_loss,
            "total_epochs": len(self.train_losses),
            "best_metrics": best_metrics
        }


def train_model(
    db_path: str = str(DEFAULT_DB_PATH),
    epochs: int = 100,
    batch_size: int = 32,
    lr: float = 1e-4,
    num_comps: int = 5,
    patience: int = 10,
    val_split: float = 0.1,
    test_split: float = 0.1,
    device: str = "cpu",
    use_vlm: bool = True,
    k_folds: int = 1,
    listing_type: str = "sale",
    label_source: str = "ask",
    time_safe_comps: bool = True,
    normalize_to: str = "latest",
    use_retriever: bool = True,
    retriever_index_path: str = str(VECTOR_INDEX_PATH),
    retriever_metadata_path: str = str(VECTOR_METADATA_PATH),
    retriever_model_name: str = "all-MiniLM-L6-v2",
    retriever_vlm_policy: str = "gated"
) -> List[Dict[str, Any]]:
    """
    High-level training function with train/val/test splitting and K-Fold support.
    """
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch not available. Install with: pip install torch")

    if use_retriever:
        if not os.path.exists(retriever_index_path) or not os.path.exists(retriever_metadata_path):
            raise FileNotFoundError("retriever_index_missing")

    from src.training.dataset import PropertyDataset, collate_fn
    from torch.utils.data import DataLoader, SubsetRandomSampler
    from sklearn.model_selection import KFold

    if val_split < 0 or test_split < 0 or (val_split + test_split) >= 1:
        raise ValueError("invalid_split_ratio")
    
    # Load dataset once
    dataset = PropertyDataset(
        db_path=db_path,
        num_comps=num_comps,
        use_vlm=use_vlm,
        text_model=retriever_model_name,
        listing_type=listing_type,
        label_source=label_source,
        time_safe_comps=time_safe_comps,
        normalize_to=normalize_to,
        use_retriever=use_retriever,
        retriever_index_path=retriever_index_path,
        retriever_metadata_path=retriever_metadata_path,
        retriever_model_name=retriever_model_name,
        retriever_vlm_policy=retriever_vlm_policy
    )
    
    # Prepare indices
    indices = np.arange(len(dataset))
    np.random.shuffle(indices)

    # Holdout test set first
    n_test = int(len(indices) * test_split)
    test_idx = indices[:n_test] if n_test > 0 else np.array([], dtype=int)
    train_val_idx = indices[n_test:]
    n_train_val = len(train_val_idx)

    if n_train_val == 0:
        raise ValueError("insufficient_data_for_train_val")

    test_loader = None
    if len(test_idx) > 0:
        test_loader = DataLoader(
            dataset, batch_size=batch_size, sampler=SubsetRandomSampler(test_idx),
            collate_fn=collate_fn, num_workers=0
        )

    # Define splits on train/val pool
    if k_folds > 1:
        kf = KFold(n_splits=k_folds, shuffle=True, random_state=42)
        splits = list(kf.split(np.arange(n_train_val)))
        logger.info("kfold_training_started", k=k_folds)
    else:
        # Standard train/val split
        split_idx = int(n_train_val * (1 - val_split))
        splits = [(np.arange(split_idx), np.arange(split_idx, n_train_val))]
        logger.info("standard_training_started", val_split=val_split)
        
    all_histories = []
    
    for i, (train_pos, val_pos) in enumerate(splits):
        fold_id = i + 1
        train_idx = train_val_idx[train_pos]
        val_idx = train_val_idx[val_pos]
        logger.info("starting_fold", fold=fold_id, train_size=len(train_idx), val_size=len(val_idx))
        
        train_loader = DataLoader(
            dataset, batch_size=batch_size, sampler=SubsetRandomSampler(train_idx),
            collate_fn=collate_fn, num_workers=0
        )
        val_loader = None
        if len(val_idx) > 0:
            val_loader = DataLoader(
                dataset, batch_size=batch_size, sampler=SubsetRandomSampler(val_idx),
                collate_fn=collate_fn, num_workers=0
            )
        
        tabular_dim = dataset.tabular_encoder.dimension
        text_dim = dataset.text_encoder.dimension
        image_dim = 512

        # Create fresh model for each fold
        model = PropertyFusionModel(
            tabular_dim=tabular_dim,
            text_dim=text_dim,
            image_dim=image_dim,
            hidden_dim=64,
            num_heads=2
        )

        config = {
            "tabular_dim": tabular_dim,
            "text_dim": text_dim,
            "image_dim": image_dim,
            "hidden_dim": 64,
            "num_heads": 2,
            "target_mode": "log_residual",
            "normalize_to": normalize_to,
            "listing_type": listing_type,
            "label_source": label_source,
            "time_safe_comps": time_safe_comps,
            "text_model": retriever_model_name,
            "retriever": {
                "index_path": retriever_index_path,
                "metadata_path": retriever_metadata_path,
                "model_name": retriever_model_name,
                "vlm_policy": retriever_vlm_policy
            }
        }
        
        if i == 0:
            logger.info("model_created", params=sum(p.numel() for p in model.parameters()))
        
        trainer = Trainer(
            model=model,
            train_loader=train_loader,
            val_loader=val_loader,
            lr=lr,
            device=device,
            checkpoint_dir=str(MODELS_DIR / f"fold_{fold_id}") if k_folds > 1 else str(MODELS_DIR)
        )

        config_path = trainer.checkpoint_dir / "fusion_config.json"
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2, sort_keys=True)
            logger.info("fusion_config_saved", path=str(config_path))
        except Exception as e:
            logger.warning("fusion_config_save_failed", path=str(config_path), error=str(e))
        
        history = trainer.train(epochs=epochs, patience=patience, fold_idx=fold_id)
        if test_loader:
            best_model_path = trainer.checkpoint_dir / "fusion_model.pt"
            if best_model_path.exists():
                trainer.model.load_state_dict(
                    torch.load(best_model_path, map_location=trainer.device)
                )
        test_loss, test_metrics = trainer.evaluate_loader(test_loader)
        history["test_loss"] = test_loss
        history["test_metrics"] = test_metrics
        if test_metrics:
            logger.info(
                "test_evaluation_completed",
                fold=fold_id,
                test_loss=f"{test_loss/1000:.1f}k",
                test_mape=f"{test_metrics.get('mape', 0):.1f}%",
                test_mae=f"€{test_metrics.get('mae', 0):,.0f}"
            )
        all_histories.append(history)
        
    return all_histories


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train PropertyFusionModel")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--test-split", type=float, default=0.1)
    parser.add_argument("--k-folds", type=int, default=1, help="Number of folds for Cross Validation")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM")
    parser.add_argument("--listing-type", default="sale", choices=["sale", "rent", "all"])
    parser.add_argument("--label-source", default="ask", choices=["ask", "sold"])
    parser.add_argument("--normalize-to", default="latest", help="latest, none, or ISO date for hedonic normalization")
    parser.add_argument("--time-safe-comps", action="store_true", help="Enforce comp dates <= target date")
    parser.add_argument("--no-time-safe-comps", dest="time_safe_comps", action="store_false")
    parser.set_defaults(time_safe_comps=True)
    parser.add_argument("--use-retriever", action="store_true", help="Use FAISS retriever for comps")
    parser.add_argument("--no-retriever", dest="use_retriever", action="store_false")
    parser.set_defaults(use_retriever=True)
    parser.add_argument("--retriever-index", default=str(VECTOR_INDEX_PATH))
    parser.add_argument("--retriever-metadata", default=str(VECTOR_METADATA_PATH))
    parser.add_argument("--retriever-model", default="all-MiniLM-L6-v2")
    parser.add_argument("--retriever-vlm-policy", default="gated", choices=["gated", "off"])
    
    args = parser.parse_args()
    
    histories = train_model(
        db_path=args.db,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
        val_split=args.val_split,
        test_split=args.test_split,
        device=args.device,
        use_vlm=not args.no_vlm,
        k_folds=args.k_folds,
        listing_type=args.listing_type,
        label_source=args.label_source,
        time_safe_comps=args.time_safe_comps,
        normalize_to=args.normalize_to,
        use_retriever=args.use_retriever,
        retriever_index_path=args.retriever_index,
        retriever_metadata_path=args.retriever_metadata,
        retriever_model_name=args.retriever_model,
        retriever_vlm_policy=args.retriever_vlm_policy
    )
    
    # Aggregate results
    avg_mae = np.mean([h['best_metrics'].get('mae', 0) for h in histories])
    avg_mape = np.mean([h['best_metrics'].get('mape', 0) for h in histories])
    avg_test_mae = np.mean([h.get('test_metrics', {}).get('mae', 0) for h in histories])
    avg_test_mape = np.mean([h.get('test_metrics', {}).get('mape', 0) for h in histories])
    
    print(f"\nTraining complete!")
    print(f"Average MAE: €{avg_mae:,.0f}")
    print(f"Average MAPE: {avg_mape:.1f}%")
    if avg_test_mae or avg_test_mape:
        print(f"Average Test MAE: €{avg_test_mae:,.0f}")
        print(f"Average Test MAPE: {avg_test_mape:.1f}%")
