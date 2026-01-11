"""
Multimodal Encoders for the AI Brain.
Provides text and vision encoding using pre-trained transformer models.
"""
import os
import structlog
import numpy as np
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = structlog.get_logger()

@dataclass
class EncodedListing:
    """Container for all encoded representations of a listing."""
    listing_id: str
    text_embedding: np.ndarray
    image_embedding: Optional[np.ndarray] = None
    tabular_vector: Optional[np.ndarray] = None

class TextEncoder:
    """
    Encodes text (title + description) into dense vectors.
    Uses SentenceTransformers for semantic understanding.
    """
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info("text_encoder_initialized", model=model_name, dim=self.dimension)

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        """
        Encode a list of texts into vectors.
        
        Args:
            texts: List of text strings to encode
            normalize: Whether to L2-normalize the embeddings
            
        Returns:
            numpy array of shape (len(texts), dimension)
        """
        embeddings = self.model.encode(texts, normalize_embeddings=normalize)
        return np.array(embeddings).astype('float32')

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        """Encode a single text string."""
        return self.encode([text], normalize)[0]


class VisionEncoder:
    """
    Encodes images into dense vectors using CLIP.
    Supports interior/exterior image analysis.
    """
    def __init__(self, model_name: str = 'ViT-B-32', pretrained: str = 'laion2b_s34b_b79k'):
        """
        Initialize vision encoder with OpenCLIP model.
        
        Args:
            model_name: CLIP model architecture
            pretrained: Pretrained weights to use
        """
        self.model = None
        self.preprocess = None
        self.dimension = 512  # Default for ViT-B-32
        self.model_name = model_name
        self.pretrained = pretrained
        self._loaded = False
        
    def _lazy_load(self):
        """Lazy load the model to avoid slow imports at module level."""
        if self._loaded:
            return
            
        try:
            import open_clip
            import torch
            
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained
            )
            self.model.eval()
            
            # Get actual dimension
            with torch.no_grad():
                dummy = torch.zeros(1, 3, 224, 224)
                out = self.model.encode_image(dummy)
                self.dimension = out.shape[-1]
                
            self._loaded = True
            logger.info("vision_encoder_initialized", model=self.model_name, dim=self.dimension)
            
        except ImportError:
            logger.warning("open_clip_not_installed", msg="Vision encoding disabled. Install with: pip install open-clip-torch")
            self._loaded = False
        except Exception as e:
            logger.error("vision_encoder_init_failed", error=str(e))
            self._loaded = False

    def encode_images(self, image_paths: List[str]) -> Optional[np.ndarray]:
        """
        Encode multiple images into vectors.
        
        Args:
            image_paths: List of paths to image files
            
        Returns:
            numpy array of shape (len(image_paths), dimension) or None if failed
        """
        self._lazy_load()
        if not self._loaded or not self.model:
            return None
            
        if not image_paths:
            return None
            
        try:
            import torch
            from PIL import Image
            
            images = []
            valid_paths = []
            
            for path in image_paths:
                if os.path.exists(path):
                    try:
                        img = Image.open(path).convert('RGB')
                        img_tensor = self.preprocess(img)
                        images.append(img_tensor)
                        valid_paths.append(path)
                    except Exception as e:
                        logger.warning("image_load_failed", path=path, error=str(e))
                        
            if not images:
                return None
                
            batch = torch.stack(images)
            
            with torch.no_grad():
                embeddings = self.model.encode_image(batch)
                embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)  # L2 normalize
                
            return embeddings.cpu().numpy().astype('float32')
            
        except Exception as e:
            logger.error("image_encoding_failed", error=str(e))
            return None

    def encode_single(self, image_path: str) -> Optional[np.ndarray]:
        """Encode a single image."""
        result = self.encode_images([image_path])
        return result[0] if result is not None else None

    def pool_embeddings(self, embeddings: np.ndarray, method: str = 'mean') -> np.ndarray:
        """
        Pool multiple image embeddings into a single vector.
        
        Args:
            embeddings: Array of shape (N, dimension)
            method: 'mean', 'max', or 'first'
            
        Returns:
            Single pooled embedding
        """
        if method == 'mean':
            return np.mean(embeddings, axis=0)
        elif method == 'max':
            return np.max(embeddings, axis=0)
        elif method == 'first':
            return embeddings[0]
        else:
            return np.mean(embeddings, axis=0)


class TabularEncoder:
    """
    Encodes tabular features into a normalized vector.
    Simple but effective for combining with other modalities.
    """
    def __init__(self, feature_names: List[str] = None):
        """
        Initialize tabular encoder.
        
        Args:
            feature_names: Ordered list of feature names to encode
        """
        # Note: price is NOT included - it's the target variable we're predicting
        self.feature_names = feature_names or [
            'bedrooms', 'bathrooms', 'surface_area_sqm', 
            'year_built', 'floor', 'lat', 'lon', 'price_per_sqm'
        ]
        self.dimension = len(self.feature_names)
        
        # Statistics for normalization (will be updated from data)
        self.means: Dict[str, float] = {}
        self.stds: Dict[str, float] = {}
        
        # Defaults
        for name in self.feature_names:
            self.means[name] = 0.0
            self.stds[name] = 1.0

    def fit(self, data: List[Dict[str, float]]):
        """Compute normalization statistics from data."""
        import numpy as np
        
        for name in self.feature_names:
            values = [d.get(name, 0) for d in data if d.get(name) is not None]
            if values:
                self.means[name] = np.mean(values)
                self.stds[name] = np.std(values) + 1e-8
                
        logger.info("tabular_encoder_fitted", features=len(self.feature_names))

    def encode(self, features: Dict[str, float]) -> np.ndarray:
        """
        Encode a dictionary of features into a normalized vector.
        
        Args:
            features: Dictionary mapping feature names to values
            
        Returns:
            numpy array of shape (dimension,)
        """
        vec = []
        for name in self.feature_names:
            val = features.get(name, 0) or 0
            # Z-score normalization
            normalized = (val - self.means.get(name, 0)) / self.stds.get(name, 1)
            vec.append(normalized)
            
        return np.array(vec, dtype='float32')

    def encode_batch(self, features_list: List[Dict[str, float]]) -> np.ndarray:
        """Encode multiple feature dictionaries."""
        return np.array([self.encode(f) for f in features_list], dtype='float32')


class MultimodalEncoder:
    """
    Combines Text, Vision, and Tabular encoders into a unified representation.
    """
    def __init__(
        self,
        enable_vision: bool = True,
        text_model: str = 'all-MiniLM-L6-v2'
    ):
        self.text_encoder = TextEncoder(model_name=text_model)
        self.tabular_encoder = TabularEncoder()
        
        self.vision_encoder = None
        if enable_vision:
            self.vision_encoder = VisionEncoder()
        
        # Total dimension depends on whether vision is enabled
        self._dimension = None

    @property
    def dimension(self) -> int:
        """Total embedding dimension."""
        if self._dimension is None:
            dim = self.text_encoder.dimension + self.tabular_encoder.dimension
            if self.vision_encoder:
                dim += self.vision_encoder.dimension
            self._dimension = dim
        return self._dimension

    def encode_listing(
        self,
        listing_id: str,
        text: str,
        features: Dict[str, float],
        image_paths: List[str] = None
    ) -> EncodedListing:
        """
        Create a complete multimodal encoding of a listing.
        
        Args:
            listing_id: Unique identifier for the listing
            text: Combined title and description
            features: Tabular features dictionary
            image_paths: Optional list of image file paths
            
        Returns:
            EncodedListing with all embeddings
        """
        # Text
        text_emb = self.text_encoder.encode_single(text)
        
        # Tabular
        tab_vec = self.tabular_encoder.encode(features)
        
        # Vision (optional)
        image_emb = None
        if self.vision_encoder and image_paths:
            embeddings = self.vision_encoder.encode_images(image_paths)
            if embeddings is not None and len(embeddings) > 0:
                image_emb = self.vision_encoder.pool_embeddings(embeddings)
        
        return EncodedListing(
            listing_id=listing_id,
            text_embedding=text_emb,
            image_embedding=image_emb,
            tabular_vector=tab_vec
        )

    def concat_embeddings(self, encoded: EncodedListing) -> np.ndarray:
        """
        Concatenate all embeddings into a single vector.
        Uses zero-padding for missing modalities.
        """
        parts = [encoded.text_embedding]
        
        if encoded.tabular_vector is not None:
            parts.append(encoded.tabular_vector)
        else:
            parts.append(np.zeros(self.tabular_encoder.dimension, dtype='float32'))
            
        if self.vision_encoder:
            if encoded.image_embedding is not None:
                parts.append(encoded.image_embedding)
            else:
                parts.append(np.zeros(self.vision_encoder.dimension, dtype='float32'))
                
        return np.concatenate(parts)
