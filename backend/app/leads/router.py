"""SNX-30 routes are mounted under the authenticated application router."""

from datetime import date
from uuid import UUID
from fastapi import APIRouter, Query
from app.auth.router import CurrentStaff
from app.db import Db
from .models import RowEdit, Confirmation, Status
from . import repository as repo, writes

router = APIRouter(tags=["leads"])


@router.get("/leads")
def leads(
    conn: Db,
    status: Status | None = None,
    q: str = Query(default="", max_length=300),
    next_action_date: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
):
    return repo.list_leads(
        conn,
        status=status,
        q=q.strip(),
        next_action=next_action_date.isoformat() if next_action_date else None,
        limit=limit,
        cursor=cursor,
    )


@router.get("/leads/due")
def due(
    conn: Db,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    business_date: date | None = Query(default=None, alias="date"),
):
    """An explicit staff/operator test date never changes the default Manila calendar rule."""
    return repo.list_leads(
        conn,
        mode="due",
        limit=limit,
        cursor=cursor,
        business_date=business_date.isoformat() if business_date else None,
    )


@router.get("/leads/needs-name")
def needs_name(
    conn: Db, limit: int = Query(default=50, ge=1, le=100), cursor: str | None = None
):
    return repo.list_leads(conn, mode="needs-name", limit=limit, cursor=cursor)


@router.get("/pipeline/status")
def pipeline_status(conn: Db):
    return repo.metadata(conn)


@router.get("/leads/{lead_id}")
def lead(lead_id: UUID, conn: Db):
    return repo.detail(conn, lead_id)


@router.get("/leads/{lead_id}/history")
def history(
    lead_id: UUID,
    conn: Db,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
):
    return repo.history(conn, lead_id, limit, cursor)


@router.patch("/clinics/{lead_id}")
def clinic_edit(lead_id: UUID, body: RowEdit, conn: Db, user: CurrentStaff):
    return writes.edit(conn, "clinic", lead_id, body, user.user_id)


@router.patch("/inquiries/{lead_id}")
def inquiry_edit(lead_id: UUID, body: RowEdit, conn: Db, user: CurrentStaff):
    return writes.edit(conn, "inquiry", lead_id, body, user.user_id)


@router.post("/inquiries/{lead_id}/confirm-clinic")
def confirm(lead_id: UUID, body: Confirmation, conn: Db, user: CurrentStaff):
    return writes.confirm(conn, lead_id, body, user.user_id)
