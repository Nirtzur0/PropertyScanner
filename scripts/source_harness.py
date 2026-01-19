import argparse
import json
import os
import sys
from typing import Any, Dict, List

sys.path.append(os.getcwd())

from src.listings.agents.factory import AgentFactory
from src.listings.services.feature_fusion import FeatureFusionService
from src.platform.settings import SourceConfig
from src.platform.domain.schema import RawListing
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.config import ConfigLoader


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def _write_output(path: str, records: List[Dict[str, Any]], jsonl: bool) -> None:
    if jsonl:
        with open(path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=True, indent=2)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Local source harness for listings crawl + normalize")
    parser.add_argument("--source", required=True, help="Source id (e.g. rightmove_uk, zoopla_uk, immobiliare_it)")
    parser.add_argument("--search-url", help="Search URL to crawl")
    parser.add_argument("--listing-url", help="Single listing URL")
    parser.add_argument("--listing-id", help="Listing id to resolve via template")
    parser.add_argument("--output", default="data/source_output.json", help="Output JSON/JSONL path")
    parser.add_argument("--jsonl", action="store_true", help="Write JSONL output")
    parser.add_argument("--raw", action="store_true", help="Output raw listings instead of normalized")
    parser.add_argument("--no-fusion", action="store_true", help="Skip LLM/VLM feature fusion")
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM image analysis during fusion")
    parser.add_argument("--max-listings", type=int, default=0, help="Limit number of listings")
    parser.add_argument("--max-pages", type=int, default=1, help="Max search pages (Rightmove only)")
    parser.add_argument("--page-size", type=int, default=24, help="Search page size (Rightmove only)")
    args = parser.parse_args(argv)

    config_loader = ConfigLoader()
    sources = config_loader.sources.sources
    source_conf = next((s for s in sources if s.id == args.source), SourceConfig(id=args.source))

    user_agent = config_loader.agents.defaults.uastring
    compliance = ComplianceManager(user_agent)

    crawler = AgentFactory.create_crawler(args.source, source_conf, compliance)

    input_payload = {}
    if args.search_url:
        input_payload["start_url"] = args.search_url
    if args.listing_url:
        input_payload["listing_url"] = args.listing_url
    if args.listing_id:
        input_payload["listing_id"] = args.listing_id
    if args.max_listings:
        input_payload["max_listings"] = args.max_listings
    if args.max_pages:
        input_payload["max_pages"] = args.max_pages
    if args.page_size:
        input_payload["page_size"] = args.page_size

    crawl_result = crawler.run(input_payload)
    raw_listings = crawl_result.data or []
    if args.raw:
        records = [_serialize(r) for r in raw_listings]
        _write_output(args.output, records, args.jsonl)
        return 0

    normalizer = AgentFactory.create_normalizer(args.source)
    raw_objs = []
    for item in raw_listings:
        if isinstance(item, dict):
            raw_objs.append(RawListing(**item))
        else:
            raw_objs.append(item)

    norm_result = normalizer.run({"raw_listings": raw_objs})
    canonical_listings = norm_result.data or []

    if canonical_listings and not args.no_fusion:
        run_vlm = not args.no_vlm
        service = FeatureFusionService(app_config=config_loader.app)
        fused = []
        for listing in canonical_listings:
            try:
                fused.append(service.fuse(listing, run_vlm=run_vlm))
            except Exception as exc:
                print(f"Fusion failed for {getattr(listing, 'id', 'unknown')}: {exc}")
        canonical_listings = fused or canonical_listings

    records = [_serialize(r) for r in canonical_listings]
    _write_output(args.output, records, args.jsonl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
