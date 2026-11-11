from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import security


def test_firebase_user_returns_uid_from_verified_token(monkeypatch):
    fake_app = object()
    calls = {}
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(firebase_project_id="test-project"),
    )
    monkeypatch.setattr(security, "get_app", lambda: fake_app)

    def verify(token, *, app, check_revoked):
        calls.update(token=token, app=app, check_revoked=check_revoked)
        return {"sub": "verified-user"}

    monkeypatch.setattr(security.auth, "verify_id_token", verify)

    uid = security.firebase_user("signed-firebase-id-token")

    assert uid == "verified-user"
    assert calls == {
        "token": "signed-firebase-id-token",
        "app": fake_app,
        "check_revoked": False,
    }


def test_firebase_user_hides_invalid_token_details(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(firebase_project_id="test-project"),
    )
    monkeypatch.setattr(security, "get_app", lambda: object())

    def reject_token(*_args, **_kwargs):
        raise ValueError("private verification detail")

    monkeypatch.setattr(security.auth, "verify_id_token", reject_token)

    with pytest.raises(HTTPException) as error:
        security.firebase_user("invalid-token")

    assert error.value.status_code == 401
    assert error.value.detail == "Sessão inválida ou expirada."
    assert "private verification detail" not in str(error.value.detail)


def test_firebase_user_fails_when_project_is_not_configured(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(firebase_project_id=""),
    )

    with pytest.raises(HTTPException) as error:
        security.firebase_user("any-token")

    assert error.value.status_code == 503


def test_firebase_initialization_is_safe_under_concurrency(monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(firebase_project_id="test-project"),
    )
    created = []
    shared_app = object()

    def fake_get_app():
        if not created:
            raise ValueError("not initialized")
        return shared_app

    def fake_initialize(*, options):
        time.sleep(0.05)
        created.append(options)
        return shared_app

    monkeypatch.setattr(security, "get_app", fake_get_app)
    monkeypatch.setattr(security, "initialize_app", fake_initialize)
    monkeypatch.setattr(security.auth, "verify_id_token", lambda *args, **kwargs: {"uid": "user"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(security.firebase_user, ["token"] * 8))
    assert results == ["user"] * 8
    assert len(created) == 1
