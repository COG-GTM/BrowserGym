from __future__ import annotations

import os
import sqlite3
import time
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    token TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS device_runs (
    token TEXT NOT NULL REFERENCES devices(token) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    PRIMARY KEY (token, run_id)
);
CREATE INDEX IF NOT EXISTS idx_device_runs_run ON device_runs(run_id);
CREATE TABLE IF NOT EXISTS notified_runs (
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    notified_at REAL NOT NULL,
    PRIMARY KEY (run_id, status)
);
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    token TEXT NOT NULL,
    ticket_id TEXT,
    state TEXT NOT NULL,
    error TEXT,
    message TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deliveries_run ON deliveries(run_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_ticket ON deliveries(ticket_id);
"""

# Delivery states:
#   dry_run  - payload logged, Expo not called
#   pending  - Expo accepted the message (ticket ok), receipt not checked yet
#   ok       - receipt ok
#   error    - ticket or receipt error (see `error`)
#   expired  - receipt never became available (Expo keeps receipts ~24h)


@dataclass
class Device:
    token: str
    platform: str
    run_ids: list[str]


@dataclass
class Delivery:
    id: int
    run_id: str
    status: str
    token: str
    ticket_id: str | None
    state: str
    error: str | None
    message: str | None
    created_at: float


class Store:
    """Tiny SQLite store. A connection per operation keeps it thread/async-safe."""

    def __init__(self, path: str):
        self.path = path
        self._uri = False
        self._keeper: sqlite3.Connection | None = None
        if path == ":memory:":
            # A plain :memory: db is per-connection; share one and keep it alive.
            self.path = f"file:side-notify-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._uri = True
            self._keeper = sqlite3.connect(self.path, uri=True, check_same_thread=False)
        else:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def close(self) -> None:
        if self._keeper is not None:
            self._keeper.close()
            self._keeper = None

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10, uri=self._uri)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # devices -----------------------------------------------------------------

    def upsert_device(self, token: str, platform: str, run_ids: Iterable[str]) -> bool:
        """Insert or replace a device's registration. Returns True if newly created."""
        now = time.time()
        with self._conn() as conn:
            existed = (
                conn.execute("SELECT 1 FROM devices WHERE token = ?", (token,)).fetchone()
                is not None
            )
            conn.execute(
                """INSERT INTO devices (token, platform, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(token) DO UPDATE SET platform = excluded.platform,
                                                    updated_at = excluded.updated_at""",
                (token, platform, now, now),
            )
            conn.execute("DELETE FROM device_runs WHERE token = ?", (token,))
            conn.executemany(
                "INSERT OR IGNORE INTO device_runs (token, run_id) VALUES (?, ?)",
                [(token, r) for r in run_ids],
            )
        return not existed

    def delete_device(self, token: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM devices WHERE token = ?", (token,))
        return cur.rowcount > 0

    def delete_devices(self, tokens: Iterable[str]) -> int:
        tokens = list(set(tokens))
        if not tokens:
            return 0
        with self._conn() as conn:
            cur = conn.executemany("DELETE FROM devices WHERE token = ?", [(t,) for t in tokens])
        return cur.rowcount

    def get_device(self, token: str) -> Device | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT token, platform FROM devices WHERE token = ?", (token,)
            ).fetchone()
            if row is None:
                return None
            runs = [
                r["run_id"]
                for r in conn.execute(
                    "SELECT run_id FROM device_runs WHERE token = ? ORDER BY run_id", (token,)
                )
            ]
        return Device(token=row["token"], platform=row["platform"], run_ids=runs)

    def subscribers(self, run_id: str) -> list[str]:
        """Tokens subscribed to `run_id`: devices with no run filter, or that list this run."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT d.token FROM devices d
                   WHERE NOT EXISTS (SELECT 1 FROM device_runs dr WHERE dr.token = d.token)
                      OR EXISTS (SELECT 1 FROM device_runs dr
                                 WHERE dr.token = d.token AND dr.run_id = ?)
                   ORDER BY d.created_at, d.token""",
                (run_id,),
            ).fetchall()
        return [r["token"] for r in rows]

    # dedupe ------------------------------------------------------------------

    def mark_notified(self, run_id: str, status: str) -> bool:
        """Returns False if this (run_id, status) was already notified."""
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO notified_runs (run_id, status, notified_at)"
                " VALUES (?, ?, ?)",
                (run_id, status, time.time()),
            )
        return cur.rowcount > 0

    def unmark_notified(self, run_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM notified_runs WHERE run_id = ? AND status = ?", (run_id, status)
            )

    # deliveries --------------------------------------------------------------

    def delivered_tokens(self, run_id: str, status: str) -> set[str]:
        """Tokens already handed to Expo (or logged in dry run) for this run status."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT DISTINCT token FROM deliveries
                   WHERE run_id = ? AND status = ?
                     AND NOT (state = 'error' AND error = 'RequestFailed')""",
                (run_id, status),
            ).fetchall()
        return {r["token"] for r in rows}

    def add_delivery(
        self,
        run_id: str,
        status: str,
        token: str,
        state: str,
        ticket_id: str | None = None,
        error: str | None = None,
        message: str | None = None,
    ) -> None:
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO deliveries
                   (run_id, status, token, ticket_id, state, error, message, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, status, token, ticket_id, state, error, message, now, now),
            )

    def pending_tickets(self, min_age_s: float) -> list[tuple[str, str, float]]:
        """(ticket_id, token, created_at) for deliveries awaiting a receipt."""
        cutoff = time.time() - min_age_s
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ticket_id, token, created_at FROM deliveries
                   WHERE state = 'pending' AND ticket_id IS NOT NULL AND created_at <= ?
                   ORDER BY created_at""",
                (cutoff,),
            ).fetchall()
        return [(r["ticket_id"], r["token"], r["created_at"]) for r in rows]

    def resolve_ticket(
        self,
        ticket_id: str,
        state: str,
        error: str | None = None,
        message: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE deliveries SET state = ?, error = ?, message = ?, updated_at = ?
                   WHERE ticket_id = ?""",
                (state, error, message, time.time(), ticket_id),
            )

    def deliveries(self, run_id: str | None = None, limit: int = 200) -> list[Delivery]:
        query = "SELECT * FROM deliveries"
        params: tuple = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " ORDER BY id DESC LIMIT ?"
        with self._conn() as conn:
            rows = conn.execute(query, (*params, limit)).fetchall()
        return [
            Delivery(
                id=r["id"],
                run_id=r["run_id"],
                status=r["status"],
                token=r["token"],
                ticket_id=r["ticket_id"],
                state=r["state"],
                error=r["error"],
                message=r["message"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
