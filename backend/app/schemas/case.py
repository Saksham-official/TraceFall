import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.db.models.enums import CaseStatus, Priority


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    ncrp_reference: str | None = Field(default=None, max_length=64)
    fir_reference: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=20000)
    reported_loss_inr: Decimal | None = Field(default=None, ge=0)
    incident_date: date | None = None
    priority: Priority = Priority.MEDIUM


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    status: CaseStatus | None = None
    priority: Priority | None = None


class CaseOut(BaseModel):
    id: uuid.UUID
    case_number: str
    title: str
    ncrp_reference: str | None
    fir_reference: str | None
    description: str | None
    reported_loss_inr: Decimal | None
    incident_date: date | None
    status: CaseStatus
    priority: Priority
    owner_id: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    pinned_finding_type: str | None = Field(default=None, max_length=64)
    pinned_finding_id: str | None = Field(default=None, max_length=64)


class NoteOut(BaseModel):
    id: int
    author_id: int
    body: str
    pinned_finding_type: str | None
    pinned_finding_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TimelineEventOut(BaseModel):
    id: int
    actor_id: int | None
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkedCaseOut(BaseModel):
    case_id: uuid.UUID
    case_number: str
    title: str
    reported_loss_inr: Decimal | None


class SharedAddressOut(BaseModel):
    """One address this case has in common with others the caller can already open."""

    address: str
    chain: str
    case_count: int
    combined_reported_loss_inr: Decimal | None
    cases: list[LinkedCaseOut]


class CorrelationOut(BaseModel):
    shared_addresses: list[SharedAddressOut]
    # Stated rather than left for the reader to assume: a shared address is an observed
    # fact, "the same fraud" is the investigator's inference. Confirmed exchange and mixer
    # addresses are excluded, so a link here is never just "both touched Binance".
    note: str = (
        "A shared address is an on-chain fact, not a conclusion that these cases are the "
        "same fraud. Confirmed exchange, mixer, bridge and merchant addresses are excluded, "
        "because they appear in almost every trace. Only cases you can already open are shown."
    )
