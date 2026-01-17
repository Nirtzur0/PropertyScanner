from typing import Dict, Tuple
import importlib
from src.platform.agents.base import BaseAgent
from src.platform.utils.compliance import ComplianceManager

class AgentFactory:
    """
    Factory to create Agents based on source_id or type.
    """
    
    _CRAWLERS: Dict[str, Tuple[str, str]] = {
        "idealista": ("src.listings.agents.crawlers.idealista", "IdealistaCrawlerAgent"),
        "idealista_es": ("src.listings.agents.crawlers.idealista", "IdealistaCrawlerAgent"),
        "idealista_local_test": ("src.listings.agents.crawlers.idealista", "IdealistaCrawlerAgent"),
        "pisos_es": ("src.listings.agents.crawlers.pisos", "PisosCrawlerAgent"),
        "pisos": ("src.listings.agents.crawlers.pisos", "PisosCrawlerAgent"),
        "immobiliare_it": ("src.listings.agents.crawlers.immobiliare", "ImmobiliareCrawlerAgent"),
        "immobiliare": ("src.listings.agents.crawlers.immobiliare", "ImmobiliareCrawlerAgent"),
        "rightmove_uk": ("src.listings.agents.crawlers.rightmove", "RightmoveCrawlerAgent"),
        "rightmove": ("src.listings.agents.crawlers.rightmove", "RightmoveCrawlerAgent"),
        "zoopla_uk": ("src.listings.agents.crawlers.zoopla", "ZooplaCrawlerAgent"),
        "zoopla": ("src.listings.agents.crawlers.zoopla", "ZooplaCrawlerAgent"),
    }
    
    _NORMALIZERS: Dict[str, Tuple[str, str]] = {
        "idealista": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_es": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_local_test": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "pisos_es": ("src.listings.agents.processors.pisos", "PisosNormalizerAgent"),
        "pisos": ("src.listings.agents.processors.pisos", "PisosNormalizerAgent"),
        "immobiliare_it": ("src.listings.agents.processors.immobiliare", "ImmobiliareNormalizerAgent"),
        "immobiliare": ("src.listings.agents.processors.immobiliare", "ImmobiliareNormalizerAgent"),
        "rightmove_uk": ("src.listings.agents.processors.rightmove", "RightmoveNormalizerAgent"),
        "rightmove": ("src.listings.agents.processors.rightmove", "RightmoveNormalizerAgent"),
        "zoopla_uk": ("src.listings.agents.processors.zoopla", "ZooplaNormalizerAgent"),
        "zoopla": ("src.listings.agents.processors.zoopla", "ZooplaNormalizerAgent"),
    }

    @classmethod
    def create_crawler(cls, source_id: str, config: Dict, compliance_manager: ComplianceManager) -> BaseAgent:
        crawler_info = cls._CRAWLERS.get(source_id)
        if not crawler_info:
            raise ValueError(f"No crawler found for source_id: {source_id}")
        module_path, class_name = crawler_info
        crawler_cls = getattr(importlib.import_module(module_path), class_name)
            
        # PisosCrawler signature is slightly different in previous code (compliance first/only?), 
        # let's check code or standardize.
        # IdealistaCrawler: (config, compliance)
        # PisosCrawler: (compliance) -> I should update PisosCrawler to accept config to be uniform.
        config_payload = config or {}
        if hasattr(config_payload, "model_dump"):
            config_payload = config_payload.model_dump()
        elif isinstance(config_payload, dict):
            config_payload = dict(config_payload)

        rate_limit = config_payload.get("rate_limit")
        if isinstance(rate_limit, dict) and "period_seconds" not in config_payload:
            config_payload["period_seconds"] = rate_limit.get("period_seconds")

        return crawler_cls(config_payload, compliance_manager)

    @classmethod
    def create_normalizer(cls, source_id: str) -> BaseAgent:
        norm_info = cls._NORMALIZERS.get(source_id)
        if not norm_info:
            raise ValueError(f"No normalizer found for source_id: {source_id}")
        module_path, class_name = norm_info
        norm_cls = getattr(importlib.import_module(module_path), class_name)
        return norm_cls()
