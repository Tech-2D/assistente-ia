"""Opt-in read-only integration checks against the configured Agenda database.

Set RUN_LIVE_AGENDA_TESTS=1 explicitly. No credentials or activity contents are
printed, and all queries use the application's verified read-only connection.
"""

import os
from datetime import timedelta

import pytest

from app.activity_tool import ACTIVITY_LIMIT, OCCURRENCE_QUERY, QUERY, query_activities
from app.dates import today_local
from app.db import read_connection
from app.types import ActivityFilters

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_AGENDA_TESTS") != "1",
        reason="requires explicit opt-in to read the configured Agenda database",
    ),
]


async def test_readonly_filtered_query_and_tool_match_live_records():
    class_id = os.getenv("LIVE_AGENDA_CLASS", "2° TECH D")
    end = today_local() - timedelta(days=1)
    start = end - timedelta(days=179)
    start_iso, end_iso = start.isoformat(), end.isoformat()

    try:
        async with read_connection() as conn:
            mode = await conn.fetchval("SHOW transaction_read_only")
            if mode != "on":
                pytest.fail("Conexão não está em modo somente leitura.", pytrace=False)
            rows = await conn.fetch(
                QUERY, class_id, True, start_iso, end_iso, ACTIVITY_LIMIT + 1, None, []
            )
            if len(rows) > ACTIVITY_LIMIT:
                pytest.skip("Intervalo de integração ultrapassou o limite de atividades.")
            candidates = [
                r
                for r in rows
                if r[3] and r[2] in {"tarefa", "licao", "trabalho", "prova", "evento"}
            ]
            if not candidates:
                pytest.skip("Sem atividades com matéria e tipo no intervalo de integração.")
            subject, kind = candidates[0][3], candidates[0][2]
            expected = [str(row[0]) for row in rows if row[3] == subject and row[2] == kind]
            filtered = await conn.fetch(
                QUERY, class_id, True, start_iso, end_iso, ACTIVITY_LIMIT + 1, subject, [kind]
            )
            if [str(row[0]) for row in filtered] != expected:
                pytest.fail("Filtro SQL não corresponde à comparação local.", pytrace=False)
            only_class = await conn.fetch(
                QUERY, class_id, False, start_iso, end_iso, ACTIVITY_LIMIT + 1, None, []
            )
            if [str(row[0]) for row in only_class] != [
                str(row[0]) for row in rows if row[6] == class_id
            ]:
                pytest.fail(
                    "Filtro de eventos gerais não corresponde à comparação local.", pytrace=False
                )
            recurrence_ids = sorted({str(row[7]) for row in rows if row[7] and row[6] == class_id})
            occurrence_rows = await conn.fetch(
                OCCURRENCE_QUERY,
                class_id,
                start_iso,
                end_iso,
                recurrence_ids or ["synthetic-no-match"],
            )
            expected_occurrences = {
                (str(row[7]), str(row[4])) for row in rows if row[7] and row[6] == class_id
            }
            observed_occurrences = {
                (str(row["recurring_id"]), str(row["date"])) for row in occurrence_rows
            }
            if observed_occurrences != expected_occurrences:
                pytest.fail(
                    "Consulta de ocorrências não corresponde à comparação local.", pytrace=False
                )

        result = await query_activities(
            ActivityFilters(start_date=start, finish_date=end, subject=subject, types=[kind]),
            class_id,
            [class_id],
        )
        if result.get("error") or result.get("clarification_code"):
            pytest.fail("A ferramenta não retornou um resultado consultável.", pytrace=False)
        if [item["id"] for item in result["items"]] != expected:
            pytest.fail(
                "Ferramenta e consulta SQL apresentaram resultados diferentes.", pytrace=False
            )
    except Exception as exc:  # noqa: BLE001 - avoid exposing database values or credentials.
        pytest.fail(f"Integração indisponível: {type(exc).__name__}.", pytrace=False)
