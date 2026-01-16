import argparse
import os
import subprocess
import sys


def run_sequence(
    *,
    db_path: str = "data/listings.db",
    epochs: int = 100,
    batch_size: int = 16,
    patience: int = 15,
    device: str = "cpu",
) -> None:
    print("=== Phase 1: VLM Preprocessing ===")

    try:
        sys.path.append(os.getcwd())
        from src.training.preprocess_vlm import batch_process_vlm

        batch_process_vlm(db_path=db_path, override=False, max_workers=4)
    except Exception as e:
        print(f"Preprocessing failed with error: {e}")

    print("\n=== Phase 2: Full Training ===")
    env = os.environ.copy()
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + ":."

    train_cmd = [
        sys.executable,
        "-m",
        "src.training.train",
        "--db",
        db_path,
        "--epochs",
        str(epochs),
        "--batch-size",
        str(batch_size),
        "--patience",
        str(patience),
        "--device",
        device,
    ]

    subprocess.run(train_cmd, env=env, check=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run VLM preprocessing + training sequence.")
    parser.add_argument("--db", default="data/listings.db", help="Path to listings database")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args(argv)

    run_sequence(
        db_path=args.db,
        epochs=args.epochs,
        batch_size=args.batch_size,
        patience=args.patience,
        device=args.device,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
