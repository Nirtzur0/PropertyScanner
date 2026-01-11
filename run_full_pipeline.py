
import subprocess
import time
import os
import sys

def run_sequence():
    db_path = "data/listings.db"
    
    # 1. Preprocess VLM
    print("=== Phase 1: VLM Preprocessing ===")
    env = os.environ.copy()
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + ":."
    
    # We run the preprocess script until completion
    proc = subprocess.Popen(
        [sys.executable, "src/training/preprocess_vlm.py"],
        env=env
    )
    proc.wait()
    
    if proc.returncode != 0:
        print("Preprocessing failed. Check logs.")
        # We might still want to train on what we have
    
    # 2. Run Training
    print("\n=== Phase 2: Full Training ===")
    train_cmd = [
        sys.executable, "-m", "src.training.train",
        "--db", db_path,
        "--epochs", "100",
        "--batch-size", "16",
        "--patience", "15",
        "--device", "mps"
    ]
    
    subprocess.run(train_cmd, env=env)

if __name__ == "__main__":
    run_sequence()
