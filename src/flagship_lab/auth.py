from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


ALGORITHM = "HS256"
VALID_ROLES = frozenset({"viewer", "analyst", "reviewer", "admin"})
bearer = HTTPBearer(auto_error=False)


def issue_token(subject: str, roles: list[str], secret: str, ttl_minutes: int = 60) -> str:
    unknown = set(roles) - VALID_ROLES
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "roles": sorted(set(roles)),
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
        options={"require": ["sub", "roles", "iat", "exp", "aud", "iss"]},
    )


def require_roles(secret: str, *allowed: str) -> Callable:
    allowed_set = set(allowed)
    if not allowed_set or not allowed_set <= VALID_ROLES:
        raise ValueError("require_roles must receive known roles")

    def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        try:
            claims = decode_token(credentials.credentials, secret)
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")
        if not (set(claims.get("roles", [])) & allowed_set):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return claims

    return dependency

