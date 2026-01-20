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
        "--run-integration",
        action="store_true",
        default=False,
        help="Run tests marked as integration.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: marks tests that hit live external services"
    )


def pytest_collection_modifyitems(config, items):
    run_integration = (
        config.getoption("--run-integration")
        or os.getenv("RUN_INTEGRATION") == "1"
    )
    if run_integration:
        return
    skip_integration = pytest.mark.skip(
        reason="integration tests require --run-integration or RUN_INTEGRATION=1"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
