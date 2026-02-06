import pytest
import os
import shutil
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.platform.domain.models import Base
from src.platform.config import DEFAULT_DB_URL

@pytest.fixture(scope="session")
def test_db_path():
    """
    Creates a temporary directory for the test database.
    Returns the path to the database file.
    """
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_listings.db")
    yield db_path
    shutil.rmtree(temp_dir)

@pytest.fixture(scope="session")
def test_db_engine(test_db_path):
    """
    Creates a real SQLAlchemy engine pointing to the temp SQLite file.
    """
    db_url = f"sqlite:///{test_db_path}"
    engine = create_engine(db_url)
    
    # Create the schema
    Base.metadata.create_all(engine)
    
    return engine

@pytest.fixture(scope="function")
def db_session(test_db_engine):
    """
    Provides a clean session for each test.
    Transactions are rolled back after each test to ensure isolation.
    """
    connection = test_db_engine.connect()
    transaction = connection.begin()
    
    Session = sessionmaker(bind=connection)
    session = Session()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="session")
def real_data_dir():
    """Returns the path to the tests/resources directory."""
    return os.path.join(os.path.dirname(__file__), "resources")


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run tests marked as live (real network/browser).",
    )

    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run tests marked as e2e.",
    )

    
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run tests marked as integration.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: offline integration tests (DB/filesystem), no live network"
    )
    config.addinivalue_line("markers", "e2e: end-to-end tests (offline, minimal mocks)")
    config.addinivalue_line("markers", "live: live network/browser tests (always opt-in)")
    config.addinivalue_line("markers", "network: hits the network")
    config.addinivalue_line("markers", "slow: long-running tests")


def pytest_collection_modifyitems(config, items):
    run_integration = (
        config.getoption("--run-integration")
        or os.getenv("RUN_INTEGRATION") == "1"
    )
    run_live = (
        config.getoption("--run-live")
        or os.getenv("RUN_LIVE") == "1"
    )
    run_e2e = (
        config.getoption("--run-e2e")
        or os.getenv("RUN_E2E") == "1"
    )

    skip_integration = pytest.mark.skip(
        reason="integration tests require --run-integration or RUN_INTEGRATION=1"
    )
    skip_live = pytest.mark.skip(
        reason="live tests require --run-live or RUN_LIVE=1"
    )
    skip_e2e = pytest.mark.skip(
        reason="e2e tests require --run-e2e or RUN_E2E=1"
    )

    for item in items:
        if "live" in item.keywords or "network" in item.keywords:
            if not run_live:
                item.add_marker(skip_live)
            continue

        if "e2e" in item.keywords:
            if not run_e2e:
                item.add_marker(skip_e2e)
            continue

        if "integration" in item.keywords:
            if not run_integration:
                item.add_marker(skip_integration)
