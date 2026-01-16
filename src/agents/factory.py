from typing import Dict, Tuple
import importlib
from src.agents.base import BaseAgent
from src.utils.compliance import ComplianceManager

class AgentFactory:
    """
    Factory to create Agents based on source_id or type.
    """
    
    _CRAWLERS: Dict[str, Tuple[str, str]] = {
        "idealista": ("src.agents.crawlers.idealista", "IdealistaCrawlerAgent"),
        "idealista_es": ("src.agents.crawlers.idealista", "IdealistaCrawlerAgent"),
        "idealista_local_test": ("src.agents.crawlers.idealista", "IdealistaCrawlerAgent"),
        "pisos_es": ("src.agents.crawlers.pisos", "PisosCrawlerAgent"),
        "pisos": ("src.agents.crawlers.pisos", "PisosCrawlerAgent"),
    }
    
    _NORMALIZERS: Dict[str, Tuple[str, str]] = {
        "idealista": ("src.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_es": ("src.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_local_test": ("src.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "pisos_es": ("src.agents.processors.pisos", "PisosNormalizerAgent"),
        "pisos": ("src.agents.processors.pisos", "PisosNormalizerAgent"),
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
        
        return crawler_cls(config, compliance_manager)

    @classmethod
    def create_normalizer(cls, source_id: str) -> BaseAgent:
        norm_info = cls._NORMALIZERS.get(source_id)
        if not norm_info:
            raise ValueError(f"No normalizer found for source_id: {source_id}")
        module_path, class_name = norm_info
        norm_cls = getattr(importlib.import_module(module_path), class_name)
        return norm_cls()
