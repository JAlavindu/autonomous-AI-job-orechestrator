from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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