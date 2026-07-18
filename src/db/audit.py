from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.db.models import AuditLogRow


def add_audit(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    target: str,
    payload: dict | None = None,
    actor: str = "system",
) -> None:
    """Stage an audit_log row in the caller's session/transaction.

    Deliberately does NOT commit: the caller commits, so the audit entry is
    atomic with the state change it records — no audited-but-not-applied or
    applied-but-not-audited states.
    """
    db.add(
        AuditLogRow(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target=target,
            payload=payload or {},
        )
    )
