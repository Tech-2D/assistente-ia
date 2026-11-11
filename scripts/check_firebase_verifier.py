"""Check public Firebase certificate retrieval without accessing a user account.

Requires the development dependencies from `pip install -e ".[test]"`. The token
and RSA key are generated in memory; the token is verified locally and is not sent
to Google. The only external request fetches Google's public signing certificates.
"""

from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from google.oauth2 import id_token

from app import security


def main() -> int:
    project = security.get_settings().firebase_project_id
    if not project:
        print("Projeto Firebase não configurado.")
        return 2

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    token = jwt.encode(
        {
            "aud": project,
            "iss": f"https://securetoken.google.com/{project}",
            "sub": "synthetic-test-user",
            "iat": now,
            "exp": now + 300,
            "auth_time": now,
        },
        key,
        algorithm="RS256",
        headers={"kid": "synthetic-test-key"},
    )
    original_fetch = id_token._fetch_certs
    certs_received = False

    def recording_fetch(*args, **kwargs):
        nonlocal certs_received
        certs = original_fetch(*args, **kwargs)
        if not isinstance(certs, dict) or not certs:
            raise ValueError("empty certificate set")
        certs_received = True
        return certs

    id_token._fetch_certs = recording_fetch
    try:
        try:
            security.firebase_user(token)
        except HTTPException as exc:
            if certs_received and exc.status_code == 401:
                print("Certificados públicos obtidos; assinatura fictícia rejeitada.")
                return 0
            print("Não foi possível confirmar a verificação de certificados Firebase.")
            return 1
        print("Falha: o token fictício foi aceito indevidamente.")
        return 1
    finally:
        id_token._fetch_certs = original_fetch


if __name__ == "__main__":
    raise SystemExit(main())
