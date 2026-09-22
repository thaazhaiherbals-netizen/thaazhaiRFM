"""Single-admin bearer authentication for V1; credentials never go in browser builds."""

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.config import get_settings

bearer = HTTPBearer(auto_error=False)


def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    expected = get_settings().admin_api_token.get_secret_value()
    if not expected:
        raise HTTPException(503, "Admin access is not configured")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(
            401, "Invalid admin credentials", headers={"WWW-Authenticate": "Bearer"}
        )
