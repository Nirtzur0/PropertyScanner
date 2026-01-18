from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

from src.platform.storage import StorageService
from src.platform.domain.models import AgentRun

logger = structlog.get_logger()


class AgentMemoryStore:
    """Persist and retrieve cognitive agent runs."""

    def __init__(self, storage: Optional[StorageService] = None) -> None:
        self.storage = storage or StorageService()

    def record_run(self, payload: Dict[str, Any]) -> str:
        run_id = payload.get("run_id") or uuid4().hex
        summary = payload.get("summary")
        error = payload.get("error")

        entry = AgentRun(
            id=run_id,
            query=payload.get("query", ""),
            target_areas=payload.get("target_areas") or [],
            strategy=payload.get("strategy", "balanced"),
            plan=payload.get("plan") or {},
            status=payload.get("status", "success" if not error else "failed"),
            summary=summary,
            error=error,
            listings_count=int(payload.get("listings_count", 0) or 0),
            evaluations_count=int(payload.get("evaluations_count", 0) or 0),
            top_listing_ids=payload.get("top_listing_ids") or [],
            ui_blocks=payload.get("ui_blocks") or [],
        )

        session = self.storage.get_session()
        try:
            session.add(entry)
            session.commit()
            return run_id
        except Exception as exc:
            session.rollback()
            logger.error("agent_memory_store_failed", error=str(exc))
            raise
        finally:
            session.close()

    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = (
                session.query(AgentRun)
                .order_by(AgentRun.created_at.desc())
                .limit(limit)
                .all()
            )
            results = []
            for row in rows:
                results.append(
                    {
                        "id": row.id,
                        "created_at": row.created_at,
                        "query": row.query,
                        "target_areas": row.target_areas or [],
                        "strategy": row.strategy,
                        "plan": row.plan or {},
                        "status": row.status,
                        "summary": row.summary,
                        "error": row.error,
                        "listings_count": row.listings_count or 0,
                        "evaluations_count": row.evaluations_count or 0,
                        "top_listing_ids": row.top_listing_ids or [],
                        "ui_blocks": row.ui_blocks or [],
                    }
                )
            return results
        finally:
            session.close()
