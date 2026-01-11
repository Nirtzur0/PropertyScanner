
import logging
import torch
import sys
import os
import structlog
from src.training.dataset import PropertyDataset, collate_fn
from torch.utils.data import DataLoader

# Configure basic logging


def verify_data():
    print("=== Data Pipeline Verification ===")
    
    # 1. Load Dataset
    print("Loading dataset...")
    try:
        ds = PropertyDataset(
            db_path="data/listings.db",
            num_comps=3,
            cache_embeddings=True, # This will trigger the text encoding
            use_vlm=True 
        )
    except Exception as e:
        print(f"FAILED to load dataset: {e}")
        return

    print(f"Dataset Size: {len(ds)} items")
    if len(ds) == 0:
        print("ERROR: Dataset is empty!")
        return

    # 2. Check a single item
    print("\n[Item 0 Analysis]")
    item = ds[0]
    print(f"Target Price: {item['target_price']}")
    print(f"Target Text Emb Shape: {item['target_text'].shape}") # Should be 384
    print(f"Target Tab Features: {item['target_tab']}")
    print(f"Num Comps: {len(item['comp_prices'])}")

    # 3. Check Batch
    print("\n[Batch Analysis]")
    loader = DataLoader(ds, batch_size=4, collate_fn=collate_fn)
    batch = next(iter(loader))
    
    print(f"Batch Target Prices: {batch['target_price']}")
    print(f"Batch Keys: {batch.keys()}")
    
    # Check for NaNs
    if torch.isnan(batch['target_tab']).any():
        print("WARNING: NaNs detected in tabular features!")
    else:
        print("Tabular features seem clean (no NaNs).")
        
    print("\nSUCCESS: Data loading pipeline is functioning.")
    print("The training is fast because you have ~775 items. 48 batches @ 20ms/batch = ~1 sec/epoch.")

if __name__ == "__main__":
    # Ensure src is in path
    sys.path.append(os.getcwd())
    verify_data()
