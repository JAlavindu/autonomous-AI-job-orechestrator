from fastapi import APIRouter, HTTPException, status

from src.auth.jwt_service import jwt_service
from src.auth.service_account_service import service_account_service
from src.core.config import settings
from src.core.logging_config import get_logger
from src.models.auth import TokenRequest, TokenResponse

router = APIRouter()
logger = get_logger(__name__)


@router.post("/auth/token", response_model=TokenResponse)
def issue_token(body: TokenRequest):
    """OAuth2 client-credentials grant: exchange a service account's
    client_id/client_secret for a short-lived JWT access token.

    Deliberately unauthenticated — the client credentials ARE the credential.
    Accepts JSON (not form-encoding) to match the rest of the API.
    """
    if not settings.JWT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="JWT authentication is disabled",
        )

    principal = service_account_service.validate_client_credentials(
        body.client_id, body.client_secret
    )
    if principal is None:
        # Generic message: don't reveal whether the client_id exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )

    token, expires_in = jwt_service.issue_access_token(
        subject_id=principal.subject_id,
        tenant_id=principal.tenant_id,
        role=principal.role,
        name=principal.name,
        auth_method="client_credentials",
    )
    logger.info(
        "Issued access token for service account %s (tenant %s)",
        principal.subject_id,
        principal.tenant_id,
    )
    return TokenResponse(access_token=token, expires_in=expires_in)
