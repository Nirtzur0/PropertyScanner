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

            descriptions = []
            prompt = (
                "Analyze this property image for real estate valuation. "
                "In 40 words describe: "
                "1) Room type (living room, kitchen, bedroom, bathroom, exterior) "
                "2) Condition (new/renovated/needs renovation/old) "
                "3) Quality (luxury/modern/standard/basic) "
                "4) Key value-affecting features (natural light, views, finishes, appliances)"
            )

            for url in image_urls[:max_images]:
                try:
                    if url.startswith("http"):
                        resp = requests.get(url, timeout=10)
                        img_bytes = resp.content
                    else:
                        with open(url, "rb") as f:
                            img_bytes = f.read()

                    # Standardize image to prevent Ollama runner crashes
                    # Use 336x336 (native for Llava) or generic 512x512
                    with Image.open(io.BytesIO(img_bytes)) as img:
                        img = img.convert("RGB")
                        img = img.resize((512, 512))
                        byte_arr = io.BytesIO()
                        img.save(byte_arr, format='PNG')
                        standardized_b64 = base64.b64encode(byte_arr.getvalue()).decode()

                    response = ollama.generate(
                        model=self.model,
                        prompt=prompt,
                        images=[standardized_b64]
                    )
                    descriptions.append(response.get('response', ''))
                except Exception as e:
                    logger.warning("image_description_failed", url=url[:50], error=str(e))

            return " ".join(descriptions)

        except Exception as e:
            logger.error("vlm_describe_failed", error=str(e))
            return ""
