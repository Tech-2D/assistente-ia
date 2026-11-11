import ssl
from pathlib import Path
from urllib.parse import unquote, urlsplit

import asyncpg

from app.config import get_settings


def connection_options() -> dict:
    settings = get_settings()
    if not settings.database_url or not settings.db_sslrootcert:
        raise RuntimeError("Banco ou certificado TLS não configurado.")
    url = urlsplit(settings.database_url)
    if (
        url.scheme not in {"postgres", "postgresql"}
        or not url.hostname
        or not url.username
        or not url.password
        or not url.path.strip("/")
    ):
        raise RuntimeError("DATABASE_URL inválida.")
    ca_path = Path(settings.db_sslrootcert).expanduser()
    if not ca_path.is_absolute():
        ca_path = Path(__file__).resolve().parent.parent / ca_path
    if not ca_path.is_file():
        raise RuntimeError("Certificado TLS não encontrado.")
    tls = ssl.create_default_context(cafile=str(ca_path))
    tls.check_hostname = True
    tls.verify_mode = ssl.CERT_REQUIRED
    return {
        "host": url.hostname,
        "port": url.port or 5432,
        "database": unquote(url.path.lstrip("/")),
        "user": unquote(url.username),
        "password": unquote(url.password),
        "ssl": tls,
        "timeout": 8,
        "command_timeout": settings.database_statement_timeout_ms / 1000,
        "server_settings": {
            "default_transaction_read_only": "on",
            "statement_timeout": str(settings.database_statement_timeout_ms),
        },
    }


async def read_connection():
    conn = await asyncpg.connect(**connection_options())
    try:
        if await conn.fetchval("SHOW transaction_read_only") != "on":
            raise RuntimeError("A sessão PostgreSQL não está somente leitura.")
        yield conn
    finally:
        await conn.close()
