
import sqlite3
from pathlib import Path
from datetime import datetime

import structlog
from src.platform.config import DEFAULT_DB_PATH
from src.listings.source_ids import canonical_source_map

logger = structlog.get_logger(__name__)
CURRENT_SCHEMA_VERSION = 2

def run_migrations(db_path=str(DEFAULT_DB_PATH)):
    """
    Applies all schema changes in order. Idempotent check should be improved in production (using version table).
    """
    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=60.0)
    current_version_row = conn.execute("PRAGMA user_version").fetchone()
    current_version = int(current_version_row[0] or 0) if current_version_row else 0
    if current_version >= CURRENT_SCHEMA_VERSION:
        conn.close()
        return
    logger.info("migration_start", from_version=current_version, to_version=CURRENT_SCHEMA_VERSION)
    
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
        CREATE TABLE IF NOT EXISTS ui_events (
            id TEXT PRIMARY KEY,
            event_name TEXT NOT NULL,
            route TEXT NOT NULL,
            subject_type TEXT,
            subject_id TEXT,
            context JSON,
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ui_events_event_route ON ui_events (event_name, route)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ui_events_occurred_at ON ui_events (occurred_at)")

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

    legacy_aliases = canonical_source_map(
        [
            "imovirtual",
            "rightmove",
            "zoopla",
            "onthemarket",
            "immobiliare",
            "funda",
            "immowelt",
            "realtor",
            "redfin",
            "homes",
            "daft",
            "sreality",
            "seloger",
            "pararius",
        ]
    )

    def _canonicalize_source_ids(table_name: str) -> None:
        if not _table_exists(table_name):
            return
        for legacy_source_id, canonical_source_id in legacy_aliases.items():
            if legacy_source_id == canonical_source_id:
                continue
            conn.execute(
                f"UPDATE {table_name} SET source_id = ? WHERE source_id = ?",
                (canonical_source_id, legacy_source_id),
            )

    for table_name in (
        "listings",
        "source_contract_runs",
        "data_quality_events",
        "listing_observations",
    ):
        _canonicalize_source_ids(table_name)

    # =========================================================================
    # V2: Consolidated market intelligence tables
    # =========================================================================

    # 1. market_fundamentals = market_indices + hedonic_indices
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_fundamentals (
            id TEXT PRIMARY KEY,
            region_id TEXT NOT NULL,
            month_date DATE NOT NULL,
            source TEXT NOT NULL,
            price_index_sqm FLOAT,
            rent_index_sqm FLOAT,
            inventory_count INT,
            new_listings_count INT,
            sold_count INT,
            absorption_rate FLOAT,
            median_dom INT,
            price_cut_share FLOAT,
            volatility_3m FLOAT,
            hedonic_index_sqm FLOAT,
            raw_median_sqm FLOAT,
            r_squared FLOAT,
            n_observations INT,
            n_neighborhoods INT,
            coefficients TEXT,
            updated_at DATETIME
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_mf_region_date "
        "ON market_fundamentals (region_id, month_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_mf_source "
        "ON market_fundamentals (source, region_id, month_date)"
    )

    # 2. macro_context = macro_indicators + macro_scenarios
    conn.execute("""
        CREATE TABLE IF NOT EXISTS macro_context (
            id TEXT PRIMARY KEY,
            date DATE NOT NULL,
            context_type TEXT NOT NULL,
            scenario_name TEXT,
            source_id TEXT,
            source_url TEXT,
            horizon_year INT,
            euribor_12m FLOAT,
            ecb_deposit_rate FLOAT,
            mortgage_rate_avg FLOAT,
            inflation FLOAT,
            unemployment_rate FLOAT,
            idealista_index_madrid FLOAT,
            idealista_index_national FLOAT,
            gdp_growth FLOAT,
            confidence_text TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_mc_type_date "
        "ON macro_context (context_type, date)"
    )

    # 3. area_signals = area_intelligence (rename)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS area_signals (
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

    # --- Migrate data from old tables into new consolidated tables ---

    def _migrate_market_indices_to_fundamentals() -> None:
        if not _table_exists("market_indices"):
            return
        rows = conn.execute(
            """
            SELECT id, region_id, month_date,
                   price_index_sqm, rent_index_sqm, inventory_count,
                   new_listings_count, sold_count, absorption_rate,
                   median_dom, price_cut_share, volatility_3m, updated_at
            FROM market_indices
            """
        ).fetchall()
        if not rows:
            return
        conn.executemany(
            """
            INSERT OR IGNORE INTO market_fundamentals
            (id, region_id, month_date, source,
             price_index_sqm, rent_index_sqm, inventory_count,
             new_listings_count, sold_count, absorption_rate,
             median_dom, price_cut_share, volatility_3m, updated_at)
            VALUES (?, ?, ?, 'market', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def _migrate_hedonic_indices_to_fundamentals() -> None:
        if not _table_exists("hedonic_indices"):
            return
        cols = [c["name"] for c in conn.execute("PRAGMA table_info(hedonic_indices)").fetchall()]
        has_nh = "n_neighborhoods" in [c[1] for c in conn.execute("PRAGMA table_info(hedonic_indices)").fetchall()]
        rows = conn.execute(
            """
            SELECT id, region_id, month_date,
                   hedonic_index_sqm, raw_median_sqm, r_squared,
                   n_observations, {nh}, coefficients, updated_at
            FROM hedonic_indices
            """.format(nh="n_neighborhoods" if has_nh else "NULL as n_neighborhoods")
        ).fetchall()
        if not rows:
            return
        for row in rows:
            rid, region_id, month_date, hedonic, raw_med, r2, n_obs, n_nh, coeff, upd = row
            hedonic_id = f"hedonic|{region_id}|{month_date}" if not rid.startswith("hedonic|") else rid
            conn.execute(
                """
                INSERT OR IGNORE INTO market_fundamentals
                (id, region_id, month_date, source,
                 hedonic_index_sqm, raw_median_sqm, r_squared,
                 n_observations, n_neighborhoods, coefficients, updated_at)
                VALUES (?, ?, ?, 'hedonic', ?, ?, ?, ?, ?, ?, ?)
                """,
                (hedonic_id, region_id, month_date, hedonic, raw_med, r2, n_obs, n_nh, coeff, upd),
            )

    def _migrate_macro_indicators_to_context() -> None:
        if not _table_exists("macro_indicators"):
            return
        col_names = [c[1] for c in conn.execute("PRAGMA table_info(macro_indicators)").fetchall()]
        has_cpi = "spain_cpi" in col_names
        has_unemp = "unemployment_rate" in col_names
        has_mortgage = "mortgage_rate_avg" in col_names
        rows = conn.execute(
            """
            SELECT date, euribor_12m, ecb_deposit_rate,
                   {mortgage}, {cpi}, {unemp},
                   idealista_index_madrid, idealista_index_national,
                   updated_at
            FROM macro_indicators
            """.format(
                mortgage="mortgage_rate_avg" if has_mortgage else "NULL",
                cpi="spain_cpi" if has_cpi else "NULL",
                unemp="unemployment_rate" if has_unemp else "NULL",
            )
        ).fetchall()
        if not rows:
            return
        for row in rows:
            dt, euribor, ecb, mortgage, cpi, unemp, ideal_mad, ideal_nat, upd = row
            conn.execute(
                """
                INSERT OR IGNORE INTO macro_context
                (id, date, context_type, euribor_12m, ecb_deposit_rate,
                 mortgage_rate_avg, inflation, unemployment_rate,
                 idealista_index_madrid, idealista_index_national, updated_at)
                VALUES (?, ?, 'actual', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"actual|{dt}", dt, euribor, ecb, mortgage, cpi, unemp, ideal_mad, ideal_nat, upd),
            )

    def _migrate_macro_scenarios_to_context() -> None:
        if not _table_exists("macro_scenarios"):
            return
        col_names = [c[1] for c in conn.execute("PRAGMA table_info(macro_scenarios)").fetchall()]
        has_source_id = "source_id" in col_names
        has_horizon = "horizon_year" in col_names
        has_retrieved = "retrieved_at" in col_names
        rows = conn.execute(
            """
            SELECT date, scenario_name, source_url,
                   {source_id}, {horizon},
                   euribor_12m_forecast, inflation_forecast,
                   gdp_growth_forecast, confidence_text,
                   {retrieved}
            FROM macro_scenarios
            """.format(
                source_id="source_id" if has_source_id else "NULL",
                horizon="horizon_year" if has_horizon else "NULL",
                retrieved="retrieved_at" if has_retrieved else "fetched_at",
            )
        ).fetchall()
        if not rows:
            return
        for row in rows:
            dt, scenario, url, src_id, horizon, euribor, inflation, gdp, conf, retrieved = row
            scenario = scenario or "unknown"
            src_id = src_id or ""
            horizon = horizon or ""
            row_id = f"forecast|{src_id}|{scenario}|{horizon}"
            conn.execute(
                """
                INSERT OR IGNORE INTO macro_context
                (id, date, context_type, scenario_name, source_id, source_url,
                 horizon_year, euribor_12m, inflation, gdp_growth,
                 confidence_text, updated_at)
                VALUES (?, ?, 'forecast', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, dt, scenario, src_id, url, horizon, euribor, inflation, gdp, conf, retrieved),
            )

    def _migrate_area_intelligence_to_signals() -> None:
        if not _table_exists("area_intelligence"):
            return
        col_names = [c[1] for c in conn.execute("PRAGMA table_info(area_intelligence)").fetchall()]
        has_as_of = "sentiment_as_of" in col_names
        has_cred = "sentiment_credibility" in col_names
        has_dev_as_of = "development_as_of" in col_names
        has_dev_cred = "development_credibility" in col_names
        rows = conn.execute(
            """
            SELECT area_id, last_updated, sentiment_score,
                   {s_as_of}, {s_cred},
                   future_development_score,
                   {d_as_of}, {d_cred},
                   news_summary, top_keywords, source_urls
            FROM area_intelligence
            """.format(
                s_as_of="sentiment_as_of" if has_as_of else "NULL",
                s_cred="sentiment_credibility" if has_cred else "NULL",
                d_as_of="development_as_of" if has_dev_as_of else "NULL",
                d_cred="development_credibility" if has_dev_cred else "NULL",
            )
        ).fetchall()
        if not rows:
            return
        conn.executemany(
            """
            INSERT OR IGNORE INTO area_signals
            (area_id, last_updated, sentiment_score,
             sentiment_as_of, sentiment_credibility,
             future_development_score,
             development_as_of, development_credibility,
             news_summary, top_keywords, source_urls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    if current_version < 2:
        _migrate_market_indices_to_fundamentals()
        _migrate_hedonic_indices_to_fundamentals()
        _migrate_macro_indicators_to_context()
        _migrate_macro_scenarios_to_context()
        _migrate_area_intelligence_to_signals()

        # Verify migration succeeded before dropping old tables
        def _new_table_has_data(name: str) -> bool:
            row = conn.execute(f"SELECT COUNT(1) FROM {name}").fetchone()
            return bool(row and row[0] and int(row[0]) > 0)

        def _old_table_has_data(name: str) -> bool:
            if not _table_exists(name):
                return False
            row = conn.execute(f"SELECT COUNT(1) FROM {name}").fetchone()
            return bool(row and row[0] and int(row[0]) > 0)

        # Only drop old tables if new tables got data (or old were empty)
        safe_to_drop = True
        for old_name, new_name in [
            ("market_indices", "market_fundamentals"),
            ("hedonic_indices", "market_fundamentals"),
            ("macro_indicators", "macro_context"),
            ("macro_scenarios", "macro_context"),
            ("area_intelligence", "area_signals"),
        ]:
            if _old_table_has_data(old_name) and not _new_table_has_data(new_name):
                safe_to_drop = False
                logger.warning("migration_v2_skip_drop", old=old_name, new=new_name)
                break

        if safe_to_drop:
            for old_table in ("market_indices", "hedonic_indices", "macro_indicators", "macro_scenarios", "area_intelligence"):
                if _table_exists(old_table):
                    conn.execute(f"DROP TABLE IF EXISTS {old_table}")
            logger.info("migration_v2_old_tables_dropped")

    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
    conn.commit()
    conn.close()
    logger.info("migration_complete", version=CURRENT_SCHEMA_VERSION)

if __name__ == "__main__":
    run_migrations()
