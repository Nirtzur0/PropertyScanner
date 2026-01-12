"""
Training Loop for PropertyFusionModel.
Implements quantile regression with early stopping and checkpointing.
"""
import os
import json
import structlog
import numpy as np
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

from src.services.fusion_model import PropertyFusionModel, QuantileLoss, TORCH_AVAILABLE
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
        checkpoint_dir: str = "models"
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
            
            # Forward pass
            self.optimizer.zero_grad()
            
            price_q, rent_q, time_q, _ = self.model(
                target_tab=target_tab,
                target_text=target_text,
                target_image=None,
                comp_tab=comp_tab,
                comp_text=comp_text,
                comp_image=None,
                comp_prices=comp_prices
            )
            
            # Compute loss (only on price for now)
            loss = self.criterion(price_q, target_price)
            
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
        if not self.val_loader:
            return 0.0, {}
            
        self.model.eval()
        total_loss = 0.0
        all_predictions = []
        all_targets = []
        num_batches = 0
        
        for batch in self.val_loader:
            target_text = batch["target_text"].to(self.device)
            target_tab = batch["target_tab"].to(self.device)
            target_price = batch["target_price"].to(self.device)
            comp_text = batch["comp_text"].to(self.device)
            comp_tab = batch["comp_tab"].to(self.device)
            comp_prices = batch["comp_prices"].to(self.device)
            
            price_q, _, _, _ = self.model(
                target_tab=target_tab,
                target_text=target_text,
                target_image=None,
                comp_tab=comp_tab,
                comp_text=comp_text,
                comp_image=None,
                comp_prices=comp_prices
            )
            
            loss = self.criterion(price_q, target_price)
            total_loss += loss.item()
            num_batches += 1
            
            # Collect predictions (median = quantile 0.5)
            all_predictions.extend(price_q[:, 1].cpu().numpy())
            all_targets.extend(target_price.cpu().numpy())
        
        avg_loss = total_loss / max(num_batches, 1)
        
        # Compute metrics
        predictions = np.array(all_predictions)
        targets = np.array(all_targets)
        
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
        min_delta: float = 1e-4
    ) -> Dict[str, Any]:
        """
        Full training loop with early stopping.
        
        Args:
            epochs: Maximum number of epochs
            patience: Epochs without improvement before stopping
            min_delta: Minimum improvement to count as progress
            
        Returns:
            Training history dictionary
        """
        logger.info("training_started", epochs=epochs, patience=patience)
        
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
            log_data = {
                "epoch": epoch + 1,
                "train_loss": f"{train_loss:.4f}",
                "val_loss": f"{val_loss:.4f}",
                "best": is_best
            }
            if metrics:
                log_data["mape"] = f"{metrics.get('mape', 0):.1f}%"
                log_data["mae"] = f"€{metrics.get('mae', 0):,.0f}"
            logger.info("epoch_completed", **log_data)
            
            # Early stopping
            if self.epochs_without_improvement >= patience:
                logger.info("early_stopping", epoch=epoch + 1)
                break
        
        return {
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
            "best_val_loss": self.best_val_loss,
            "total_epochs": len(self.train_losses),
            "best_metrics": best_metrics
        }


def train_model(
    db_path: str = "data/listings.db",
    epochs: int = 100,
    batch_size: int = 32,
    lr: float = 1e-4,
    num_comps: int = 5,
    patience: int = 10,
    val_split: float = 0.1,
    device: str = "cpu",
    use_vlm: bool = True
) -> Dict[str, Any]:
    """
    High-level training function.
    
    Args:
        db_path: Path to SQLite database with listings
        epochs: Number of training epochs
        batch_size: Batch size
        lr: Learning rate
        num_comps: Number of comparables per sample
        patience: Early stopping patience
        val_split: Fraction for validation
        device: Device to train on
        use_vlm: Whether to use VLM
    """
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch not available. Install with: pip install torch")
    
    # Create dataloaders directly from database
    train_loader, val_loader = create_dataloaders(
        db_path=db_path,
        batch_size=batch_size,
        num_comps=num_comps,
        val_split=val_split,
        use_vlm=use_vlm
    )
    
    # Create compact model (92k params)
    model = PropertyFusionModel(
        tabular_dim=8,
        text_dim=384,
        image_dim=512,
        hidden_dim=64,
        num_heads=2
    )
    
    logger.info("model_created", params=sum(p.numel() for p in model.parameters()))
    
    # Create trainer
    trainer = Trainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        lr=lr,
        device=device
    )
    
    # Train
    history = trainer.train(epochs=epochs, patience=patience)
    
    return history


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train PropertyFusionModel")
    parser.add_argument("--db", default="data/listings.db", help="SQLite database path")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM")
    
    args = parser.parse_args()
    
    history = train_model(
        db_path=args.db,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
        val_split=args.val_split,
        device=args.device,
        use_vlm=not args.no_vlm
    )
    
    print(f"\nTraining complete!")
    print(f"Best validation loss: {history['best_val_loss']:.4f}")
    print(f"Total epochs: {history['total_epochs']}")
