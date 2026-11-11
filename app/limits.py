from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    """Atomic per-Firebase-UID daily counter for a single local app instance."""

    def __init__(self, path: str, limit: int, enabled: bool = True):
        self.path = path
        self.limit = max(0, limit)
        self.enabled = enabled
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS daily_usage ("
                "uid_hash TEXT NOT NULL, day TEXT NOT NULL, used INTEGER NOT NULL, "
                "PRIMARY KEY(uid_hash, day))"
            )

    def _db(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        return db

    def consume(self, uid: str) -> int | None:
        if not self.enabled:
            return None
        digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()
        today = datetime.now(TZ).date()
        day = today.isoformat()
        retention_floor = (today - timedelta(days=7)).isoformat()

        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM daily_usage WHERE day < ?", (retention_floor,))
            row = db.execute(
                "SELECT used FROM daily_usage WHERE uid_hash=? AND day=?",
                (digest, day),
            ).fetchone()
            used = row[0] if row else 0
            if used >= self.limit:
                db.execute("ROLLBACK")
                raise RateLimitExceeded
            db.execute(
                "INSERT INTO daily_usage(uid_hash,day,used) VALUES(?,?,1) "
                "ON CONFLICT(uid_hash,day) DO UPDATE SET used=used+1",
                (digest, day),
            )
            remaining = self.limit - used - 1
            db.execute("COMMIT")
            return remaining
