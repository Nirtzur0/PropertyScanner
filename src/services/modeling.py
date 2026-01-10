import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
import structlog
import joblib
import os
from typing import Dict, List, Tuple
from src.core.domain.schema import CanonicalListing

logger = structlog.get_logger()

class ValuationModel:
    """
    Manages training and inference for the Property Valuation Model.
    Uses Sklearn GradientBoostingRegressor (Quantile Loss) to predict Price/Sqm Uncertainty.
    """
    def __init__(self, model_dir: str = "data/models"):
        self.model_dir = model_dir
        self.models = {} # tau -> model
        self.quantiles = [0.1, 0.5, 0.9]
        os.makedirs(model_dir, exist_ok=True)
        
    def _extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extracts numerical features for the model.
        """
        # Basic features
        features = pd.DataFrame()
        features['sqm'] = df['surface_area_sqm'].fillna(0)
        features['bedrooms'] = df['bedrooms'].fillna(0)
        
        if 'lat' in df.columns:
            features['lat'] = df['lat'].fillna(0)
        else:
            features['lat'] = 0.0
            
        if 'lon' in df.columns:
            features['lon'] = df['lon'].fillna(0)
        else:
            features['lon'] = 0.0
        
        # In a real system, we'd add 'neighborhood_avg_sqm' from DB here
        
        return features.astype(float)

    def train(self, data_path: str = "data/training/training_set.csv"):
        """
        Trains Quantile Regressors.
        """
        if not os.path.exists(data_path):
            logger.error("training_data_not_found", path=data_path)
            return

        df = pd.read_csv(data_path)
        if df.empty:
            return

        # Target: Price Per Sqm (normalized target is easier)
        # Filter valid data
        df = df[(df['price'] > 0) & (df['surface_area_sqm'] > 10)]
        df['target_price_sqm'] = df['price'] / df['surface_area_sqm']
        
        X = self._extract_features(df)
        y = df['target_price_sqm']
        
        for q in self.quantiles:
            logger.info("training_quantile", q=q)
            # Use GradientBoostingRegressor with quantile loss
            model = GradientBoostingRegressor(loss='quantile', alpha=q, n_estimators=100)
            model.fit(X, y)
            
            # Save
            save_path = os.path.join(self.model_dir, f"sklearn_q{int(q*100)}.pkl")
            joblib.dump(model, save_path)
            self.models[q] = model
            
        logger.info("training_complete", quantiles=self.quantiles)

    def load(self):
        """Loads models from disk."""
        for q in self.quantiles:
            path = os.path.join(self.model_dir, f"sklearn_q{int(q*100)}.pkl")
            if os.path.exists(path):
                self.models[q] = joblib.load(path)
            else:
                logger.warning("model_not_found", q=q, path=path)

    def predict(self, listing: CanonicalListing) -> Dict[str, float]:
        """
        Returns estimated Price/Sqm for 0.1, 0.5, 0.9 quantiles.
        """
        if not self.models:
            self.load()
            
        # Create 1-row DataFrame
        record = {
            'surface_area_sqm': listing.surface_area_sqm,
            'bedrooms': listing.bedrooms,
            'lat': listing.location.lat if listing.location else 0,
            'lon': listing.location.lon if listing.location else 0
        }
        df = pd.DataFrame([record])
        X = self._extract_features(df)
        
        results = {}
        for q, model in self.models.items():
            # logger.info("predicting_quantile", q=q)
            pred_sqm = model.predict(X)[0]
            results[f"q{int(q*100)}"] = pred_sqm
            
        return results
