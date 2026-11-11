from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def today_local() -> date:
    return datetime.now(TZ).date()


def calendar_context(today: date) -> dict[str, str]:
    """Calendar anchors are calculated in code and interpreted in the user's context."""
    monday = today - timedelta(days=today.weekday())
    return {
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        "current_week_start": monday.isoformat(),
        "current_week_end": (monday + timedelta(days=6)).isoformat(),
        "next_week_start": (monday + timedelta(days=7)).isoformat(),
        "next_week_end": (monday + timedelta(days=13)).isoformat(),
        "next_monday": (monday + timedelta(days=7)).isoformat(),
    }


def anniversary(value: date) -> date:
    try:
        return value.replace(year=value.year + 1)
    except ValueError:
        return date(value.year + 1, 3, 1)


def period(start: date | None, finish: date | None) -> tuple[date, date]:
    today = today_local()
    if start is None and finish is None:
        return today, today + timedelta(days=6)
    if start is None:
        raise ValueError("Preciso da data inicial para pesquisar até essa data.")
    if finish is None:
        finish = start + timedelta(days=6)
    if start > finish:
        raise ValueError("A data inicial precisa ser anterior ou igual à data final.")
    if finish >= anniversary(start):
        raise ValueError(
            "Eita, pera ai, A agenda não é uma máquina do tempo! Escolha um período de até um ano para eu procurar as atividades."
        )
    return start, finish
