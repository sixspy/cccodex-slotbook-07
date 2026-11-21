"""对账：盘面 booked 与正式册席同源校验（路径甲，只读零写）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from db import connect
from formal_source import (
    ambiguous_seats_by_slot,
    begin_read,
    formal_seats_by_slot,
    same_source,
)

router = APIRouter(tags=["reconcile"])


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        begin_read(conn)
        report = same_source(conn)
        slots = conn.execute("SELECT * FROM slots ORDER BY code").fetchall()
        formal = formal_seats_by_slot(conn)
        ambiguous = ambiguous_seats_by_slot(conn)
        items = []
        for s in slots:
            booked_sum = formal.get(int(s["id"]), 0)
            amb_sum = ambiguous.get(int(s["id"]), 0)
            ok = booked_sum == int(s["booked"]) and amb_sum == 0
            items.append(
                {
                    "slot_code": s["code"],
                    "slot_booked": s["booked"],
                    "booking_seats": booked_sum,
                    "ambiguous_seats": amb_sum,
                    "generation": s["generation"],
                    "ok": ok,
                    "status": s["status"],
                }
            )
        # 无主正式行不属于任何档期，必须并进整盘结论，否则会假绿。
        all_ok = report["ok"] and all(i["ok"] for i in items)
        return {"items": items, "all_ok": all_ok, "same_source": report}


@router.get("/api/reconcile/{code}")
def reconcile_one(code: str, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        begin_read(conn)
        s = conn.execute("SELECT * FROM slots WHERE code=?", (code,)).fetchone()
        if not s:
            raise HTTPException(404, "档期不存在")
        booked_sum = formal_seats_by_slot(conn).get(int(s["id"]), 0)
        amb_sum = ambiguous_seats_by_slot(conn).get(int(s["id"]), 0)
        holds = conn.execute(
            "SELECT COUNT(*) c FROM holds WHERE slot_id=? AND status='占位中'",
            (s["id"],),
        ).fetchone()["c"]
        return {
            "slot_code": code,
            "slot_booked": s["booked"],
            "booking_seats": booked_sum,
            "ambiguous_seats": amb_sum,
            "open_holds": holds,
            "ok": booked_sum == int(s["booked"]) and amb_sum == 0,
            "split": amb_sum > 0 or booked_sum != int(s["booked"]),
            "generation": s["generation"],
        }
