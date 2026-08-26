"""Durable SQLite ledger and projections for the autonomous runtime."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from src.risk.portfolio import PortfolioSnapshot

from .events import EVENT_TYPES, LEGACY_EVENT_TYPES, RuntimeEvent, payload_digest

REQUIRED = ("cycle_id", "trace_id", "created_ms", "mode", "product_type", "symbol", "payload_hash", "schema_version")
TABLES = ("cycles", "events", "orders", "fills", "positions", "protection", "reconciliation", "runtime_state", "portfolio_snapshots")


def _now() -> int:
    return int(time.time() * 1000)


class EventLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10.0)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _init(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_ms INTEGER NOT NULL,
                  cycle_id TEXT NOT NULL DEFAULT '', trace_id TEXT NOT NULL DEFAULT '', created_ms INTEGER NOT NULL DEFAULT 0,
                  mode TEXT NOT NULL DEFAULT 'system', product_type TEXT NOT NULL DEFAULT 'system', symbol TEXT NOT NULL DEFAULT '',
                  payload_hash TEXT NOT NULL DEFAULT '', schema_version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS cycles (cycle_id TEXT PRIMARY KEY, terminal_status TEXT, created_ms INTEGER NOT NULL,
                  trace_id TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL DEFAULT 'paper', product_type TEXT NOT NULL DEFAULT 'SUSDT-FUTURES', symbol TEXT NOT NULL DEFAULT '', payload_hash TEXT NOT NULL DEFAULT '', schema_version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, event_json TEXT NOT NULL, created_ms INTEGER NOT NULL,
                  cycle_id TEXT NOT NULL DEFAULT '', trace_id TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL DEFAULT 'paper', product_type TEXT NOT NULL DEFAULT 'SUSDT-FUTURES', symbol TEXT NOT NULL DEFAULT '', payload_hash TEXT NOT NULL DEFAULT '', schema_version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, client_order_id TEXT NOT NULL UNIQUE, venue_order_id TEXT UNIQUE, event_json TEXT NOT NULL,
                  cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY AUTOINCREMENT, fill_id TEXT NOT NULL UNIQUE, client_order_id TEXT, event_json TEXT NOT NULL,
                  cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS positions (id INTEGER PRIMARY KEY AUTOINCREMENT, position_id TEXT NOT NULL UNIQUE, event_json TEXT NOT NULL,
                  cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS protection (id INTEGER PRIMARY KEY AUTOINCREMENT, event_json TEXT NOT NULL, cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS reconciliation (id INTEGER PRIMARY KEY AUTOINCREMENT, event_json TEXT NOT NULL, cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_json TEXT NOT NULL, created_ms INTEGER NOT NULL, cycle_id TEXT NOT NULL DEFAULT '', trace_id TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL DEFAULT 'paper', product_type TEXT NOT NULL DEFAULT 'SUSDT-FUTURES', symbol TEXT NOT NULL DEFAULT '', payload_hash TEXT NOT NULL DEFAULT '', schema_version INTEGER NOT NULL DEFAULT 1);
            """)
            for table in TABLES:
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for column in REQUIRED:
                    if column not in columns:
                        default = "1" if column == "schema_version" else ("0" if column == "created_ms" else "''")
                        typ = "INTEGER" if column in ("created_ms", "schema_version") else "TEXT"
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typ} NOT NULL DEFAULT {default}")
            if db.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone() is None:
                db.execute("INSERT INTO schema_migrations(version, applied_ms) VALUES(1, ?)", (_now(),))

    @staticmethod
    def _event(value: RuntimeEvent | Mapping[str, Any]) -> RuntimeEvent:
        return value if isinstance(value, RuntimeEvent) else RuntimeEvent.from_dict(value)

    @staticmethod
    def _canonical_value(value: RuntimeEvent | Mapping[str, Any]) -> RuntimeEvent:
        """Parse a runtime event without manufacturing identity metadata."""
        if isinstance(value, RuntimeEvent):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("invalid event")
        missing = [field for field in ("cycle_id", "trace_id", "mode", "product_type", "symbol")
                   if not isinstance(value.get(field), str) or not value[field]]
        if "created_ms" not in value and "timestamp" not in value:
            missing.append("timestamp")
        if missing:
            raise ValueError("missing " + ", ".join(missing))
        normalized = dict(value)
        if "created_ms" not in normalized:
            normalized["created_ms"] = normalized.pop("timestamp")
        return RuntimeEvent.from_dict(normalized)

    def claim_cycle(self, cycle_id: str, *, trace_id: str = "", mode: str = "paper", product_type: str = "SUSDT-FUTURES", symbol: str = "") -> bool:
        if not cycle_id:
            raise ValueError("missing cycle_id")
        with self._connect() as db:
            cur = db.execute("INSERT OR IGNORE INTO cycles(cycle_id,terminal_status,created_ms,trace_id,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?)", (cycle_id, None, _now(), trace_id, mode, product_type, symbol, "", 1))
            return cur.rowcount == 1

    def set_terminal(self, cycle_id: str, status: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE cycles SET terminal_status=? WHERE cycle_id=?", (status, cycle_id))

    def cycle_status(self, cycle_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT terminal_status FROM cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
            return row[0] if row else None

    def append_legacy(self, event_type: str, payload: dict) -> int:
        """Explicit compatibility adapter for historical, identity-light fixtures."""
        if event_type not in EVENT_TYPES | LEGACY_EVENT_TYPES:
            raise ValueError("unknown event type")
        if not isinstance(payload, dict):
            raise ValueError("invalid event")
        cycle_id = str(payload.get("cycle_id") or f"legacy-{uuid.uuid4().hex}")
        value = {"event_type": event_type, "cycle_id": cycle_id, "trace_id": str(payload.get("trace_id") or f"trace-{cycle_id}"),
                 "created_ms": _now(), "mode": str(payload.get("mode") or "paper"),
                 "product_type": str(payload.get("product_type") or "SUSDT-FUTURES"),
                 "symbol": str(payload.get("symbol") or "UNKNOWN"), "payload_hash": payload_digest(payload), "payload": payload}
        return self.append_event(value)

    def append(self, event_type: str, payload: dict) -> int:
        """Backward-compatible spelling for the explicit legacy adapter."""
        return self.append_legacy(event_type, payload)

    def _insert_event(self, db: sqlite3.Connection, event: RuntimeEvent) -> int:
        d = event.to_dict()
        cur = db.execute("INSERT INTO events(event_type,event_json,created_ms,cycle_id,trace_id,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (event.event_type, json.dumps(d, sort_keys=True), event.created_ms, event.cycle_id, event.trace_id, event.mode, event.product_type, event.symbol, event.payload_hash, event.schema_version))
        return int(cur.lastrowid)

    def append_event(self, value: RuntimeEvent | Mapping[str, Any]) -> int:
        event = self._canonical_value(value)
        with self._connect() as db:
            return self._insert_event(db, event)

    def append_event_with_projection(self, value, table: str, projection: Mapping[str, Any], fault_injector=None) -> int:
        if table not in {"orders", "fills", "positions", "protection", "reconciliation"}:
            raise ValueError("invalid projection table")
        event = self._canonical_value(value)
        with self._connect() as db:
            try:
                event_id = self._insert_event(db, event)
                if fault_injector:
                    fault_injector()
                self._insert_projection(db, table, event, projection)
                return event_id
            except Exception:
                db.rollback()
                raise

    def _insert_projection(self, db, table, event, payload):
        p = dict(payload)
        common = (json.dumps(p, sort_keys=True), event.cycle_id, event.trace_id, event.created_ms, event.mode, event.product_type, event.symbol, event.payload_hash, event.schema_version)
        if table == "orders":
            db.execute("INSERT INTO orders(client_order_id,venue_order_id,event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (p["client_order_id"], p.get("venue_order_id"), *common))
        elif table == "fills":
            db.execute("INSERT INTO fills(fill_id,client_order_id,event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (p["fill_id"], p.get("client_order_id"), *common))
        elif table == "positions":
            db.execute("INSERT INTO positions(position_id,event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?)", (p["position_id"], *common))
        else:
            db.execute(f"INSERT INTO {table}(event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?)", common)

    def _record(self, table, value):
        event = self._event(value)
        p = dict(event.payload)
        with self._connect() as db:
            self._insert_projection(db, table, event, p)
            return int(db.execute("SELECT last_insert_rowid()").fetchone()[0])

    record_order = lambda self, value: self._record("orders", value)
    record_fill = lambda self, value: self._record("fills", value)
    record_position = lambda self, value: self._record("positions", value)
    record_protection = lambda self, value: self._record("protection", value)
    record_reconciliation = lambda self, value: self._record("reconciliation", value)

    def all(self):
        return self.recent_events(limit=None)

    def recent_events(self, limit=50):
        with self._connect() as db:
            sql = "SELECT id,event_type,event_json,created_ms,cycle_id,trace_id,mode,product_type,symbol,payload_hash,schema_version FROM events ORDER BY id DESC"
            rows = db.execute(sql + (" LIMIT ?" if limit is not None else ""), (limit,) if limit is not None else ()).fetchall()
        result = []
        for row in reversed(rows):
            data = json.loads(row[2]); payload = data.pop("payload", data)
            result.append({"id": row[0], "event_type": row[1], "payload": payload, "created_ms": row[3], "cycle_id": row[4], "trace_id": row[5], "mode": row[6], "product_type": row[7], "symbol": row[8], "payload_hash": row[9], "schema_version": row[10], **data})
        return result

    def _rows(self, table):
        with self._connect() as db:
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
            rows = db.execute(f"SELECT {','.join(cols)} FROM {table} ORDER BY id" if "id" in cols else f"SELECT {','.join(cols)} FROM {table}").fetchall()
        return [dict(zip(cols, row)) for row in rows]

    def table_rows(self, table): return self._rows(table)
    def latest_cycle(self):
        rows = self._rows("cycles"); return rows[-1] if rows else None
    def disposition_counts(self):
        counts = {}
        for e in self.all():
            value = e["payload"].get("disposition")
            if value: counts[value] = counts.get(value, 0) + 1
        return counts
    def open_positions(self):
        result = []
        for row in self._rows("positions"):
            payload = json.loads(row.pop("event_json"))
            if payload.get("status") == "OPEN": result.append(row | payload)
        return result
    def _latest(self, table):
        rows = self._rows(table)
        if not rows: return None
        row = rows[-1]; return row | json.loads(row.pop("event_json"))
    def closed_trades(self): return [r | json.loads(r.pop("event_json")) for r in self._rows("positions") if json.loads(r["event_json"]).get("status") == "CLOSED"]
    def realized_pnl(self):
        values = [float(json.loads(r["event_json"]).get("realized_pnl", 0)) for r in self._rows("fills")]
        if not values:
            values = [float(e["payload"].get("net_pnl", 0)) for e in self.all() if e["event_type"] == "TRADE_CLOSED"]
        return sum(values)
    def fees(self):
        values = [float(json.loads(r["event_json"]).get("fee", 0)) for r in self._rows("fills")]
        if not values:
            values = [float(e["payload"].get("fee", 0)) for e in self.all() if e["event_type"] == "FILL_OBSERVED"]
        return sum(values)
    def funding(self):
        values = [float(json.loads(r["event_json"]).get("funding", 0)) for r in self._rows("fills")]
        if values:
            return sum(values)
        return sum(float(e["payload"].get("funding", 0)) for e in self.all() if e["event_type"] == "TRADE_CLOSED")
    def latest_protection_status(self): return self._latest("protection")
    def latest_reconciliation_status(self): return self._latest("reconciliation")
    def active_breakers(self): return [e for e in self.all() if e["event_type"] in {"CIRCUIT_BREAKER", "RISK_BREAKER_OPEN"} and e["payload"].get("status", "OPEN") != "CLOSED"]
    def save_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO portfolio_snapshots(snapshot_json,created_ms) VALUES(?,?)",
                       (json.dumps(snapshot.to_dict(), sort_keys=True), _now()))

    def latest_portfolio_snapshot(self) -> PortfolioSnapshot | None:
        with self._connect() as db:
            row = db.execute("SELECT snapshot_json FROM portfolio_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        return PortfolioSnapshot.from_dict(json.loads(row[0])) if row else None

    def runtime_status(self):
        return {"latest_cycle": self.latest_cycle(), "disposition_counts": self.disposition_counts(), "open_positions": self.open_positions(), "closed_trades": self.closed_trades(), "realized_pnl": self.realized_pnl(), "fees": self.fees(), "funding": self.funding(), "protection": self.latest_protection_status(), "reconciliation": self.latest_reconciliation_status(), "active_breakers": self.active_breakers(), "recent_events": self.recent_events(), "portfolio": self.latest_portfolio_snapshot()}

    def replay_state(self):
        from scripts.replay_ledger import assert_replay_equal, replay_events
        replayed = replay_events(self.all())
        expected = {"dispositions": self.disposition_counts(),
                    "positions": {p.get("symbol"): p for p in self.open_positions()},
                    "protection": replayed["protection"], "reconciliation": replayed["reconciliation"],
                    "risk_breaker": replayed["risk_breaker"], "fees": self.fees(),
                    "funding": self.funding(), "net_pnl": sum(float(e["payload"].get("net_pnl", 0)) for e in self.all() if e["event_type"] == "TRADE_CLOSED"),
                    "closed_trades": [e["payload"] for e in self.all() if e["event_type"] == "TRADE_CLOSED"]}
        assert_replay_equal(expected, replayed)
        return replayed | {"replay_equal": True}
