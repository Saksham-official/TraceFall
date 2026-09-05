import uuid
from datetime import datetime

from pydantic import BaseModel

from app.db.models.enums import NarrativeSource, ReportFormat, ReportType


class ReportCreate(BaseModel):
    analysis_run_id: uuid.UUID
    format: ReportFormat = ReportFormat.PDF
    report_type: ReportType = ReportType.FULL


class ReportOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    report_type: ReportType
    format: ReportFormat
    content_sha256: str
    # Recorded and printed so a reader knows whether prose was machine-written (FR-115).
    # Nothing writes LLM; see ADR-021.
    narrative_source: NarrativeSource
    generated_by: int
    generated_at: datetime
    download_url: str
    # None when not checked on this request.
    content_verified: bool | None = None

    model_config = {"from_attributes": True}
