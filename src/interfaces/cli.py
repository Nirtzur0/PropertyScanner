import argparse
import subprocess
import sys
from typing import List


def _run_module(module: str, args: List[str]) -> int:
    cmd = [sys.executable, "-m", module] + args
    return subprocess.run(cmd, check=False).returncode


def _run_streamlit(args: List[str]) -> int:
    cmd = [sys.executable, "-m", "streamlit", "run", "src/interfaces/dashboard/app.py"] + args
    return subprocess.run(cmd, check=False).returncode


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Property Scanner CLI (preflight is the canonical entry point)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def passthrough(name: str, help_text: str) -> None:
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("args", nargs=argparse.REMAINDER)

    passthrough("market-data", "Build market/hedonic indices & ingest registries (wraps src.market.workflows.market_data)")
    passthrough("build-index", "Build vector index (FAISS/LanceDB) (wraps src.valuation.workflows.indexing)")
    passthrough("train", "Train the fusion model (wraps src.ml.training.train)")
    passthrough("backfill", "Backfill cached valuations (wraps src.valuation.workflows.backfill)")
    passthrough("dashboard", "Launch Streamlit dashboard")
    passthrough("agent", "Run the cognitive agent (wraps src.interfaces.agent)")
    passthrough("calibrators", "Update conformal calibrators (wraps src.valuation.workflows.calibration)")
    passthrough("clean-data", "Fix metadata/geocoding issues (wraps src.listings.workflows.maintenance)")
    passthrough("preflight", "Refresh stale data and artifacts (wraps src.platform.workflows.preflight)")
    passthrough("orchestrator", "Run orchestrated flows (wraps src.platform.workflows.orchestration)")
    passthrough("unified-crawl", "Run unified multi-source crawl (wraps src.listings.workflows.unified_crawl)")
    passthrough("migrate", "Run database schema migrations (wraps src.platform.migrations)")
    passthrough("train-pipeline", "Run full training sequence: VLM prep + Fusion Train (wraps src.platform.workflows.full_pipeline)")
    passthrough("caption-images", "Run image captioning batch job (wraps src.ml.training.image_captioning)")

    args, remaining = parser.parse_known_args(argv)
    cmd_args = getattr(args, "args", None)
    if cmd_args is None:
        cmd_args = remaining
    if not cmd_args:
        cmd_args = []

    module_map = {
        "market-data": "src.market.workflows.market_data", # Renamed from build-market
        "build-index": "src.valuation.workflows.indexing",
        "train": "src.ml.training.train",
        "backfill": "src.valuation.workflows.backfill",
        "agent": "src.interfaces.agent",
        "calibrators": "src.valuation.workflows.calibration",
        "clean-data": "src.listings.workflows.maintenance",
        "preflight": "src.platform.workflows.preflight",
        "orchestrator": "src.platform.workflows.orchestration",
        "unified-crawl": "src.listings.workflows.unified_crawl",
        "migrate": "src.platform.migrations",
        "train-pipeline": "src.platform.workflows.full_pipeline",
        "caption-images": "src.ml.training.image_captioning",
    }

    if args.command == "dashboard":
        if "--skip-preflight" in cmd_args:
            cmd_args = [arg for arg in cmd_args if arg != "--skip-preflight"]
        else:
            _run_module("src.platform.workflows.preflight", [])
        return _run_streamlit(cmd_args)

    module = module_map.get(args.command)
    if not module:
        parser.error(f"Unknown command: {args.command}")
        return 2

    return _run_module(module, cmd_args)


if __name__ == "__main__":
    raise SystemExit(main())
