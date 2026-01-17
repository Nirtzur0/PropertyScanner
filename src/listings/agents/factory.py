from typing import Dict, Tuple, Any
import importlib
import threading
from src.platform.agents.base import BaseAgent
from src.platform.utils.compliance import ComplianceManager

# Global lock for imports to prevent deadlocks in threaded environments
_IMPORT_LOCK = threading.RLock()

class AgentFactory:
    """
    Factory to create Agents based on source_id or type.
    """
    
    _CRAWLERS: Dict[str, Tuple[str, str]] = {
        # Spain
        "idealista": ("src.listings.agents.crawlers.spain.idealista", "IdealistaCrawlerAgent"),
        "idealista_es": ("src.listings.agents.crawlers.spain.idealista", "IdealistaCrawlerAgent"),
        "idealista_it": ("src.listings.agents.crawlers.spain.idealista", "IdealistaCrawlerAgent"), 
        "idealista_pt": ("src.listings.agents.crawlers.spain.idealista", "IdealistaCrawlerAgent"),
        "idealista_local_test": ("src.listings.agents.crawlers.spain.idealista", "IdealistaCrawlerAgent"),
        "pisos_es": ("src.listings.agents.crawlers.spain.pisos", "PisosCrawlerAgent"),
        "pisos": ("src.listings.agents.crawlers.spain.pisos", "PisosCrawlerAgent"),
        
        # Italy
        "immobiliare_it": ("src.listings.agents.crawlers.italy.immobiliare", "ImmobiliareCrawlerAgent"),
        "immobiliare": ("src.listings.agents.crawlers.italy.immobiliare", "ImmobiliareCrawlerAgent"),
        "casa_it": ("src.listings.agents.crawlers.italy.casa_it", "CasaItCrawlerAgent"),
        
        # United Kingdom
        "rightmove_uk": ("src.listings.agents.crawlers.uk.rightmove", "RightmoveCrawlerAgent"),
        "rightmove": ("src.listings.agents.crawlers.uk.rightmove", "RightmoveCrawlerAgent"),
        "zoopla_uk": ("src.listings.agents.crawlers.uk.zoopla", "ZooplaCrawlerAgent"),
        "zoopla": ("src.listings.agents.crawlers.uk.zoopla", "ZooplaCrawlerAgent"),
        "onthemarket_uk": ("src.listings.agents.crawlers.uk.onthemarket", "OnTheMarketCrawlerAgent"),
        "onthemarket": ("src.listings.agents.crawlers.uk.onthemarket", "OnTheMarketCrawlerAgent"),
        
        # France
        "seloger_fr": ("src.listings.agents.crawlers.france.seloger", "SeLogerCrawlerAgent"),
        "seloger": ("src.listings.agents.crawlers.france.seloger", "SeLogerCrawlerAgent"),
        
        # USA
        "realtor_us": ("src.listings.agents.crawlers.usa.realtor", "RealtorCrawlerAgent"),
        "realtor": ("src.listings.agents.crawlers.usa.realtor", "RealtorCrawlerAgent"),
        "redfin_us": ("src.listings.agents.crawlers.usa.redfin", "RedfinCrawlerAgent"),
        "redfin": ("src.listings.agents.crawlers.usa.redfin", "RedfinCrawlerAgent"),
        "homes_us": ("src.listings.agents.crawlers.usa.homes", "HomesCrawlerAgent"),
        "homes": ("src.listings.agents.crawlers.usa.homes", "HomesCrawlerAgent"),
        
        # Netherlands
        "funda_nl": ("src.listings.agents.crawlers.netherlands.funda", "FundaCrawlerAgent"),
        "funda": ("src.listings.agents.crawlers.netherlands.funda", "FundaCrawlerAgent"),
        
        # Germany
        "immowelt_de": ("src.listings.agents.crawlers.germany.immowelt", "ImmoweltCrawlerAgent"),
        "immowelt": ("src.listings.agents.crawlers.germany.immowelt", "ImmoweltCrawlerAgent"),
        
        # Portugal
        "imovirtual_pt": ("src.listings.agents.crawlers.portugal.imovirtual", "ImovirtualCrawlerAgent"),
        "imovirtual": ("src.listings.agents.crawlers.portugal.imovirtual", "ImovirtualCrawlerAgent"),
    }
    
    _NORMALIZERS: Dict[str, Tuple[str, str]] = {
        "idealista": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_es": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_it": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
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
        
        # Thread-safe import
        with _IMPORT_LOCK:
            module = importlib.import_module(module_path)
            crawler_cls = getattr(module, class_name)
            
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
            # Fallback for new agents without normalizers yet
            # Return a dummy or generic normalizer if possible, for now we let it fail or implementation needs to follow
            # We can map them to generic or raise error. 
            # For this test, let's allow "generic" if not found? No, better to be strict or user will see empty data.
            # But the user asked to test crawling mainly. 
            # Let's see if we can use a pass-through normalizer?
            # Or just update map.
            raise ValueError(f"No normalizer found for source_id: {source_id}")
            
        module_path, class_name = norm_info
        with _IMPORT_LOCK:
            module = importlib.import_module(module_path)
            norm_cls = getattr(module, class_name)
        return norm_cls()
