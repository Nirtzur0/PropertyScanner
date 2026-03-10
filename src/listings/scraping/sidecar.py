from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List
from uuid import uuid4

from pydantic import BaseModel, Field


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SIDECAR_ROOT = _REPO_ROOT / "scraper"


class CrawlPlan(BaseModel):
    job_id: str
    source_id: str
    mode: str = Field(default="search", pattern="^(search|listing|backfill)$")
    start_urls: List[str] = Field(default_factory=list)
    max_pages: int = 1
    max_listings: int = 0
    page_size: int = 24
    proxy_policy: Dict[str, Any] = Field(default_factory=dict)
    session_policy: Dict[str, Any] = Field(default_factory=dict)
    snapshot_dir: str
    result_path: str


def _default_plan_path(job_id: str) -> Path:
    return _REPO_ROOT / "data" / "crawl_plans" / f"{job_id}.json"


def write_plan(plan: CrawlPlan, *, plan_path: Path | None = None) -> Path:
    target = Path(plan_path or _default_plan_path(plan.job_id))
    target.parent.mkdir(parents=True, exist_ok=True)
    Path(plan.snapshot_dir).mkdir(parents=True, exist_ok=True)
    Path(plan.result_path).parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_results(path: str | Path) -> List[Dict[str, Any]]:
    result_path = Path(path)
    if not result_path.exists():
        return []
    results: List[Dict[str, Any]] = []
    for line in result_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        results.append(json.loads(line))
    return results


def invoke_sidecar(plan: CrawlPlan, *, plan_path: Path | None = None) -> Dict[str, Any]:
    written_path = write_plan(plan, plan_path=plan_path)
    entrypoint = _SIDECAR_ROOT / "src" / "index.ts"
    cmd = ["npx", "tsx", str(entrypoint), "--plan", str(written_path)]
    proc = subprocess.run(
        cmd,
        cwd=_SIDECAR_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "plan_path": str(written_path),
        "result_path": plan.result_path,
        "results": load_results(plan.result_path),
    }


def _build_plan_from_args(args: argparse.Namespace) -> CrawlPlan:
    job_id = args.job_id or uuid4().hex
    snapshot_dir = args.snapshot_dir or str(_REPO_ROOT / "data" / "crawl_snapshots" / job_id)
    result_path = args.result_path or str(_REPO_ROOT / "data" / "crawl_results" / f"{job_id}.ndjson")
    return CrawlPlan(
        job_id=job_id,
        source_id=args.source_id,
        mode=args.mode,
        start_urls=list(args.start_url or []),
        max_pages=int(args.max_pages),
        max_listings=int(args.max_listings),
        page_size=int(args.page_size),
        proxy_policy=_parse_json_arg(args.proxy_policy),
        session_policy=_parse_json_arg(args.session_policy),
        snapshot_dir=snapshot_dir,
        result_path=result_path,
    )


def _parse_json_arg(raw: str | None) -> Dict[str, Any]:
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("json_arg_must_be_object")
    return payload


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write and optionally invoke the Node/TypeScript crawl sidecar.")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--mode", default="search", choices=["search", "listing", "backfill"])
    parser.add_argument("--start-url", action="append", dest="start_url", default=None)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--max-listings", type=int, default=0)
    parser.add_argument("--page-size", type=int, default=24)
    parser.add_argument("--proxy-policy", default=None, help="JSON object")
    parser.add_argument("--session-policy", default=None, help="JSON object")
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--result-path", default=None)
    parser.add_argument("--plan-out", default=None)
    parser.add_argument("--write-only", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    plan = _build_plan_from_args(args)
    plan_path = write_plan(plan, plan_path=Path(args.plan_out) if args.plan_out else None)
    if args.write_only:
        print(json.dumps({"plan_path": str(plan_path), "plan": plan.model_dump(mode="json")}, indent=2))
        return 0

    result = invoke_sidecar(plan, plan_path=plan_path)
    print(json.dumps(result, indent=2, default=str))
    return 0 if int(result["returncode"]) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
