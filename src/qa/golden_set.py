import pandas as pd
import sqlite3
import structlog
from typing import List, Optional
from src.core.domain.schema import CanonicalListing
from src.services.storage import StorageService

logger = structlog.get_logger(__name__)

class GoldenSetGenerator:
    """
    Generates a stratified "Golden Set" of listings for end-to-end testing.
    Stratification strategy:
    - Region/City (ensure coverage)
    - Property Type (ensure coverage)
    - Price Band (Low, Mid, High per region)
    """
    
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        self.storage = StorageService(db_url=f"sqlite:///{db_path}")

    def generate(self, size: int = 200, random_seed: int = 42) -> List[CanonicalListing]:
        """
        Generate a stratified sample of listings.
        """
        logger.info("generating_golden_set", target_size=size)
        
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT id, external_id, title, price, surface_area_sqm, city, property_type, 
                   description, vlm_description, image_urls,
                   bedrooms, bathrooms, floor, url, source_id, listed_at
            FROM listings
            WHERE price > 10000 AND price < 20000000 
            AND surface_area_sqm > 10
            AND vlm_description IS NOT NULL
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        if len(df) <= size:
            logger.warning("golden_set_insufficient_data", available=len(df), requested=size)
            return self._df_to_listings(df)
            
        # Stratification Features
        # Helper for price binning
        def get_price_bucket(group):
            if len(group) < 3:
                return pd.Series(['mid'] * len(group), index=group.index)
            try:
                # Use rank to force bins if qcut fails on duplicates
                return pd.qcut(group, 3, labels=['low', 'mid', 'high'], duplicates='drop')
            except ValueError:
                # If duplicates='drop' results in fewer bins than labels
                return pd.Series(['mid'] * len(group), index=group.index)

        df['price_bucket'] = df.groupby('city')['price'].transform(get_price_bucket)
        
        # 2. Stratify
        # We want to sample proportionally from (city, property_type, price_bucket) groups
        # If a group is too small, we take all of it.
        
        # Calculate ideal sample size per group
        strat_cols = ['city', 'property_type', 'price_bucket']
        # Fill NA to avoid dropping
        df[strat_cols] = df[strat_cols].fillna('unknown')
        
        # Sampling
        sampled_df = df.groupby(strat_cols, group_keys=False).apply(
            lambda x: x.sample(frac=size/len(df), random_state=random_seed)
        )
        
        # If we under-sampled due to rounding, fill up nicely
        if len(sampled_df) < size:
            remaining = df[~df['id'].isin(sampled_df['id'])]
            n_needed = size - len(sampled_df)
            if not remaining.empty:
                extra = remaining.sample(n=min(n_needed, len(remaining)), random_state=random_seed)
                sampled_df = pd.concat([sampled_df, extra])
        
        # If we over-sampled (rare with frac), trim
        if len(sampled_df) > size:
            sampled_df = sampled_df.sample(n=size, random_state=random_seed)
            
        logger.info("golden_set_generated", size=len(sampled_df))
        return self._df_to_listings(sampled_df)

    def _df_to_listings(self, df: pd.DataFrame) -> List[CanonicalListing]:
        listings = []
        valid_property_types = {"apartment", "house", "penthouse", "duplex", "studio", "land", "commercial", "other"}
        
        for _, row in df.iterrows():
            # Parse image_urls (string representation of list in SQLite?)
            # Usually stored as JSON string or delimiter. 
            # Assuming StorageService logic used JSON or text.
            img_urls = row['image_urls']
            if isinstance(img_urls, str):
                import json
                try:
                    img_urls = json.loads(img_urls.replace("'", '"')) # Simple fix for python repr
                except:
                    img_urls = []
            
            ptype = row['property_type']
            if ptype not in valid_property_types:
                ptype = "other"
            
            l = CanonicalListing(
                id=row['id'],
                external_id=row['external_id'],
                title=row['title'],
                price=row['price'],
                features={
                    "bedrooms": row['bedrooms'],
                    "bathrooms": row['bathrooms'], 
                    "floor": row['floor']
                },
                surface_area_sqm=row['surface_area_sqm'],
                city=row['city'],
                neighborhood=None,
                property_type=ptype,
                description=row['description'],
                vlm_description=row['vlm_description'],
                image_urls=img_urls if isinstance(img_urls, list) else [],
                source_id=row['source_id'],
                url=row['url'],
                listed_at=pd.to_datetime(row['listed_at']).isoformat() if row['listed_at'] else None
            )
            listings.append(l)
        return listings

if __name__ == "__main__":
    # Test
    gen = GoldenSetGenerator()
    listings = gen.generate(size=50)
    print(f"Generated {len(listings)} listings")
    print(listings[0].model_dump_json(indent=2))
