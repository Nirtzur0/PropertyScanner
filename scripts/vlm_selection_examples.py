import argparse
import ast
import json
import os
import random
import sys
from datetime import datetime
from typing import List

sys.path.append(os.getcwd())

from src.core.config import DEFAULT_DB_PATH
from src.repositories.listings import ListingsRepository
from src.services.vlm import VLMImageDescriber


def _parse_image_urls(raw) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(u) for u in raw if u]
    if isinstance(raw, str):
        try:
            return [str(u) for u in json.loads(raw) if u]
        except json.JSONDecodeError:
            try:
                return [str(u) for u in ast.literal_eval(raw) if u]
            except Exception:
                return []
    return []


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate real VLM tile examples with smart image selection.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to listings database")
    parser.add_argument("--limit", type=int, default=3, help="Number of listings to sample")
    parser.add_argument("--max-images", type=int, default=4, help="Max images per VLM tile")
    parser.add_argument("--output-dir", default="data/vlm_examples", help="Output directory for examples")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    args = parser.parse_args()

    describer = VLMImageDescriber()
    if not describer._check_availability():
        print("VLM not available. Start Ollama and install a vision model (e.g. llava).")
        return 1

    repo = ListingsRepository(db_path=args.db)
    rows = repo.fetch_vlm_candidates(override=True)
    if not rows:
        print("No listings with images found.")
        return 1

    random.seed(args.seed)
    sample = random.sample(rows, min(args.limit, len(rows)))

    run_dir = _ensure_dir(
        os.path.join(args.output_dir, datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    )
    index_path = os.path.join(run_dir, "index.html")
    jsonl_path = os.path.join(run_dir, "examples.jsonl")

    html_lines = [
        "<html><head><meta charset='utf-8'><title>VLM Selection Examples</title></head><body>",
        "<h1>VLM Selection Examples</h1>",
    ]

    with open(jsonl_path, "w", encoding="utf-8") as jsonl:
        for row in sample:
            listing_id = row.get("id")
            image_urls = _parse_image_urls(row.get("image_urls"))
            if not image_urls:
                continue

            result = describer.describe_images_with_debug(
                image_urls=image_urls,
                max_images=args.max_images,
                output_dir=run_dir,
                listing_id=listing_id,
                run_vlm=True,
            )
            result["listing_id"] = listing_id
            jsonl.write(json.dumps(result, ensure_ascii=True) + "\n")

            tile_path = result.get("tile_path")
            selected = result.get("selected", [])
            description = result.get("description", "")

            html_lines.append(f"<h2>Listing {listing_id}</h2>")
            if tile_path:
                rel_tile = os.path.basename(tile_path)
                html_lines.append(f"<img src='{rel_tile}' style='max-width: 800px; width: 100%;'/>")
            html_lines.append("<h3>Selected Images</h3>")
            html_lines.append("<div>")
            for idx, _ in enumerate(selected, start=1):
                img_name = f"{describer._safe_id(listing_id or 'listing')}_img_{idx}.jpg"
                if os.path.exists(os.path.join(run_dir, img_name)):
                    html_lines.append(
                        f"<img src='{img_name}' style='max-width: 240px; margin: 4px;'/>"
                    )
            html_lines.append("</div>")
            html_lines.append("<h3>VLM Description</h3>")
            html_lines.append(f"<pre>{description}</pre>")
            html_lines.append("<hr/>")

    html_lines.append("</body></html>")
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(html_lines))

    print(f"Saved examples to: {run_dir}")
    print(f"- {index_path}")
    print(f"- {jsonl_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
