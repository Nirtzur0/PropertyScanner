from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from src.core.runtime import RuntimeConfig
from src.platform.domain.models import JobRun
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


class JobService:
    def __init__(self, *, storage: StorageService, runtime_config: RuntimeConfig) -> None:
        self.storage = storage
        self.runtime_config = runtime_config

    @staticmethod
    @lru_cache(maxsize=1)
    def _executor(max_workers: int) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="property-scanner-job")

    def _create_job(self, session: Session, *, job_type: str, payload: Dict[str, Any]) -> JobRun:
        job = JobRun(
            id=uuid4().hex,
            job_type=job_type,
            status="queued",
            payload=payload,
            logs=[],
            created_at=utcnow(),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    def _update_job(
        self,
        session: Session,
        job_id: str,
        *,
        status: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        append_log: Optional[str] = None,
    ) -> JobRun:
        job = session.query(JobRun).filter(JobRun.id == job_id).first()
        if job is None:
            raise ValueError("job_not_found")
        if status is not None:
            job.status = status
        if started_at is not None:
            job.started_at = started_at
        if completed_at is not None:
            job.completed_at = completed_at
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        if append_log is not None:
            logs = list(job.logs or [])
            logs.append(append_log)
            job.logs = logs
        session.commit()
        session.refresh(job)
        return job

    def _execute_job(self, job_id: str, job_fn: Callable[[], Dict[str, Any]]) -> None:
        session = self.storage.get_session()
        try:
            self._update_job(
                session,
                job_id,
                status="running",
                started_at=utcnow(),
                append_log="job_started",
            )
        finally:
            session.close()

        try:
            result = job_fn()
            session = self.storage.get_session()
            try:
                self._update_job(
                    session,
                    job_id,
                    status="succeeded",
                    completed_at=utcnow(),
                    result=result,
                    append_log="job_succeeded",
                )
            finally:
                session.close()
        except Exception as exc:
            session = self.storage.get_session()
            try:
                self._update_job(
                    session,
                    job_id,
                    status="failed",
                    completed_at=utcnow(),
                    error=str(exc),
                    append_log=f"job_failed:{exc}",
                )
            finally:
                session.close()

    def submit(self, *, job_type: str, payload: Dict[str, Any], job_fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            job = self._create_job(session, job_type=job_type, payload=payload)
        finally:
            session.close()
        executor = self._executor(max(1, self.runtime_config.jobs.max_workers))
        executor.submit(self._execute_job, job.id, job_fn)
        return self.get_job(job.id)

    def run_sync(self, *, job_type: str, payload: Dict[str, Any], job_fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            job = self._create_job(session, job_type=job_type, payload=payload)
        finally:
            session.close()
        self._execute_job(job.id, job_fn)
        return self.get_job(job.id)

    def get_job(self, job_id: str) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            job = session.query(JobRun).filter(JobRun.id == job_id).first()
            if job is None:
                raise ValueError("job_not_found")
            return {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "payload": job.payload or {},
                "result": job.result or {},
                "error": job.error,
                "logs": list(job.logs or []),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
        finally:
            session.close()

    def list_jobs(
        self,
        *,
        limit: int = 25,
        job_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            query = session.query(JobRun)
            if job_type:
                query = query.filter(JobRun.job_type == job_type)
            if status:
                query = query.filter(JobRun.status == status)
            rows = query.order_by(JobRun.created_at.desc()).limit(max(1, min(limit, 200))).all()
            return [
                {
                    "id": row.id,
                    "job_type": row.job_type,
                    "status": row.status,
                    "payload": row.payload or {},
                    "result": row.result or {},
                    "error": row.error,
                    "logs": list(row.logs or []),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "started_at": row.started_at.isoformat() if row.started_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                }
                for row in rows
            ]
        finally:
            session.close()
