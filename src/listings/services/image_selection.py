import io
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
import structlog
from PIL import Image, ImageFilter, ImageOps

from src.platform.settings import ImageSelectorConfig

logger = structlog.get_logger(__name__)


@dataclass
class ImageCandidate:
    url: str
    image: Image.Image
    width: int
    height: int
    score: float = 0.0
    scores: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    ahash: Optional[int] = None

    def to_debug(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "score": round(self.score, 4),
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "reasons": list(self.reasons),
        }


@dataclass
class ImageSelectionResult:
    selected: List[ImageCandidate]
    rejected: List[ImageCandidate]
    errors: List[str]


class ClipRelevanceScorer:
    POSITIVE_PROMPTS = [
        "interior of a home",
        "kitchen interior",
        "living room interior",
        "bedroom interior",
        "bathroom interior",
        "apartment interior photo",
    ]
    NEGATIVE_PROMPTS = [
        "map",
        "floor plan",
        "blueprint",
        "logo",
        "street map",
        "exterior of a building",
        "site plan",
    ]

    def __init__(self) -> None:
        self._loaded = False
        self._available = None
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._text_features = None
        self._pos_count = len(self.POSITIVE_PROMPTS)

    def _lazy_load(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            import open_clip
            import torch

            self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32",
                pretrained="laion2b_s34b_b79k",
            )
            self._model.eval()
            self._tokenizer = open_clip.get_tokenizer("ViT-B-32")

            prompts = self.POSITIVE_PROMPTS + self.NEGATIVE_PROMPTS
            tokens = self._tokenizer(prompts)
            with torch.no_grad():
                text_features = self._model.encode_text(tokens)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            self._text_features = text_features

            self._loaded = True
            self._available = True
        except Exception as exc:
            logger.info("clip_unavailable", error=str(exc))
            self._available = False
        return self._available

    def score(self, images: List[Image.Image]) -> Optional[List[float]]:
        if not images:
            return None
        if not self._lazy_load():
            return None

        import torch

        tensors = []
        for img in images:
            tensors.append(self._preprocess(img))
        if not tensors:
            return None

        batch = torch.stack(tensors)
        with torch.no_grad():
            image_features = self._model.encode_image(batch)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            sims = image_features @ self._text_features.T

        pos = sims[:, : self._pos_count].mean(dim=1)
        neg = sims[:, self._pos_count :].mean(dim=1)
        scores = (pos - neg).cpu().numpy().tolist()
        return [float(s) for s in scores]


class ImageSelector:
    """
    Scores and filters listing images to keep the most relevant interior shots.
    Uses lightweight heuristics, with optional CLIP ranking if available.
    """

    def __init__(
        self,
        max_candidates: Optional[int] = None,
        max_bytes: Optional[int] = None,
        min_side: Optional[int] = None,
        min_pixels: Optional[int] = None,
        duplicate_threshold: Optional[int] = None,
        use_clip: Optional[bool] = None,
        clip_weight: Optional[float] = None,
        config: Optional[ImageSelectorConfig] = None,
    ) -> None:
        if config is None:
            config = ImageSelectorConfig()

        self.max_candidates = config.max_candidates if max_candidates is None else max_candidates
        self.max_bytes = config.max_bytes if max_bytes is None else max_bytes
        self.min_side = config.min_side if min_side is None else min_side
        self.min_pixels = config.min_pixels if min_pixels is None else min_pixels
        self.duplicate_threshold = (
            config.duplicate_threshold if duplicate_threshold is None else duplicate_threshold
        )
        self.use_clip = config.use_clip if use_clip is None else use_clip
        self.clip_weight = config.clip_weight if clip_weight is None else clip_weight
        self._clip = ClipRelevanceScorer()

    def select(self, image_urls: List[str], max_images: int = 4) -> ImageSelectionResult:
        if not image_urls:
            return ImageSelectionResult(selected=[], rejected=[], errors=[])

        deduped = []
        seen = set()
        for url in image_urls:
            if not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            deduped.append(url)

        candidates: List[ImageCandidate] = []
        errors: List[str] = []

        for url in deduped[: self.max_candidates]:
            img = self._download_image(url)
            if not img:
                errors.append(f"download_failed:{url}")
                continue
            width, height = img.size
            candidate = ImageCandidate(url=url, image=img, width=width, height=height)
            score, scores, reasons = self._score_image(img)
            candidate.score = score
            candidate.scores = scores
            candidate.reasons = reasons
            candidate.ahash = self._average_hash(img)
            candidates.append(candidate)

        if not candidates:
            return ImageSelectionResult(selected=[], rejected=[], errors=errors)

        if self.use_clip:
            clip_scores = self._clip.score([c.image for c in candidates])
            if clip_scores:
                for candidate, clip_score in zip(candidates, clip_scores):
                    candidate.scores["clip"] = clip_score
                    candidate.score += self.clip_weight * clip_score

        candidates.sort(key=lambda c: c.score, reverse=True)

        selected: List[ImageCandidate] = []
        rejected: List[ImageCandidate] = []

        for candidate in candidates:
            if self._is_duplicate(candidate, selected):
                candidate.reasons.append("near_duplicate")
                rejected.append(candidate)
                continue
            selected.append(candidate)
            if len(selected) >= max_images:
                break

        selected_ids = {id(c) for c in selected}
        rejected_ids = {id(c) for c in rejected}
        for candidate in candidates:
            if id(candidate) in selected_ids or id(candidate) in rejected_ids:
                continue
            candidate.reasons.append("lower_score")
            rejected.append(candidate)

        if not selected and candidates:
            selected = [candidates[0]]
            rejected = [c for c in candidates[1:]]

        return ImageSelectionResult(selected=selected, rejected=rejected, errors=errors)

    def _download_image(self, url: str) -> Optional[Image.Image]:
        try:
            if url.startswith("http"):
                resp = requests.get(
                    url,
                    timeout=10,
                    headers={"User-Agent": "PropertyScanner/1.0"},
                )
                if resp.status_code != 200:
                    return None
                content = resp.content
            else:
                with open(url, "rb") as handle:
                    content = handle.read()

            if not content or len(content) > self.max_bytes:
                return None

            img = Image.open(io.BytesIO(content))
            img = ImageOps.exif_transpose(img).convert("RGB")
            return img
        except Exception as exc:
            logger.warning("image_download_failed", url=url[:80], error=str(exc))
            return None

    def _score_image(self, image: Image.Image) -> Tuple[float, Dict[str, float], List[str]]:
        width, height = image.size
        aspect = width / max(height, 1)
        resolution = width * height

        resized = image.resize((256, 256))
        arr = np.asarray(resized).astype("float32")
        gray = np.mean(arr, axis=2) / 255.0
        brightness = float(gray.mean())
        contrast = float(gray.std())

        edges = resized.filter(ImageFilter.FIND_EDGES)
        edge_mean = float(np.asarray(edges).mean() / 255.0)

        colorfulness = self._colorfulness(arr)

        res_score = min(1.0, resolution / 900_000.0)
        sharpness = min(1.0, edge_mean / 0.18)
        color_score = min(1.0, colorfulness / 60.0)
        contrast_score = min(1.0, contrast / 0.25)

        score = (
            0.35 * res_score
            + 0.25 * sharpness
            + 0.2 * color_score
            + 0.2 * contrast_score
        )

        reasons = []
        penalty = 0.0

        if resolution < self.min_pixels or min(width, height) < self.min_side:
            penalty += 0.35
            reasons.append("low_resolution")

        if aspect > 2.3 or aspect < 0.45:
            penalty += 0.15
            reasons.append("banner_aspect")

        if colorfulness < 6 and edge_mean > 0.12:
            penalty += 0.35
            reasons.append("line_art_map")

        if colorfulness < 4 and brightness > 0.85:
            penalty += 0.2
            reasons.append("mostly_white")

        if edge_mean < 0.02:
            penalty += 0.15
            reasons.append("low_detail")

        score = max(0.0, score - penalty)

        return score, {
            "resolution": res_score,
            "sharpness": sharpness,
            "color": color_score,
            "contrast": contrast_score,
            "edge_mean": edge_mean,
            "brightness": brightness,
            "colorfulness": colorfulness,
        }, reasons

    def _colorfulness(self, arr: np.ndarray) -> float:
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]
        rg = np.abs(r - g)
        yb = np.abs(0.5 * (r + g) - b)
        std_rg = np.std(rg)
        std_yb = np.std(yb)
        mean_rg = np.mean(rg)
        mean_yb = np.mean(yb)
        return float(math.sqrt(std_rg ** 2 + std_yb ** 2) + 0.3 * math.sqrt(mean_rg ** 2 + mean_yb ** 2))

    def _average_hash(self, image: Image.Image) -> int:
        img = image.convert("L").resize((8, 8))
        pixels = np.asarray(img).astype("float32")
        mean_val = float(pixels.mean())
        bits = pixels >= mean_val
        flat = bits.flatten()
        value = 0
        for idx, bit in enumerate(flat):
            if bit:
                value |= 1 << idx
        return value

    def _is_duplicate(self, candidate: ImageCandidate, selected: List[ImageCandidate]) -> bool:
        if candidate.ahash is None:
            return False
        for chosen in selected:
            if chosen.ahash is None:
                continue
            if self._hamming_distance(candidate.ahash, chosen.ahash) <= self.duplicate_threshold:
                return True
        return False

    @staticmethod
    def _hamming_distance(a: int, b: int) -> int:
        return bin(a ^ b).count("1")
