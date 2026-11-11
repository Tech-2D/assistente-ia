from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import security


@pytest.fixture(autouse=True)
def no_auth_emulator(monkeypatch):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)


def test_firebase_user_returns_uid_from_verified_token(monkeypatch):
    fake_app = SimpleNamespace(project_id="test-project")
    calls = {}
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(firebase_project_id="test-project"),
    )
    monkeypatch.setattr(security, "get_app", lambda name: fake_app)

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
    monkeypatch.setattr(
        security, "get_app", lambda name: SimpleNamespace(project_id="test-project")
    )

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
    shared_app = SimpleNamespace(project_id="test-project")

    def fake_get_app(name):
        if not created:
            raise ValueError("not initialized")
        return shared_app

    def fake_initialize(*, credential, options, name):
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


def test_certificate_fetch_failure_is_unavailable_not_invalid_token(monkeypatch):
    monkeypatch.setattr(
        security, "get_settings", lambda: SimpleNamespace(firebase_project_id="test-project")
    )
    monkeypatch.setattr(
        security, "get_app", lambda name: SimpleNamespace(project_id="test-project")
    )

    def fail(*args, **kwargs):
        raise security.auth.CertificateFetchError(
            "private network detail", cause=RuntimeError("network")
        )

    monkeypatch.setattr(security.auth, "verify_id_token", fail)
    with pytest.raises(HTTPException) as error:
        security.firebase_user("token")
    assert error.value.status_code == 503
    assert "private" not in error.value.detail


def test_wrong_firebase_app_project_fails_closed(monkeypatch):
    monkeypatch.setattr(
        security, "get_settings", lambda: SimpleNamespace(firebase_project_id="test-project")
    )
    monkeypatch.setattr(
        security, "get_app", lambda name: SimpleNamespace(project_id="another-project")
    )
    with pytest.raises(HTTPException) as error:
        security.firebase_user("token")
    assert error.value.status_code == 503


def test_emulator_environment_is_not_accepted(monkeypatch):
    monkeypatch.setattr(
        security, "get_settings", lambda: SimpleNamespace(firebase_project_id="test-project")
    )
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    with pytest.raises(HTTPException) as error:
        security.firebase_user("token")
    assert error.value.status_code == 503


def test_official_sdk_verifies_signature_without_application_default_credentials(monkeypatch):
    import time
    import uuid

    import firebase_admin
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.oauth2 import id_token

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(
        security, "get_settings", lambda: SimpleNamespace(firebase_project_id="test-project")
    )
    app_name = f"test-verifier-{uuid.uuid4()}"
    monkeypatch.setattr(security, "_FIREBASE_APP_NAME", app_name)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    monkeypatch.setattr(id_token, "_fetch_certs", lambda *args, **kwargs: {"test-kid": public_pem})
    now = int(time.time())
    claims = {
        "aud": "test-project",
        "iss": "https://securetoken.google.com/test-project",
        "sub": "verified-user",
        "iat": now,
        "exp": now + 300,
        "auth_time": now,
    }

    def sign(payload, signing_key=key):
        return jwt.encode(payload, signing_key, algorithm="RS256", headers={"kid": "test-kid"})

    try:
        assert security.firebase_user(sign(claims)) == "verified-user"
        app = firebase_admin.get_app(app_name)
        assert isinstance(app.credential, security._PublicVerificationCredential)
        assert isinstance(app.credential.get_credential(), security.AnonymousCredentials)
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        invalid_tokens = (
            sign(claims, wrong_key),
            sign({**claims, "aud": "another-project"}),
            sign({**claims, "iss": "https://securetoken.google.com/another-project"}),
            sign({**claims, "sub": ""}),
            sign({**claims, "exp": now - 10}),
            jwt.encode(
                claims, "test-only-key-" * 4, algorithm="HS256", headers={"kid": "test-kid"}
            ),
        )
        for token in invalid_tokens:
            with pytest.raises(HTTPException) as error:
                security.firebase_user(token)
            assert error.value.status_code == 401
    finally:
        firebase_admin.delete_app(firebase_admin.get_app(app_name))
