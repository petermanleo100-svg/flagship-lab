from __future__ import annotations

import fnmatch

from fastapi import HTTPException, status


def authorize_resource(claims: dict, resource_type: str, resource_id: str, action: str) -> None:
    """Authorize a signed subject claim against a canonical resource action.

    Scopes use ``type:id:action`` with segment-local ``*`` wildcards, for example
    ``tax_run:*:read``. Tenant isolation is enforced separately by every query.
    """
    required = f"{resource_type}:{resource_id}:{action}"
    scopes = claims.get("resource_scopes", [])
    if not isinstance(scopes, list) or not any(
        isinstance(scope, str) and fnmatch.fnmatchcase(required, scope) for scope in scopes
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"code": "resource_access_denied", "required": required})
