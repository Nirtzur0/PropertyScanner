import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser() if raw else default


DATA_DIR = _env_path("PROPERTY_SCANNER_DATA_DIR", PROJECT_ROOT / "data")
MODELS_DIR = _env_path("PROPERTY_SCANNER_MODELS_DIR", PROJECT_ROOT / "models")
CONFIG_DIR = _env_path("PROPERTY_SCANNER_CONFIG_DIR", PROJECT_ROOT / "config")
SNAPSHOTS_DIR = _env_path("PROPERTY_SCANNER_SNAPSHOTS_DIR", DATA_DIR / "snapshots")

DEFAULT_DB_PATH = _env_path("PROPERTY_SCANNER_DB_PATH", DATA_DIR / "listings.db")
DEFAULT_DB_URL = os.getenv("PROPERTY_SCANNER_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")

VECTOR_INDEX_PATH = _env_path("PROPERTY_SCANNER_VECTOR_INDEX_PATH", DATA_DIR / "vector_index.faiss")
VECTOR_METADATA_PATH = _env_path("PROPERTY_SCANNER_VECTOR_METADATA_PATH", DATA_DIR / "vector_metadata.json")
LANCEDB_PATH = _env_path("PROPERTY_SCANNER_LANCEDB_PATH", DATA_DIR / "vector_index.lancedb")

FUSION_MODEL_PATH = _env_path("PROPERTY_SCANNER_FUSION_MODEL_PATH", MODELS_DIR / "fusion_model.pt")
FUSION_CONFIG_PATH = _env_path("PROPERTY_SCANNER_FUSION_CONFIG_PATH", MODELS_DIR / "fusion_config.json")
CALIBRATION_PATH = _env_path("PROPERTY_SCANNER_CALIBRATION_PATH", MODELS_DIR / "calibration_registry.json")
TFT_MODEL_PATH = _env_path("PROPERTY_SCANNER_TFT_MODEL_PATH", MODELS_DIR / "tft_forecaster.pt")

SEEN_URLS_DB = _env_path("PROPERTY_SCANNER_SEEN_URLS_DB", DATA_DIR / "seen_urls.sqlite3")

TRANSACTIONS_PATH = _env_path("PROPERTY_SCANNER_TRANSACTIONS_PATH", DATA_DIR / "transactions.csv")
