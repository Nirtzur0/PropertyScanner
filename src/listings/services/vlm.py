"""
VLM Service for image description.
"""
import base64
import io
import os
import re
import time
from typing import Dict, List, Optional

import structlog
from PIL import Image
from litellm import completion

from src.platform.settings import ImageSelectorConfig, VLMConfig
from src.listings.services.image_selection import ImageSelector
from src.platform.utils.llm import build_completion_kwargs

logger = structlog.get_logger()


class VisionBackendUnsupportedError(RuntimeError):
    pass


class VLMImageDescriber:
    """
    Uses a configurable vision backend to extract structured descriptions from property images.
    """
    def __init__(
        self,
        config: Optional[VLMConfig] = None,
        model: Optional[str] = None,
        image_selector: Optional[ImageSelector] = None,
        image_selector_config: Optional[ImageSelectorConfig] = None,
    ):
        if config is None:
            config = VLMConfig()

        self.config = config
        self.provider = config.provider
        self.model = model or config.model
        self.api_base = config.api_base
        self.api_key_env = config.api_key_env
        self.supports_vision = config.supports_vision
        self._available = None
        if image_selector is None:
            image_selector = ImageSelector(config=image_selector_config)
        self.selector = image_selector
        self.max_images = config.max_images
        self.debug_max_images = config.debug_max_images
        self.timeout_seconds = config.timeout_seconds

    def _check_availability(self) -> bool:
        """Check if the configured vision backend is available."""
        if self._available is not None:
            return self._available

        if self.provider != "ollama":
            self._available = bool(self.supports_vision and self.model and self.api_base)
            if not self._available:
                logger.info(
                    "vlm_backend_unavailable",
                    provider=self.provider,
                    model=self.model,
                    api_base=self.api_base,
                    supports_vision=self.supports_vision,
                )
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

    def describe_images(self, image_urls: List[str], max_images: Optional[int] = None) -> str:
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
            limit = self.max_images if max_images is None else max_images
            selection = self.selector.select(image_urls, max_images=limit)
            if not selection.selected:
                return ""

            stitched_img = self._stitch_images([c.image for c in selection.selected])
            return self._run_vlm_on_tile(stitched_img)

        except VisionBackendUnsupportedError:
            raise
        except Exception as e:
            logger.error("vlm_describe_failed", error=str(e))
            return ""

    def describe_images_with_debug(
        self,
        image_urls: List[str],
        max_images: Optional[int] = None,
        output_dir: Optional[str] = None,
        listing_id: Optional[str] = None,
        run_vlm: bool = True,
    ) -> Dict[str, object]:
        """
        Generate description + selection debug metadata and optionally save tiles.
        """
        limit = self.debug_max_images if max_images is None else max_images
        return self._describe_images_internal(
            image_urls=image_urls,
            max_images=limit,
            output_dir=output_dir,
            listing_id=listing_id,
            run_vlm=run_vlm,
        )

    def _describe_images_internal(
        self,
        image_urls: List[str],
        max_images: int,
        output_dir: Optional[str],
        listing_id: Optional[str],
        run_vlm: bool,
    ) -> Dict[str, object]:
        selection = self.selector.select(image_urls, max_images=max_images)
        selected = selection.selected
        if not selected:
            return {
                "description": "",
                "selected": [],
                "rejected": [c.to_debug() for c in selection.rejected],
                "errors": list(selection.errors),
                "vlm_available": self._check_availability(),
            }

        stitched_img = self._stitch_images([c.image for c in selected])

        debug_paths = {}
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            safe_id = self._safe_id(listing_id or "listing")
            tile_name = f"{safe_id}_tile.jpg"
            tile_path = os.path.join(output_dir, tile_name)
            stitched_img.save(tile_path, format="JPEG", quality=85)
            debug_paths["tile_path"] = tile_path

            selected_paths = []
            for idx, candidate in enumerate(selected, start=1):
                img_name = f"{safe_id}_img_{idx}.jpg"
                img_path = os.path.join(output_dir, img_name)
                candidate.image.save(img_path, format="JPEG", quality=85)
                selected_paths.append(img_path)
            debug_paths["selected_paths"] = selected_paths

        description = ""
        vlm_available = self._check_availability()
        if run_vlm and vlm_available:
            description = self._run_vlm_on_tile(stitched_img)

        return {
            "description": description,
            "selected": [c.to_debug() for c in selected],
            "rejected": [c.to_debug() for c in selection.rejected],
            "errors": list(selection.errors),
            "vlm_available": vlm_available,
            **debug_paths,
        }

    def _stitch_images(self, images: List[Image.Image], thumb_size: int = 512) -> Image.Image:
        if not images:
            return Image.new("RGB", (thumb_size, thumb_size))

        count = len(images)
        if count == 1:
            return images[0]

        cols = 2
        rows = (count + 1) // 2
        w = thumb_size
        h = thumb_size

        stitched_img = Image.new("RGB", (cols * w, rows * h))
        for idx, img in enumerate(images):
            resized = img.resize((w, h))
            x = (idx % cols) * w
            y = (idx // cols) * h
            stitched_img.paste(resized, (x, y))
        return stitched_img

    def _run_vlm_on_tile(self, stitched_img: Image.Image) -> str:
        byte_arr = io.BytesIO()
        stitched_img.save(byte_arr, format="JPEG", quality=85)
        standardized_b64 = base64.b64encode(byte_arr.getvalue()).decode()

        prompt = """This image is a composite grid of property photos. Analyze the grid as a whole.
Only report what is visible. If unsure, use "unknown" or empty lists rather than guessing.
Return strict JSON only, no markdown. Use snake_case for list items; keep lists to 8 items max.

Definitions:
- condition: renovated (fresh, like-new), good (clean/updated), fair (dated but serviceable), needs_work (visible damage/wear).
- quality: luxury (premium materials/fixtures, designer finishes), standard (mid-market), basic (low-end finishes).
- luxury_vs_fixer: luxury only if quality=luxury and condition in {renovated,good}; fixer_upper if condition=needs_work or major defects.
- If rooms are mixed, choose the lower condition/quality. If view is not visible, use "unknown".

JSON format:
{
  "condition": "renovated/good/fair/needs_work/unknown",
  "quality": "luxury/standard/basic/unknown",
  "luxury_vs_fixer": "luxury/standard/fixer_upper/unknown",
  "visual_sentiment": 0.0,
  "rooms": ["kitchen", "living_room", "bedroom", "bathroom", "dining_room", "hallway", "balcony", "terrace"],
  "features": ["hardwood_floors", "tile_floors", "modern_kitchen", "large_windows", "built_in_wardrobes", "fireplace", "air_conditioning_unit"],
  "value_drivers": ["natural_light", "spacious_rooms", "quality_finishes", "renovated_kitchen", "views"],
  "red_flags": ["water_damage", "mold_or_damp", "broken_fixtures", "unsafe_wiring", "unfinished_renovation", "poor_lighting"],
  "lighting": "dark/average/bright/unknown",
  "ceiling_height": "low/standard/high/unknown",
  "layout": "open_plan/segmented/unknown",
  "view_type": "none/street/courtyard/park/sea/city/unknown",
  "staging": "poor/average/good/unknown",
  "summary": "Concise 10-word description of value drivers and risks."
}

visual_sentiment must be a float in [-1.0, 1.0]:
-1.0 = severe negatives (dilapidated, unsafe)
0.0 = neutral/standard condition
+1.0 = exceptional quality/renovation
"""

        if self.provider == "ollama":
            return self._run_ollama_vlm_on_tile(standardized_b64, prompt)

        return self._run_openai_compatible_vlm_on_tile(standardized_b64, prompt)

    def _run_ollama_vlm_on_tile(self, standardized_b64: str, prompt: str) -> str:
        import ollama

        retries = 3
        for attempt in range(retries):
            try:
                response = ollama.generate(
                    model=self.model,
                    prompt=prompt,
                    images=[standardized_b64],
                    format="json",
                    options={"timeout": self.timeout_seconds},
                )
                return response.get("response", "")
            except Exception as exc:
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    logger.warning("vlm_retrying", wait_seconds=wait, error=str(exc))
                    time.sleep(wait)
                else:
                    raise

        return ""

    def _run_openai_compatible_vlm_on_tile(self, standardized_b64: str, prompt: str) -> str:
        data_url = f"data:image/jpeg;base64,{standardized_b64}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]

        try:
            response = completion(
                **build_completion_kwargs(
                    model=self.model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=900,
                    timeout_seconds=self.timeout_seconds,
                    api_base=self.api_base,
                    api_key_env=self.api_key_env,
                    response_format={"type": "json_object"},
                )
            )
        except Exception as exc:
            message = str(exc)
            logger.error(
                "vlm_backend_request_failed",
                provider=self.provider,
                model=self.model,
                api_base=self.api_base,
                error=message,
            )
            lowered = message.lower()
            if "vision" in lowered or "image" in lowered or "multimodal" in lowered:
                raise VisionBackendUnsupportedError(message) from exc
            raise

        response_data = response if isinstance(response, dict) else getattr(response, "model_dump", lambda: {})()
        choices = response_data.get("choices", []) if isinstance(response_data, dict) else []
        if not choices and hasattr(response, "choices"):
            choices = response.choices
        if not choices:
            raise VisionBackendUnsupportedError("vlm_missing_choices")

        choice = choices[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else getattr(choice, "message", {}) or {}
        content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "") or ""
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                    text_parts.append(str(item.get("text", "")))
            content = "\n".join(part for part in text_parts if part)
        return str(content or "")

    def _safe_id(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
        return cleaned.strip("_") or "listing"
