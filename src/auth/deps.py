from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from src.auth.service import api_key_service
from src.core.config import settings
from src.models.auth import ROLE_RANK, Principal, Role


def _extract_api_key(request: Request) -> str | None:
    header_key = request.headers.get(settings.API_KEY_HEADER)
    if header_key:
        return header_key.strip()

    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()

    return None


def get_current_principal(request: Request) -> Principal:
    if not settings.AUTH_ENABLED:
        return Principal(
            api_key_id="auth-disabled",
            tenant_id=settings.DEFAULT_TENANT_ID,
            role=Role.OPERATOR,
            name="auth-disabled",
        )

    raw_key = _extract_api_key(request)
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = api_key_service.validate_key(raw_key)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return principal


def require_min_role(min_role: Role):
    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not settings.AUTH_ENABLED:
            return principal
        if ROLE_RANK[principal.role] < ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role {min_role.value} or higher",
            )
        return principal

    return _dependency