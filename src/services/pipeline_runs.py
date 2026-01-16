import uuid
from typing import Any, Dict, Optional

from src.repositories.pipeline_runs import PipelineRunsRepository
from src.repositories.base import resolve_db_url


class PipelineRunTracker:
    def __init__(self, *, db_url: Optional[str] = None, db_path: Optional[str] = None) -> None:
        resolved = resolve_db_url(db_url=db_url, db_path=db_path)
        self.repo = PipelineRunsRepository(db_url=resolved)
        self.repo.ensure_table()

    def start(self, *, step_name: str, run_type: str = "workflow", metadata: Optional[Dict[str, Any]] = None) -> str:
        run_id = uuid.uuid4().hex
        self.repo.start_run(run_id=run_id, run_type=run_type, step_name=step_name, metadata=metadata)
        return run_id

    def finish(self, *, run_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.repo.finish_run(run_id=run_id, status=status, metadata=metadata)
