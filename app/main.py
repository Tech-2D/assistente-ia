from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from app.assistant import (
    ERROR_REPLY,
    REFUSAL,
    ambiguous_monday,
    build_assistant_graph,
    is_in_scope,
    requests_multiple_classes,
)
from app.classes import list_classes
from app.config import get_settings
from app.limits import RateLimiter, RateLimitExceeded
from app.security import blocked_input, blocked_terms, firebase_user

logger = logging.getLogger(__name__)
settings = get_settings()
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
RATE_LIMIT_PATH = Path(settings.rate_limit_db).expanduser()
if not RATE_LIMIT_PATH.is_absolute():
    RATE_LIMIT_PATH = ROOT / RATE_LIMIT_PATH

# Session state is memory-only, bound to one Firebase UID, and removed after inactivity.
# No user transcript or activity rows are persisted to disk.
sessions: dict[str, dict] = {}
session_registry_lock = asyncio.Lock()

BLOCKED_REPLY = "Não posso ajudar com esse tipo de mensagem. Vamos manter a conversa respeitosa."
AUTH_REQUIRED = "Autenticação necessária."


def prune_sessions(now: float | None = None) -> None:
    current = now if now is not None else time.time()
    ttl = settings.session_ttl_minutes * 60
    for session_id, state in list(sessions.items()):
        lock = state.get("lock")
        if current - state["updated"] > ttl and not (lock and lock.locked()):
            sessions.pop(session_id, None)


async def _session_reaper() -> None:
    interval = min(max(settings.session_ttl_minutes * 15, 30), 300)
    while True:
        await asyncio.sleep(interval)
        async with session_registry_lock:
            prune_sessions()


@asynccontextmanager
async def lifespan(_app):
    reaper = asyncio.create_task(_session_reaper())
    try:
        yield
    finally:
        reaper.cancel()
        with suppress(asyncio.CancelledError):
            await reaper


app = FastAPI(title="Tech-2D Agenda Assistant", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
limiter = RateLimiter(
    str(RATE_LIMIT_PATH), settings.daily_message_limit, settings.rate_limit_enabled
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    session_id: str | None = None
    preferred_class: str | None = None


class ActivityCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    type: Literal["tarefa", "licao", "trabalho", "prova", "evento"] | str
    type_label: str
    subject: str | None = None
    date: str
    time: str | None = None
    is_general: bool
    recurrence_summary: str | None = None
    was_overridden: bool = False
    url: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    cards: list[ActivityCard] = Field(default_factory=list)
    remaining_messages: int | None = None


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(401, AUTH_REQUIRED)
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        raise HTTPException(401, AUTH_REQUIRED)
    return token.strip()


def _session_id_or_new(value: str | None) -> str:
    if value is None:
        return str(uuid.uuid4())
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(400, "Sessão inválida.") from exc
    if str(parsed) != value.lower():
        raise HTTPException(400, "Sessão inválida.")
    return str(parsed)


def _response(
    session_id: str,
    answer: str,
    remaining: int | None,
    cards: list[dict] | None = None,
) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        answer=answer,
        cards=cards or [],
        remaining_messages=remaining,
    )


async def _get_or_create_session(session_id: str, uid: str, preferred_class: str | None) -> dict:
    async with session_registry_lock:
        now = time.time()
        prune_sessions(now)
        state = sessions.get(session_id)
        if state and state["uid"] != uid:
            raise HTTPException(404, "Sessão não encontrada.")
        if state is None:
            state = {
                "uid": uid,
                "updated": now,
                "preferred_class": preferred_class,
                "last_query": None,
                "pending_message": None,
                "pending_reason": None,
                "lock": asyncio.Lock(),
            }
            sessions[session_id] = state
        return state


async def _process_chat(
    body: ChatRequest,
    uid: str,
    message: str,
    session_id: str,
    state: dict,
) -> ChatResponse:
    if "preferred_class" in body.model_fields_set:
        state["preferred_class"] = body.preferred_class
    state["updated"] = time.time()

    try:
        remaining = limiter.consume(uid)
    except RateLimitExceeded:
        raise HTTPException(429, "Você atingiu o limite diário de mensagens.") from None

    if blocked_input(message, blocked_terms(settings.blocked_terms)):
        state["last_query"] = None
        state["pending_message"] = None
        state["pending_reason"] = None
        return _response(session_id, BLOCKED_REPLY, remaining)

    pending_message = state.get("pending_message")
    if ambiguous_monday(message):
        state["pending_message"] = message
        state["pending_reason"] = "ambiguous_monday"
        return _response(
            session_id,
            "Você quer dizer hoje ou a próxima segunda-feira?",
            remaining,
        )

    if not is_in_scope(message) and not pending_message and not state.get("last_query"):
        return _response(session_id, REFUSAL, remaining)

    try:
        available_classes = await list_classes()
        if requests_multiple_classes(message, available_classes):
            state["pending_message"] = message
            state["pending_reason"] = "multiple_classes"
            return _response(
                session_id,
                "A consulta é feita para uma turma por vez. Qual turma você quer consultar?",
                remaining,
            )
    except Exception as exc:  # noqa: BLE001 - dependency boundary hides internal errors.
        logger.error("Class catalog unavailable (%s)", type(exc).__name__)
        return _response(session_id, ERROR_REPLY, remaining)

    if not settings.groq_api_key:
        raise HTTPException(503, "O provedor de IA ainda não está configurado.")

    try:
        preferred_class = state.get("preferred_class")
        if preferred_class not in available_classes:
            preferred_class = None
        graph = build_assistant_graph(
            default_class=preferred_class,
            classes=available_classes,
            previous_query=state.get("last_query"),
            pending_message=pending_message,
            pending_reason=state.get("pending_reason"),
        )
        result = await graph.ainvoke(
            {
                "message": message,
                "previous_query": state.get("last_query"),
                "pending_message": pending_message,
                "pending_reason": state.get("pending_reason"),
            }
        )
        state["updated"] = time.time()
        intent = result.get("intent")
        clarification_reason = None
        if intent and intent.action == "clarify":
            clarification_reason = intent.clarification_reason
        elif intent and intent.action == "consult":
            clarification_reason = (result.get("result") or {}).get("clarification_code")

        is_refusal = bool(
            intent and (intent.action == "refuse" or intent.clarification_reason == "off_topic")
        )
        if is_refusal:
            state["last_query"] = None
            state["pending_message"] = None
            state["pending_reason"] = None
        elif clarification_reason and clarification_reason not in {"none", "off_topic"}:
            # Keep the original request so the next reply can fill the missing
            # filter instead of starting a context-free conversation.
            state["pending_message"] = pending_message or message
            state["pending_reason"] = clarification_reason
        else:
            state["pending_message"] = None
            state["pending_reason"] = None
        if isinstance(result.get("query_context"), dict):
            state["last_query"] = result["query_context"]
        return _response(
            session_id,
            result.get("answer") or ERROR_REPLY,
            remaining,
            result.get("cards", []),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - never return provider/database exceptions.
        logger.error("Assistant request failed (%s)", type(exc).__name__)
        return _response(session_id, ERROR_REPLY, remaining)


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
def client_config():
    """Firebase web config is public client configuration, never a service credential."""
    return {
        "firebase": {
            "apiKey": settings.vite_firebase_api_key,
            "authDomain": settings.vite_firebase_auth_domain,
            "projectId": settings.vite_firebase_project_id,
            "appId": settings.vite_firebase_app_id,
            "storageBucket": settings.vite_firebase_storage_bucket,
            "messagingSenderId": settings.vite_firebase_messaging_sender_id,
        }
    }


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.app_env}


@app.get("/ready")
async def ready():
    """Readiness check without returning credentials or database contents."""
    missing = []
    if not settings.groq_api_key:
        missing.append("groq")
    if not settings.vite_firebase_api_key or not settings.vite_firebase_app_id:
        missing.append("firebase_web")
    if settings.vite_firebase_project_id != settings.firebase_project_id:
        missing.append("firebase_project_mismatch")
    if not settings.database_url or not settings.db_sslrootcert:
        missing.append("agenda_database")
    if missing:
        return JSONResponse(status_code=503, content={"ready": False, "missing": missing})
    try:
        classes = await list_classes()
        if not classes:
            return JSONResponse(
                status_code=503,
                content={"ready": False, "missing": ["agenda_classes"]},
            )
    except Exception:  # noqa: BLE001 - boundary returns a generic readiness state.
        return JSONResponse(
            status_code=503,
            content={"ready": False, "missing": ["agenda_database"]},
        )
    return {"ready": True, "missing": []}


@app.get("/api/classes")
async def classes(authorization: str | None = Header(default=None)):
    firebase_user(_bearer_token(authorization))
    try:
        return {"classes": await list_classes()}
    except Exception as exc:  # noqa: BLE001 - dependency boundary hides internal errors.
        logger.error("Class catalog unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, "Agenda temporariamente indisponível.") from None


@app.delete("/api/session/{session_id}")
async def close_session(session_id: str, authorization: str | None = Header(default=None)):
    uid = firebase_user(_bearer_token(authorization))
    async with session_registry_lock:
        state = sessions.get(session_id)
    if state and state["uid"] == uid:
        lock = state.setdefault("lock", asyncio.Lock())
        async with lock, session_registry_lock:
            if sessions.get(session_id) is state:
                sessions.pop(session_id, None)
    return {"closed": True}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    authorization: str | None = Header(default=None),
):
    uid = firebase_user(_bearer_token(authorization))
    message = body.message.strip()
    if not message:
        raise HTTPException(422, "A mensagem não pode ficar vazia.")

    session_id = _session_id_or_new(body.session_id)
    state = await _get_or_create_session(session_id, uid, body.preferred_class)
    async with state["lock"]:
        return await _process_chat(body, uid, message, session_id, state)
