from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from src.core.uow import IUnitOfWork


class ExamCsvRepository:
    """Bounded, scoped reads in the caller's repeatable-read transaction."""

    def __init__(self, uow: IUnitOfWork, workspace_id: int, exam_id: int, *, max_rows: int):
        self.uow = uow
        self.params = {"workspace_id": workspace_id, "exam_id": exam_id}
        self.remaining = max_rows

    async def rows(self, sql: str) -> list[dict]:
        result = await self.uow.session.execute(
            text(sql + " LIMIT :fetch_limit"), {**self.params, "fetch_limit": self.remaining + 1}
        )
        rows = [dict(row) for row in result.mappings()]
        self.remaining -= len(rows)
        if self.remaining < 0:
            raise HTTPException(413, detail={"code": "csv_export_limit_exceeded", "message": "Too many source rows"})
        return rows

    async def registrations(self) -> list[dict]:
        return await self.rows("""
            SELECT r.id AS registration_id, r.project_id,
                COALESCE(a.project_type_id, r.project_type_id_at_registration) AS project_type_id,
                r.status AS registration_status, r.queue_hold,
                p.name AS project_name, t.name AS project_type_name,
                a.id AS attempt_id, a.status AS defense_status, a.started_at, a.finished_at,
                a.postponed_at, w.id AS window_id, w.opened_at, w.closes_at
            FROM exam_registration r
            JOIN project p ON p.id=r.project_id
            JOIN project_type t ON t.id=COALESCE(
                (SELECT a2.project_type_id FROM exam_attempt a2 WHERE a2.registration_id=r.id),
                r.project_type_id_at_registration)
            LEFT JOIN exam_attempt a ON a.registration_id=r.id AND a.exam_id=r.exam_id AND a.workspace_id=r.workspace_id
            LEFT JOIN assessment_window w ON w.attempt_id=a.id AND w.exam_id=r.exam_id AND w.workspace_id=r.workspace_id
            WHERE r.workspace_id=:workspace_id AND r.exam_id=:exam_id
            ORDER BY r.id
        """)

    async def editions(self) -> list[dict]:
        return await self.rows("""
            SELECT DISTINCT ON (e.attempt_id) e.*,
                concat_ws(' ', NULLIF(u.first_name,''), NULLIF(u.last_name,''), NULLIF(u.middle_name,'')) AS decided_by_name
            FROM exam_result_edition e JOIN "user" u ON u.id=e.decided_by
            WHERE e.workspace_id=:workspace_id AND e.exam_id=:exam_id
            ORDER BY e.attempt_id, e.version DESC
        """)

    async def questions(self) -> list[dict]:
        return await self.rows("""
            SELECT q.id, q.project_type_id, q.position, q.text
            FROM project_type_question q
            WHERE q.project_type_id IN (
                SELECT COALESCE(a.project_type_id, r.project_type_id_at_registration)
                FROM exam_registration r LEFT JOIN exam_attempt a ON a.registration_id=r.id
                WHERE r.workspace_id=:workspace_id AND r.exam_id=:exam_id)
            ORDER BY q.project_type_id, q.position, q.id
        """)

    async def audience(self) -> list[dict]:
        return await self.rows("""
            SELECT w.attempt_id, a.user_id, a.role, a.own_project_ids, a.admitted, a.exclusion_reason,
                concat_ws(' ', NULLIF(u.first_name,''), NULLIF(u.last_name,''), NULLIF(u.middle_name,'')) AS assessor_name,
                sub.id AS submission_id, sub.version AS submission_version, sub.submitted_at, sub.total
            FROM assessment_window w
            JOIN assessment_window_audience a ON a.window_id=w.id AND a.workspace_id=w.workspace_id
            JOIN "user" u ON u.id=a.user_id
            LEFT JOIN exam_assessment_sheet sh ON sh.attempt_id=w.attempt_id AND sh.user_id=a.user_id
                AND sh.exam_id=w.exam_id AND sh.workspace_id=w.workspace_id AND a.admitted
            LEFT JOIN LATERAL (
                SELECT s.id, s.version, s.submitted_at, s.total
                FROM exam_assessment_submission s
                WHERE s.sheet_id=sh.id AND s.workspace_id=w.workspace_id AND s.exam_id=w.exam_id
                    AND s.submitted_at >= w.opened_at AND s.submitted_at < w.closes_at
                ORDER BY s.version DESC LIMIT 1
            ) sub ON TRUE
            WHERE w.workspace_id=:workspace_id AND w.exam_id=:exam_id
            ORDER BY w.attempt_id, a.user_id
        """)
