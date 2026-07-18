from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from src.auth.service import api_key_service
from src.core.config import settings
from src.models.auth import ROLE_RANK, Principal, Role
from src.tenancy.exceptions import RateLimitExceededError
from src.tenancy.rate_limit import rate_limiter
from src.auth.jwt_service import jwt_service

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
            subject_id="auth-disabled",
            tenant_id=settings.DEFAULT_TENANT_ID,
            role=Role.OPERATOR,
            name="auth-disabled",
            auth_method="api_key",
        )

    raw_credential = _extract_api_key(request)
    if not raw_credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # JWT first: cheap local decode, no DB hit. validate_access_token returns
    # None for anything that isn't a valid, unexpired token we issued
    # (including plain API keys, which aren't JWT-shaped), so fallthrough is safe.
    principal = jwt_service.validate_access_token(raw_credential)
    if principal is None:
        principal = api_key_service.validate_key(raw_credential)

    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    
    if settings.RATE_LIMIT_ENABLED:
        try:
            rate_limiter.check(principal.tenant_id)
        except RateLimitExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc

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