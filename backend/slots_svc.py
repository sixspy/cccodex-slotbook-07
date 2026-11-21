"""档期盘：开档、关档、容量查询。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth import AuthHeader, require_user, require_writer
from db import connect, write_audit
from formal_source import (
    ambiguous_seats_by_slot,
    begin_read,
    formal_seats_by_slot,
    same_source,
)
from locks import release, require_lock

router = APIRouter(tags=["slots"])


class SlotIn(BaseModel):
    code: str
    title: str
    start_at: str
    end_at: str
    capacity: int = Field(ge=1, le=500)


class CloseIn(BaseModel):
    code: str


def _slot_view(row, formal: dict, ambiguous: dict) -> dict:
    item = dict(row)
    f = formal.get(int(row["id"]), 0)
    a = ambiguous.get(int(row["id"]), 0)
    item["formal_seats"] = f
    item["ambiguous_seats"] = a
    item["split"] = a > 0 or f != int(row["booked"])
    return item


@router.get("/api/slots")
def list_slots(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        begin_read(conn)
        rows = conn.execute(
            "SELECT * FROM slots ORDER BY start_at, code"
        ).fetchall()
        formal = formal_seats_by_slot(conn)
        ambiguous = ambiguous_seats_by_slot(conn)
        return {
            "items": [_slot_view(r, formal, ambiguous) for r in rows],
            "same_source": same_source(conn),
        }


@router.get("/api/slots/{code}")
def get_slot(code: str, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        begin_read(conn)
        row = conn.execute("SELECT * FROM slots WHERE code=?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, "档期不存在")
        return _slot_view(
            row, formal_seats_by_slot(conn), ambiguous_seats_by_slot(conn)
        )


@router.post("/api/slots")
def create_slot(body: SlotIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, f"slot:{body.code}", user)
        try:
            exists = conn.execute(
                "SELECT id FROM slots WHERE code=?", (body.code,)
            ).fetchone()
            if exists:
                raise HTTPException(409, "档期编码已存在")
            if body.end_at <= body.start_at:
                raise HTTPException(400, "结束时间必须晚于开始")
            conn.execute(
                """INSERT INTO slots(code,title,start_at,end_at,capacity,booked,status,generation)
                   VALUES (?,?,?,?,?,0,'开放',1)""",
                (body.code, body.title, body.start_at, body.end_at, body.capacity),
            )
            write_audit(conn, user, "slot_create", body.code, body.model_dump())
            conn.commit()
        finally:
            release(conn, f"slot:{body.code}", user)
            conn.commit()
    return {"ok": True, "code": body.code}


@router.post("/api/slots/close")
def close_slot(body: CloseIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, f"slot:{body.code}", user)
        try:
            row = conn.execute(
                "SELECT * FROM slots WHERE code=?", (body.code,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "档期不存在")
            if row["status"] == "关闭":
                raise HTTPException(409, "档期已关闭")
            open_holds = conn.execute(
                "SELECT COUNT(*) c FROM holds WHERE slot_id=? AND status='占位中'",
                (row["id"],),
            ).fetchone()["c"]
            if open_holds:
                raise HTTPException(409, "仍有未确认占位，禁止关档")
            conn.execute(
                "UPDATE slots SET status='关闭' WHERE id=?", (row["id"],)
            )
            write_audit(conn, user, "slot_close", body.code, {"generation": row["generation"]})
            conn.commit()
        finally:
            release(conn, f"slot:{body.code}", user)
            conn.commit()
    return {"ok": True}


@router.get("/api/dashboard")
def dashboard(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        begin_read(conn)
        report = same_source(conn)
        return {
            "slots_open": conn.execute(
                "SELECT COUNT(*) c FROM slots WHERE status='开放'"
            ).fetchone()["c"],
            "holds_open": conn.execute(
                "SELECT COUNT(*) c FROM holds WHERE status='占位中'"
            ).fetchone()["c"],
            "bookings": report["formal_count"],
            "ambiguous_bookings": report["ambiguous_count"],
            "orphan_bookings": report["orphan_count"],
            "same_source_ok": report["ok"],
            "waitlist": conn.execute(
                "SELECT COUNT(*) c FROM waitlist WHERE status='候补中'"
            ).fetchone()["c"],
            "now": datetime.now().isoformat(timespec="seconds"),
        }
