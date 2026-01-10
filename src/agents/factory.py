from typing import Dict, Type
from src.agents.base import BaseAgent
from src.utils.compliance import ComplianceManager
from src.agents.crawlers.idealista import IdealistaCrawlerAgent
from src.agents.crawlers.pisos import PisosCrawlerAgent
from src.agents.processors.idealista import IdealistaNormalizerAgent
from src.agents.processors.pisos import PisosNormalizerAgent

class AgentFactory:
    """
    Factory to create Agents based on source_id or type.
    """
    
    _CRAWLERS = {
        "idealista_es": IdealistaCrawlerAgent,
        "idealista_local_test": IdealistaCrawlerAgent,
        "pisos_es": PisosCrawlerAgent,
        "pisos": PisosCrawlerAgent
    }
    
    _NORMALIZERS = {
        "idealista_es": IdealistaNormalizerAgent,
        "idealista_local_test": IdealistaNormalizerAgent,
        "pisos_es": PisosNormalizerAgent,
        "pisos": PisosNormalizerAgent
    }

    @classmethod
    def create_crawler(cls, source_id: str, config: Dict, compliance_manager: ComplianceManager) -> BaseAgent:
        crawler_cls = cls._CRAWLERS.get(source_id)
        if not crawler_cls:
            raise ValueError(f"No crawler found for source_id: {source_id}")
            
        # PisosCrawler signature is slightly different in previous code (compliance first/only?), 
        # let's check code or standardize.
        # IdealistaCrawler: (config, compliance)
        # PisosCrawler: (compliance) -> I should update PisosCrawler to accept config to be uniform.
        
        return crawler_cls(config, compliance_manager)

    @classmethod
    def create_normalizer(cls, source_id: str) -> BaseAgent:
        norm_cls = cls._NORMALIZERS.get(source_id)
        if not norm_cls:
            raise ValueError(f"No normalizer found for source_id: {source_id}")
        return norm_cls()
