import argparse
import subprocess
import sys
from typing import List


def _run_module(module: str, args: List[str]) -> int:
    cmd = [sys.executable, "-m", module] + args
    return subprocess.run(cmd, check=False).returncode


def _run_streamlit(args: List[str]) -> int:
    cmd = [sys.executable, "-m", "streamlit", "run", "src/dashboard.py"] + args
    return subprocess.run(cmd, check=False).returncode


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Property Scanner CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def passthrough(name: str, help_text: str) -> None:
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("args", nargs=argparse.REMAINDER)

    passthrough("harvest", "Run the listing harvester (wraps src.scripts.harvest_batch)")
    passthrough("build-market", "Build macro + market/hedonic indices (wraps src.scripts.build_market_data)")
    passthrough("build-index", "Build FAISS vector index (wraps src.scripts.build_vector_index)")
    passthrough("train", "Train the fusion model (wraps src.training.train)")
    passthrough("backfill", "Backfill cached valuations (wraps src.scripts.backfill_valuations)")
    passthrough("dashboard", "Launch Streamlit dashboard")
    passthrough("agent", "Run the cognitive agent (wraps src.main)")
    passthrough("calibrators", "Update conformal calibrators (wraps src.scripts.update_calibrators)")
    passthrough("clean-data", "Fix metadata/geocoding issues (wraps src.scripts.clean_data)")

    args = parser.parse_args(argv)
    cmd_args = getattr(args, "args", []) or []

    module_map = {
        "harvest": "src.scripts.harvest_batch",
        "build-market": "src.scripts.build_market_data",
        "build-index": "src.scripts.build_vector_index",
        "train": "src.training.train",
        "backfill": "src.scripts.backfill_valuations",
        "agent": "src.main",
        "calibrators": "src.scripts.update_calibrators",
        "clean-data": "src.scripts.clean_data",
    }

    if args.command == "dashboard":
        return _run_streamlit(cmd_args)

    module = module_map.get(args.command)
    if not module:
        parser.error(f"Unknown command: {args.command}")
        return 2

    return _run_module(module, cmd_args)


if __name__ == "__main__":
    raise SystemExit(main())
