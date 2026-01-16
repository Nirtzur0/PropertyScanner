import structlog
from typing import List, Optional, Dict, Any
from src.core.domain.schema import CanonicalListing
from src.services.vlm import VLMImageDescriber
from src.services.description_analyst import DescriptionAnalyst
from src.services.feature_sanitizer import sanitize_listing_features

logger = structlog.get_logger()

class FeatureFusionService:
    """
    Single source of truth for feature extraction.
    Orchestrates Raw Data, LLM Text Analysis, and VLM Visual Analysis.
    
    Priority for Facts:
    1. Raw HTML (PisosNormalizer) - Highest confidence
    2. LLM Description Analysis - High confidence interpretation
    3. VLM Visual Verification - Medium confidence (can hallucinate small details)
    """
    
    def __init__(self):
        self.vlm = VLMImageDescriber(model="llava")
        self.analyst = DescriptionAnalyst()
        
    def fuse(self, listing: CanonicalListing, run_vlm: bool = True) -> CanonicalListing:
        """
        Orchestrates the enrichment pipeline:
        1. Analyzes Description (LLM)
        2. Analyzes Images (VLM)
        3. Fuses data into the listing object (in-place)
        """
        # 1. LLM Analysis
        llm_data = {}
        if listing.description:
            try:
                llm_data = self.analyst.analyze(listing.description)
                listing.analysis_meta = llm_data
            except Exception as e:
                logger.error("fusion_llm_failed", id=listing.id, error=str(e))

        # 2. VLM Analysis
        vlm_data = {}
        vlm_text = ""
        if run_vlm and listing.image_urls:
            try:
                # Cast HttpUrl to str for VLM
                img_urls = [str(u) for u in listing.image_urls]
                vlm_text = self.vlm.describe_images(img_urls, max_images=4)
                
                # Parse VLM JSON
                import json
                import re
                try:
                    # Try to find a JSON block
                    json_match = re.search(r'\{.*\}', vlm_text.replace('\n', ' '), re.DOTALL)
                    if json_match:
                        vlm_data = json.loads(json_match.group())
                    else:
                        # Fallback try simple cleaning
                        clean_text = vlm_text.replace("```json", "").replace("```", "").strip()
                        vlm_data = json.loads(clean_text)
                except:
                    logger.warning("vlm_json_parse_failed", id=listing.id, vlm_text=vlm_text)
                    vlm_data = {}
            except Exception as e:
                logger.error("fusion_vlm_failed", id=listing.id, error=str(e))

        # 3. MERGE LOGIC
        
        # A. Apply LLM Facts
        facts = llm_data.get("facts", {})
        if listing.has_elevator is None:
            if "has_elevator" in facts: listing.has_elevator = facts["has_elevator"]
        if listing.floor is None:
            if "floor" in facts: listing.floor = facts["floor"]
        
        # B. Apply Financial Analysis (Tags)
        financial = llm_data.get("financial_analysis", {})
        pos_drivers = financial.get("positive_drivers", [])
        neg_drivers = financial.get("negative_drivers", [])
        
        current_tags = set(listing.tags)
        for dr in pos_drivers: current_tags.add(f"PLUS:{dr}")
        for dr in neg_drivers: current_tags.add(f"MINUS:{dr}")
        listing.tags = list(current_tags)
        
        # C. SENTIMENT SCORES (Text vs Image)
        # Text
        if "investor_sentiment" in financial:
            try:
                sentiment = float(financial["investor_sentiment"])
                if sentiment > 1.0:
                    sentiment = 1.0
                elif sentiment < -1.0:
                    sentiment = -1.0
                listing.text_sentiment = sentiment
            except: pass
            
        # Image
        if "visual_sentiment" in vlm_data:
            try:
                 sentiment = float(vlm_data["visual_sentiment"])
                 if sentiment > 1.0:
                     sentiment = 1.0
                 elif sentiment < -1.0:
                     sentiment = -1.0
                 listing.image_sentiment = sentiment
            except: pass
            
        # D. Store Raw VLM Text
        if vlm_text:
            listing.vlm_description = vlm_text

        return sanitize_listing_features(listing)
