from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.auth.security import hash_api_key, key_prefix  # reuse HMAC-style hash with pepper
from src.core.config import settings
from src.db.models import ServiceAccountRow, TenantRow
from src.db.session import SessionLocal
from src.models.auth import Principal, Role


class ServiceAccountService:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def create(
        self, name: str, role: Role, tenant_id: str
    ) -> tuple[ServiceAccountRow, str]:
        client_id = f"sa_{secrets.token_urlsafe(12)}"
        client_secret = f"ssec_{secrets.token_urlsafe(32)}"
        secret_hash = hash_api_key(client_secret, settings.API_KEY_PEPPER)

        with self.session_factory() as db:
            row = ServiceAccountRow(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                name=name,
                client_id=client_id,
                secret_hash=secret_hash,
                role=role.value,
                enabled=True,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row, client_secret

    def validate_client_credentials(self, client_id: str, client_secret: str) -> Principal | None:
        if not client_id or not client_secret:
            return None
        hashed = hash_api_key(client_secret, settings.API_KEY_PEPPER)
        with self.session_factory() as db:
            row = db.scalar(
                select(ServiceAccountRow).where(
                    ServiceAccountRow.client_id == client_id,
                    ServiceAccountRow.secret_hash == hashed,
                    ServiceAccountRow.enabled.is_(True),
                )
            )
            if not row:
                return None
            return Principal(
                subject_id=row.id,
                tenant_id=row.tenant_id,
                role=Role(row.role),
                name=row.name,
                auth_method="client_credentials",
            )

    def list_accounts(self, tenant_id: str) -> list[ServiceAccountRow]:
        with self.session_factory() as db:
            stmt = (
                select(ServiceAccountRow)
                .where(ServiceAccountRow.tenant_id == tenant_id)
                .order_by(ServiceAccountRow.created_at.desc())
            )
            return list(db.scalars(stmt).all())

    def revoke(self, account_id: str, tenant_id: str) -> bool:
        with self.session_factory() as db:
            row = db.get(ServiceAccountRow, account_id)
            if not row or row.tenant_id != tenant_id:
                return False
            row.enabled = False
            db.commit()
            return True


service_account_service = ServiceAccountService()