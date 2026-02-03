from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"

class JobBase(BaseModel):
    name: str = Field(..., description="Name of the job")
    description: Optional[str] = None
    priority: int = Field(1, ge=1, le=10, description="Priority 1-10")
    deadline: Optional[datetime] = None
    estimated_duration: float = Field(..., description="Estimated duration in seconds")
    dependencies: List[str] = Field(default_factory=list, description="List of Job IDs this job depends on")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the job execution")

class JobCreate(JobBase):
    pass

class Job(JobBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    worker_id: Optional[str] = None

    class Config:
        use_enum_values = True