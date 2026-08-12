from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from flagship_lab.auth import OIDCJWKSTokenVerifier


class StaticJWKClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token):
        return type("SigningKey", (), {"key": self.key})()


def _token(private_key, **overrides):
    now = datetime.now(timezone.utc)
    claims = {"sub": "alice", "tenant_id": "alpha", "roles": ["analyst"], "iat": now,
              "exp": now + timedelta(minutes=5), "aud": "flagship-api", "iss": "https://identity.example.com"}
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def test_oidc_verifier_validates_signature_issuer_audience_roles_and_tenant():
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OIDCJWKSTokenVerifier("https://identity.example.com", "flagship-api",
                                    "https://identity.example.com/.well-known/jwks.json",
                                    jwks_client=StaticJWKClient(private_key.public_key()))
    assert verifier.verify(_token(private_key))["tenant_id"] == "alpha"
    with pytest.raises(jwt.InvalidAudienceError):
        verifier.verify(_token(private_key, aud="another-api"))
    with pytest.raises(jwt.InvalidTokenError):
        verifier.verify(_token(private_key, roles=["superuser"]))
    with pytest.raises(jwt.InvalidTokenError):
        verifier.verify(_token(private_key, tenant_id="../escape"))
