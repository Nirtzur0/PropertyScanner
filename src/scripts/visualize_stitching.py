import json
import sqlite3

from src.core.config import DEFAULT_DB_PATH
from src.services.vlm import VLMImageDescriber

# Connect to DB
conn = sqlite3.connect(str(DEFAULT_DB_PATH))
cursor = conn.cursor()

# Get a listing with images
cursor.execute(
    "SELECT id, image_urls FROM listings WHERE image_urls IS NOT NULL AND image_urls != '[]' ORDER BY RANDOM() LIMIT 1"
)
row = cursor.fetchone()

if not row:
    print("No listings with images found.")
    exit()

listing_id, image_payload = row
image_urls = json.loads(image_payload)
print(f"Found listing {listing_id} with {len(image_urls)} images.")

describer = VLMImageDescriber()
result = describer.describe_images_with_debug(
    image_urls=image_urls,
    max_images=4,
    output_dir="data/vlm_debug",
    listing_id=listing_id,
    run_vlm=False,
)

tile_path = result.get("tile_path")
selected = result.get("selected", [])

if tile_path:
    print(f"\n✅ Saved stitched visualization to: {tile_path}")
else:
    print("No tile generated.")

print(f"Selected {len(selected)} images for the VLM tile.")
print("(This matches exactly what the VLM sees during harvest)")
