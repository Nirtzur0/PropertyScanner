import subprocess
import time
import os
import sys

def run_sequence():
    db_path = "data/listings.db"
    
    # 1. Preprocess VLM
    print("=== Phase 1: VLM Preprocessing ===")
    
    # Import and run directly to reuse code
    try:
        # Ensure src is in python path
        sys.path.append(os.getcwd())
        from src.training.preprocess_vlm import batch_process_vlm
        # Default to 4 workers, no override (efficient incremental update)
        batch_process_vlm(db_path=db_path, override=False, max_workers=4)
    except Exception as e:
        print(f"Preprocessing failed with error: {e}")
        # We continue to training even if VLM fails, as it's optional enhancement
    
    # 2. Run Training
    print("\n=== Phase 2: Full Training ===")
    env = os.environ.copy()
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + ":."
    
    train_cmd = [
        sys.executable, "-m", "src.training.train",
        "--db", db_path,
        "--epochs", "100",
        "--batch-size", "16",
        "--patience", "15",
        "--device", "cpu"
    ]
    
    subprocess.run(train_cmd, env=env)

if __name__ == "__main__":
    run_sequence()
