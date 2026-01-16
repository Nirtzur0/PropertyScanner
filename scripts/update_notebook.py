import json
import os

notebook_path = 'notebooks/project_overview.ipynb'

new_cells = [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 4. VLM Input Visualization\n",
    "\n",
    "The Vision Language Model (VLM) doesn't just see one image at a time. To efficiently process property listings, we stitch multiple images into a single grid. This allows the model to reason about the property holistically (e.g., consistency of style, layout).\n",
    "\n",
    "Below, we visualize exactly what the VLM \"sees\" for a few examples."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "from PIL import Image\n",
    "import requests\n",
    "import io\n",
    "import json\n",
    "\n",
    "def visualize_vlm_input(image_urls_json, max_images=6):\n",
    "    \"\"\"\n",
    "    Recreates the VLM input grid from a list of image URLs.\n",
    "    \"\"\"\n",
    "    try:\n",
    "        image_urls = json.loads(image_urls_json)\n",
    "    except:\n",
    "        image_urls = []\n",
    "    \n",
    "    if not image_urls:\n",
    "        print(\"No images found.\")\n",
    "        return\n",
    "        \n",
    "    # Download images (limit to max_images)\n",
    "    pil_images = []\n",
    "    headers = {'User-Agent': 'Mozilla/5.0'} \n",
    "    for url in image_urls[:max_images]:\n",
    "        try:\n",
    "            # Basic check for local vs remote\n",
    "            if url.startswith(\"http\"):\n",
    "                resp = requests.get(url, headers=headers, timeout=5)\n",
    "                if resp.status_code == 200:\n",
    "                    img = Image.open(io.BytesIO(resp.content)).convert(\"RGB\")\n",
    "                    pil_images.append(img)\n",
    "            else:\n",
    "                # Handle local files if any (though dataframe usually has URLs)\n",
    "                pass \n",
    "        except Exception as e:\n",
    "            pass # Skip failed images\n",
    "            \n",
    "    if not pil_images:\n",
    "        print(\"Could not download any images.\")\n",
    "        return\n",
    "\n",
    "    # Stitching parameters\n",
    "    thumb_size = 512\n",
    "    cols = 2\n",
    "    count = len(pil_images)\n",
    "    rows = (count + 1) // 2\n",
    "    w, h = thumb_size, thumb_size\n",
    "    \n",
    "    # Create canvas\n",
    "    stitched_img = Image.new('RGB', (cols * w, rows * h), (255, 255, 255))\n",
    "    \n",
    "    for i, img in enumerate(pil_images):\n",
    "        # Resize to square (simple resize for this viz, real pipeline might differ slightly)\n",
    "        img = img.resize((w, h))\n",
    "        \n",
    "        x = (i % cols) * w\n",
    "        y = (i // cols) * h\n",
    "        stitched_img.paste(img, (x, y))\n",
    "        \n",
    "    return stitched_img\n",
    "\n",
    "# Select a few Interesting Examples (with descriptions)\n",
    "examples = df[df['vlm_description'].notna()].sample(3, random_state=42)\n",
    "\n",
    "for idx, row in examples.iterrows():\n",
    "    print(f\"\\n--- Property: {row['title']} ---\")\n",
    "    print(f\"Location: {row['city']}, Price: €{row['price']:,.0f}\")\n",
    "    \n",
    "    # Show VLM Description\n",
    "    try:\n",
    "        desc = json.loads(row['vlm_description'])\n",
    "        print(\"\\nVLM Analysis:\")\n",
    "        print(json.dumps(desc, indent=2))\n",
    "    except:\n",
    "        print(f\"\\nRaw Description: {row['vlm_description']}\")\n",
    "\n",
    "    # Show Input Image Grid\n",
    "    print(\"\\nVLM Input (Stitched Grid):\")\n",
    "    stitched = visualize_vlm_input(row['image_urls'])\n",
    "    if stitched:\n",
    "        display(stitched)\n",
    "    print(\"-\" * 80)"
   ]
  }
]

try:
    with open(notebook_path, 'r') as f:
        nb = json.load(f)
    
    # Check if visualization cells already exist (simple check)
    exists = False
    for cell in nb['cells']:
        if "VLM Input Visualization" in "".join(cell.get('source', [])):
            exists = True
            break
    
    if not exists:
        nb['cells'].extend(new_cells)
        
        with open(notebook_path, 'w') as f:
            json.dump(nb, f, indent=1)
        print("Notebook updated successfully.")
    else:
        print("Visualization section already exists.")

except Exception as e:
    print(f"Error updating notebook: {e}")
