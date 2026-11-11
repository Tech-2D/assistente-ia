from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from scripts import check_firebase_verifier as diagnostic


@pytest.mark.parametrize(
    ("status", "fetch_certificates", "expected"),
    [(401, True, 0), (401, False, 1), (503, False, 1), (None, True, 1)],
)
def test_diagnostic_requires_certificate_fetch_and_rejection(
    monkeypatch, status, fetch_certificates, expected
):
    monkeypatch.setattr(
        diagnostic.security, "get_settings", lambda: SimpleNamespace(firebase_project_id="test")
    )
    monkeypatch.setattr(
        diagnostic.id_token, "_fetch_certs", lambda *args, **kwargs: {"test": "key"}
    )

    def verify(_token):
        if fetch_certificates:
            diagnostic.id_token._fetch_certs(None, None)
        if status is not None:
            raise HTTPException(status, "test")
        return "user"

    monkeypatch.setattr(diagnostic.security, "firebase_user", verify)
    assert diagnostic.main() == expected
