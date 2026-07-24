"""SQLite-backed decision & equity journal.

Two tables:
  decisions  — one row per (scan, symbol): the signal, the plan, the evidence
               (nn_score, support/resistance), and an outcome filled in later
               when the trade closes or the thesis invalidates.
  equity     — one row per scan: the mark-to-market portfolio value, so a real
               equity curve accumulates over days/weeks.

Everything is append-only except an outcome update on an open decision. The
connection is opened per call (SQLite handles this fine) so the store is safe
to use from the API and a scheduled scan without shared-state surprises.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
JOURNAL_DB = DATA_DIR / "journal.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    scan_id       TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    direction     TEXT NOT NULL,          -- long | short | hold
    signal        TEXT,                   -- raw technical signal
    confidence    REAL,
    entry_price   REAL,
    stop_loss     REAL,
    take_profit   REAL,
    risk_reward   REAL,
    est_hold_days INTEGER,
    nn_score      REAL,
    support       REAL,
    resistance    REAL,
    trend         TEXT,
    thesis        TEXT,
    source        TEXT,                   -- llm | fallback
    status        TEXT NOT NULL DEFAULT 'open',   -- open | closed | expired
    exit_price    REAL,
    exit_ts       TEXT,
    outcome       TEXT,                   -- win | loss | flat | none
    pnl_pct       REAL,
    screen_score  REAL,                   -- composite screen score (0..1)
    screen_rank   INTEGER                 -- rank within the scan's shortlist
);
CREATE TABLE IF NOT EXISTS equity (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    scan_id        TEXT NOT NULL,
    equity         REAL NOT NULL,
    cash           REAL,
    positions_value REAL,
    open_positions INTEGER,
    return_percent REAL
);
CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, path: Path = JOURNAL_DB):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)
            self._migrate(c)

    @staticmethod
    def _migrate(c: sqlite3.Connection) -> None:
        """Add columns introduced after a DB was first created (SQLite has no
        'ADD COLUMN IF NOT EXISTS'), so an existing journal keeps working."""
        have = {r[1] for r in c.execute("PRAGMA table_info(decisions)").fetchall()}
        for col, decl in (("screen_score", "REAL"), ("screen_rank", "INTEGER")):
            if col not in have:
                c.execute(f"ALTER TABLE decisions ADD COLUMN {col} {decl}")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── writes ──
    def record_decision(self, scan_id: str, symbol: str, fields: dict[str, Any]) -> int:
        cols = {
            "ts": _now(), "scan_id": scan_id, "symbol": symbol,
            "direction": fields.get("direction", "hold"),
            "signal": fields.get("signal"),
            "confidence": fields.get("confidence"),
            "entry_price": fields.get("entry_price"),
            "stop_loss": fields.get("stop_loss"),
            "take_profit": fields.get("take_profit"),
            "risk_reward": fields.get("risk_reward"),
            "est_hold_days": fields.get("est_hold_days"),
            "nn_score": fields.get("nn_score"),
            "support": fields.get("support"),
            "resistance": fields.get("resistance"),
            "trend": fields.get("trend"),
            "thesis": fields.get("thesis"),
            "source": fields.get("source"),
            # A hold is not an open trade to track; only directional calls are.
            "status": "open" if fields.get("direction") in ("long", "short") else "closed",
            "outcome": "none" if fields.get("direction") in ("long", "short") else "flat",
            "screen_score": fields.get("screen_score"),
            "screen_rank": fields.get("screen_rank"),
        }
        placeholders = ",".join("?" for _ in cols)
        with self._conn() as c:
            cur = c.execute(
                f"INSERT INTO decisions ({','.join(cols)}) VALUES ({placeholders})",
                list(cols.values()),
            )
            return int(cur.lastrowid)

    def record_equity(self, scan_id: str, snapshot: dict[str, Any]) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO equity (ts, scan_id, equity, cash, positions_value, "
                "open_positions, return_percent) VALUES (?,?,?,?,?,?,?)",
                (
                    _now(), scan_id,
                    snapshot.get("equity"), snapshot.get("cash"),
                    snapshot.get("positions_value"),
                    len(snapshot.get("open_positions", [])),
                    snapshot.get("return_percent"),
                ),
            )

    def close_decision(self, decision_id: int, exit_price: float, outcome: str, pnl_pct: float) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE decisions SET status='closed', exit_price=?, exit_ts=?, "
                "outcome=?, pnl_pct=? WHERE id=?",
                (exit_price, _now(), outcome, round(pnl_pct, 3), decision_id),
            )

    # ── reads ──
    def open_decisions(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM decisions WHERE status='open' ORDER BY ts"
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_decisions(self, limit: int = 50, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM decisions"
        params: list[Any] = []
        if symbol:
            q += " WHERE symbol=?"
            params.append(symbol)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, params).fetchall()]

    def equity_curve(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT ts, equity, return_percent, open_positions FROM equity "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows][::-1]  # oldest first for plotting

    def stats(self) -> dict[str, Any]:
        """Track-record summary: decisions taken, win rate on closed trades."""
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            directional = c.execute(
                "SELECT COUNT(*) FROM decisions WHERE direction IN ('long','short')"
            ).fetchone()[0]
            closed = c.execute(
                "SELECT COUNT(*) FROM decisions WHERE status='closed' AND outcome IN ('win','loss')"
            ).fetchone()[0]
            wins = c.execute(
                "SELECT COUNT(*) FROM decisions WHERE outcome='win'"
            ).fetchone()[0]
            open_ct = c.execute(
                "SELECT COUNT(*) FROM decisions WHERE status='open'"
            ).fetchone()[0]
            scans = c.execute("SELECT COUNT(DISTINCT scan_id) FROM decisions").fetchone()[0]
        return {
            "scans": scans,
            "decisions": total,
            "directional_calls": directional,
            "open": open_ct,
            "closed_resolved": closed,
            "wins": wins,
            "win_rate_pct": round(wins / closed * 100, 1) if closed else None,
        }


_journal: Optional[Journal] = None


def get_journal() -> Journal:
    global _journal
    if _journal is None:
        _journal = Journal()
    return _journal
