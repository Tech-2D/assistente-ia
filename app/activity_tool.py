from __future__ import annotations

import json
from datetime import date, time, timedelta
from urllib.parse import quote

from app.dates import period, today_local
from app.db import read_connection
from app.recurrence_check import expected_dates, recurrence_is_valid, recurrence_summary
from app.subjects import OFFICIAL_SUBJECTS, resolve_subject
from app.types import ActivityFilters

ACTIVITY_LIMIT = 10_000
ACTIVITY_URL = "https://tech-2d.github.io/Agenda/#atividade="
QUERY = """SELECT a.id,a.title,a.type,a.subject,a.date,a.time,a.turma_id,a.recurring_id,d.data
FROM tech2d.activities a
LEFT JOIN tech2d.app_documents d
 ON d.collection='recurringActivities' AND d.id=a.recurring_id
WHERE (a.turma_id=$1 OR ($2 AND a.turma_id IS NULL))
 AND a.date >= $3 AND a.date <= $4
ORDER BY a.date,a.time NULLS LAST,a.id
LIMIT $5"""


def _iso(value) -> str:
    if isinstance(value, (date, time)):
        return value.isoformat()
    return str(value)


def _display_time(value) -> str | None:
    if value is None:
        return None
    return _iso(value)[:5]


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def query_activities(
    filters: ActivityFilters,
    default_class: str,
    allowed_classes: list[str],
) -> dict:
    """Read the public activity projection under a verified read-only TLS connection."""
    class_id = filters.class_id or default_class
    if not class_id:
        return {"clarification_code": "missing_class"}
    if class_id not in allowed_classes:
        return {
            "clarification_code": "unknown_class",
            "options": allowed_classes,
        }

    try:
        start, finish = period(filters.start_date, filters.finish_date)
    except ValueError as exc:
        if "máquina do tempo" in str(exc):
            return {"error": True, "error_code": "period_limit"}
        if "data inicial" in str(exc) and filters.start_date is None:
            return {"clarification_code": "missing_start_date"}
        if "anterior" in str(exc):
            return {"clarification_code": "invalid_dates"}
        return {"clarification_code": "date_parse"}

    async for conn in read_connection():
        subject_rows = await conn.fetch(
            "SELECT DISTINCT subject FROM tech2d.activities "
            "WHERE subject IS NOT NULL ORDER BY subject"
        )
        known_subjects = sorted(
            set(OFFICIAL_SUBJECTS).union(row["subject"] for row in subject_rows),
            key=str.casefold,
        )
        chosen_subject, subject_options = resolve_subject(filters.subject, known_subjects)
        if filters.subject and not chosen_subject:
            if subject_options:
                return {
                    "clarification_code": "ambiguous_subject",
                    "options": subject_options,
                }
            return {
                "clarification_code": "unknown_subject",
                "options": known_subjects,
            }

        rows = await conn.fetch(
            QUERY,
            class_id,
            filters.include_general,
            start.isoformat(),
            finish.isoformat(),
            ACTIVITY_LIMIT + 1,
        )
        recurrence_templates = await conn.fetch(
            "SELECT id,data FROM tech2d.app_documents "
            "WHERE collection='recurringActivities' "
            "AND data->>'turmaId'=$1 AND data->>'active'='true' "
            "AND coalesce(data->>'deleted','false')!='true'",
            class_id,
        )

    if len(rows) > ACTIVITY_LIMIT:
        return {"error": True, "error_code": "too_many_results"}

    now = today_local()
    found_occurrences = {(row[7], _iso(row[4])) for row in rows if row[7] is not None}
    missing_occurrences = 0
    unreadable_recurrence_models = False
    for template in recurrence_templates:
        model = _json_object(template["data"])
        if chosen_subject and model.get("subject") != chosen_subject:
            continue
        if filters.types and model.get("type") not in filters.types:
            continue
        if not recurrence_is_valid(model):
            unreadable_recurrence_models = True
            continue
        for expected in expected_dates(model, start, finish, today=now):
            if (template["id"], expected) not in found_occurrences:
                missing_occurrences += 1

    items: list[dict] = []
    for row in rows:
        (
            activity_id,
            title,
            activity_type,
            subject,
            activity_date,
            activity_time,
            turma_id,
            recurrence_id,
            model,
        ) = row
        normalized_date = _iso(activity_date)
        model = _json_object(model)

        if chosen_subject and subject != chosen_subject:
            continue
        if filters.types and activity_type not in filters.types:
            continue

        if (
            recurrence_id
            and normalized_date >= now.isoformat()
            and (not model or not model.get("active") or model.get("deleted"))
        ):
            # Pausing/deleting a series may take one scheduled cleanup cycle to remove
            # projected future occurrences. Do not present those as live activities.
            continue

        active_model = bool(
            recurrence_id and model and model.get("active") and not model.get("deleted")
        )
        is_overridden = False
        summary = None
        if active_model:
            model_time = model.get("time")
            normalized_model_time = str(model_time)[:5] if model_time else None
            is_overridden = any(
                (
                    _display_time(row[5]) != normalized_model_time
                    if field == "time"
                    else row[index] != model.get(field)
                )
                for field, index in (("title", 1), ("type", 2), ("subject", 3), ("time", 5))
            )
            summary = recurrence_summary(model)

        safe_id = quote(str(activity_id), safe="")
        items.append(
            {
                "id": str(activity_id),
                "title": str(title),
                "type": str(activity_type),
                "type_label": {
                    "tarefa": "Tarefa",
                    "licao": "Lição",
                    "trabalho": "Trabalho",
                    "prova": "Prova",
                    "evento": "Evento",
                }.get(str(activity_type), str(activity_type)),
                "subject": subject,
                "date": normalized_date,
                "time": _display_time(activity_time),
                "class_id": turma_id,
                "is_general": turma_id is None,
                "recurring_id": str(recurrence_id) if recurrence_id else None,
                "recurrence_summary": summary,
                "was_overridden": is_overridden,
                "url": ACTIVITY_URL + safe_id,
            }
        )

    return {
        "class_id": class_id,
        "start_date": start.isoformat(),
        "finish_date": finish.isoformat(),
        "types": list(filters.types),
        "subject": chosen_subject,
        "include_general": filters.include_general,
        "items": items,
        "future_recurrence_warning": finish > now + timedelta(days=56),
        "missing_occurrences_detected": missing_occurrences > 0 or unreadable_recurrence_models,
    }
