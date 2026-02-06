import streamlit as st
import random
import pandas as pd
from typing import List, Tuple, Dict, Set, Any, Optional

from src.interfaces.api.pipeline import PipelineAPI
from src.listings.services.image_selection import ImageSelector
from src.platform.utils.config import load_app_config_safe
from src.platform.pipeline.state import PipelineStateService
from src.platform.domain.models import DBListing
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.platform.domain.schema import DealAnalysis, ValuationProjection
from src.interfaces.dashboard.utils.formatting import safe_num
from src.platform.utils.serialize import model_to_dict

@st.cache_resource
def get_services():
    """Initializes and caches core services."""
    api = PipelineAPI()
    app_config = load_app_config_safe()
    selector = ImageSelector(config=app_config.image_selector)
    return api.storage, api.valuation, api.retriever, selector

@st.cache_data(ttl=600)
def load_filter_options(_storage) -> Tuple[List[str], List[str], List[str], Dict[str, List[str]]]:
    """Loads distinct cities and countries from the database for filtering."""
    session = _storage.get_session()
    try:
        rows = session.query(DBListing.country, DBListing.city).distinct().all()
        cities = sorted({city for _, city in rows if city})
        countries = sorted({country for country, _ in rows if country})
        cities_by_country = {}
        for country, city in rows:
            if not country or not city:
                continue
            cities_by_country.setdefault(country, set()).add(city)
        cities_by_country = {country: sorted(list(cities)) for country, cities in cities_by_country.items()}
        types = [t[0] for t in session.query(DBListing.property_type).distinct().all() if t[0]]
        types = sorted(set(types))
    finally:
        session.close()
    return cities, types, countries, cities_by_country

@st.cache_data(ttl=120)
def load_pipeline_status():
    """Loads the current status of the data pipeline."""
    try:
        return PipelineStateService().snapshot().to_dict()
    except Exception as e:
        return {"error": str(e), "needs_refresh": False, "reasons": ["status_unavailable"]}

@st.cache_data(ttl=900)
def rank_images(image_urls: List[str], max_images: int = 6, _image_selector: ImageSelector = None) -> List[str]:
    """Ranks and selects best images using ImageSelector."""
    if not image_urls:
        return []
    
    if _image_selector:
         selection = _image_selector.select(image_urls, max_images=max_images)
         if selection and selection.selected:
            return [item.url for item in selection.selected]
            
    return list(image_urls)[:max_images]

@st.cache_data(ttl=900)
def rank_images_sample(image_urls: List[str], sample_size: int = 5, _image_selector: ImageSelector = None) -> List[str]:
    """Ranks a sample of images for efficiency."""
    if not image_urls:
        return []
    urls = [str(url) for url in image_urls if url]
    if not urls:
        return []
    sample_size = max(1, min(sample_size, len(urls)))
    sampled = random.sample(urls, sample_size)
    
    ranked_subset = rank_images(sampled, max_images=sample_size, _image_selector=_image_selector)
    ranked_set = set(ranked_subset)
    remainder = [url for url in urls if url not in ranked_set]
    return ranked_subset + remainder

def fetch_listings_dataframe(
    storage, 
    valuation_service, 
    retriever_service,
    selected_country: str,
    selected_city: str,
    selected_types: List[str],
    max_listings: int = 300
) -> pd.DataFrame:
    """Fetches listings from DB, enriches with valuation/signals, and returns a DataFrame."""
    session = storage.get_session()
    raw_rows = []
    
    try:
        query = session.query(DBListing).order_by(DBListing.updated_at.desc())
        if selected_country != "All":
            query = query.filter(DBListing.country == selected_country)
        if selected_city != "All":
            query = query.filter(DBListing.city == selected_city)
        if selected_types:
            query = query.filter(DBListing.property_type.in_(selected_types))
        
        listings_db = query.limit(max_listings).all()

        if not listings_db:
             return pd.DataFrame()

        # Try to import ValuationPersister
        try:
            from src.valuation.services.valuation_persister import ValuationPersister
            persister = ValuationPersister(session)
        except Exception:
            persister = None

        # Determine if we should show progress
        # Since this is a service function, we might want to avoid direct UI calls
        # But for 'app.py' refactor it's common to pass a progress callback
        # For now, we will just process. Use st.spinner in app calls.
        
        for db_item in listings_db:
            listing = db_listing_to_canonical(db_item)
            cached_val = persister.get_latest_valuation(db_item.id) if persister else None
            comps = []
            ext_signals = {}
            analysis = None

            if cached_val:
                # Rehydrate cached analysis
                projections = [ValuationProjection(**p) for p in cached_val.evidence.get("projections", [])]
                rent_projections = [ValuationProjection(**p) for p in cached_val.evidence.get("rent_projections", [])]
                yield_projections = [ValuationProjection(**p) for p in cached_val.evidence.get("yield_projections", [])]
                
                rent_est = None
                if rent_projections:
                    rent_est = min(rent_projections, key=lambda p: p.months_future).predicted_value
                
                yield_est = None
                if yield_projections:
                    yield_est = min(yield_projections, key=lambda p: p.months_future).predicted_value
                elif db_item.gross_yield:
                    yield_est = db_item.gross_yield

                analysis = DealAnalysis(
                    listing_id=db_item.id,
                    fair_value_estimate=cached_val.fair_value,
                    fair_value_uncertainty_pct=0.10,
                    deal_score=cached_val.confidence_score,
                    investment_thesis=cached_val.evidence.get("thesis", "Cached Analysis"),
                    market_signals=cached_val.evidence.get("signals", {}),
                    projections=projections,
                    rent_projections=rent_projections,
                    yield_projections=yield_projections,
                    evidence=None,
                    rental_yield_estimate=yield_est,
                )
                ext_signals = cached_val.evidence.get("evidence", {}).get("external_signals", {}) if cached_val.evidence else {}
            else:
                # Live valuation fallback
                try:
                    comps = retriever_service.retrieve_comps(listing, k=3)
                    analysis = valuation_service.evaluate_deal(listing, comps=comps)
                    if persister:
                         try:
                             persister.save_valuation(db_item.id, analysis)
                         except Exception:
                             pass
                    if analysis.evidence and analysis.evidence.external_signals:
                        ext_signals = analysis.evidence.external_signals
                except Exception:
                    continue # Skip failed valuations

            if not analysis:
                continue

            # Extract signals
            evidence_payload = None
            if cached_val:
                 evidence_payload = cached_val.evidence.get("evidence", {}) if cached_val.evidence else {}
            elif analysis.evidence:
                 try:
                     evidence_payload = model_to_dict(analysis.evidence)
                 except Exception:
                     pass
            
            signals = analysis.market_signals or {}
            momentum = signals.get("momentum")
            liquidity = signals.get("liquidity")
            catchup = signals.get("catchup")
            market_yield = signals.get("market_yield")
            price_to_rent_years = safe_num(signals.get("price_to_rent_years"), None)
            market_price_to_rent_years = safe_num(signals.get("market_price_to_rent_years"), None)
            area_sentiment = signals.get("area_sentiment")
            area_development = signals.get("area_development")

            # Final estimates
            rent_est = db_item.estimated_rent
            if not rent_est and getattr(analysis, "rent_projections", None):
                rent_est = min(analysis.rent_projections, key=lambda p: p.months_future).predicted_value
            
            yield_est = getattr(analysis, "rental_yield_estimate", None)
            if yield_est is None and db_item.gross_yield:
                 yield_est = db_item.gross_yield
            if yield_est is None and getattr(analysis, "yield_projections", None):
                 yield_est = min(analysis.yield_projections, key=lambda p: p.months_future).predicted_value
            
            value_delta = None
            value_delta_pct = None
            if listing.price and listing.price > 0 and analysis.fair_value_estimate:
                value_delta = analysis.fair_value_estimate - listing.price
                value_delta_pct = value_delta / listing.price
            
            # Projections logic
            projected_value_12m = safe_num(signals.get("projected_value_12m"), None)
            price_return_12m_pct = safe_num(signals.get("price_return_12m_pct"), None)
            
            if price_return_12m_pct is None and projected_value_12m is not None and listing.price and listing.price > 0:
                 price_return_12m_pct = ((projected_value_12m - listing.price) / listing.price) * 100
                 
            if price_return_12m_pct is None and listing.price and listing.price > 0:
                # Helper to find 12m projection
                def _find_proj(projs, target=12):
                    if not projs: return None
                    exact = [p for p in projs if getattr(p, "months_future", None) == target]
                    if exact: return exact[0]
                    return min(projs, key=lambda p: abs(getattr(p, "months_future", target) - target))
                
                proj_12m = _find_proj(getattr(analysis, "projections", []))
                if proj_12m and getattr(proj_12m, "predicted_value", None):
                     projected_value_12m = float(proj_12m.predicted_value)
                     price_return_12m_pct = ((projected_value_12m - listing.price) / listing.price) * 100
                elif value_delta_pct is not None:
                     price_return_12m_pct = value_delta_pct * 100
            
            total_return_12m_pct = safe_num(signals.get("total_return_12m_pct"), None)
            if total_return_12m_pct is None and (price_return_12m_pct is not None or yield_est is not None):
                 total_return_12m_pct = (price_return_12m_pct or 0.0) + (yield_est or 0.0)

            image_urls = [str(url) for url in listing.image_urls] if listing.image_urls else []
            
            raw_rows.append({
                "ID": listing.id,
                "Title": listing.title,
                "Price": listing.price,
                "Sqm": listing.surface_area_sqm,
                "Bedrooms": listing.bedrooms,
                "City": listing.location.city if listing.location else None,
                "Country": listing.location.country if listing.location else None,
                "Property Type": str(listing.property_type),
                "Deal Score": analysis.deal_score,
                "Fair Value": analysis.fair_value_estimate,
                "Uncertainty %": analysis.fair_value_uncertainty_pct,
                "Value Delta": value_delta,
                "Value Delta %": value_delta_pct,
                "Projected Value 12m": projected_value_12m,
                "Price Return 12m %": price_return_12m_pct,
                "Total Return 12m %": total_return_12m_pct,
                "Rent Est": rent_est,
                "Yield %": yield_est,
                "Market Yield %": market_yield,
                "Price-to-Rent (yrs)": price_to_rent_years,
                "Market P/R (yrs)": market_price_to_rent_years,
                "Momentum %": (momentum * 100) if momentum is not None else None,
                "Liquidity": liquidity,
                "Catchup": catchup,
                "Area Sentiment": area_sentiment,
                "Area Development": area_development,
                "Income Weight": ext_signals.get("income_weight"),
                "Area Adjustment": ext_signals.get("area_adjustment"),
                "Thesis": analysis.investment_thesis,
                "URL": str(listing.url),
                "lat": listing.location.lat if listing.location else None,
                "lon": listing.location.lon if listing.location else None,
                "Image": image_urls[0] if image_urls else None,
                "Images": image_urls,
                "Desc": listing.description,
                "VLM Desc": listing.vlm_description,
                "Projections": analysis.projections,
                "Rent Projections": getattr(analysis, "rent_projections", []),
                "Yield Projections": getattr(analysis, "yield_projections", []),
                "Signals": signals,
                "Evidence": evidence_payload,
                "Comps": comps if comps else [],
            })

    finally:
        session.close()
        
    return pd.DataFrame(raw_rows)
