from concurrent.futures import ThreadPoolExecutor

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


def _consume(limiter, uid):
    try:
        limiter.consume(uid)
        return True
    except RateLimitExceeded:
        return False
