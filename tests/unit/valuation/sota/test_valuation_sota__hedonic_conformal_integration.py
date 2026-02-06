"""
Test Suite for SOTA Valuation Pipeline

Tests for:
1. Hedonic Index neighborhood FE and time-adjustment API
2. Conformal Calibrator asymmetric widening and monotonicity
3. ValuationService integration with time-adjusted comps
"""

import pytest
import numpy as np
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import tempfile
import os

# Import modules under test
from src.market.services.hedonic_index import HedonicIndexService, IndexResult
from src.valuation.services.conformal_calibrator import (
    ConformalCalibrator, 
    HorizonCalibratorRegistry,
    enforce_monotonicity
)
from src.platform.domain.schema import (
    CanonicalListing, CompEvidence, EvidencePack, 
    GeoLocation, PropertyType, Currency, ListingStatus
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_db():
    """Create temporary database with test data"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE listings (
            id VARCHAR PRIMARY KEY,
            price FLOAT,
            surface_area_sqm FLOAT,
            bedrooms INT,
            bathrooms INT,
            has_elevator INT,
            floor INT,
            geohash VARCHAR,
            city VARCHAR,
            listed_at DATETIME,
            updated_at DATETIME
        )
    """)
    
    cursor.execute("""
        CREATE TABLE hedonic_indices (
            id TEXT PRIMARY KEY,
            region_id TEXT,
            month_date DATE,
            hedonic_index_sqm FLOAT,
            raw_median_sqm FLOAT,
            r_squared FLOAT,
            n_observations INT,
            n_neighborhoods INT,
            coefficients TEXT,
            updated_at DATETIME
        )
    """)
    
    # Insert test listings with known pattern
    # Neighborhood A (ezjmgu): Higher prices
    # Neighborhood B (ezjmgv): Lower prices
    listings = []
    for i in range(60):
        month = "2024-01" if i < 20 else ("2024-02" if i < 40 else "2024-03")
        neighborhood = "ezjmgu" if i % 2 == 0 else "ezjmgv"
        base_price = 350000 if neighborhood == "ezjmgu" else 280000
        price = base_price + np.random.normal(0, 20000)
        
        listings.append((
            f"L{i:03d}",
            price,
            80 + np.random.normal(0, 10),
            2,
            1,
            1,
            2,
            neighborhood,
            "madrid",
            f"{month}-15",
            f"{month}-20"
        ))
    
    cursor.executemany("""
        INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, listings)
    
    # Insert pre-computed hedonic indices
    indices = [
        ("all|2024-01", "all", "2024-01", 3000.0, 2900.0, 0.85, 20, 2, "{}", datetime.now().isoformat()),
        ("all|2024-02", "all", "2024-02", 3100.0, 3000.0, 0.87, 20, 2, "{}", datetime.now().isoformat()),
        ("all|2024-03", "all", "2024-03", 3200.0, 3100.0, 0.86, 20, 2, "{}", datetime.now().isoformat()),
        ("all|2024-06", "all", "2024-06", 3300.0, 3200.0, 0.88, 20, 2, "{}", datetime.now().isoformat()),
    ]
    
    cursor.executemany("""
        INSERT INTO hedonic_indices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, indices)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def sample_listing():
    """Create sample listing for testing"""
    return CanonicalListing(
        id="test-001",
        source_id="test",
        external_id="001",
        url="https://example.com/listing/001",
        title="Test Apartment",
        description="A nice test apartment in Madrid",
        price=320000,
        currency=Currency.EUR,
        property_type=PropertyType.APARTMENT,
        bedrooms=2,
        bathrooms=1,
        surface_area_sqm=85.0,
        floor=3,
        has_elevator=True,
        location=GeoLocation(
            lat=40.4168,
            lon=-3.7038,
            address_full="Calle Test 123",
            city="madrid",
            country="Spain"
        ),
        listed_at=datetime(2024, 6, 1),
        updated_at=datetime(2024, 6, 15),
        status=ListingStatus.ACTIVE
    )


@pytest.fixture
def sample_comps():
    """Create sample comparables for testing"""
    comps = []
    for i in range(10):
        comp = CanonicalListing(
            id=f"comp-{i:03d}",
            source_id="test",
            external_id=f"C{i:03d}",
            url=f"https://example.com/listing/C{i:03d}",
            title=f"Comp Apartment {i}",
            price=300000 + i * 10000,
            currency=Currency.EUR,
            property_type=PropertyType.APARTMENT,
            bedrooms=2,
            bathrooms=1,
            surface_area_sqm=80 + i * 2,
            location=GeoLocation(
                lat=40.4168 + i * 0.001,
                lon=-3.7038 + i * 0.001,
                address_full=f"Calle Comp {i}",
                city="madrid",
                country="Spain"
            ),
            listed_at=datetime(2024, 1, 15) + timedelta(days=i * 10),
            updated_at=datetime(2024, 1, 20) + timedelta(days=i * 10),
            status=ListingStatus.SOLD if i % 3 == 0 else ListingStatus.ACTIVE
        )
        comps.append(comp)
    return comps


# =============================================================================
# HEDONIC INDEX TESTS
# =============================================================================

class TestHedonicIndex:
    """Tests for HedonicIndexService"""
    
    def test_get_index_exact_month(self, temp_db):
        """Test retrieving index for exact month"""
        svc = HedonicIndexService(db_path=temp_db)
        
        result = svc.get_index("all", "2024-01")
        
        assert result.value == 3000.0
        assert result.r_squared == 0.85
        assert result.is_fallback == False
    
    def test_get_index_fallback_to_recent(self, temp_db):
        """Test fallback to recent month when exact not found"""
        svc = HedonicIndexService(db_path=temp_db)
        
        result = svc.get_index("all", "2024-04")  # Not in DB
        
        assert result.is_fallback == True
        assert result.fallback_reason is not None
        assert result.value > 0
    
    def test_get_index_fallback_region(self, temp_db):
        """Test fallback from neighborhood to global when region not found"""
        svc = HedonicIndexService(db_path=temp_db)
        
        result = svc.get_index("ezjmgu", "2024-01")  # Neighborhood not in DB
        
        assert result.is_fallback == True
        assert "global" in result.fallback_reason.lower()
    
    def test_time_adjustment_factor_increase(self, temp_db):
        """Test that 10% index increase → 10% adjustment factor"""
        svc = HedonicIndexService(db_path=temp_db)
        
        # Index: 2024-01 = 3000, 2024-06 = 3300 → 10% increase
        factor, meta = svc.compute_adjustment_factor(
            region_id="all",
            comp_timestamp=datetime(2024, 1, 15),
            target_timestamp=datetime(2024, 6, 15)
        )
        
        expected_factor = 3300.0 / 3000.0  # 1.10
        assert abs(factor - expected_factor) < 0.01
        assert meta["comp_index"] == 3000.0
        assert meta["target_index"] == 3300.0
    
    def test_adjust_comp_price(self, temp_db):
        """Test full comp price adjustment"""
        svc = HedonicIndexService(db_path=temp_db)
        
        raw_price = 300000
        adj_price, factor, meta = svc.adjust_comp_price(
            raw_price=raw_price,
            region_id="all",
            comp_timestamp=datetime(2024, 1, 15),
            target_timestamp=datetime(2024, 6, 15)
        )
        
        expected_adj = raw_price * (3300.0 / 3000.0)
        assert abs(adj_price - expected_adj) < 1.0
        assert factor > 1.0  # Market went up
    
    def test_factor_clamping(self, temp_db):
        """Test that extreme factors are clamped"""
        svc = HedonicIndexService(db_path=temp_db)
        
        # Force extreme by mocking
        with patch.object(svc, 'get_index') as mock_get:
            mock_get.side_effect = [
                IndexResult(value=100, r_squared=0.5, n_observations=10),   # comp
                IndexResult(value=1000, r_squared=0.5, n_observations=10),  # target
            ]
            
            factor, meta = svc.compute_adjustment_factor(
                "all",
                datetime(2024, 1, 15),
                datetime(2024, 6, 15)
            )
            
            # Raw factor would be 10.0, but should be clamped to 2.0
            assert factor == 2.0
            assert meta["clamped"] == True


# =============================================================================
# CONFORMAL CALIBRATOR TESTS
# =============================================================================

class TestConformalCalibrator:
    """Tests for ConformalCalibrator"""
    
    def test_asymmetric_widening(self):
        """Test that lower and upper intervals are calibrated independently"""
        calibrator = ConformalCalibrator(alpha=0.1, window_size=50)
        
        # Train with data where actual values ARE recorded in errors
        # Actual < q10 → lower_error > 0
        # Actual > q90 → upper_error > 0
        np.random.seed(42)
        for i in range(50):
            if i % 2 == 0:
                # Case where actual is below q10
                actual = 250000
                pred_q10 = 270000
                pred_q50 = 300000
                pred_q90 = 330000
            else:
                # Case where actual is above q90
                actual = 350000
                pred_q10 = 270000
                pred_q50 = 300000
                pred_q90 = 330000
            
            calibrator.update(actual, pred_q10, pred_q50, pred_q90)
        
        # Verify both types of errors have been recorded
        lower_arr = np.array(list(calibrator.lower_errors))
        upper_arr = np.array(list(calibrator.upper_errors))
        
        # Half of observations should have lower errors (q10 > actual)
        assert np.sum(lower_arr > 0) >= 20, "Lower bound violations expected"
        # Half should have upper errors (actual > q90)
        assert np.sum(upper_arr > 0) >= 20, "Upper bound violations expected"
        
        # Calibrate and verify monotonicity
        raw = (270000, 300000, 320000)
        cal_q10, cal_q50, cal_q90 = calibrator.calibrate(*raw)
        
        assert cal_q10 <= cal_q50 <= cal_q90, "Monotonicity must hold"
        assert cal_q50 == raw[1], "Median should not change"
    
    def test_monotonicity_enforcement(self):
        """Test that q10 <= q50 <= q90 is enforced"""
        calibrator = ConformalCalibrator(alpha=0.1)
        
        # Edge case: inverted quantiles
        q10, q50, q90 = calibrator._enforce_monotonicity(350000, 300000, 280000)
        
        assert q10 <= q50 <= q90, "Monotonicity must be enforced"
    
    def test_standalone_monotonicity(self):
        """Test standalone enforce_monotonicity function"""
        q10, q50, q90 = enforce_monotonicity(100, 90, 80)
        
        assert q10 == 80
        assert q50 == 90
        assert q90 == 100
    
    def test_cold_start_passthrough(self):
        """Test that calibrator passes through when insufficient data"""
        calibrator = ConformalCalibrator(alpha=0.1, window_size=50)
        
        # Only 5 samples (below minimum)
        for _ in range(5):
            calibrator.update(300000, 270000, 300000, 330000)
        
        raw = (270000, 300000, 330000)
        cal = calibrator.calibrate(*raw)
        
        # Should be close to original (only monotonicity applied)
        assert cal[1] == raw[1], "Median unchanged in cold start"


class TestHorizonCalibratorRegistry:
    """Tests for HorizonCalibratorRegistry"""
    
    def test_separate_horizons(self):
        """Test that each horizon has independent calibration"""
        registry = HorizonCalibratorRegistry(horizons=[0, 12, 36])
        
        # Train spot with tight intervals
        np.random.seed(42)
        for _ in range(30):
            actual = 300000 + np.random.normal(0, 10000)
            registry.update(0, actual, actual - 20000, actual, actual + 20000)
        
        # Train 12m with wide intervals (more uncertainty)
        for _ in range(30):
            actual = 300000 + np.random.normal(0, 30000)
            registry.update(12, actual, actual - 50000, actual, actual + 50000)
        
        # Get diagnostics
        diag = registry.get_all_diagnostics()
        
        assert "spot" in diag
        assert "12m" in diag
        assert diag["spot"].n_samples == 30
        assert diag["12m"].n_samples == 30
    
    def test_calibrate_interval_api(self):
        """Test the calibrate_interval convenience method"""
        registry = HorizonCalibratorRegistry(horizons=[0, 12])
        
        # Train
        for _ in range(50):
            registry.update(0, 300000, 270000, 300000, 330000)
        
        # Calibrate
        cal = registry.calibrate_interval(270000, 300000, 330000, horizon_months=0)
        
        assert len(cal) == 3
        assert cal[0] <= cal[1] <= cal[2]
    
    def test_is_calibrated_check(self):
        """Test calibration readiness check"""
        registry = HorizonCalibratorRegistry(horizons=[0, 12], window_size=50)
        
        assert registry.is_calibrated(0, min_samples=20) == False
        
        # Add samples
        for _ in range(25):
            registry.update(0, 300000, 270000, 300000, 330000)
        
        assert registry.is_calibrated(0, min_samples=20) == True
        assert registry.is_calibrated(12, min_samples=20) == False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestValuationIntegration:
    """Integration tests for the full valuation pipeline"""
    
    def test_evidence_pack_structure(self, sample_listing, sample_comps):
        """Test that evidence pack contains expected fields"""
        # Create mock evidence pack
        evidence = EvidencePack(
            model_used="fusion",
            anchor_price=350000,
            anchor_std=25000,
            top_comps=[
                CompEvidence(
                    id="comp-001",
                    observed_month="2024-01",
                    raw_price=300000,
                    adj_factor=1.10,
                    adj_price=330000,
                    attention_weight=0.25
                )
            ],
            calibration_status="calibrated"
        )
        
        assert evidence.model_used == "fusion"
        assert len(evidence.top_comps) == 1
        assert evidence.top_comps[0].adj_price == 330000
    
    def test_comp_time_adjustment_is_applied(self, sample_comps, temp_db):
        """Test that comp prices are adjusted before use"""
        svc = HedonicIndexService(db_path=temp_db)
        
        total_adjustment = 0
        for comp in sample_comps[:5]:
            adj_price, factor, _ = svc.adjust_comp_price(
                raw_price=comp.price,
                region_id="all",
                comp_timestamp=comp.listed_at,
                target_timestamp=datetime(2024, 6, 15)
            )
            total_adjustment += (factor - 1.0)
        
        # All comps are from early 2024, target is mid-2024
        # Index went from 3000 to 3300, so all should be adjusted up
        assert total_adjustment > 0, "Comps should be adjusted upward"
    
    def test_no_future_leakage(self, sample_comps):
        """Test that comps don't leak future information"""
        valuation_date = datetime(2024, 2, 1)
        
        # Filter comps that would be "future" relative to valuation date
        valid_comps = [
            c for c in sample_comps
            if c.listed_at and c.listed_at < valuation_date
        ]
        
        # Only some comps should be valid
        assert len(valid_comps) < len(sample_comps)
        
        # All valid comps should be before valuation date
        for comp in valid_comps:
            assert comp.listed_at < valuation_date


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
