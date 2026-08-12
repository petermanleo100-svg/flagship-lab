from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Callable, Protocol

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


ALGORITHM = "HS256"
VALID_ROLES = frozenset({"viewer", "analyst", "reviewer", "admin"})
bearer = HTTPBearer(auto_error=False)


class TokenVerifier(Protocol):
    def verify(self, token: str) -> dict: ...


@dataclass(frozen=True)
class HMACTokenVerifier:
    secret: str

    def verify(self, token: str) -> dict:
        return decode_token(token, self.secret)


class OIDCJWKSTokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str, *, jwks_client=None,
                 algorithms: tuple[str, ...] = ("RS256", "ES256")):
        if not issuer.startswith("https://") and issuer not in {"http://localhost", "http://127.0.0.1"}:
            raise ValueError("OIDC issuer must use HTTPS")
        if not audience or not jwks_url:
            raise ValueError("OIDC audience and JWKS URL are required")
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.algorithms = algorithms
        self.jwks_client = jwks_client or jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5)

    def verify(self, token: str) -> dict:
        signing_key = self.jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=list(self.algorithms),
                            audience=self.audience, issuer=self.issuer,
                            options={"require": ["sub", "tenant_id", "roles", "iat", "exp", "aud", "iss"]})
        unknown = set(claims.get("roles", [])) - VALID_ROLES
        if unknown or not claims.get("roles"):
            raise jwt.InvalidTokenError("token contains invalid roles")
        tenant = claims.get("tenant_id", "")
        if not tenant or len(tenant) > 64 or not tenant.replace("_", "").replace("-", "").isalnum():
            raise jwt.InvalidTokenError("token contains invalid tenant_id")
        scopes = claims.get("resource_scopes")
        if not isinstance(scopes, list) or not scopes or not all(isinstance(scope, str) for scope in scopes):
            raise jwt.InvalidTokenError("token contains invalid resource_scopes")
        return claims


def issue_token(
    subject: str, roles: list[str], secret: str, ttl_minutes: int = 60, tenant_id: str = "default",
    resource_scopes: list[str] | None = None,
) -> str:
    if not tenant_id or len(tenant_id) > 64 or not tenant_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("tenant_id must use 1-64 letters, digits, underscores or hyphens")
    unknown = set(roles) - VALID_ROLES
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")
    now = datetime.now(timezone.utc)
    scopes = resource_scopes if resource_scopes is not None else ["*:*:*"]
    if not scopes or not all(isinstance(scope, str) and 3 <= len(scope) <= 300 for scope in scopes):
        raise ValueError("resource_scopes must contain valid scope strings")
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "roles": sorted(set(roles)),
        "resource_scopes": sorted(set(scopes)),
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "aud": "flagship-lab",
        "iss": "flagship-lab",
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(
        token,
        secret,
        algorithms=[ALGORITHM],
        audience="flagship-lab",
        issuer="flagship-lab",
        options={"require": ["sub", "tenant_id", "roles", "iat", "exp", "aud", "iss"]},
    )


def require_verified_roles(verifier: TokenVerifier, *allowed: str) -> Callable:
    allowed_set = set(allowed)
    if not allowed_set or not allowed_set <= VALID_ROLES:
        raise ValueError("require_roles must receive known roles")

    def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        try:
            claims = verifier.verify(credentials.credentials)
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")
        if not (set(claims.get("roles", [])) & allowed_set):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return claims

    return dependency


def require_roles(secret: str, *allowed: str) -> Callable:
    """Backward-compatible development helper."""
    return require_verified_roles(HMACTokenVerifier(secret), *allowed)
