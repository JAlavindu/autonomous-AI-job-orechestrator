from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from src.core.config import settings
from src.models.auth import AuthMethod, Principal, Role


class JwtService:
    def issue_access_token(
        self,
        *,
        subject_id: str,
        tenant_id: str,
        role: Role,
        name: str,
        auth_method: AuthMethod,
    ) -> tuple[str, int]:
        expires_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=expires_minutes)
        payload = {
            "sub": subject_id,
            "tenant_id": tenant_id,
            "role": role.value,
            "name": name,
            "auth_method": auth_method,
            "jti": str(uuid.uuid4()),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        return token, expires_minutes * 60

    def validate_access_token(self, token: str) -> Principal | None:
        if not settings.JWT_ENABLED:
            return None
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                audience=settings.JWT_AUDIENCE,
                issuer=settings.JWT_ISSUER,
            )
        except jwt.PyJWTError:
            return None

        try:
            role = Role(payload["role"])
        except (KeyError, ValueError):
            return None

        return Principal(
            subject_id=str(payload["sub"]),
            tenant_id=str(payload["tenant_id"]),
            role=role,
            name=str(payload.get("name", "jwt-user")),
            auth_method=payload.get("auth_method", "jwt"),
        )


jwt_service = JwtService()