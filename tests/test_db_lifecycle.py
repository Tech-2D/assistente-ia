import asyncio
import ssl
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app import activity_tool, classes, db
from app.types import ActivityFilters


class FakeConnection:
    def __init__(self, *, read_only="on", fail_query=False):
        self.read_only = read_only
        self.fail_query = fail_query
        self.closed = False
        self.transaction_exited = False

    @asynccontextmanager
    async def transaction(self, *, isolation, readonly):
        assert isolation == "repeatable_read"
        assert readonly is True
        try:
            yield
        finally:
            self.transaction_exited = True

    async def fetchval(self, query):
        assert query == "SHOW transaction_read_only"
        return self.read_only

    async def fetch(self, query, *args):
        if self.fail_query:
            raise RuntimeError("query failed")
        return []

    async def close(self):
        assert self.transaction_exited
        self.closed = True


def configure_connection(monkeypatch, conn):
    async def connect(**kwargs):
        return conn

    monkeypatch.setattr(db, "connection_options", dict)
    monkeypatch.setattr(db.asyncpg, "connect", connect)


def test_connection_options_identify_service_and_enforce_readonly_tls(monkeypatch, tmp_path):
    cert = tmp_path / "ca.pem"
    cert.touch()
    settings = SimpleNamespace(
        database_url="postgresql://test-user:test-password@example.test:1234/test-db",
        db_sslrootcert=str(cert),
        database_statement_timeout_ms=15000,
    )
    context = SimpleNamespace(check_hostname=False, verify_mode=None)
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    monkeypatch.setattr(db.ssl, "create_default_context", lambda cafile: context)

    options = db.connection_options()
    assert options["server_settings"]["application_name"] == "tech2d-ai-assistant"
    assert options["server_settings"]["default_transaction_read_only"] == "on"
    assert options["server_settings"]["statement_timeout"] == "15000"
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.asyncio
async def test_class_catalog_closes_connection_before_return(monkeypatch):
    conn = FakeConnection()
    configure_connection(monkeypatch, conn)
    assert await classes.list_classes()
    assert conn.closed


@pytest.mark.asyncio
async def test_early_clarification_closes_connection_before_return(monkeypatch):
    conn = FakeConnection()
    configure_connection(monkeypatch, conn)
    result = await activity_tool.query_activities(
        ActivityFilters(subject="nome inexistente 984"), "Turma A", ["Turma A"]
    )
    assert result["clarification_code"] == "unknown_subject"
    assert conn.closed


@pytest.mark.asyncio
async def test_query_exception_closes_connection_immediately(monkeypatch):
    conn = FakeConnection(fail_query=True)
    configure_connection(monkeypatch, conn)
    with pytest.raises(RuntimeError, match="query failed"):
        await classes.list_classes()
    assert conn.closed


@pytest.mark.asyncio
async def test_not_read_only_connection_is_closed(monkeypatch):
    conn = FakeConnection(read_only="off")
    configure_connection(monkeypatch, conn)
    with pytest.raises(RuntimeError, match="somente leitura"):
        await classes.list_classes()
    assert conn.closed


@pytest.mark.asyncio
async def test_cancellation_closes_connection(monkeypatch):
    conn = FakeConnection()
    started = asyncio.Event()

    async def wait_forever(query, *args):
        started.set()
        await asyncio.Event().wait()

    conn.fetch = wait_forever
    configure_connection(monkeypatch, conn)
    task = asyncio.create_task(classes.list_classes())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert conn.closed
