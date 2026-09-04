import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models.enums import AnalysisStage, AnalysisStatus, TraceDirection


class AnalysisStart(BaseModel):
    address_id: int
    direction: TraceDirection = TraceDirection.FORWARD
    max_depth: int = Field(default=5, ge=1, le=10)
    taint_threshold: float = Field(default=0.01, gt=0, le=1)
    time_window_days: int = Field(default=90, ge=1, le=365)
    stop_at_services: bool = True
    include_patterns: bool = True
    include_risk: bool = True


class StageOut(BaseModel):
    name: AnalysisStage
    status: str
    duration_ms: int | None = None
    detail: str | None = None


class AnalysisOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    status: AnalysisStatus
    stage: AnalysisStage | None
    progress_pct: int
    stages: list[StageOut] = []
    degradations: list[Any] = []
    partial_results_available: bool = False
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None

    model_config = {"from_attributes": True}


class AnalysisAccepted(BaseModel):
    analysis_run_id: uuid.UUID
    status: AnalysisStatus
    poll_url: str
    estimated_seconds: int
