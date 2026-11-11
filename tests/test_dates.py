import os
import subprocess
import sys
from datetime import date

import pytest

from app.dates import calendar_context, period


def test_default_period_is_seven_days():
    start, finish = period(None, None)
    assert (finish - start).days == 6


def test_inclusive_one_calendar_year_boundaries():
    assert period(date(2026, 1, 1), date(2026, 12, 31)) == (date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(ValueError, match="máquina do tempo"):
        period(date(2026, 1, 1), date(2027, 1, 1))
    assert period(date(2024, 2, 29), date(2025, 2, 28))[1] == date(2025, 2, 28)
    with pytest.raises(ValueError, match="máquina do tempo"):
        period(date(2024, 2, 29), date(2025, 3, 1))


def test_only_finish_and_inverted_dates_need_correction():
    with pytest.raises(ValueError, match="data inicial"):
        period(None, date(2026, 11, 11))
    with pytest.raises(ValueError, match="anterior"):
        period(date(2026, 11, 12), date(2026, 11, 11))


@pytest.mark.parametrize(
    ("today", "next_monday", "week_start", "week_end"),
    [
        (date(2026, 11, 9), "2026-11-16", "2026-11-09", "2026-11-15"),
        (date(2026, 11, 15), "2026-11-16", "2026-11-09", "2026-11-15"),
        (date(2023, 12, 31), "2024-01-01", "2023-12-25", "2023-12-31"),
        (date(2024, 2, 29), "2024-03-04", "2024-02-26", "2024-03-03"),
    ],
)
def test_calendar_context_respects_week_boundaries(today, next_monday, week_start, week_end):
    result = calendar_context(today)
    assert result["today"] == today.isoformat()
    assert result["next_monday"] == next_monday
    assert result["current_week_start"] == week_start
    assert result["current_week_end"] == week_end


def test_calendar_context_contains_adjacent_days_and_next_week():
    result = calendar_context(date(2024, 2, 28))
    assert result["yesterday"] == "2024-02-27"
    assert result["tomorrow"] == "2024-02-29"
    assert result["next_week_start"] == "2024-03-04"
    assert result["next_week_end"] == "2024-03-10"


def test_sao_paulo_timezone_loads_without_system_timezone_database():
    env = {**os.environ, "PYTHONTZPATH": ""}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from zoneinfo import ZoneInfo; print(ZoneInfo('America/Sao_Paulo'))",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "America/Sao_Paulo"
