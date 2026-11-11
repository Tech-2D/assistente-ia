from datetime import date

from app.recurrence_check import expected_dates, recurrence_summary


def test_expected_weekly_dates_use_sunday_zero_and_56_day_horizon():
    model = {
        "startDate": "2026-11-11",
        "weekdays": [3, 5],  # Wednesday and Friday, Sunday is zero in the Agenda model.
        "intervalWeeks": 1,
    }
    expected = expected_dates(
        model,
        date(2026, 11, 11),
        date(2027, 2, 1),
        today=date(2026, 11, 11),
    )
    assert "2026-11-11" in expected
    assert "2026-11-13" in expected
    assert all(date.fromisoformat(value) <= date(2027, 1, 6) for value in expected)


def test_expected_dates_respect_end_date_interval_and_invalid_weekdays():
    model = {
        "startDate": "2026-11-11",
        "endDate": "2026-11-30",
        "weekdays": [3],
        "intervalWeeks": 2,
    }
    expected = expected_dates(
        model,
        date(2026, 11, 11),
        date(2026, 12, 31),
        today=date(2026, 11, 11),
    )
    assert expected == {"2026-11-11", "2026-11-25"}
    assert (
        expected_dates(
            {**model, "weekdays": [8]},
            date(2026, 11, 11),
            date(2026, 11, 30),
            today=date(2026, 11, 11),
        )
        == set()
    )


def test_recurrence_summary_reports_stored_weekdays_and_end_date():
    model = {
        "title": "Entrega do relatório",
        "startDate": "2026-11-11",
        "endDate": "2026-12-16",
        "weekdays": [3, 5],
        "intervalWeeks": 1,
    }
    assert recurrence_summary(model) == "Toda quarta-feira e sexta-feira até 16/12/2026"
