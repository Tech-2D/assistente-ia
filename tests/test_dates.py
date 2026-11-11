from datetime import date

import pytest

from app.dates import period


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
