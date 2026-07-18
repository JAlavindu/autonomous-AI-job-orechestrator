from fastapi import APIRouter, Depends, HTTPException, status

from src.auth.deps import require_min_role
from src.auth.service import api_key_service
from src.auth.service_account_service import service_account_service
from src.core.logging_config import get_logger
from src.models.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
    ApiKeySummary,
    Principal,
    Role,
    ServiceAccountCreateRequest,
    ServiceAccountCreatedResponse,
    ServiceAccountListResponse,
    ServiceAccountSummary,
)

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/admin/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(
    body: ApiKeyCreateRequest,
    principal: Principal = Depends(require_min_role(Role.OPERATOR)),
):
    row, raw_key = api_key_service.create_key(
        name=body.name,
        role=body.role,
        tenant_id=principal.tenant_id,
    )
    logger.info("Created API key %s (%s) for tenant %s", row.name, row.id, row.tenant_id)
    return ApiKeyCreatedResponse(
        id=row.id,
        name=row.name,
        role=Role(row.role),
        key_prefix=row.key_prefix,
        api_key=raw_key,
        tenant_id=row.tenant_id,
        created_at=row.created_at,
    )


@router.get("/admin/api-keys", response_model=ApiKeyListResponse)
def list_api_keys(
    principal: Principal = Depends(require_min_role(Role.OPERATOR)),
):
    rows = api_key_service.list_keys(tenant_id=principal.tenant_id)
    items = [
        ApiKeySummary(
            id=row.id,
            name=row.name,
            role=Role(row.role),
            key_prefix=row.key_prefix,
            tenant_id=row.tenant_id,
            enabled=row.enabled,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
        )
        for row in rows
    ]
    return ApiKeyListResponse(items=items, total=len(items))


@router.delete("/admin/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    principal: Principal = Depends(require_min_role(Role.OPERATOR)),
):
    revoked = api_key_service.revoke_key(key_id, tenant_id=principal.tenant_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    logger.info("Revoked API key %s for tenant %s", key_id, principal.tenant_id)
    return None

@router.post(
    "/admin/service-accounts",
    response_model=ServiceAccountCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_service_account(
    body: ServiceAccountCreateRequest,
    principal: Principal = Depends(require_min_role(Role.OPERATOR)),
):
    row, client_secret = service_account_service.create(
        name=body.name,
        role=body.role,
        tenant_id=principal.tenant_id,
    )
    logger.info(
        "Created service account %s (%s) for tenant %s", row.name, row.id, row.tenant_id
    )
    return ServiceAccountCreatedResponse(
        id=row.id,
        name=row.name,
        role=Role(row.role),
        client_id=row.client_id,
        client_secret=client_secret,  # shown once
        tenant_id=row.tenant_id,
        created_at=row.created_at,
    )


@router.get("/admin/service-accounts", response_model=ServiceAccountListResponse)
def list_service_accounts(
    principal: Principal = Depends(require_min_role(Role.OPERATOR)),
):
    rows = service_account_service.list_accounts(tenant_id=principal.tenant_id)
    items = [
        ServiceAccountSummary(
            id=row.id,
            name=row.name,
            role=Role(row.role),
            client_id=row.client_id,
            tenant_id=row.tenant_id,
            enabled=row.enabled,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return ServiceAccountListResponse(items=items, total=len(items))


@router.delete(
    "/admin/service-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_service_account(
    account_id: str,
    principal: Principal = Depends(require_min_role(Role.OPERATOR)),
):
    revoked = service_account_service.revoke(account_id, tenant_id=principal.tenant_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Service account not found")
    logger.info(
        "Revoked service account %s for tenant %s", account_id, principal.tenant_id
    )
    return None
