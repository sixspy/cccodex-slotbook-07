"""互证与正式册同源唯一定义 —— 路径甲，当日锁死。

契约（2026-11-21 锁定，见 docs/互证同源说明.md）：
- 路径甲：互证只读，已确认正式行与盘面占用同事务派生；不另造缓存。
- 失败则查询零写；写侧检出分裂即记「互证同源偏航」并拒写。
- 两侧不得混用（路径乙未启用）。

「正式行」只认同时满足以下三条的 bookings：
  1. status = '已确认'
  2. 所属档期存在（JOIN slots 命中）
  3. snapshot_gen = slots.generation（快照代未落后）

不满足 1~3 的已确认行一律归为「歧义行」，五处同态暴露，不得静默。
"""
from __future__ import annotations

PATH = "甲"
LOCKED_ON = "2026-11-21"

_FORMAL_FROM = """
FROM bookings b
JOIN slots s ON s.id = b.slot_id
WHERE b.status = '已确认' AND b.snapshot_gen = s.generation
"""

_AMBIGUOUS_FROM = """
FROM bookings b
LEFT JOIN slots s ON s.id = b.slot_id
WHERE b.status = '已确认'
  AND (s.id IS NULL OR b.snapshot_gen <> s.generation)
"""


def begin_read(conn) -> None:
    """只读事务起点：让同一请求内的多次派生共享一个快照，且绝不写库。"""
    if not conn.in_transaction:
        conn.execute("BEGIN")


def formal_bookings(conn, party_key: str | None = None) -> list[dict]:
    sql = (
        "SELECT b.*, s.code AS slot_code, s.generation AS slot_generation "
        + _FORMAL_FROM
    )
    args: tuple = ()
    if party_key is not None:
        sql += " AND b.party_key = ?"
        args = (party_key,)
    sql += " ORDER BY b.id DESC"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def ambiguous_bookings(conn, party_key: str | None = None) -> list[dict]:
    sql = (
        "SELECT b.*, s.code AS slot_code, s.generation AS slot_generation,"
        " CASE WHEN s.id IS NULL THEN '无主档期' ELSE '快照代落后' END AS reason "
        + _AMBIGUOUS_FROM
    )
    args: tuple = ()
    if party_key is not None:
        sql += " AND b.party_key = ?"
        args = (party_key,)
    sql += " ORDER BY b.id DESC"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def formal_seats_by_slot(conn) -> dict[int, int]:
    rows = conn.execute(
        "SELECT b.slot_id AS slot_id, COALESCE(SUM(b.seats),0) AS seats "
        + _FORMAL_FROM
        + " GROUP BY b.slot_id"
    ).fetchall()
    return {int(r["slot_id"]): int(r["seats"]) for r in rows}


def ambiguous_seats_by_slot(conn) -> dict[int, int]:
    rows = conn.execute(
        "SELECT b.slot_id AS slot_id, COALESCE(SUM(b.seats),0) AS seats "
        + _AMBIGUOUS_FROM
        + " GROUP BY b.slot_id"
    ).fetchall()
    return {int(r["slot_id"]): int(r["seats"]) for r in rows}


def same_source(conn) -> dict:
    """只读汇总：正式行、歧义行、无主行数目与同源是否成立。"""
    formal = conn.execute(
        "SELECT COUNT(*) c " + _FORMAL_FROM
    ).fetchone()["c"]
    ambiguous = conn.execute(
        "SELECT COUNT(*) c " + _AMBIGUOUS_FROM
    ).fetchone()["c"]
    orphans = conn.execute(
        """SELECT COUNT(*) c FROM bookings b
           LEFT JOIN slots s ON s.id = b.slot_id
           WHERE b.status = '已确认' AND s.id IS NULL"""
    ).fetchone()["c"]
    return {
        "path": PATH,
        "locked_on": LOCKED_ON,
        "ok": int(ambiguous) == 0,
        "formal_count": int(formal),
        "ambiguous_count": int(ambiguous),
        "orphan_count": int(orphans),
    }


def slot_rollup(conn, slot_id: int, generation: int, booked: int) -> dict:
    """单档五面共用派生：正式席、歧义席、分裂标志。"""
    formal = formal_seats_by_slot(conn).get(int(slot_id), 0)
    amb = ambiguous_seats_by_slot(conn).get(int(slot_id), 0)
    return {
        "formal_seats": formal,
        "ambiguous_seats": amb,
        "split": amb > 0 or int(formal) != int(booked),
    }
