from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class JobBase(BaseModel):
    name: str = Field(..., description="Name of the job")
    description: Optional[str] = None
    priority: int = Field(1, ge=1, le=10, description="Priority 1-10")
    deadline: Optional[datetime] = None
    estimated_duration: float = Field(..., description="Estimated duration in seconds")
    dependencies: List[str] = Field(default_factory=list, description="List of Job IDs this job depends on")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the job execution")


class JobCreate(JobBase):
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional idempotency key; duplicate submits return the existing job",
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
    depends_on: List[str] = Field(default_factory=list, description="Keys of upstream jobs in this DAG")


class DagSubmit(BaseModel):
    jobs: List[DagJobCreate] = Field(..., min_length=1)


class DagSubmitResponse(BaseModel):
    jobs: List[Job]