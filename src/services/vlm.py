"""
VLM Service for image description.
"""
import structlog
from typing import List
from PIL import Image
import io

logger = structlog.get_logger()

class VLMImageDescriber:
    """
    Uses Ollama's vision model to extract structured descriptions from property images.
    Descriptions are cached in the database to avoid re-processing.
    """
    def __init__(self, model: str = "llava"):
        self.model = model
        self._available = None

    def _check_availability(self) -> bool:
        """Check if Ollama and a vision model are available."""
        if self._available is not None:
            return self._available

        try:
            import ollama
            response = ollama.list()
            # Handle new API: response.models is a list of Model objects
            models = response.models if hasattr(response, 'models') else response.get('models', [])
            model_names = []
            for m in models:
                # New API uses .model attribute, old uses dict
                name = m.model if hasattr(m, 'model') else m.get('name', '')
                model_names.append(name.split(':')[0])

            # Check for vision-capable models
            vision_models = ['llava', 'moondream', 'bakllava', 'llava-phi3']
            self._available = any(vm in model_names for vm in vision_models)
            if self._available:
                for vm in vision_models:
                    if vm in model_names:
                        self.model = vm
                        break
                logger.info("vlm_available", model=self.model)
            else:
                logger.info("no_vision_model_installed", available=model_names,
                           hint="Run: ollama pull llava")
        except Exception as e:
            logger.warning("ollama_not_available", error=str(e))
            self._available = False

        return self._available

    def describe_images(self, image_urls: List[str], max_images: int = 2) -> str:
        """
        Generate text descriptions from property images.

        Args:
            image_urls: List of image URLs or local paths
            max_images: Maximum number of images to process

        Returns:
            Combined description string
        """
        if not self._check_availability():
            return ""

        if not image_urls:
            return ""

        try:
            import ollama
            import requests
            import base64

            # Download images
            pil_images = []
            for url in image_urls[:max_images]:
                try:
                    if url.startswith("http"):
                        resp = requests.get(url, timeout=10)
                        img_bytes = resp.content
                    else:
                        with open(url, "rb") as f:
                            img_bytes = f.read()
                    
                    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    pil_images.append(img)
                except Exception as e:
                    logger.warning("image_download_failed", url=url[:50], error=str(e))

            if not pil_images:
                return ""

            # Stitch images
            # Target individual size
            thumb_size = 512
            
            # Simple stitching logic
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
                    # Resize/Crop center to fit square
                    # img.thumbnail((w, h)) -- maintains aspect ratio, might verify background
                    # Let's just resize for simplicity or CenterCrop
                    img = img.resize((w, h))
                    
                    x = (i % cols) * w
                    y = (i // cols) * h
                    stitched_img.paste(img, (x, y))

            # Encode
            byte_arr = io.BytesIO()
            stitched_img.save(byte_arr, format='JPEG', quality=85)
            standardized_b64 = base64.b64encode(byte_arr.getvalue()).decode()

            # Update prompt context
            prompt = (
                "This image is a composite grid of 4 separate property photos. Analyze the grid as a whole. "
                "Provide a strict JSON summary of the visible features. Do not use markdown. Format: "
                "{"
                "\"condition\": \"renovated/good/fair/needs_work\", "
                "\"quality\": \"luxury/standard/basic\", "
                "\"visual_sentiment\": 0.0, " 
                "\"rooms\": [\"kitchen\", \"bedroom\", \"bathroom\", \"balcony\"], "
                "\"features\": [\"hardwood_floors\", \"modern_kitchen\", \"large_windows\", \"view\", \"pool\", \"terrace\"], "
                "\"summary\": \"Concise 10-word description of value drivers.\""
                "}"
            )

            import time
            retries = 3
            for attempt in range(retries):
                try:
                    response = ollama.generate(
                        model=self.model,
                        prompt=prompt,
                        images=[standardized_b64],
                        format='json'
                    )
                    return response.get('response', '')
                except Exception as oe:
                    if attempt < retries - 1:
                        wait = 2 ** attempt
                        logger.warning(f"Ollama call failed, retrying in {wait}s", error=str(oe))
                        time.sleep(wait)
                    else:
                        raise oe

        except Exception as e:
            logger.error("vlm_describe_failed", error=str(e))
            return ""
