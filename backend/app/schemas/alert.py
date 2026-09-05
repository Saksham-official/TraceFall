import uuid
from datetime import datetime

from pydantic import BaseModel

from app.db.models.enums import AlertType, Severity


class AlertOut(BaseModel):
    id: int
    case_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    alert_type: AlertType
    severity: Severity
    # None for an alert that names no single address, such as a future case-level trigger.
    address: str | None
    # The sentence an investigator reads. Written where the alert is raised, so the
    # reason and the rule that produced it cannot drift apart.
    trigger_reason: str
    source_finding_type: str | None
    acknowledged_at: datetime | None
    acknowledged_by: int | None
    created_at: datetime
