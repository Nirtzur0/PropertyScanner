import sqlite3
import json
import random
import io
from PIL import Image
import requests
import base64
import matplotlib.pyplot as plt

# Connect to DB
conn = sqlite3.connect('data/listings.db')
cursor = conn.cursor()

# Get a listing with images
cursor.execute("SELECT image_urls FROM listings WHERE image_urls IS NOT NULL AND image_urls != '[]' ORDER BY RANDOM() LIMIT 1")
row = cursor.fetchone()

if not row:
    print("No listings with images found.")
    exit()

image_urls = json.loads(row[0])
print(f"Found listing with {len(image_urls)} images.")

# --- VLM Stitching Logic (Replicated exactly) ---
max_images = 4
pil_images = []

for url in image_urls[:max_images]:
    try:
        print(f"Downloading {url}...")
        if url.startswith("http"):
            resp = requests.get(url, timeout=10)
            img_bytes = resp.content
        else:
            with open(url, "rb") as f:
                img_bytes = f.read()
        
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        pil_images.append(img)
    except Exception as e:
        print(f"Failed to download: {e}")

if not pil_images:
    print("No images downloaded.")
    exit()

# Stitch images
thumb_size = 512
count = len(pil_images)

if count == 1:
    stitched_img = pil_images[0]
else:
    # Create grid (2 columns)
    cols = 2
    rows = (count + 1) // 2
    w = thumb_size
    h = thumb_size
    
    stitched_img = Image.new('RGB', (cols * w, rows * h))
    
    for i, img in enumerate(pil_images):
        img = img.resize((w, h))
        x = (i % cols) * w
        y = (i // cols) * h
        stitched_img.paste(img, (x, y))

# Show/Save
output_path = "stitched_sample_debug.jpg"
stitched_img.save(output_path)
print(f"\n✅ Saved stitched visualization to: {output_path}")
print(f"Grid Size: {stitched_img.size}")
print("(This matches exactly what the VLM sees during harvest)")
