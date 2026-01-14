from typing import List
import structlog
from src.utils.config import ConfigLoader
from src.utils.compliance import ComplianceManager
from src.agents.factory import AgentFactory
from src.agents.analysts.enricher import EnrichmentAgent
from src.core.domain.schema import CanonicalListing
from src.services.storage import StorageService
from src.services.valuation import ValuationService
from src.services.retrieval import CompRetriever
from src.services.valuation_persister import ValuationPersister
import pandas as pd
from datetime import datetime

logger = structlog.get_logger()

class Orchestrator:
    def __init__(self):
        self.config_loader = ConfigLoader()
        self.config = self.config_loader.agents
        self.sources = self.config_loader.sources
        
        # Shared User Agent
        self.user_agent = self.config.get("defaults", {}).get("uastring", "PropertyScanner/1.0")
        
        self.compliance = ComplianceManager(self.user_agent)
        self.storage = StorageService() # Defaults to sqlite:///data/listings.db
        
        self.enricher = EnrichmentAgent(self.compliance)
        self.valuation = ValuationService(self.storage)
        self.retriever = CompRetriever()

    def run_job(self, target_area: str = None):
        if not target_area:
            raise ValueError("target_area_required")

        # Determine source.
        source_id = "idealista_es"
        search_path = target_area
        
        if target_area:
            if "pisos.com" in target_area:
                 source_id = "pisos_es"
                 search_path = target_area # Full URL for pisos
            elif target_area.startswith("file://"):
                 source_id = "idealista_local_test"
                 search_path = ""

        # Get Source Config
        source_conf = next((s for s in self.sources['sources'] if s['id'] == source_id), None)
        if not source_conf:
            raise ValueError(f"source_config_missing:{source_id}")

        logger.info("starting_job", source=source_id, target=search_path)
        
        # Instantiate Agents via Factory
        try:
            crawler = AgentFactory.create_crawler(source_id, source_conf, self.compliance)
            normalizer = AgentFactory.create_normalizer(source_id)
        except ValueError as e:
            logger.error("factory_error", error=str(e))
            return
            
        # 1. Crawl
        # Different crawlers might expect slightly different inputs, but standardizing on 'start_url' or 'search_path'
        # Idealista expects 'search_path' (appended to base), Pisos expects 'start_url' (full).
        # We can handle this by passing both or unifying.
        # PisosCrawler checks 'start_url'. IdealistaCrawler checks 'search_path'.
        # Let's pass both.
        input_payload = {
            "search_path": search_path,
            "start_url": search_path 
        }
        
        crawl_resp = crawler.run(input_payload)
        
        if crawl_resp.status == "failure":
            logger.error("crawl_failed", errors=crawl_resp.errors)
            return
            
        raw_listings = crawl_resp.data
        logger.info("crawl_completed", count=len(raw_listings))
        
        if not raw_listings:
            return
            
        # 2. Normalize
        norm_resp = normalizer.run({"raw_listings": raw_listings})
        canonical_listings: List[CanonicalListing] = norm_resp.data
        
        if norm_resp.errors:
             logger.warning("normalization_partial_errors", errors=norm_resp.errors)
        
        logger.info("normalization_completed", count=len(canonical_listings))
        
        # 3. Enrich (Geo)
        logger.info("enrichment_started")
        enrich_resp = self.enricher.run({"listings": canonical_listings})
        enriched_listings = enrich_resp.data
        logger.info("enrichment_completed", enriched=enrich_resp.metadata.get("enriched_count", 0))

        # 3b. Index for Retrieval (MVP)
        self.retriever.add_listings(enriched_listings)

        # 4. Save to DB
        saved_count = self.storage.save_listings(enriched_listings)
        logger.info("db_save_completed", saved=saved_count, total=len(enriched_listings))
        
        # 5. Valuation & Scoring
        logger.info("valuation_started")
        deals = []
        session = self.storage.get_session()
        try:
            persister = ValuationPersister(session)

            for l in enriched_listings:
                cached_val = persister.get_latest_valuation(l.id)
                if cached_val:
                    continue

                try:
                    analysis = self.valuation.evaluate_deal(l, comps=None)
                except Exception as e:
                    logger.error("valuation_failed", id=l.external_id, error=str(e))
                    continue

                persister.save_valuation(l.id, analysis)
                deals.append(analysis)

                if analysis.deal_score > 0.6:
                    logger.info(
                        "deal_found",
                        id=l.external_id,
                        title=l.title,
                        score=f"{analysis.deal_score:.2f}",
                        thesis=analysis.investment_thesis,
                    )
        finally:
            session.close()
        
        # In a real app, we'd save 'deals' to a separate table or alert the user.

    def run_batch(self, target_areas: List[str], max_workers: int = 3):
        """
        Runs multiple jobs in parallel (e.g. for different neighborhoods).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        logger.info("starting_batch_job", targets=target_areas, workers=max_workers)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_area = {executor.submit(self.run_job, area): area for area in target_areas}
            
            for future in as_completed(future_to_area):
                area = future_to_area[future]
                try:
                    future.result()
                    logger.info("batch_job_completed", area=area)
                except Exception as e:
                    logger.error("batch_job_failed", area=area, error=str(e))
