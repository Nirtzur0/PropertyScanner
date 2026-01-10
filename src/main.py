import sys
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

from src.core.orchestration.workflow import Orchestrator
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "/venta-viviendas/madrid/"
    
    orchestrator = Orchestrator()
    orchestrator.run_job(target_area=target)

if __name__ == "__main__":
    main()
