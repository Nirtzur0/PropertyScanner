
import sqlite3
from datetime import datetime

import structlog
from src.platform.config import DEFAULT_DB_PATH

logger = structlog.get_logger(__name__)

def run_migrations(db_path=str(DEFAULT_DB_PATH)):
    """
    Applies all schema changes in order. Idempotent check should be improved in production (using version table).
    """
    logger.info("migration_start")
    conn = sqlite3.connect(db_path, timeout=60.0)
    
    # 1. Market Indices
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_indices (
            id TEXT PRIMARY KEY, -- "region_id|month"
            region_id TEXT, -- "city:madrid" or "gh6:ezjmgu"
            month_date DATE,
            price_index_sqm FLOAT,
            rent_index_sqm FLOAT,
            inventory_count INT,
            new_listings_count INT,
            sold_count INT,
            absorption_rate FLOAT,
            median_dom INT,
            price_cut_share FLOAT,
            volatility_3m FLOAT,
            updated_at DATETIME
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_market_indices_region_date ON market_indices (region_id, month_date)")
    try:
        conn.execute("ALTER TABLE market_indices ADD COLUMN updated_at DATETIME")
        logger.info("migration_market_indices_updated_at_added")
    except Exception:
        pass
    
    # 2. Macro Indicators
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            date DATE PRIMARY KEY,        -- Monthly (YYYY-MM-01)
            euribor_12m FLOAT,            -- Key benchmark
            ecb_deposit_rate FLOAT,       -- ECB main rate
            mortgage_rate_avg FLOAT,      -- Avg commercial mortgage rate
            spain_cpi FLOAT,              -- Inflation
            unemployment_rate FLOAT,      -- Spain Unemployment
            idealista_index_madrid FLOAT, -- Scraped benchmark
            idealista_index_national FLOAT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 3. Macro Scenarios (LLM)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            source_url TEXT,
            scenario_name TEXT, -- "base", "optimistic", "pessimistic"
            euribor_12m_forecast FLOAT,
            inflation_forecast FLOAT,
            gdp_growth_forecast FLOAT,
            confidence_text TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 4. Geohash
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN geohash VARCHAR")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_listings_geohash ON listings (geohash)")
        logger.info("migration_geohash_added")
    except Exception:
        pass

    # 4b. Listing type (sale vs rent) for downstream indices/forecasting
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN listing_type TEXT DEFAULT 'sale'")
        logger.info("migration_listing_type_added")
        try:
            # Best-effort backfill from URL patterns.
            conn.execute(
                """
                UPDATE listings
                SET listing_type = 'rent'
                WHERE (
                    listing_type IS NULL OR listing_type = '' OR listing_type = 'sale'
                ) AND (
                    url LIKE '%/alquiler/%' OR url LIKE '%/rent/%' OR url LIKE '%/rental/%'
                )
                """
            )
        except Exception:
            pass
    except Exception:
        pass

    # 4b2. Sold transaction price (when available)
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN sold_price FLOAT")
        logger.info("migration_sold_price_added")
    except Exception:
        pass

    # 4c. Location metadata (zip, country)
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN zip_code TEXT")
        logger.info("migration_zip_code_added")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE listings ADD COLUMN country TEXT")
        logger.info("migration_country_added")
    except Exception:
        pass

    # 4d. Plot area + image embeddings
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN plot_area_sqm FLOAT")
        logger.info("migration_plot_area_added")
    except Exception:
        pass

    try:
        conn.execute("ALTER TABLE listings ADD COLUMN image_embeddings JSON")
        logger.info("migration_image_embeddings_added")
    except Exception:
        pass
    
    # 5. Hedonic Indices (SOTA V3)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hedonic_indices (
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
    conn.execute("CREATE INDEX IF NOT EXISTS ix_hedonic_region_date ON hedonic_indices (region_id, month_date)")
    try:
        conn.execute("ALTER TABLE hedonic_indices ADD COLUMN n_neighborhoods INT")
        logger.info("migration_hedonic_n_neighborhoods_added")
    except Exception:
        pass

    # 5b. Area Intelligence (used by forecasting)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS area_intelligence (
            area_id TEXT PRIMARY KEY,
            last_updated DATETIME,
            sentiment_score FLOAT,
            sentiment_as_of DATETIME,
            sentiment_credibility FLOAT,
            future_development_score FLOAT,
            development_as_of DATETIME,
            development_credibility FLOAT,
            news_summary TEXT,
            top_keywords TEXT,
            source_urls TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE area_intelligence ADD COLUMN sentiment_as_of DATETIME")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE area_intelligence ADD COLUMN sentiment_credibility FLOAT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE area_intelligence ADD COLUMN development_as_of DATETIME")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE area_intelligence ADD COLUMN development_credibility FLOAT")
    except Exception:
        pass

    # 5c. Agent Runs (Cognitive Orchestrator memory)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            query TEXT NOT NULL,
            target_areas TEXT,
            strategy TEXT,
            plan TEXT,
            status TEXT,
            summary TEXT,
            error TEXT,
            listings_count INT,
            evaluations_count INT,
            top_listing_ids TEXT,
            ui_blocks TEXT
        )
    """)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_runs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            payload JSON,
            result JSON,
            logs JSON,
            error TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_job_runs_type_status ON job_runs (job_type, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_job_runs_created_at ON job_runs (created_at)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_contract_runs (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            status TEXT NOT NULL,
            metrics JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_source_contract_runs_source_created ON source_contract_runs (source_id, created_at)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_quality_events (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            listing_id TEXT,
            field_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            code TEXT NOT NULL,
            details JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_events_source_code ON data_quality_events (source_id, code)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_observations (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            external_id TEXT NOT NULL,
            listing_id TEXT,
            observed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            raw_payload JSON,
            normalized_payload JSON,
            status TEXT NOT NULL,
            field_confidence JSON
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_listing_observations_source_external ON listing_observations (source_id, external_id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listing_entities (
            id TEXT PRIMARY KEY,
            canonical_listing_id TEXT NOT NULL UNIQUE,
            attributes JSON,
            source_links JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_listing_entities_canonical ON listing_entities (canonical_listing_id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            config JSON,
            metrics JSON,
            output_json_path TEXT,
            output_md_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_benchmark_runs_created ON benchmark_runs (created_at)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS coverage_reports (
            id TEXT PRIMARY KEY,
            listing_type TEXT NOT NULL,
            segment_key TEXT NOT NULL,
            segment_value TEXT NOT NULL,
            sample_size INT NOT NULL DEFAULT 0,
            empirical_coverage FLOAT,
            avg_interval_width FLOAT,
            status TEXT NOT NULL,
            report JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_coverage_reports_segment ON coverage_reports "
        "(listing_type, segment_key, segment_value)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            listing_ids JSON,
            filters JSON,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_watchlists_status ON watchlists (status)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_searches (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            query TEXT,
            filters JSON,
            sort JSON,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_saved_searches_name ON saved_searches (name)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memos (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            listing_id TEXT,
            watchlist_id TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            assumptions JSON,
            risks JSON,
            sections JSON,
            export_format TEXT NOT NULL DEFAULT 'markdown',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_memos_status_created ON memos (status, created_at)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comp_reviews (
            id TEXT PRIMARY KEY,
            listing_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            selected_comp_ids JSON,
            rejected_comp_ids JSON,
            overrides JSON,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_comp_reviews_listing_status ON comp_reviews (listing_id, status)")

    # 6. Official Metrics (ERI/Registry/INE unified)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS official_metrics (
            id TEXT PRIMARY KEY,
            provider_id TEXT,
            region_id TEXT,
            period TEXT,
            period_date DATE,
            housing_type TEXT,
            metric TEXT,
            value FLOAT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_official_metrics_provider_region_date "
        "ON official_metrics (provider_id, region_id, period_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_official_metrics_provider_region_metric "
        "ON official_metrics (provider_id, region_id, metric, housing_type, period_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_official_metrics_provider_metric "
        "ON official_metrics (provider_id, metric)"
    )

    def _table_exists(name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def _normalize_date(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.date().isoformat()
        text = str(value).strip()
        if not text:
            return ""
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            return text

    def _period_to_date(period: str) -> str:
        text = str(period).strip()
        if not text:
            return ""
        if "Q" in text:
            text = text.replace("-Q", "Q")
            if len(text) == 6 and text[:4].isdigit() and text[4] == "Q" and text[5].isdigit():
                year = int(text[:4])
                quarter = int(text[5])
                month = (quarter - 1) * 3 + 1
                return f"{year}-{month:02d}-01"
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError:
            return ""

    def _migrate_registry_table(table_name: str, provider_id: str) -> None:
        rows = conn.execute(
            f"""
            SELECT region_id, period_date, txn_count, mortgage_count, price_sqm, price_sqm_yoy, price_sqm_qoq
            FROM {table_name}
            """
        ).fetchall()
        if not rows:
            return
        payloads = []
        for (
            region_id,
            period_date,
            txn_count,
            mortgage_count,
            price_sqm,
            price_sqm_yoy,
            price_sqm_qoq,
        ) in rows:
            if not region_id or not period_date:
                continue
            period = _normalize_date(period_date)
            if not period:
                period = str(period_date)
            metrics = {
                "txn_count": txn_count,
                "mortgage_count": mortgage_count,
                "price_sqm": price_sqm,
                "price_sqm_yoy": price_sqm_yoy,
                "price_sqm_qoq": price_sqm_qoq,
            }
            for metric, value in metrics.items():
                if value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                payloads.append(
                    (
                        f"{provider_id}|{region_id}|{period}|{metric}",
                        provider_id,
                        region_id,
                        period,
                        period,
                        None,
                        metric,
                        numeric,
                    )
                )
        if payloads:
            conn.executemany(
                """
                INSERT OR IGNORE INTO official_metrics
                (id, provider_id, region_id, period, period_date, housing_type, metric, value, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                payloads,
            )

    def _migrate_ine_ipv() -> None:
        rows = conn.execute(
            """
            SELECT period, region_id, housing_type, metric, value
            FROM ine_ipv
            """
        ).fetchall()
        if not rows:
            return
        payloads = []
        for period, region_id, housing_type, metric, value in rows:
            if not period or not region_id or metric is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            period_text = str(period).strip()
            period_date = _period_to_date(period_text)
            payloads.append(
                (
                    f"ine_ipv|{region_id}|{period_text}|{housing_type}|{metric}",
                    "ine_ipv",
                    region_id,
                    period_text,
                    period_date,
                    housing_type,
                    metric,
                    numeric,
                )
            )
        if payloads:
            conn.executemany(
                """
                INSERT OR IGNORE INTO official_metrics
                (id, provider_id, region_id, period, period_date, housing_type, metric, value, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                payloads,
            )

    if _table_exists("eri_metrics"):
        _migrate_registry_table("eri_metrics", "eri_es")
    if _table_exists("uk_registry_metrics"):
        _migrate_registry_table("uk_registry_metrics", "uk_land_registry")
    if _table_exists("it_registry_metrics"):
        _migrate_registry_table("it_registry_metrics", "it_omi_registry")
    if _table_exists("ine_ipv"):
        _migrate_ine_ipv()

    def _official_metrics_populated() -> bool:
        row = conn.execute("SELECT COUNT(1) FROM official_metrics").fetchone()
        return bool(row and row[0] and int(row[0]) > 0)

    if _official_metrics_populated():
        for legacy in ("eri_metrics", "uk_registry_metrics", "it_registry_metrics", "ine_ipv"):
            if _table_exists(legacy):
                conn.execute(f"DROP TABLE IF EXISTS {legacy}")

    # 8. Pipeline Runs (operational audit/logs)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            run_type TEXT,
            step_name TEXT,
            status TEXT,
            started_at DATETIME,
            completed_at DATETIME,
            metadata TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_pipeline_runs_step_status ON pipeline_runs (step_name, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_pipeline_runs_completed_at ON pipeline_runs (completed_at)")
    
    
    # 7. Update macro_scenarios schema for SOTA V3 (cite-or-drop)
    try:
        conn.execute("ALTER TABLE macro_scenarios ADD COLUMN source_id TEXT")
        conn.execute("ALTER TABLE macro_scenarios ADD COLUMN horizon_year INT")
        conn.execute("ALTER TABLE macro_scenarios ADD COLUMN retrieved_at DATETIME")
    except Exception:
        pass
        
    conn.commit()
    conn.close()
    logger.info("migration_complete")

if __name__ == "__main__":
    run_migrations()
