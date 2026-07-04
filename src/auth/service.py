from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from src.auth.security import generate_api_key, hash_api_key, key_prefix
from src.core.config import settings
from src.core.logging_config import get_logger
from src.db.models import ApiKeyRow, TenantRow
from src.db.session import SessionLocal
from src.models.auth import Principal, Role

logger = get_logger(__name__)


class ApiKeyService:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def _ensure_default_tenant(self, db: Session) -> TenantRow:
        tenant = db.get(TenantRow, settings.DEFAULT_TENANT_ID)
        if tenant:
            return tenant
        tenant = TenantRow(id=settings.DEFAULT_TENANT_ID, name=settings.DEFAULT_TENANT_NAME)
        db.add(tenant)
        db.flush()
        return tenant

    def create_key(
        self,
        name: str,
        role: Role,
        tenant_id: str | None = None,
    ) -> tuple[ApiKeyRow, str]:
        raw_key = generate_api_key()
        hashed = hash_api_key(raw_key, settings.API_KEY_PEPPER)

        with self.session_factory() as db:
            self._ensure_default_tenant(db)
            row = ApiKeyRow(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id or settings.DEFAULT_TENANT_ID,
                name=name,
                key_prefix=key_prefix(raw_key),
                key_hash=hashed,
                role=role.value,
                enabled=True,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row, raw_key

    def import_key(
        self,
        raw_key: str,
        name: str,
        role: Role,
        tenant_id: str | None = None,
    ) -> ApiKeyRow:
        """Store a known raw key (e.g. bootstrap from env)."""
        hashed = hash_api_key(raw_key, settings.API_KEY_PEPPER)

        with self.session_factory() as db:
            self._ensure_default_tenant(db)
            row = ApiKeyRow(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id or settings.DEFAULT_TENANT_ID,
                name=name,
                key_prefix=key_prefix(raw_key),
                key_hash=hashed,
                role=role.value,
                enabled=True,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

    def validate_key(self, raw_key: str) -> Optional[Principal]:
        if not raw_key:
            return None

        hashed = hash_api_key(raw_key, settings.API_KEY_PEPPER)
        with self.session_factory() as db:
            row = db.scalar(
                select(ApiKeyRow).where(
                    ApiKeyRow.key_hash == hashed,
                    ApiKeyRow.enabled.is_(True),
                )
            )
            if not row:
                return None

            row.last_used_at = datetime.utcnow()
            db.commit()

            return Principal(
                api_key_id=row.id,
                tenant_id=row.tenant_id,
                role=Role(row.role),
                name=row.name,
            )

    def list_keys(self, tenant_id: str | None = None) -> list[ApiKeyRow]:
        with self.session_factory() as db:
            stmt = select(ApiKeyRow).order_by(ApiKeyRow.created_at.desc())
            if tenant_id:
                stmt = stmt.where(ApiKeyRow.tenant_id == tenant_id)
            return list(db.scalars(stmt).all())

    def revoke_key(self, key_id: str, tenant_id: str | None = None) -> bool:
        with self.session_factory() as db:
            row = db.get(ApiKeyRow, key_id)
            if not row:
                return False
            if tenant_id and row.tenant_id != tenant_id:
                return False
            row.enabled = False
            db.commit()
            return True

    def bootstrap_if_empty(self) -> str | None:
        raw = settings.AUTH_BOOTSTRAP_OPERATOR_KEY.strip()
        if not raw:
            return None

        with self.session_factory() as db:
            count = db.scalar(select(func.count()).select_from(ApiKeyRow)) or 0
            if count > 0:
                return None

        self.import_key(raw, name="bootstrap-operator", role=Role.OPERATOR)
        logger.warning(
            "Bootstrapped operator API key with prefix %s from AUTH_BOOTSTRAP_OPERATOR_KEY",
            key_prefix(raw),
        )
        return raw


api_key_service = ApiKeyService()