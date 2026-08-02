from __future__ import annotations

import hmac
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


_bearer = HTTPBearer(auto_error=False)


def _credentials_or_401(
    credentials: HTTPAuthorizationCredentials | None,
    *,
    message: str = "missing bearer token",
) -> str:
    if not credentials or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> bool:
    token = os.getenv("ADMIN_API_TOKEN") or os.getenv("ADMIN_PASSWORD")
    if not token:
        raise HTTPException(status_code=503, detail="admin API token is not configured")

    presented = _credentials_or_401(credentials)
    if not hmac.compare_digest(presented, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
