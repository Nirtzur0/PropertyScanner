from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.platform.domain.models import AgentRun, CompReview, Memo, SavedSearch, Watchlist
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


class WorkspaceService:
    def __init__(self, *, storage: StorageService) -> None:
        self.storage = storage

    @staticmethod
    def _watchlist_to_dict(row: Watchlist) -> Dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "status": row.status,
            "listing_ids": list(row.listing_ids or []),
            "filters": dict(row.filters or {}),
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _saved_search_to_dict(row: SavedSearch) -> Dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "query": row.query,
            "filters": dict(row.filters or {}),
            "sort": dict(row.sort or {}),
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _memo_to_dict(row: Memo) -> Dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title,
            "listing_id": row.listing_id,
            "watchlist_id": row.watchlist_id,
            "status": row.status,
            "assumptions": list(row.assumptions or []),
            "risks": list(row.risks or []),
            "sections": list(row.sections or []),
            "export_format": row.export_format,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _comp_review_to_dict(row: CompReview) -> Dict[str, Any]:
        return {
            "id": row.id,
            "listing_id": row.listing_id,
            "status": row.status,
            "selected_comp_ids": list(row.selected_comp_ids or []),
            "rejected_comp_ids": list(row.rejected_comp_ids or []),
            "overrides": dict(row.overrides or {}),
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _agent_run_to_dict(row: AgentRun) -> Dict[str, Any]:
        return {
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "query": row.query,
            "target_areas": list(row.target_areas or []),
            "strategy": row.strategy,
            "plan": dict(row.plan or {}),
            "status": row.status,
            "summary": row.summary,
            "error": row.error,
            "listings_count": row.listings_count or 0,
            "evaluations_count": row.evaluations_count or 0,
            "top_listing_ids": list(row.top_listing_ids or []),
            "ui_blocks": list(row.ui_blocks or []),
        }

    def list_watchlists(self) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = session.query(Watchlist).order_by(Watchlist.updated_at.desc()).all()
            return [self._watchlist_to_dict(row) for row in rows]
        finally:
            session.close()

    def create_watchlist(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        status: str = "active",
        listing_ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            row = Watchlist(
                id=uuid4().hex,
                name=name.strip(),
                description=description,
                status=status,
                listing_ids=list(listing_ids or []),
                filters=dict(filters or {}),
                notes=notes,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._watchlist_to_dict(row)
        finally:
            session.close()

    def list_saved_searches(self) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = session.query(SavedSearch).order_by(SavedSearch.updated_at.desc()).all()
            return [self._saved_search_to_dict(row) for row in rows]
        finally:
            session.close()

    def create_saved_search(
        self,
        *,
        name: str,
        query: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        sort: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            row = SavedSearch(
                id=uuid4().hex,
                name=name.strip(),
                query=query,
                filters=dict(filters or {}),
                sort=dict(sort or {}),
                notes=notes,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._saved_search_to_dict(row)
        finally:
            session.close()

    def list_memos(self) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = session.query(Memo).order_by(Memo.updated_at.desc()).all()
            return [self._memo_to_dict(row) for row in rows]
        finally:
            session.close()

    def get_memo(self, memo_id: str) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            row = session.query(Memo).filter(Memo.id == memo_id).first()
            if row is None:
                raise ValueError("memo_not_found")
            return self._memo_to_dict(row)
        finally:
            session.close()

    def create_memo(
        self,
        *,
        title: str,
        listing_id: Optional[str] = None,
        watchlist_id: Optional[str] = None,
        status: str = "draft",
        assumptions: Optional[List[str]] = None,
        risks: Optional[List[str]] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
        export_format: str = "markdown",
    ) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            row = Memo(
                id=uuid4().hex,
                title=title.strip(),
                listing_id=listing_id,
                watchlist_id=watchlist_id,
                status=status,
                assumptions=list(assumptions or []),
                risks=list(risks or []),
                sections=list(sections or []),
                export_format=export_format,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._memo_to_dict(row)
        finally:
            session.close()

    def export_memo(self, memo_id: str) -> Dict[str, Any]:
        memo = self.get_memo(memo_id)
        sections = memo.get("sections") or []
        rendered_sections: List[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = str(section.get("heading") or "Section").strip()
            body = str(section.get("body") or "").strip()
            rendered_sections.append(f"## {heading}\n{body}".strip())
        assumptions = "\n".join(f"- {item}" for item in memo.get("assumptions") or [])
        risks = "\n".join(f"- {item}" for item in memo.get("risks") or [])
        markdown = "\n\n".join(
            part
            for part in [
                f"# {memo['title']}",
                f"Status: {memo['status']}",
                f"Listing: {memo.get('listing_id') or 'unassigned'}",
                "## Assumptions\n" + (assumptions or "- None recorded"),
                "## Risks\n" + (risks or "- None recorded"),
                "\n\n".join(rendered_sections) if rendered_sections else "## Notes\nNo memo sections recorded.",
            ]
            if part
        )
        return {
            "memo_id": memo_id,
            "format": memo.get("export_format") or "markdown",
            "content": markdown,
        }

    def list_comp_reviews(self, *, listing_id: Optional[str] = None) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            query = session.query(CompReview)
            if listing_id:
                query = query.filter(CompReview.listing_id == listing_id)
            rows = query.order_by(CompReview.updated_at.desc()).all()
            return [self._comp_review_to_dict(row) for row in rows]
        finally:
            session.close()

    def create_comp_review(
        self,
        *,
        listing_id: str,
        status: str = "draft",
        selected_comp_ids: Optional[List[str]] = None,
        rejected_comp_ids: Optional[List[str]] = None,
        overrides: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            row = CompReview(
                id=uuid4().hex,
                listing_id=listing_id,
                status=status,
                selected_comp_ids=list(selected_comp_ids or []),
                rejected_comp_ids=list(rejected_comp_ids or []),
                overrides=dict(overrides or {}),
                notes=notes,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._comp_review_to_dict(row)
        finally:
            session.close()

    def list_command_center_runs(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            rows = (
                session.query(AgentRun)
                .order_by(AgentRun.created_at.desc())
                .limit(max(1, min(limit, 100)))
                .all()
            )
            return [self._agent_run_to_dict(row) for row in rows]
        finally:
            session.close()
