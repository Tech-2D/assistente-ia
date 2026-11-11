from __future__ import annotations

from datetime import date, timedelta

from app.dates import today_local

WEEKDAY_NAMES = (
    "domingo",
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
)


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _weekdays(model: dict, first: date) -> tuple[int, ...]:
    values = model.get("weekdays")
    if values is None:
        return ((first.weekday() + 1) % 7,)
    if not isinstance(values, list) or not values:
        return ()
    if any(type(value) is not int or value < 0 or value > 6 for value in values):
        return ()
    return tuple(sorted(set(values)))


def recurrence_is_valid(model: dict) -> bool:
    first = _parse_date(model.get("startDate"))
    if first is None:
        return False
    interval = model.get("intervalWeeks", 1)
    if type(interval) is not int or interval < 1:
        return False
    if not _weekdays(model, first):
        return False
    last = _parse_date(model.get("endDate"))
    return last is None or last >= first


def expected_dates(
    model: dict,
    start: date,
    finish: date,
    *,
    today: date | None = None,
) -> set[str]:
    """Expected generated dates within the scheduler's current +56 day horizon.

    The Agenda projection is the source of truth. This is only a completeness check;
    it never creates an occurrence or presents a model-generated date as an activity.
    """
    try:
        first = _parse_date(model.get("startDate"))
        if first is None:
            return set()
        local_today = today or today_local()
        last = _parse_date(model.get("endDate")) or local_today + timedelta(days=56)
        last = min(last, local_today + timedelta(days=56), finish)
        cursor = max(first, start, local_today)
        interval = model.get("intervalWeeks", 1)
        if type(interval) is not int or interval < 1:
            return set()
        weekdays = _weekdays(model, first)
        if not weekdays or cursor > last:
            return set()

        anchor = first - timedelta(days=first.weekday())
        expected: set[str] = set()
        while cursor <= last:
            week_index = (cursor - anchor).days // 7
            weekday_sunday_zero = (cursor.weekday() + 1) % 7
            if week_index >= 0 and week_index % interval == 0 and weekday_sunday_zero in weekdays:
                expected.add(cursor.isoformat())
            cursor += timedelta(days=1)
        return expected
    except (TypeError, ValueError, OverflowError):
        return set()


def recurrence_summary(model: dict) -> str | None:
    """Describe a confirmed active recurrence from its stored model fields."""
    first = _parse_date(model.get("startDate"))
    if first is None:
        return None
    weekdays = _weekdays(model, first)
    if not weekdays:
        return None

    interval = model.get("intervalWeeks", 1)
    if type(interval) is not int or interval < 1:
        return None
    names = [WEEKDAY_NAMES[day] for day in weekdays]
    if len(names) == 1:
        frequency = f"Toda {names[0]}"
    elif len(names) == 2:
        frequency = f"Toda {names[0]} e {names[1]}"
    else:
        frequency = "Toda " + ", ".join(names[:-1]) + f" e {names[-1]}"
    if interval > 1:
        frequency = f"A cada {interval} semanas, {frequency[0].lower() + frequency[1:]}"

    end = _parse_date(model.get("endDate"))
    if end:
        frequency += f" até {end.strftime('%d/%m/%Y')}"
    return frequency
