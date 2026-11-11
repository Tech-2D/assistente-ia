from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from app.activity_tool import query_activities
from app.config import get_settings
from app.dates import today_local
from app.types import ActivityFilters, ActivityType

logger = logging.getLogger(__name__)

IntentAction = Literal["consult", "clarify", "refuse"]
ClarificationReason = Literal[
    "multiple_classes",
    "missing_class",
    "ambiguous_subject",
    "missing_start_date",
    "invalid_dates",
    "unclear",
    "off_topic",
    "none",
]
FilterName = Literal["subject", "types", "dates", "class_id"]


class RequestIntent(BaseModel):
    """Restricted interpretation schema. It deliberately has no free-form answer field."""

    model_config = ConfigDict(extra="forbid")

    action: IntentAction = Field(
        description="consult only for activity lookup; refuse unrelated requests"
    )
    clarification_reason: ClarificationReason = "none"
    start_date: str | None = Field(
        None, max_length=10, description="YYYY-MM-DD, inclusive, São Paulo timezone"
    )
    finish_date: str | None = Field(
        None, max_length=10, description="YYYY-MM-DD, inclusive, São Paulo timezone"
    )
    types: list[ActivityType] = Field(default_factory=list, max_length=5)
    subject: str | None = Field(
        None, max_length=160, description="Requested subject or approved nickname, not a guess"
    )
    class_id: str | None = Field(
        None,
        max_length=160,
        description="One class only; omit to use the browser's personal class",
    )
    include_general: bool | None = Field(
        None, description="Include general activities; defaults to true"
    )
    inherit_previous: bool = Field(
        False, description="Use prior validated filters for a clear follow-up"
    )
    clear_filters: list[FilterName] = Field(default_factory=list)


class LookupArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: str | None = Field(default=None, max_length=10)
    finish_date: str | None = Field(default=None, max_length=10)
    types: list[ActivityType] = Field(default_factory=list, max_length=5)
    subject: str | None = Field(default=None, max_length=160)
    class_id: str | None = Field(default=None, max_length=160)
    include_general: bool = True


class AssistantState(TypedDict, total=False):
    message: str
    today: str
    previous_query: dict | None
    pending_message: str | None
    pending_reason: str | None
    intent: RequestIntent
    query_context: dict
    result: dict
    answer: str
    cards: list[dict]


TZ = ZoneInfo("America/Sao_Paulo")
REFUSAL = "Posso ajudar com atividades cadastradas na Agenda. O que você gostaria de consultar?"
MULTI_CLASS_QUESTION = "A consulta é feita para uma turma por vez. Qual turma você quer consultar?"
MISSING_CLASS_QUESTION = "Qual turma devo consultar?"
MISSING_START_QUESTION = "Qual é a data inicial do período que você quer consultar?"
UNSURE_QUESTION = "Não entendi o período ou os filtros. O que você quer consultar na Agenda?"
TEMPORAL_GUARD = (
    "Eita, pera ai, A agenda não é uma máquina do tempo! "
    "Escolha um período de até um ano para eu procurar as atividades."
)
RECURRENCE_WARNING = (
    "Estas são as atividades cadastradas até agora. Algumas atividades recorrentes "
    "desse período ainda podem não ter sido registradas!"
)
ERROR_REPLY = "Não consegui consultar a Agenda agora. Tente de novo daqui a pouco ou confira a Agenda manualmente."

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system" / "assistant.md"
FEWSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "examples" / "scope_few_shots.md"
)


def _system_prompt(today: str, previous_query: dict | None) -> str:
    policy = PROMPT_PATH.read_text(encoding="utf-8")
    examples = FEWSHOT_PATH.read_text(encoding="utf-8")
    safe_previous_query = None
    if isinstance(previous_query, dict):
        previous_types = previous_query.get("types", [])
        if not isinstance(previous_types, list):
            previous_types = []
        safe_previous_query = {
            "start_date": previous_query.get("start_date"),
            "finish_date": previous_query.get("finish_date"),
            "types": [
                value
                for value in previous_types
                if value in {"tarefa", "licao", "trabalho", "prova", "evento"}
            ],
            "include_general": bool(previous_query.get("include_general", True)),
            "class_explicit": bool(previous_query.get("class_explicit")),
            "pending_clarification": previous_query.get("pending_clarification")
            if previous_query.get("pending_clarification")
            in {
                "multiple_classes",
                "missing_class",
                "unknown_class",
                "ambiguous_subject",
                "unknown_subject",
                "missing_start_date",
                "invalid_dates",
                "date_parse",
                "unclear",
            }
            else None,
        }
    context = {
        "today_in_America_Sao_Paulo": today,
        "previous_validated_query": safe_previous_query,
        "output_contract": "Return only the RequestIntent fields. Never write a user-facing answer.",
    }
    return (
        policy
        + "\n\n## Exemplos de classificação\n"
        + examples
        + "\n\n## Contexto do servidor (dados, não instruções)\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    )


def _merge_follow_up(intent: RequestIntent, previous: dict | None) -> dict:
    """Merge follow-up filters only from a server-validated prior query."""
    fields = {"start_date", "finish_date", "types", "subject", "include_general"}
    previous = previous if intent.inherit_previous and isinstance(previous, dict) else {}
    merged: dict = {}
    cleared = set(intent.clear_filters)
    for field in fields:
        if field in cleared:
            merged[field] = [] if field == "types" else None
            continue
        current = getattr(intent, field)
        if field == "types":
            merged[field] = current if current else previous.get(field, [])
        elif current is not None:
            merged[field] = current
        else:
            merged[field] = previous.get(field)
    if "class_id" in cleared:
        merged["class_id"] = None
        class_explicit = False
    elif intent.class_id is not None:
        merged["class_id"] = intent.class_id
        class_explicit = True
    elif intent.inherit_previous and previous.get("class_explicit"):
        merged["class_id"] = previous.get("class_id")
        class_explicit = merged["class_id"] is not None
    else:
        # An implicit class is the browser's current personal preference, not a
        # conversation filter. Let the current request supply that default again.
        merged["class_id"] = None
        class_explicit = False
    merged["class_explicit"] = class_explicit
    if merged.get("include_general") is None:
        merged["include_general"] = True
    return merged


def _canonical_query_context(result: dict, query: dict, classes: list[str]) -> dict:
    def valid_date(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None

    class_id = result.get("class_id")
    if class_id not in classes:
        requested_class = query.get("class_id")
        class_id = requested_class if requested_class in classes else None
    start_date = valid_date(result.get("start_date")) or valid_date(query.get("start_date"))
    finish_date = valid_date(result.get("finish_date")) or valid_date(query.get("finish_date"))
    result_types = result.get("types")
    types = result_types if isinstance(result_types, list) else query.get("types", [])
    types = [
        value for value in types if value in {"tarefa", "licao", "trabalho", "prova", "evento"}
    ]
    return {
        "class_id": class_id,
        "start_date": start_date,
        "finish_date": finish_date,
        "types": types,
        "subject": result.get("subject"),
        "include_general": result.get("include_general")
        if isinstance(result.get("include_general"), bool)
        else bool(query.get("include_general", True)),
        "class_explicit": bool(query.get("class_explicit")) and class_id is not None,
        "pending_clarification": result.get("clarification_code"),
    }


def _mentioned_classes(message: str, classes: list[str]) -> list[str]:
    text = _class_key(message)

    mentioned = []
    for class_name in classes:
        normalized = _class_key(class_name)
        if normalized and re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
            mentioned.append(class_name)
    return mentioned


def _class_key(value: str) -> str:
    """Normalize canonical Agenda IDs and the shorter labels shown to students."""
    from app.subjects import norm

    normalized = norm(value)
    normalized = re.sub(r"(?<=\d)o\b", "", normalized)
    normalized = re.sub(r"\btec\b", "tech", normalized)
    return normalized


def _format_clarification(result: dict) -> str:
    code = result.get("clarification_code")
    options = result.get("options") or []
    if code == "multiple_classes":
        return MULTI_CLASS_QUESTION
    if code == "missing_class":
        return MISSING_CLASS_QUESTION
    if code == "missing_start_date":
        return MISSING_START_QUESTION
    if code == "ambiguous_subject":
        if options:
            return "Qual destas matérias você quis dizer?\n" + "\n".join(
                f"• {name}" for name in options
            )
        return "Qual matéria você quis dizer?"
    if code == "unknown_subject":
        if options:
            return "Não encontrei essa matéria. Qual destas devo procurar?\n" + "\n".join(
                f"• {name}" for name in options
            )
        return "Não encontrei essa matéria cadastrada. Qual matéria devo procurar?"
    if code == "unknown_class":
        if options:
            return "Não reconheci essa turma. Escolha uma destas turmas:\n" + "\n".join(
                f"• {name}" for name in options
            )
        return MISSING_CLASS_QUESTION
    if code == "invalid_dates":
        return "A data inicial precisa ser anterior ou igual à data final. Qual período devo consultar?"
    if code == "date_parse":
        return "Não consegui identificar essa data. Qual período devo consultar?"
    return UNSURE_QUESTION


def _pending_question(reason: str | None) -> str:
    """Return safe, static dialogue context for a clarification being answered."""
    return {
        "multiple_classes": MULTI_CLASS_QUESTION,
        "ambiguous_monday": "Você quer dizer hoje ou a próxima segunda-feira?",
        "missing_class": MISSING_CLASS_QUESTION,
        "unknown_class": "Não reconheci a turma. Qual turma deseja consultar?",
        "ambiguous_subject": "Qual matéria você quis dizer?",
        "unknown_subject": "Não encontrei essa matéria. Qual matéria devo procurar?",
        "missing_start_date": MISSING_START_QUESTION,
        "invalid_dates": "A data inicial precisa ser anterior ou igual à final. Qual período devo consultar?",
        "date_parse": "Não consegui identificar essa data. Qual período devo consultar?",
        "unclear": UNSURE_QUESTION,
    }.get(reason or "", UNSURE_QUESTION)


def _display_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value


def _format_result(result: dict) -> tuple[str, list[dict]]:
    if result.get("error"):
        if result.get("error_code") == "period_limit":
            return TEMPORAL_GUARD, []
        return ERROR_REPLY, []
    if result.get("clarification_code"):
        return _format_clarification(result), []

    items = result.get("items")
    if not isinstance(items, list):
        return ERROR_REPLY, []

    start = result.get("start_date", "")
    finish = result.get("finish_date", "")
    class_name = result.get("class_id") or "a turma selecionada"
    subject = result.get("subject")
    if not items:
        answer = (
            f"Não encontrei atividades de {_display_date(start)} a {_display_date(finish)} "
            f"para {class_name} com esses filtros."
        )
        if subject:
            answer += f"\nMatéria selecionada: {subject}."
        if result.get("future_recurrence_warning") or result.get("missing_occurrences_detected"):
            answer += "\n\n" + RECURRENCE_WARNING
        return answer, []

    count = len(items)
    answer = (
        f"Encontrei {count} atividade{'s' if count != 1 else ''} de "
        f"{_display_date(start)} a {_display_date(finish)} para {class_name}."
    )
    if subject:
        answer += f"\nMatéria selecionada: {subject}."
    if result.get("future_recurrence_warning") or result.get("missing_occurrences_detected"):
        answer += "\n\n" + RECURRENCE_WARNING
    safe_cards = [
        {
            "title": item.get("title", "Atividade"),
            "type": item.get("type", "evento"),
            "type_label": item.get("type_label", "Atividade"),
            "subject": item.get("subject"),
            "date": item.get("date", ""),
            "time": item.get("time"),
            "is_general": bool(item.get("is_general")),
            "recurrence_summary": item.get("recurrence_summary"),
            "was_overridden": bool(item.get("was_overridden")),
            "url": item.get("url", "https://tech-2d.github.io/Agenda/"),
        }
        for item in items
    ]
    return answer, safe_cards


def build_assistant_graph(
    default_class: str | None,
    classes: list[str],
    previous_query: dict | None = None,
    pending_message: str | None = None,
    pending_reason: str | None = None,
    classifier=None,
):
    """Build a LangGraph that extracts intent, calls one read-only tool, then formats in code.

    The model never sees database rows and cannot compose arbitrary user-facing output.
    """
    settings = get_settings()
    if classifier is None:
        llm = ChatGroq(
            model=settings.groq_model,
            temperature=settings.llm_temperature,
            model_kwargs={"top_p": settings.llm_top_p},
            api_key=settings.groq_api_key,
            request_timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
        classifier = llm.with_structured_output(RequestIntent, method="json_schema", strict=True)

    @tool("consultar_atividades", args_schema=LookupArgs)
    async def consultar_atividades(
        start_date: str | None = None,
        finish_date: str | None = None,
        types: list[ActivityType] | None = None,
        subject: str | None = None,
        class_id: str | None = None,
        include_general: bool = True,
    ) -> str:
        """Consulta atividades cadastradas para uma turma e período, sem alterar o banco."""
        try:
            filters = ActivityFilters(
                start_date=start_date,
                finish_date=finish_date,
                types=types or [],
                subject=subject,
                class_id=class_id,
                include_general=include_general,
            )
            result = await query_activities(filters, default_class or "", classes)
            return json.dumps(result, ensure_ascii=False, default=str)
        except ValueError:
            return json.dumps({"clarification_code": "date_parse"}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 - tool boundary returns no internal details.
            logger.error("Activity lookup failed (%s)", type(exc).__name__)
            return json.dumps({"error": "agenda_unavailable"}, ensure_ascii=False)

    async def classify_node(state: AssistantState) -> dict:
        today = state.get("today") or today_local().isoformat()
        system = _system_prompt(today, state.get("previous_query", previous_query))
        messages = [SystemMessage(content=system)]
        resumed_message = state.get("pending_message", pending_message)
        if resumed_message:
            question = _pending_question(state.get("pending_reason", pending_reason))
            messages.extend(
                [
                    HumanMessage(content=resumed_message),
                    AIMessage(content=question),
                ]
            )
        messages.append(HumanMessage(content=state["message"]))
        raw = await classifier.ainvoke(messages)
        intent = raw if isinstance(raw, RequestIntent) else RequestIntent.model_validate(raw)
        return {"intent": intent}

    async def consultation_node(state: AssistantState) -> dict:
        intent = state["intent"]
        if intent.action == "refuse" or intent.clarification_reason == "off_topic":
            return {"result": {"clarification_code": "off_topic"}}
        if intent.action == "clarify" or intent.clarification_reason != "none":
            code = intent.clarification_reason
            return {"result": {"clarification_code": code if code != "none" else "unclear"}}

        query_context = _merge_follow_up(intent, state.get("previous_query", previous_query))
        mentioned = _mentioned_classes(state["message"], classes)
        previous = state.get("previous_query", previous_query) or {}
        if len(mentioned) > 1:
            result = {"clarification_code": "multiple_classes"}
            answer, cards = _format_result(result)
            return {"result": result, "answer": answer, "cards": cards}
        if len(mentioned) == 1:
            query_context["class_id"] = mentioned[0]
            query_context["class_explicit"] = True
        elif intent.inherit_previous and previous.get("class_explicit"):
            query_context["class_id"] = previous.get("class_id")
            query_context["class_explicit"] = query_context["class_id"] in classes
        elif intent.class_id is not None:
            if intent.class_id == default_class:
                # If the model echoed the browser's selection without the user naming
                # a class, preserve it as a default filter, not an explicit override.
                query_context["class_id"] = None
                query_context["class_explicit"] = False
            else:
                result = {"clarification_code": "unknown_class", "options": classes}
                safe_query = _canonical_query_context(result, query_context, classes)
                answer, cards = _format_result(result)
                return {
                    "result": result,
                    "query_context": safe_query,
                    "answer": answer,
                    "cards": cards,
                }
        # Validate the class before using it as the default. Public catalog access permits
        # every active class, but the request always resolves to exactly one class.
        tool_arguments = {
            key: value for key, value in query_context.items() if key in LookupArgs.model_fields
        }
        tool_result = await consultar_atividades.ainvoke(tool_arguments)
        try:
            result = json.loads(tool_result)
        except (json.JSONDecodeError, TypeError):
            result = {"error": "agenda_unavailable"}

        canonical_query = _canonical_query_context(result, query_context, classes)
        answer, cards = _format_result(result)
        return {
            "result": result,
            "query_context": canonical_query,
            "answer": answer,
            "cards": cards,
        }

    async def finish_node(state: AssistantState) -> dict:
        intent = state.get("intent")
        if intent is None:
            return {"answer": REFUSAL, "cards": []}
        if intent.action == "refuse" or intent.clarification_reason == "off_topic":
            return {"answer": REFUSAL, "cards": []}
        if intent.action == "clarify":
            query_context = _merge_follow_up(intent, state.get("previous_query", previous_query))
            reason = intent.clarification_reason
            if reason == "none":
                reason = "unclear"
            canonical_query = _canonical_query_context(
                {"clarification_code": reason}, query_context, classes
            )
            return {
                "answer": _format_clarification({"clarification_code": reason}),
                "cards": [],
                "query_context": canonical_query,
            }
        result = state.get("result", {})
        answer, cards = _format_result(result)
        return {"answer": answer, "cards": cards}

    def route(state: AssistantState) -> str:
        return (
            "consult" if state.get("intent") and state["intent"].action == "consult" else "finish"
        )

    builder = StateGraph(AssistantState)
    builder.add_node("classify", classify_node)
    builder.add_node("consult", consultation_node)
    builder.add_node("finish", finish_node)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route, {"consult": "consult", "finish": "finish"})
    builder.add_edge("consult", "finish")
    builder.add_edge("finish", END)
    return builder.compile()


def ambiguous_monday(message: str, today=None) -> bool:
    import re

    from app.dates import today_local

    local_today = today or today_local()
    text = message.casefold()
    asks_about_monday = bool(re.search(r"\bsegunda(?:-feira)?\b", text))
    explicit_choice = any(
        phrase in text
        for phrase in (
            "hoje",
            "próxima segunda",
            "proxima segunda",
            "segunda que vem",
            "semana que vem",
        )
    )
    return local_today.weekday() == 0 and asks_about_monday and not explicit_choice


def is_in_scope(message: str) -> bool:
    """Allow recognizable activity lookups to reach the closed-schema intent model."""
    from app.subjects import ALIASES, OFFICIAL_SUBJECTS, norm

    text = norm(message)
    lookup_terms = (
        "quais",
        "qual",
        "tem",
        "tenho",
        "temos",
        "mostre",
        "mostrar",
        "lista",
        "listar",
        "veja",
        "ver",
        "buscar",
        "consulte",
        "consultar",
        "procure",
        "quando",
        "existe",
        "alguma",
        "algum",
        "o que",
        "me mostra",
        "me diga",
        "me fale",
        "há",
        "ha",
    )
    activity_terms = (
        "agenda",
        "atividade",
        "atividades",
        "tarefa",
        "tarefas",
        "licao",
        "licoes",
        "trabalho",
        "trabalhos",
        "prova",
        "provas",
        "evento",
        "eventos",
        "entrega",
        "entregas",
        "prazo",
        "prazos",
        "vencimento",
        "vencimentos",
        "turma",
        "turmas",
        "materia",
        "materias",
    )
    time_terms = (
        "hoje",
        "amanha",
        "ontem",
        "semana",
        "mes",
        "ano",
        "segunda",
        "terca",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "domingo",
        "dia",
        "depois de amanha",
    )
    has_lookup = any(
        re.search(rf"(?<![a-z0-9]){re.escape(norm(term))}(?![a-z0-9])", text)
        for term in lookup_terms
    )
    if any(
        phrase in text
        for phrase in (
            "todas as turmas",
            "todas turmas",
            "duas turmas",
            "varias turmas",
            "mais de uma turma",
        )
    ):
        return True
    has_activity = any(term in text for term in activity_terms)
    has_time = any(term in text for term in time_terms)
    subject_names = [norm(name) for name in OFFICIAL_SUBJECTS]
    subject_names.extend(norm(alias) for aliases in ALIASES.values() for alias in aliases)
    has_subject = any(
        name and (text == name or f" {name} " in f" {text} ") for name in subject_names
    )
    help_terms = (
        "ajuda",
        "ajudar",
        "ajude",
        "resolver",
        "resolva",
        "ensina",
        "ensine",
        "ensinar",
        "explica",
        "explique",
        "explicar",
        "resposta",
        "faca",
        "script",
        "programar",
        "escreva",
        "crie",
        "gere",
    )
    has_help_intent = any(
        re.search(rf"(?<![a-z0-9]){re.escape(norm(term))}(?![a-z0-9])", text) for term in help_terms
    )

    if has_help_intent and not (has_activity and has_lookup):
        return False
    if has_activity and (has_lookup or has_time or "?" in message):
        return True
    if (
        has_time
        and has_lookup
        and any(term in text for term in ("tenho", "temos", "alguma", "algum", "coisa", "algo"))
    ):
        return True
    if has_activity and has_subject:
        return True
    if has_subject:
        return True
    return bool(has_activity and len(text.split()) <= 2)


def requests_multiple_classes(message: str, classes: list[str]) -> bool:
    """Detect explicit multi-class requests before the model can pick one arbitrarily."""
    import re

    text = _class_key(message)
    all_classes_phrases = (
        "todas as turmas",
        "todas turmas",
        "todos os cursos",
        "cada turma",
        "todas as classes",
        "todas as salas",
        "todas as turmas ao mesmo tempo",
        "duas turmas",
        "tres turmas",
        "várias turmas",
        "varias turmas",
        "mais de uma turma",
        "turmas diferentes",
        "all classes",
        "outra turma",
        "mais uma turma",
    )
    if any(_class_key(phrase) in text for phrase in all_classes_phrases):
        return True
    if re.search(r"\b(?:duas|dois|[2-9]|varias|todas|cada)\s+(?:as?\s+)?turmas?\b", text):
        return True

    matched = set()
    for class_name in classes:
        normalized = _class_key(class_name)
        if normalized and re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
            matched.add(class_name)
    if len(matched) > 1:
        return True
    return len(matched) == 0 and re.search(r"\bturmas\b", text) is not None
