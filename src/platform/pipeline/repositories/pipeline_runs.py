import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from src.platform.db.base import RepositoryBase


class PipelineRunsRepository(RepositoryBase):
    def ensure_table(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS pipeline_runs (
                        run_id TEXT PRIMARY KEY,
                        run_type TEXT,
                        step_name TEXT,
                        status TEXT,
                        started_at DATETIME,
                        completed_at DATETIME,
                        metadata TEXT
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_pipeline_runs_step_status
                    ON pipeline_runs (step_name, status)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_pipeline_runs_completed_at
                    ON pipeline_runs (completed_at)
                    """
                )
            )

    def start_run(
        self,
        *,
        run_id: str,
        run_type: str,
        step_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "run_id": run_id,
            "run_type": run_type,
            "step_name": step_name,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "metadata": json.dumps(metadata or {}),
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO pipeline_runs
                    (run_id, run_type, step_name, status, started_at, completed_at, metadata)
                    VALUES (:run_id, :run_type, :step_name, :status, :started_at, :completed_at, :metadata)
                    """
                ),
                payload,
            )

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "run_id": run_id,
            "status": status,
            "completed_at": datetime.utcnow().isoformat(),
            "metadata": json.dumps(metadata or {}),
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE pipeline_runs
                    SET status = :status,
                        completed_at = :completed_at,
                        metadata = :metadata
                    WHERE run_id = :run_id
                    """
                ),
                payload,
            )

    def latest_run(self, step_name: str) -> Optional[Dict[str, Any]]:
        query = text(
            """
            SELECT run_id, run_type, status, started_at, completed_at, metadata
            FROM pipeline_runs
            WHERE step_name = :step_name
            ORDER BY completed_at DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"step_name": step_name}).fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "run_type": row[1],
            "status": row[2],
            "started_at": row[3],
            "completed_at": row[4],
            "metadata": json.loads(row[5]) if row[5] else {},
        }
