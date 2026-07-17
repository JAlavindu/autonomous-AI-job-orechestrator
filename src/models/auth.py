from datetime import datetime
from enum import Enum
from typing import Optional, Literal

from pydantic import BaseModel, Field

AuthMethod = Literal["api_key", "jwt", "client_credentials"]

class Role(str, Enum):
    VIEWER = "viewer"
    PRODUCER = "producer"
    OPERATOR = "operator"


ROLE_RANK = {
    Role.VIEWER: 1,
    Role.PRODUCER: 2,
    Role.OPERATOR: 3,
}


class Principal(BaseModel):
    api_key_id: str
    tenant_id: str
    role: Role
    name: str


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    role: Role = Role.PRODUCER


class ApiKeyCreatedResponse(BaseModel):
    id: str
    name: str
    role: Role
    key_prefix: str
    api_key: str
    tenant_id: str
    created_at: datetime


class ApiKeySummary(BaseModel):
    id: str
    name: str
    role: Role
    key_prefix: str
    tenant_id: str
    enabled: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeySummary]
    total: int

class Principal(BaseModel):
    subject_id: str 
    tenant_id: str
    role: Role
    name: str
    auth_method: AuthMethod = "api_key"
    @property
    def api_key_id(self) -> str:
        """Backward-compatible alias used in existing code."""
        return self.subject_id
        
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
class ServiceAccountCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    role: Role = Role.PRODUCER
class ServiceAccountCreatedResponse(BaseModel):
    id: str
    name: str
    role: Role
    client_id: str
    client_secret: str  # shown once
    tenant_id: str
    created_at: datetime
class ServiceAccountSummary(BaseModel):
    id: str
    name: str
    role: Role
    client_id: str
    tenant_id: str
    enabled: bool
    created_at: datetime
class AuditLogEntry(BaseModel):
    id: str
    tenant_id: str
    actor: str
    action: str
    target: str
    payload: dict
    ts: datetime
class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    limit: int
    offset: int