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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
JOURNAL_DB = DATA_DIR / "journal.db"

# The agent trades the Indian session; a "day" on the dashboard means an IST day,
# so a pre-open and a post-close scan land on the same calendar date a user sees.
IST = timezone(timedelta(hours=5, minutes=30))

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
    screen_rank   INTEGER,                -- rank within the scan's shortlist
    features      TEXT,                   -- JSON feature vector at entry (for learning)
    exit_reason   TEXT                    -- stop | target | expiry (how it closed)
);
CREATE TABLE IF NOT EXISTS equity (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    scan_id        TEXT NOT NULL,
    equity         REAL NOT NULL,
    cash           REAL,
    positions_value REAL,
    open_positions INTEGER,
    return_percent REAL,
    benchmark      REAL                   -- fair equal-weight buy-and-hold equity
);
CREATE TABLE IF NOT EXISTS learning (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                 TEXT NOT NULL,
    trained            INTEGER NOT NULL,       -- 1 = model updated, 0 = skipped
    experience_samples INTEGER,                -- the agent's own closed trades used
    bootstrap_samples  INTEGER,                -- backtest trades blended in
    total              INTEGER,
    oos_auc            REAL,                   -- out-of-sample AUC of the new gate
    note               TEXT                    -- human-readable reason / summary
);
CREATE TABLE IF NOT EXISTS insights (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                    TEXT NOT NULL,
    long_trades           INTEGER, long_win_rate  REAL, long_net_pct  REAL,
    short_trades          INTEGER, short_win_rate REAL, short_net_pct REAL,
    nn_hi_win_rate        REAL,    nn_lo_win_rate REAL,      -- gate discrimination
    agent_return_pct      REAL, benchmark_return_pct REAL, spread_pct REAL,
    headline              TEXT,                        -- one-line derived insight
    suggestion            TEXT                         -- the action the data argues for
);
CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# The honest track record is built from the JOURNAL's realized P&L (which persists
# across cloud runs), NOT the paper broker's in-memory book (gitignored, resets
# every run). We model each closed trade as deploying a fixed fraction of the
# starting capital — a transparent, reproducible sizing assumption — so the equity
# line reflects real trade outcomes instead of a broker that keeps resetting to 100k.
POSITION_FRACTION = 0.10


def _starting_cash() -> float:
    """Paper account's starting capital (config-driven, state-independent)."""
    try:
        from app.config import get_config
        trading = get_config("trading")["mode"]
        mode = trading.get("current", "paper")
        block = trading.get(mode, {})
        if isinstance(block, dict) and block.get("initial_balance"):
            return float(block["initial_balance"])
    except Exception:
        pass
    return 100_000.0


def _ist_date(ts: Optional[str]) -> Optional[str]:
    """The IST calendar date of a stored UTC timestamp (YYYY-MM-DD), or None."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).date().isoformat()
    except ValueError:
        return None


def today_ist() -> str:
    return datetime.now(IST).date().isoformat()


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
        for col, decl in (("screen_score", "REAL"), ("screen_rank", "INTEGER"),
                          ("features", "TEXT"), ("exit_reason", "TEXT")):
            if col not in have:
                c.execute(f"ALTER TABLE decisions ADD COLUMN {col} {decl}")
        eq_have = {r[1] for r in c.execute("PRAGMA table_info(equity)").fetchall()}
        if "benchmark" not in eq_have:
            c.execute("ALTER TABLE equity ADD COLUMN benchmark REAL")

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
            "features": fields.get("features"),
        }
        placeholders = ",".join("?" for _ in cols)
        with self._conn() as c:
            cur = c.execute(
                f"INSERT INTO decisions ({','.join(cols)}) VALUES ({placeholders})",
                list(cols.values()),
            )
            return int(cur.lastrowid)

    def record_equity(self, scan_id: str, snapshot: dict[str, Any],
                      benchmark: Optional[float] = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO equity (ts, scan_id, equity, cash, positions_value, "
                "open_positions, return_percent, benchmark) VALUES (?,?,?,?,?,?,?,?)",
                (
                    _now(), scan_id,
                    snapshot.get("equity"), snapshot.get("cash"),
                    snapshot.get("positions_value"),
                    len(snapshot.get("open_positions", [])),
                    snapshot.get("return_percent"), benchmark,
                ),
            )

    def close_decision(self, decision_id: int, exit_price: float, outcome: str,
                       pnl_pct: float, exit_reason: Optional[str] = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE decisions SET status='closed', exit_price=?, exit_ts=?, "
                "outcome=?, pnl_pct=?, exit_reason=? WHERE id=?",
                (exit_price, _now(), outcome, round(pnl_pct, 3), exit_reason, decision_id),
            )

    def record_learning(self, summary: dict[str, Any]) -> None:
        """Log one retrain of the validator — the agent's memory of *learning*.

        Called by the learning loop so the dashboard can answer "what did it
        learn, and when" instead of the model silently changing under the hood.
        """
        note = summary.get("reason") or (
            f"retrained on {summary.get('experience_samples', 0)} lived "
            f"+ {summary.get('bootstrap_samples', 0)} bootstrap trades"
            if summary.get("trained") else "skipped — not enough data yet"
        )
        with self._conn() as c:
            c.execute(
                "INSERT INTO learning (ts, trained, experience_samples, "
                "bootstrap_samples, total, oos_auc, note) VALUES (?,?,?,?,?,?,?)",
                (
                    _now(), 1 if summary.get("trained") else 0,
                    summary.get("experience_samples"), summary.get("bootstrap_samples"),
                    summary.get("total"), summary.get("oos_auc"), note,
                ),
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

    def learning_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Most-recent retrains, newest first — the agent's learning history."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM learning ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def record_insight(self, ins: dict[str, Any]) -> None:
        """Persist a snapshot of the agent's derived edge, so conclusions (not just
        raw decisions) accumulate and can be tracked over time."""
        d, nn, o = ins.get("by_direction", {}), ins.get("nn_gate", {}), ins.get("overall", {})
        lg, sh = d.get("long", {}), d.get("short", {})
        with self._conn() as c:
            c.execute(
                "INSERT INTO insights (ts, long_trades, long_win_rate, long_net_pct, "
                "short_trades, short_win_rate, short_net_pct, nn_hi_win_rate, nn_lo_win_rate, "
                "agent_return_pct, benchmark_return_pct, spread_pct, headline, suggestion) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    _now(), lg.get("trades"), lg.get("win_rate"), lg.get("net_pct"),
                    sh.get("trades"), sh.get("win_rate"), sh.get("net_pct"),
                    (nn.get("hi") or {}).get("win_rate"), (nn.get("lo") or {}).get("win_rate"),
                    o.get("agent_return"), o.get("benchmark_return"), o.get("spread_pct"),
                    ins.get("headline"), ins.get("suggestion"),
                ),
            )

    def insights_history(self, limit: int = 30) -> list[dict[str, Any]]:
        """Stored insight snapshots, oldest-first — for trending the agent's edge."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM insights ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows][::-1]

    def open_positions_detail(self, limit: int = 20) -> list[dict[str, Any]]:
        """Open directional calls with the plan + thesis, so a summary can say
        plainly what the agent is holding and why."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT symbol, direction, entry_price, stop_loss, take_profit, "
                "nn_score, thesis, source, ts FROM decisions WHERE status='open' "
                "AND direction IN ('long','short') ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def today_summary(self) -> dict[str, Any]:
        """What happened *today* (IST): scans run, trades opened, trades closed
        and their win/loss, and the day's realised P&L on the paper book."""
        today = today_ist()
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT scan_id, direction, ts, exit_ts, outcome, pnl_pct "
                "FROM decisions"
            ).fetchall()]
        opened = [r for r in rows if _ist_date(r["ts"]) == today]
        closed = [r for r in rows if _ist_date(r["exit_ts"]) == today
                  and r["outcome"] in ("win", "loss")]
        longs = sum(1 for r in opened if r["direction"] == "long")
        shorts = sum(1 for r in opened if r["direction"] == "short")
        wins = sum(1 for r in closed if r["outcome"] == "win")
        losses = sum(1 for r in closed if r["outcome"] == "loss")
        pnl = sum(float(r["pnl_pct"] or 0.0) for r in closed)
        return {
            "date": today,
            "scans": len({r["scan_id"] for r in opened}),
            "opened": longs + shorts,
            "longs": longs,
            "shorts": shorts,
            "closed": len(closed),
            "wins": wins,
            "losses": losses,
            "realized_pnl_pct": round(pnl, 2) if closed else None,
        }

    def training_rows(self) -> list[dict[str, Any]]:
        """Closed directional trades with a stored feature vector and a win/loss
        outcome — the agent's own experience, ready to learn from."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT features, outcome, pnl_pct, ts FROM decisions "
                "WHERE status='closed' AND direction IN ('long','short') "
                "AND features IS NOT NULL AND outcome IN ('win','loss') ORDER BY ts"
            ).fetchall()
            return [dict(r) for r in rows]

    def realized_pnl_series(self) -> list[tuple[str, float]]:
        """(exit_ts, pnl_pct) for every closed directional trade, oldest first —
        the persisted, honest record of how the agent's trades actually turned out."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT exit_ts, pnl_pct FROM decisions WHERE status='closed' "
                "AND direction IN ('long','short') AND pnl_pct IS NOT NULL "
                "AND exit_ts IS NOT NULL ORDER BY exit_ts"
            ).fetchall()
        return [(r["exit_ts"], float(r["pnl_pct"])) for r in rows]

    def equity_curve(self, limit: int = 500,
                     starting_cash: Optional[float] = None,
                     fraction: float = POSITION_FRACTION) -> list[dict[str, Any]]:
        """The agent's equity over time, derived from realized journal P&L.

        The equity table gives the time axis and the (persisted) buy-and-hold
        benchmark; the agent line is the starting capital plus the cumulative
        rupee P&L of every trade closed by each snapshot, sized at `fraction` of
        starting capital per trade. This is the honest, cloud-persistent curve —
        it no longer depends on the paper broker, which resets each run.
        """
        start = starting_cash if starting_cash is not None else _starting_cash()
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT ts, open_positions, benchmark FROM equity "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()][::-1]  # oldest first for plotting
        realized = self.realized_pnl_series()
        out = []
        for row in rows:
            ts = row["ts"]
            pnl = sum(start * fraction * (p / 100.0) for ets, p in realized if ets <= ts)
            eq = round(start + pnl, 2)
            out.append({
                "ts": ts, "equity": eq,
                "return_percent": round((eq / start - 1) * 100, 3) if start else None,
                "open_positions": row.get("open_positions"),
                "benchmark": row.get("benchmark"),
            })
        return out

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
