import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from src.core.config import settings


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class ResourceReq(BaseModel):
    """Per-job resource requests/limits enforced by the isolated runner.

    All fields optional; unset fields fall back to the runner's configured defaults.
    cpu_seconds / memory_mb are best-effort (enforced via setrlimit on Unix, skipped on Windows);
    timeout_seconds is a cross-platform hard wall-clock limit.
    """

    cpu_seconds: Optional[float] = Field(default=None, gt=0, description="Max CPU seconds (Unix best-effort)")
    memory_mb: Optional[int] = Field(default=None, gt=0, description="Max resident memory in MB (Unix best-effort)")
    timeout_seconds: Optional[float] = Field(default=None, gt=0, description="Hard wall-clock timeout in seconds")


class JobBase(BaseModel):
    name: str = Field(..., description="Name of the job")
    description: Optional[str] = None
    priority: int = Field(1, ge=1, le=10, description="Priority 1-10")
    deadline: Optional[datetime] = None
    estimated_duration: float = Field(..., description="Estimated duration in seconds")
    dependencies: List[str] = Field(default_factory=list, description="List of Job IDs this job depends on")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the job execution")
    resource_req: Optional[ResourceReq] = Field(default=None, description="Per-job resource requests/limits")

    @field_validator("dependencies")
    @classmethod
    def validate_dependency_count(cls, value: list[str]) -> list[str]:
        if len(value) > settings.MAX_JOB_DEPENDENCIES:
            raise ValueError(f"At most {settings.MAX_JOB_DEPENDENCIES} dependencies allowed")
        return value

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, value: dict) -> dict:
        if len(json.dumps(value, default=str)) > settings.MAX_JOB_PAYLOAD_BYTES:
            raise ValueError(f"Payload exceeds {settings.MAX_JOB_PAYLOAD_BYTES} bytes")
        return value


class JobCreate(JobBase):
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional idempotency key; duplicate submits return the existing job",
    )
    enqueue: bool = Field(
        default=False,
        description="Enqueue immediately when dependencies are already satisfied",
    )


class Job(JobBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    worker_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    tenant_id: Optional[str] = None

    class Config:
        use_enum_values = True


class JobListResponse(BaseModel):
    items: List[Job]
    total: int
    limit: int
    offset: int


class Run(BaseModel):
    id: str
    job_id: str
    attempt: int
    worker_id: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    log_ref: Optional[str] = None


class RunListResponse(BaseModel):
    items: List[Run]
    total: int


class DagJobCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=64, description="Unique key within the DAG submit")
    name: str
    description: Optional[str] = None
    priority: int = Field(1, ge=1, le=10)
    deadline: Optional[datetime] = None
    estimated_duration: float
    payload: Dict[str, Any] = Field(default_factory=dict)
    resource_req: Optional[ResourceReq] = Field(default=None, description="Per-job resource requests/limits")
    depends_on: List[str] = Field(default_factory=list, description="Keys of upstream jobs in this DAG")


class DagSubmit(BaseModel):
    jobs: List[DagJobCreate] = Field(..., min_length=1)
    @field_validator("jobs")
    @classmethod
    def validate_dag_size(cls, value: list) -> list:
        if len(value) > settings.MAX_DAG_JOBS:
            raise ValueError(f"At most {settings.MAX_DAG_JOBS} jobs per DAG submit")
        return value


class DagSubmitResponse(BaseModel):
    jobs: List[Job]

class RunLogsResponse(BaseModel):
    run_id: str
    job_id: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None
    stdout_ref: Optional[str] = None
    stderr_ref: Optional[str] = None
    error_ref: Optional[str] = None
    spilled: bool = False


class DlqEntry(BaseModel):
    message_id: str
    job_id: Optional[str] = None
    reason: Optional[str] = None
    source_message_id: Optional[str] = None


class DlqListResponse(BaseModel):
    items: List[DlqEntry]
    total: int