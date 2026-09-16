import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models.enums import AnalysisStage, AnalysisStatus, ChainCode, TraceDirection

# The one place the analysis defaults are written down. The worker falls back to these
# rather than repeating the literals, and `tests/test_demo_config.py` asserts that
# config/demo_addresses.yaml still matches — the demo runs on whatever the intake sends,
# so a default that drifts from the demo config silently changes what the demo traces.
#
# 180 days, not 90: victims report weeks or months after the fact, and the window has to
# reach back past the incident to see it at all.
DEFAULT_MAX_DEPTH = 5
DEFAULT_TIME_WINDOW_DAYS = 180
DEFAULT_TAINT_THRESHOLD = 0.01


class AnalysisStart(BaseModel):
    address_id: int
    direction: TraceDirection = TraceDirection.FORWARD
    max_depth: int = Field(default=DEFAULT_MAX_DEPTH, ge=1, le=10)
    taint_threshold: float = Field(default=DEFAULT_TAINT_THRESHOLD, gt=0, le=1)
    time_window_days: int = Field(default=DEFAULT_TIME_WINDOW_DAYS, ge=1, le=365)
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
    root_address_id: int
    # So the progress screen can name the address being analysed.
    root_address: str | None = None
    root_chain: ChainCode | None = None
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
