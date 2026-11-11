import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.limits import RateLimiter, RateLimitExceeded


def test_daily_counter_is_atomic_and_per_user(tmp_path):
    limiter = RateLimiter(str(tmp_path / "limits.sqlite3"), 5)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: _consume(limiter, "same-user"), range(10)))
    assert sum(outcomes) == 5
    assert sum(not outcome for outcome in outcomes) == 5
    assert limiter.consume("different-user") == 4


def test_limit_can_be_disabled(tmp_path):
    limiter = RateLimiter(str(tmp_path / "limits.sqlite3"), 0, enabled=False)
    assert limiter.consume("same-user") is None


def test_sqlite_connections_close_after_initialization_success_and_limit(tmp_path, monkeypatch):
    real_connect = sqlite3.connect
    opened = []

    def tracked_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    limiter = RateLimiter(str(tmp_path / "closed.sqlite3"), 1)
    assert limiter.consume("user") == 0
    with pytest.raises(RateLimitExceeded):
        limiter.consume("user")
    assert len(opened) == 3
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_sqlite_connection_closes_when_pragma_fails(tmp_path, monkeypatch):
    class FailingConnection:
        closed = False

        def execute(self, query):
            raise sqlite3.OperationalError("pragma failed")

        def close(self):
            self.closed = True

    conn = FailingConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: conn)
    with pytest.raises(sqlite3.OperationalError, match="pragma failed"):
        RateLimiter(str(tmp_path / "failure.sqlite3"), 1)
    assert conn.closed


def test_counter_rolls_back_and_closes_on_failed_insert(tmp_path, monkeypatch):
    real_connect = sqlite3.connect
    opened = []

    class FailingConnection(sqlite3.Connection):
        def execute(self, query, *args):
            if query.startswith("INSERT INTO daily_usage"):
                raise sqlite3.OperationalError("insert failed")
            return super().execute(query, *args)

    def tracked_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs, factory=FailingConnection)
        opened.append(conn)
        return conn

    path = str(tmp_path / "failed-insert.sqlite3")
    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    limiter = RateLimiter(path, 1)
    with pytest.raises(sqlite3.OperationalError, match="insert failed"):
        limiter.consume("user")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[-1].execute("SELECT 1")
    conn = real_connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM daily_usage").fetchone()[0] == 0
    finally:
        conn.close()


def _consume(limiter, uid):
    try:
        limiter.consume(uid)
        return True
    except RateLimitExceeded:
        return False
