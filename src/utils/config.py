import yaml
from pathlib import Path
from typing import Dict, Any
from src.core.config import CONFIG_DIR

class ConfigLoader:
    def __init__(self, config_dir: str = str(CONFIG_DIR)):
        self.config_paths = Path(config_dir).resolve()
        
    def load_yaml(self, filename: str) -> Dict[str, Any]:
        file_path = self.config_paths / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")
            
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)

    @property
    def sources(self) -> Dict[str, Any]:
        return self.load_yaml("sources.yaml")
        
    @property
    def agents(self) -> Dict[str, Any]:
        return self.load_yaml("agents.yaml")
        
    @property
    def scoring(self) -> Dict[str, Any]:
        return self.load_yaml("scoring.yaml")
