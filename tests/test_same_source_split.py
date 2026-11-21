"""互证同源红测：先用假绿夹具见红，再修审计/对账/确认/档期四服务。

路径甲：互证只读，与正式册同源派生，不造缓存、查询零写。
本文件所有夹具都落在本机 SQLite 文件库（tmp_path 下的真实文件）。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import app  # noqa: E402
from db import init_db  # noqa: E402
import db as dbmod  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def file_db(tmp_path, monkeypatch):
    """本机文件库：真实 SQLite 文件，不换产品库路径，不碰 data/app.db。"""
    path = tmp_path / "slotbook_local.db"
    monkeypatch.setattr(dbmod, "DB_PATH", path)
    init_db()
    return path


def _login(c: TestClient, user: str = "admin") -> dict:
    r = c.post("/api/login", json={"username": user, "password": "123456"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _apply_booking_fixture(db_path: Path, name: str, *, fk_off: bool = False) -> None:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    conn = sqlite3.connect(db_path)
    try:
        if fk_off:
            conn.execute("PRAGMA foreign_keys=OFF")
        for b in data.get("bookings", []):
            conn.execute(
                """INSERT INTO bookings(slot_id,hold_id,party_key,seats,snapshot_gen,status,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    b["slot_id"],
                    b.get("hold_id"),
                    b["party_key"],
                    b["seats"],
                    b["snapshot_gen"],
                    b["status"],
                    b["created_at"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _insert_stale_generation_booking(db_path: Path, *, party_key: str, seats: int = 2) -> None:
    """在 S-PM-02 上造一条已确认但快照代落后的歧义正式行，并同步盘面占用。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        slot = conn.execute("SELECT * FROM slots WHERE code='S-PM-02'").fetchone()
        assert slot is not None
        conn.execute(
            """INSERT INTO bookings(slot_id,hold_id,party_key,seats,snapshot_gen,status,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                slot["id"],
                None,
                party_key,
                seats,
                int(slot["generation"]) - 1,
                "已确认",
                "2026-11-21T09:10:00",
            ),
        )
        conn.execute(
            "UPDATE slots SET booked = booked + ? WHERE id=?", (seats, slot["id"])
        )
        conn.commit()
    finally:
        conn.close()


def _counts(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("slots", "holds", "bookings", "waitlist", "audit_trail", "contention_log")
        }
    finally:
        conn.close()


def _bookings(c: TestClient, h: dict) -> list:
    return c.get("/api/bookings", headers=h).json()["items"]


def _hold_id(c: TestClient, h: dict, party_key: str) -> int:
    rows = c.get("/api/holds", headers=h).json()["items"]
    return [r for r in rows if r["party_key"] == party_key][-1]["id"]


# ---------------------------------------------------------------------------
# 红测一：互证有行、正式册无行，对账不得假绿
# ---------------------------------------------------------------------------
def test_fake_green_orphan_must_not_be_green(file_db):
    _apply_booking_fixture(file_db, "fake_green_orphan.json", fk_off=True)

    with TestClient(app) as c:
        h = _login(c)

        # 互证页不得把无主行拼成正式席
        proof = c.get("/api/proof/P-GHOST", headers=h).json()
        assert proof["bookings"] == [], "互证把无主行当正式席 = 假绿"
        amb = [x for x in proof.get("ambiguous", []) if x["party_key"] == "P-GHOST"]
        assert len(amb) == 1, "无主行必须作为歧义行暴露，不得静默吞掉"
        assert proof.get("split") is True

        # 正式册确实查无
        formal = _bookings(c, h)
        assert all(b["party_key"] != "P-GHOST" for b in formal)

        # 对账不得仍打勾
        recon = c.get("/api/reconcile", headers=h).json()
        assert recon["all_ok"] is False, "存在无主正式行时对账仍打勾 = 假绿"

        # 档期盘与审计同态
        dash = c.get("/api/dashboard", headers=h).json()
        assert dash.get("same_source_ok") is False
        assert dash.get("orphan_bookings") == 1
        audit = c.get("/api/audit", headers=h).json()
        assert audit["same_source"]["ok"] is False

        # 只读面零写
        before = _counts(file_db)
        c.get("/api/proof/P-GHOST", headers=h)
        c.get("/api/reconcile", headers=h)
        c.get("/api/slots", headers=h)
        c.get("/api/audit", headers=h)
        assert _counts(file_db) == before, "互证/对账只读失败时不得写库"


# ---------------------------------------------------------------------------
# 红测二：快照代落后的歧义正式行，五面同态
# ---------------------------------------------------------------------------
def test_stale_generation_split_visible_everywhere(file_db):
    _insert_stale_generation_booking(file_db, party_key="P-STALE", seats=2)

    with TestClient(app) as c:
        h = _login(c)

        formal = _bookings(c, h)
        assert all(b["party_key"] != "P-STALE" for b in formal), "歧义正式行不得进正式册"

        proof = c.get("/api/proof/P-STALE", headers=h).json()
        assert proof["bookings"] == []
        assert [x["party_key"] for x in proof.get("ambiguous", [])] == ["P-STALE"]

        item = c.get("/api/reconcile/S-PM-02", headers=h).json()
        assert item["ok"] is False
        assert item["ambiguous_seats"] == 2
        assert item["booking_seats"] == 0
        assert item["slot_booked"] == 2

        slot = c.get("/api/slots/S-PM-02", headers=h).json()
        assert slot["formal_seats"] == 0
        assert slot["ambiguous_seats"] == 2
        assert slot["split"] is True

        assert c.get("/api/reconcile", headers=h).json()["all_ok"] is False
        assert c.get("/api/dashboard", headers=h).json()["same_source_ok"] is False


# ---------------------------------------------------------------------------
# 红测三：偏航必须记“互证同源偏航”并拒写，正式册零改
# ---------------------------------------------------------------------------
def test_deviation_refuses_write_and_records_drift(file_db):
    _apply_booking_fixture(file_db, "fake_green_orphan.json", fk_off=True)

    with TestClient(app) as c:
        h = _login(c, "clerk")
        r = c.post(
            "/api/holds",
            headers=h,
            json={"slot_code": "S-AM-01", "party_key": "P-DRIFT", "seats": 1},
        )
        assert r.status_code == 200, r.text
        hid = r.json()["hold_id"]

        slot_before = c.get("/api/slots/S-AM-01", headers=h).json()
        r2 = c.post("/api/bookings/confirm", headers=h, json={"hold_id": hid})
        assert r2.status_code == 409, "存在互证分裂时必须拒写"
        assert "互证同源偏航" in r2.json()["detail"]

        assert all(b["party_key"] != "P-DRIFT" for b in _bookings(c, h))
        hold = [x for x in c.get("/api/holds", headers=h).json()["items"] if x["id"] == hid][0]
        assert hold["status"] == "占位中"
        slot_after = c.get("/api/slots/S-AM-01", headers=h).json()
        assert slot_after["booked"] == slot_before["booked"]

        audits = c.get("/api/audit", headers=h).json()["items"]
        drift = [a for a in audits if a["action"] == "互证同源偏航" and a["actor"] == "clerk"]
        assert drift, "偏航必须落审计，不是只改文案"


# ---------------------------------------------------------------------------
# 红测四：两人同修同一当事人，抢档锁；后到只留争用痕
# ---------------------------------------------------------------------------
def test_two_writers_same_party_contention_trace_only(file_db):
    with TestClient(app) as c:
        admin = _login(c, "admin")
        clerk = _login(c, "clerk")

        r = c.post(
            "/api/holds",
            headers=admin,
            json={"slot_code": "S-AM-01", "party_key": "P-RACE", "seats": 1},
        )
        assert r.status_code == 200, r.text
        hid = r.json()["hold_id"]

        # 甲已在修（模拟在飞事务持有档锁）
        lk = c.post("/api/locks/acquire", headers=admin, json={"lock_key": "slot:S-AM-01"})
        assert lk.status_code == 200, lk.text

        slot_before = c.get("/api/slots/S-AM-01", headers=admin).json()
        # 乙后到，只能撞锁
        r2 = c.post("/api/bookings/confirm", headers=clerk, json={"hold_id": hid})
        assert r2.status_code == 409

        # 后到只留争用痕
        cont = c.get("/api/contention", headers=admin).json()["items"]
        mine = [
            x
            for x in cont
            if x["lock_key"] == "slot:S-AM-01" and x["actor"] == "clerk" and x["action"] == "争用"
        ]
        assert len(mine) == 1, "后到者必须留下争用痕，不能被回滚吃掉"

        # 业务零写
        assert all(b["party_key"] != "P-RACE" for b in _bookings(c, admin))
        hold = [x for x in c.get("/api/holds", headers=admin).json()["items"] if x["id"] == hid][0]
        assert hold["status"] == "占位中"
        slot_after = c.get("/api/slots/S-AM-01", headers=admin).json()
        assert slot_after["booked"] == slot_before["booked"]


# ---------------------------------------------------------------------------
# 红测五：修完人数对得上，五面同态
# ---------------------------------------------------------------------------
def test_five_surfaces_headcount_match(file_db):
    with TestClient(app) as c:
        h = _login(c)
        for party in ("P-A", "P-B"):
            r = c.post(
                "/api/holds",
                headers=h,
                json={"slot_code": "S-PM-02", "party_key": party, "seats": 1},
            )
            assert r.status_code == 200, r.text
            hid = r.json()["hold_id"]
            assert c.post("/api/bookings/confirm", headers=h, json={"hold_id": hid}).status_code == 200

        books = _bookings(c, h)
        dash = c.get("/api/dashboard", headers=h).json()
        assert dash["bookings"] == len(books)
        assert dash["same_source_ok"] is True
        assert dash["orphan_bookings"] == 0

        for party in ("P-A", "P-B"):
            proof = c.get(f"/api/proof/{party}", headers=h).json()
            listed = [b for b in books if b["party_key"] == party]
            assert len(proof["bookings"]) == len(listed) == 1
            assert proof["split"] is False

        assert c.get("/api/reconcile", headers=h).json()["all_ok"] is True
        for item in c.get("/api/reconcile", headers=h).json()["items"]:
            seat_sum = sum(b["seats"] for b in books if b["slot_code"] == item["slot_code"])
            assert item["booking_seats"] == seat_sum


# ---------------------------------------------------------------------------
# 锁死：同源契约必须被五面共用，且说明当日锁定
# ---------------------------------------------------------------------------
def test_same_source_contract_is_locked():
    import formal_source
    import audit_svc
    import confirm_svc
    import reconcile_svc
    import slots_svc

    assert formal_source.PATH == "甲"
    assert formal_source.LOCKED_ON == "2026-11-21"
    for mod in (audit_svc, reconcile_svc, confirm_svc, slots_svc):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "formal_source" in src, f"{mod.__name__} 未接同源唯一定义"

    doc = ROOT / "docs" / "互证同源说明.md"
    assert doc.is_file(), "必须落互证同源说明"
    text = doc.read_text(encoding="utf-8")
    for key in ("路径甲", "当日锁定", "互证同源偏航", "五处同态"):
        assert key in text
