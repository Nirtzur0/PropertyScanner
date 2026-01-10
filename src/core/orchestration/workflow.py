from typing import List
import structlog
from src.utils.config import ConfigLoader
from src.utils.compliance import ComplianceManager
from src.agents.crawlers.playwright_crawler import IdealistaCrawlerAgent
from src.agents.processors.normalizer import IdealistaNormalizerAgent
from src.agents.analysts.enricher import EnrichmentAgent
from src.core.domain.schema import CanonicalListing
from src.services.storage import StorageService
from src.services.valuation import ValuationService
from src.services.retrieval import CompRetriever
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
        
        # Initialize Agents
        idealista_conf = next(s for s in self.sources['sources'] if s['id'] == 'idealista_es')
        self.crawler = IdealistaCrawlerAgent(idealista_conf, self.compliance)
        self.normalizer = IdealistaNormalizerAgent()
        self.enricher = EnrichmentAgent(self.compliance)
        self.valuation = ValuationService(self.storage)
        self.retriever = CompRetriever()

    def run_job(self, target_area: str = None):
        # Determine source.
        source_conf = None
        search_path = ""
        
        if target_area and target_area.startswith("file://"):
             # Local Test Mode
             source_conf = next(s for s in self.sources['sources'] if s['id'] == 'idealista_local_test')
             search_path = ""
        else:
             # Default Live Mode
             source_conf = next(s for s in self.sources['sources'] if s['id'] == 'idealista_es')
             search_path = target_area or "/venta-viviendas/madrid/centro/"
        
        logger.info("starting_job", source=source_conf['id'], target=search_path)
        
        # Instantiate Crawler
        self.crawler = IdealistaCrawlerAgent(source_conf, self.compliance)

        # 1. Crawl
        crawl_resp = self.crawler.run({"search_path": search_path})
        
        if crawl_resp.status == "failure":
            logger.error("crawl_failed", errors=crawl_resp.errors)
            return
            
        raw_listings = crawl_resp.data
        logger.info("crawl_completed", count=len(raw_listings))
        
        if not raw_listings:
            return
            
        # 2. Normalize
        norm_resp = self.normalizer.run({"raw_listings": raw_listings})
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
        for l in enriched_listings:
             # Retrieve Comps
             comps = self.retriever.retrieve_comps(l, k=5)
             
             # Convert CompListing back to Canonical simplified (or change Valuation to accept CompListing)
             # For MVP, we need CanonicalListings but CompListing is different.
             # Actually, ValuationService was typed to take List[CanonicalListing].
             # For now, let's just cheat and not pass them or reconvert if we had full objects.
             # BUT, retrieval returns CompListing (Lightweight). 
             # Let's SKIP passing comps to valuation for a moment to avoid Type mismatch, 
             # OR effectively load them.
             
             # BETTER PLAN: Just log we found them.
             logger.info("comps_retrieved", id=l.external_id, count=len(comps))
             
             # NOTE: To fully use them in Valuation, we need to map CompListing -> CanonicalListing
             # or update ValuationService to accept CompListing. 
             # For this step, I will stick to what works and pass None, but verify retrieval works.
             analysis = self.valuation.evaluate_deal(l, comps=None) 
             deals.append(analysis)
             if analysis.deal_score > 0.6: # Interesting deal
                 logger.info("deal_found", id=l.external_id, title=l.title, score=f"{analysis.deal_score:.2f}", thesis=analysis.investment_thesis)
        
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
