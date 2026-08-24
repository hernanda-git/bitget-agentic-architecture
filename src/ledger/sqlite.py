"""Durable SQLite ledger and projections for the autonomous runtime."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from .events import RuntimeEvent

REQUIRED = ("cycle_id", "trace_id", "created_ms", "mode", "product_type", "symbol", "payload_hash", "schema_version")
TABLES = ("cycles", "events", "orders", "fills", "positions", "protection", "reconciliation", "runtime_state")


def _now() -> int:
    return int(time.time() * 1000)


class EventLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.path) as db:
            db.executescript("""
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
            CREATE TABLE IF NOT EXISTS protection (id INTEGER PRIMARY KEY AUTOINCREMENT, event_json TEXT NOT NULL,
              cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS reconciliation (id INTEGER PRIMARY KEY AUTOINCREMENT, event_json TEXT NOT NULL,
              cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL,
              cycle_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_ms INTEGER NOT NULL, mode TEXT NOT NULL, product_type TEXT NOT NULL, symbol TEXT NOT NULL, payload_hash TEXT NOT NULL, schema_version INTEGER NOT NULL);
            """)
            # CREATE IF NOT EXISTS does not migrate old installations.
            for table in TABLES:
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for column in REQUIRED:
                    if column not in columns:
                        default = "1" if column == "schema_version" else ("0" if column == "created_ms" else "''")
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER NOT NULL DEFAULT {default}" if column in ("created_ms", "schema_version") else f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}")

    @staticmethod
    def _event(value: RuntimeEvent | Mapping[str, Any]) -> RuntimeEvent:
        return value if isinstance(value, RuntimeEvent) else RuntimeEvent.from_dict(value)

    def claim_cycle(self, cycle_id: str, *, trace_id: str = "", mode: str = "paper", product_type: str = "SUSDT-FUTURES", symbol: str = "") -> bool:
        with sqlite3.connect(self.path) as db:
            cur = db.execute("INSERT OR IGNORE INTO cycles(cycle_id,terminal_status,created_ms,trace_id,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?)", (cycle_id, None, _now(), trace_id, mode, product_type, symbol, "", 1))
            return cur.rowcount == 1

    def set_terminal(self, cycle_id: str, status: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE cycles SET terminal_status=? WHERE cycle_id=?", (status, cycle_id))

    def cycle_status(self, cycle_id: str) -> str | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT terminal_status FROM cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
            return row[0] if row else None

    def append(self, event_type: str, payload: dict) -> int:
        # Compatibility with the original public API. New code should use append_event.
        if not event_type or not isinstance(payload, dict):
            raise ValueError("invalid event")
        with sqlite3.connect(self.path) as db:
            cur = db.execute("INSERT INTO events(event_type,event_json,created_ms) VALUES(?,?,?)", (event_type, json.dumps(payload, sort_keys=True), _now()))
            return int(cur.lastrowid)

    def append_event(self, value: RuntimeEvent | Mapping[str, Any]) -> int:
        event = self._event(value)
        d = event.to_dict()
        with sqlite3.connect(self.path) as db:
            cur = db.execute("INSERT INTO events(event_type,event_json,created_ms,cycle_id,trace_id,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?)", (event.event_type, json.dumps(d["payload"], sort_keys=True), event.created_ms, event.cycle_id, event.trace_id, event.mode, event.product_type, event.symbol, event.payload_hash, event.schema_version))
            return int(cur.lastrowid)

    def _record(self, table: str, value: RuntimeEvent | Mapping[str, Any], identity: str | None = None, key: str | None = None) -> int:
        event = self._event(value); d = event.to_dict(); payload = dict(event.payload)
        with sqlite3.connect(self.path) as db:
            if table == "orders":
                cur = db.execute("INSERT INTO orders(client_order_id,venue_order_id,event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (payload["client_order_id"], payload.get("venue_order_id"), json.dumps(payload, sort_keys=True), event.cycle_id,event.trace_id,event.created_ms,event.mode,event.product_type,event.symbol,event.payload_hash,event.schema_version))
            elif table == "fills":
                cur = db.execute("INSERT INTO fills(fill_id,client_order_id,event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (payload["fill_id"],payload.get("client_order_id"),json.dumps(payload,sort_keys=True),event.cycle_id,event.trace_id,event.created_ms,event.mode,event.product_type,event.symbol,event.payload_hash,event.schema_version))
            elif table == "positions":
                cur = db.execute("INSERT INTO positions(position_id,event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?)", (payload["position_id"],json.dumps(payload,sort_keys=True),event.cycle_id,event.trace_id,event.created_ms,event.mode,event.product_type,event.symbol,event.payload_hash,event.schema_version))
            else:
                cur = db.execute(f"INSERT INTO {table}(event_json,cycle_id,trace_id,created_ms,mode,product_type,symbol,payload_hash,schema_version) VALUES(?,?,?,?,?,?,?,?,?)", (json.dumps(payload,sort_keys=True),event.cycle_id,event.trace_id,event.created_ms,event.mode,event.product_type,event.symbol,event.payload_hash,event.schema_version))
            return int(cur.lastrowid)

    def record_order(self, value): return self._record("orders", value)
    def record_fill(self, value): return self._record("fills", value)
    def record_position(self, value): return self._record("positions", value)
    def record_protection(self, value): return self._record("protection", value)
    def record_reconciliation(self, value): return self._record("reconciliation", value)

    def all(self) -> list[dict]:
        return self.recent_events(limit=None)

    def recent_events(self, limit: int | None = 50) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            sql = "SELECT id,event_type,event_json,created_ms,cycle_id,trace_id,mode,product_type,symbol,payload_hash,schema_version FROM events ORDER BY id DESC"
            rows = db.execute(sql + (" LIMIT ?" if limit is not None else ""), (limit,) if limit is not None else ()).fetchall()
        return [{"id":r[0],"event_type":r[1],"payload":json.loads(r[2]),"created_ms":r[3],"cycle_id":r[4],"trace_id":r[5],"mode":r[6],"product_type":r[7],"symbol":r[8],"payload_hash":r[9],"schema_version":r[10]} for r in reversed(rows)]

    def _rows(self, table: str) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
            rows = db.execute(f"SELECT {','.join(cols)} FROM {table} ORDER BY id" if "id" in cols else f"SELECT {','.join(cols)} FROM {table}").fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def table_rows(self, table: str) -> list[dict]: return self._rows(table)
    def latest_cycle(self):
        rows = self._rows("cycles"); return rows[-1] if rows else None
    def disposition_counts(self):
        counts = {}
        for e in self.recent_events(limit=None):
            disposition = e["payload"].get("disposition")
            if disposition: counts[disposition] = counts.get(disposition, 0) + 1
        return counts
    def open_positions(self):
        return [r | json.loads(r.pop("event_json")) for r in self._rows("positions") if json.loads(r["event_json"]).get("status") == "OPEN"]
    def _latest(self, table):
        rows = self._rows(table); return (lambda r: r | json.loads(r.pop("event_json")))(rows[-1]) if rows else None
    def latest_protection_status(self): return self._latest("protection")
    def latest_reconciliation_status(self): return self._latest("reconciliation")
    def runtime_status(self):
        return {"latest_cycle": self.latest_cycle(), "disposition_counts": self.disposition_counts(), "open_positions": self.open_positions(), "protection": self.latest_protection_status(), "reconciliation": self.latest_reconciliation_status(), "recent_events": self.recent_events()}
