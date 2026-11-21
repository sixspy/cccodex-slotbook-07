"""审计与互证只读面：与正式册同源（路径甲，只读零写）。"""
from __future__ import annotations

from fastapi import APIRouter

from auth import AuthHeader, require_user
from db import connect
from formal_source import (
    ambiguous_bookings,
    begin_read,
    formal_bookings,
    same_source,
)

router = APIRouter(tags=["audit"])


@router.get("/api/audit")
def list_audit(authorization: AuthHeader = None, limit: int = 100):
    require_user(authorization)
    lim = max(1, min(limit, 500))
    with connect() as conn:
        begin_read(conn)
        rows = conn.execute(
            "SELECT * FROM audit_trail ORDER BY id DESC LIMIT ?", (lim,)
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "same_source": same_source(conn),
        }


@router.get("/api/proof/{party_key}")
def proof(party_key: str, authorization: AuthHeader = None):
    """按当事人互证：只读正式行与歧义行，与正式册同源派生，不造缓存。"""
    require_user(authorization)
    with connect() as conn:
        begin_read(conn)
        holds = conn.execute(
            "SELECT * FROM holds WHERE party_key=? ORDER BY id DESC", (party_key,)
        ).fetchall()
        waits = conn.execute(
            "SELECT * FROM waitlist WHERE party_key=? ORDER BY id DESC", (party_key,)
        ).fetchall()
        bookings = formal_bookings(conn, party_key)
        ambiguous = ambiguous_bookings(conn, party_key)
        report = same_source(conn)
        return {
            "party_key": party_key,
            "holds": [dict(r) for r in holds],
            "bookings": bookings,
            "ambiguous": ambiguous,
            "waitlist": [dict(r) for r in waits],
            "split": not report["ok"],
            "same_source": report,
        }
