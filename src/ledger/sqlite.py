"""Append-only SQLite event ledger for autonomous decisions."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

class EventLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()
    def _init(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, event_json TEXT NOT NULL, created_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS cycles (cycle_id TEXT PRIMARY KEY, terminal_status TEXT, created_ms INTEGER NOT NULL)")
    def claim_cycle(self, cycle_id: str) -> bool:
        with sqlite3.connect(self.path) as db:
            cur=db.execute("INSERT OR IGNORE INTO cycles(cycle_id,terminal_status,created_ms) VALUES(?,?,?)", (cycle_id,None,int(time.time()*1000)))
            return cur.rowcount == 1
    def set_terminal(self, cycle_id: str, status: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE cycles SET terminal_status=? WHERE cycle_id=?", (status,cycle_id))
    def cycle_status(self, cycle_id: str) -> str | None:
        with sqlite3.connect(self.path) as db:
            row=db.execute("SELECT terminal_status FROM cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
            return row[0] if row else None
    def append(self, event_type: str, payload: dict) -> int:
        if not event_type or not isinstance(payload, dict): raise ValueError("invalid event")
        with sqlite3.connect(self.path) as db:
            cur=db.execute("INSERT INTO events(event_type,event_json,created_ms) VALUES(?,?,?)", (event_type,json.dumps(payload,sort_keys=True),int(time.time()*1000)))
            return int(cur.lastrowid)
    def all(self) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            return [{"id":r[0],"event_type":r[1],"payload":json.loads(r[2]),"created_ms":r[3]} for r in db.execute("SELECT id,event_type,event_json,created_ms FROM events ORDER BY id")]
