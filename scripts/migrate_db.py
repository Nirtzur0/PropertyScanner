import sys
import os
sys.path.append(os.getcwd())

from src.services.storage import StorageService
from src.core.domain.models import Base

def migrate():
    print("Migrating database...")
    storage = StorageService()
    # This will create any missing tables (like 'valuations')
    Base.metadata.create_all(storage.engine)
    print("Detailed migration complete. 'valuations' table should exist.")

if __name__ == "__main__":
    migrate()
