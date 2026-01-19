from typing import Dict, Tuple, Any
import importlib
import threading
import structlog
from src.platform.agents.base import BaseAgent
from src.platform.utils.compliance import ComplianceManager
from src.platform.utils.config import load_app_config_safe

# Global lock for imports to prevent deadlocks in threaded environments
_IMPORT_LOCK = threading.RLock()
logger = structlog.get_logger(__name__)

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
        # Spain
        "idealista": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_es": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_it": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "idealista_local_test": ("src.listings.agents.processors.idealista", "IdealistaNormalizerAgent"),
        "pisos_es": ("src.listings.agents.processors.pisos", "PisosNormalizerAgent"),
        "pisos": ("src.listings.agents.processors.pisos", "PisosNormalizerAgent"),
        
        # Italy
        "immobiliare_it": ("src.listings.agents.processors.immobiliare", "ImmobiliareNormalizerAgent"),
        "immobiliare": ("src.listings.agents.processors.immobiliare", "ImmobiliareNormalizerAgent"),
        "casa_it": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        
        # United Kingdom
        "rightmove_uk": ("src.listings.agents.processors.rightmove", "RightmoveNormalizerAgent"),
        "rightmove": ("src.listings.agents.processors.rightmove", "RightmoveNormalizerAgent"),
        "zoopla_uk": ("src.listings.agents.processors.zoopla", "ZooplaNormalizerAgent"),
        "zoopla": ("src.listings.agents.processors.zoopla", "ZooplaNormalizerAgent"),
        "onthemarket_uk": ("src.listings.agents.processors.onthemarket", "OnTheMarketNormalizerAgent"),
        "onthemarket": ("src.listings.agents.processors.onthemarket", "OnTheMarketNormalizerAgent"),
        
        # France
        "seloger_fr": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "seloger": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        
        # USA
        "realtor_us": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "realtor": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "redfin_us": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "redfin": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "homes_us": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "homes": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        
        # Netherlands
        "funda_nl": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "funda": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        
        # Germany
        "immowelt_de": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        "immowelt": ("src.listings.agents.processors.generic", "GenericNormalizerAgent"),
        
        # Portugal
        "imovirtual_pt": ("src.listings.agents.processors.imovirtual", "ImovirtualNormalizerAgent"),
        "imovirtual": ("src.listings.agents.processors.imovirtual", "ImovirtualNormalizerAgent"),
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
            raise ValueError(f"No normalizer found for source_id: {source_id}")
            
        module_path, class_name = norm_info
        with _IMPORT_LOCK:
            module = importlib.import_module(module_path)
            norm_cls = getattr(module, class_name)
        normalizer = norm_cls()
        try:
            app_config = load_app_config_safe()
            if app_config.llm.normalizer_enabled:
                from src.listings.agents.processors.llm_fallback import LLMFallbackNormalizer
                from src.listings.services.llm_normalizer import LLMNormalizerService

                llm_service = LLMNormalizerService(app_config=app_config)
                return LLMFallbackNormalizer(normalizer, llm_service)
        except Exception as exc:
            logger.warning("llm_normalizer_init_failed", error=str(exc))
        return normalizer
