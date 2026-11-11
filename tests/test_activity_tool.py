from datetime import date

import pytest

from app import activity_tool
from app.types import ActivityFilters


@pytest.mark.asyncio
async def test_filtered_limit_and_recurrence_override(monkeypatch):
    """An overridden occurrence still exists even if its type no longer matches."""
    monkeypatch.setattr(activity_tool, "ACTIVITY_LIMIT", 2)
    monkeypatch.setattr(activity_tool, "today_local", lambda: date(2026, 11, 11))
    model = {
        "active": True,
        "startDate": "2026-11-11",
        "weekdays": [3],
        "intervalWeeks": 1,
        "subject": "Matemática",
        "type": "prova",
    }
    activities = [
        ("1", "Outra", "tarefa", "Matemática", "2026-11-11", None, "Turma A", "r1", model),
        ("2", "Outra", "tarefa", "Matemática", "2026-11-11", None, "Turma A", None, None),
        ("3", "Outra", "tarefa", "Matemática", "2026-11-11", None, "Turma A", None, None),
        ("4", "Prova", "prova", "Matemática", "2026-11-11", None, "Turma A", None, None),
    ]

    class FakeConnection:
        async def fetch(self, query, *args):
            if query.startswith("SELECT DISTINCT subject"):
                return [{"subject": "Matemática"}]
            if query == activity_tool.QUERY:
                _, _, _, _, limit, subject, types = args
                assert "a.subject=$6" in query and "a.type=ANY($7::text[])" in query
                return [
                    row
                    for row in activities
                    if (not subject or row[3] == subject) and (not types or row[2] in types)
                ][:limit]
            if query == activity_tool.OCCURRENCE_QUERY:
                assert args[-1] == ["r1"]
                return [{"recurring_id": "r1", "date": "2026-11-11"}]
            return [{"id": "r1", "data": model}]

    async def connection():
        yield FakeConnection()

    monkeypatch.setattr(activity_tool, "read_connection", connection)
    result = await activity_tool.query_activities(
        ActivityFilters(
            start_date=date(2026, 11, 11),
            finish_date=date(2026, 11, 11),
            subject="matemática",
            types=["prova"],
        ),
        "Turma A",
        ["Turma A"],
    )
    assert [item["title"] for item in result["items"]] == ["Prova"]
    assert result["subject"] == "Matemática"
    assert result["missing_occurrences_detected"] is False


@pytest.mark.asyncio
async def test_too_many_matching_results_stop_before_recurrence_query(monkeypatch):
    monkeypatch.setattr(activity_tool, "ACTIVITY_LIMIT", 2)

    class FakeConnection:
        async def fetch(self, query, *args):
            if query.startswith("SELECT DISTINCT subject"):
                return []
            assert query == activity_tool.QUERY
            assert args[-2:] == (None, [])
            return [object(), object(), object()]

    async def connection():
        yield FakeConnection()

    monkeypatch.setattr(activity_tool, "read_connection", connection)
    result = await activity_tool.query_activities(ActivityFilters(), "Turma A", ["Turma A"])
    assert result == {"error": True, "error_code": "too_many_results"}
