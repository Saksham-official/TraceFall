import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models.enums import AddressRole, ChainCode


class ReportedAmount(BaseModel):
    value: Decimal = Field(gt=0)
    asset_symbol: str = Field(max_length=32)


class CaseAddressCreate(BaseModel):
    address: str = Field(min_length=10, max_length=64)
    chain: ChainCode | None = None
    role: AddressRole = AddressRole.SUSPECT
    # Amount and time anchor the trace to the victim's actual transaction, which
    # substantially improves the result (FR-41).
    reported_amount: ReportedAmount | None = None
    reported_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)


class CrossCaseMatch(BaseModel):
    case_id: uuid.UUID
    case_number: str
    owner_id: int


class CaseAddressOut(BaseModel):
    id: int
    address: str
    display_address: str
    chain: ChainCode
    is_contract: bool | None
    role: AddressRole
    reported_at: datetime | None
    added_at: datetime
    # Surfaced at intake, not later: another officer may already be working this address.
    cross_case_matches: list[CrossCaseMatch] = []
