"""Durable, transactional accounting for the teacher-provided OpenRouter quota.

Each *attempted* external POST is reserved and committed BEFORE the HTTP call.
The counter is never automatically reset; a crash leaves the reservation spent.
Successful HTTP responses are cached by full model/endpoint/request JSON. Errors
and timeouts are still stored in the durable call log (not replayed as answers).
The same SQLite file is shared across runs and application restarts.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# These are code-enforced, never overridden by .env, browser, or request inputs.
MAX_TOTAL = 65
MAX_DECISION_EACH = 20
MAX_CLAUDE = 5
MAX_POSSIBLE_KEY_QUOTA = 100  # informational; never intentionally spend this many


class QuotaExhausted(Exception):
    """An attempted network call would exceed the assignment's strict budget."""


@dataclass(frozen=True)
class Claim:
    request_hash: str
    row_id: int | None = None
    cached_body: dict | None = None
    cache_ms: float = 0.0

    @property
    def cache_hit(self) -> bool:
        return self.cached_body is not None


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class APILedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_key TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    reserved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    finished_at TEXT,
                    outcome TEXT NOT NULL DEFAULT 'reserved',
                    http_status INTEGER,
                    network_ms REAL,
                    cost_usd REAL,
                    response_json TEXT,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS calls_by_model ON calls(model_key);
                CREATE TABLE IF NOT EXISTS cache (
                    request_hash TEXT PRIMARY KEY,
                    model_key TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    saved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS cache_hits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_hash TEXT NOT NULL,
                    model_key TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    @staticmethod
    def fingerprint(url: str, payload: dict) -> str:
        # No Authorization header / API secret is ever in the fingerprint input.
        return hashlib.sha256(_json({"url": url, "body": payload}).encode("utf-8")).hexdigest()

    def claim(self, model_key: str, model_id: str, url: str, payload: dict) -> Claim:
        """Atomically check cache then reserve a paid call, or refuse safely."""
        t0 = time.perf_counter()
        fingerprint = self.fingerprint(url, payload)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cached = db.execute("SELECT response_json FROM cache WHERE request_hash=?", (fingerprint,)).fetchone()
            if cached is not None:
                elapsed = (time.perf_counter() - t0) * 1000
                db.execute("INSERT INTO cache_hits(request_hash,model_key,latency_ms) VALUES(?,?,?)",
                           (fingerprint, model_key, elapsed))
                db.execute("COMMIT")
                return Claim(fingerprint, cached_body=json.loads(cached[0]), cache_ms=elapsed)
            total = db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            used = db.execute("SELECT COUNT(*) FROM calls WHERE model_key=?", (model_key,)).fetchone()[0]
            model_cap = MAX_CLAUDE if model_key == "opus" else MAX_DECISION_EACH
            if total >= MAX_TOTAL or used >= model_cap:
                db.execute("ROLLBACK")
                raise QuotaExhausted(
                    f"API quota exhausted for {model_key}: {used}/{model_cap} model calls, "
                    f"{total}/{MAX_TOTAL} total. Cached responses can still be used."
                )
            cur = db.execute(
                "INSERT INTO calls(model_key,model_id,request_hash) VALUES(?,?,?)",
                (model_key, model_id, fingerprint),
            )
            row = cur.lastrowid
            db.execute("COMMIT")
            return Claim(fingerprint, row_id=row)

    def finish(self, claim: Claim, *, status: int | None, body: dict | None,
               network_ms: float, error: str | None = None) -> None:
        if claim.row_id is None:
            return
        cost = None
        if isinstance(body, dict):
            usage = body.get("usage")
            if isinstance(usage, dict) and isinstance(usage.get("cost"), (float, int)):
                cost = float(usage["cost"])
        # Persist the entire response for every completed call, even HTTP errors.
        response_json = _json(body) if body is not None else None
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE calls SET finished_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                 outcome=?, http_status=?, network_ms=?, cost_usd=?, response_json=?, error=? WHERE id=?""",
                 ("http" if status is not None else "network_error", status, network_ms,
                  cost, response_json, (error or "")[:500], claim.row_id))
            # Only a usable 2xx JSON object is replayed on future identical prompts;
            # transient errors and network failures are always counted but never cached.
            if status is not None and 200 <= status < 300 and isinstance(body, dict):
                model_row = db.execute("SELECT model_key,model_id FROM calls WHERE id=?", (claim.row_id,)).fetchone()
                db.execute("""INSERT OR IGNORE INTO cache(request_hash,model_key,model_id,response_json)
                              VALUES(?,?,?,?)""", (claim.request_hash, model_row[0], model_row[1], response_json))
            db.execute("COMMIT")

    def snapshot(self) -> dict:
        with self._connect() as db:
            counts = dict(db.execute("SELECT model_key, COUNT(*) FROM calls GROUP BY model_key").fetchall())
            hits = dict(db.execute("SELECT model_key, COUNT(*) FROM cache_hits GROUP BY model_key").fetchall())
            return {
                "total_used": sum(counts.values()), "total_limit": MAX_TOTAL,
                "by_model": {
                    k: {"used": counts.get(k, 0), "limit": MAX_CLAUDE if k == "opus" else MAX_DECISION_EACH,
                        "cache_hits": hits.get(k, 0)}
                    for k in ("jev", "luna", "clef", "opus")
                },
                "cache_entries": db.execute("SELECT COUNT(*) FROM cache").fetchone()[0],
                "known_cost_usd": round(db.execute("SELECT COALESCE(SUM(cost_usd),0) FROM calls").fetchone()[0], 8),
                "unreported_cost_calls": db.execute(
                    "SELECT COUNT(*) FROM calls WHERE cost_usd IS NULL"
                ).fetchone()[0],
                "db_file": self.path.name,
            }
