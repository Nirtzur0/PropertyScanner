import argparse
import subprocess
import sys
from typing import List


def _run_module(module: str, args: List[str]) -> int:
    cmd = [sys.executable, "-m", module] + args
    return subprocess.run(cmd, check=False).returncode


def _run_streamlit(args: List[str]) -> int:
    cmd = [sys.executable, "-m", "streamlit", "run", "src/dashboard/app.py"] + args
    return subprocess.run(cmd, check=False).returncode


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Property Scanner CLI (preflight is the canonical entry point)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def passthrough(name: str, help_text: str) -> None:
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("args", nargs=argparse.REMAINDER)

    passthrough("harvest", "Run the listing harvester (wraps src.workflows.harvest)")
    passthrough("build-market", "Build macro + market/hedonic indices (wraps src.workflows.market_data)")
    passthrough("build-index", "Build FAISS vector index (wraps src.workflows.indexing)")
    passthrough("train", "Train the fusion model (wraps src.training.train)")
    passthrough("backfill", "Backfill cached valuations (wraps src.workflows.backfill)")
    passthrough("dashboard", "Launch Streamlit dashboard")
    passthrough("agent", "Run the cognitive agent (wraps src.main)")
    passthrough("calibrators", "Update conformal calibrators (wraps src.workflows.calibration)")
    passthrough("clean-data", "Fix metadata/geocoding issues (wraps src.workflows.maintenance)")
    passthrough("preflight", "Refresh stale data and artifacts (wraps src.workflows.preflight)")
    passthrough("schedule", "Run scheduled preflight refreshes (wraps src.workflows.scheduler)")

    args = parser.parse_args(argv)
    cmd_args = getattr(args, "args", []) or []

    module_map = {
        "harvest": "src.workflows.harvest",
        "build-market": "src.workflows.market_data",
        "build-index": "src.workflows.indexing",
        "train": "src.training.train",
        "backfill": "src.workflows.backfill",
        "agent": "src.main",
        "calibrators": "src.workflows.calibration",
        "clean-data": "src.workflows.maintenance",
        "preflight": "src.workflows.preflight",
        "schedule": "src.workflows.scheduler",
    }

    if args.command == "dashboard":
        if "--skip-preflight" in cmd_args:
            cmd_args = [arg for arg in cmd_args if arg != "--skip-preflight"]
        else:
            _run_module("src.workflows.preflight", [])
        return _run_streamlit(cmd_args)

    module = module_map.get(args.command)
    if not module:
        parser.error(f"Unknown command: {args.command}")
        return 2

    return _run_module(module, cmd_args)


if __name__ == "__main__":
    raise SystemExit(main())
