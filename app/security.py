import re
import unicodedata

from fastapi import HTTPException
from firebase_admin import auth, get_app, initialize_app

from app.config import get_settings


def firebase_user(token: str) -> str:
    settings = get_settings()
    if not settings.firebase_project_id:
        raise HTTPException(503, "Autenticação indisponível.")
    try:
        try:
            app = get_app()
        except ValueError:
            app = initialize_app(options={"projectId": settings.firebase_project_id})
        claims = auth.verify_id_token(token, app=app, check_revoked=False)
        uid = claims.get("uid") or claims.get("sub")
        if not isinstance(uid, str) or not uid:
            raise ValueError("missing uid")
        return uid
    except Exception as exc:
        raise HTTPException(401, "Sessão inválida ou expirada.") from exc


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.translate(
        str.maketrans(
            {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
        )
    )
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def blocked_terms(extra_terms: str = "") -> str:
    path = (
        __import__("pathlib").Path(__file__).parent.parent / "prompts/guardrails/blocked_terms.txt"
    )
    built_in = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    configured = [
        term.strip() for term in extra_terms.replace("\n", ",").split(",") if term.strip()
    ]
    return ",".join(dict.fromkeys(built_in + configured))


def blocked_input(message: str, terms: str) -> bool:
    normalized = f" {normalize_text(message)} "
    for term in terms.split(","):
        needle = normalize_text(term)
        if needle and f" {needle} " in normalized:
            return True
    return False
