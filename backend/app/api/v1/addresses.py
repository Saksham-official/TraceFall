import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

from app.chains.base import InvalidAddressError
from app.chains.registry import get_adapter, validate
from app.core.deps import CurrentUser, SessionDep, get_accessible_case, require_role
from app.core.exceptions import InvalidAddress, NotFound
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case, CaseAddress, CaseTimelineEvent
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.schemas.address import CaseAddressCreate, CaseAddressOut, CrossCaseMatch

router = APIRouter(prefix="/cases/{case_id}/addresses", tags=["addresses"])

Investigator = Annotated[
    User, Depends(require_role(UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST))
]


@router.post("", response_model=CaseAddressOut, status_code=201)
async def add_address(
    case_id: uuid.UUID, payload: CaseAddressCreate, user: Investigator, session: SessionDep
) -> CaseAddressOut:
    await get_accessible_case(case_id, user, session)

    # Validation happens before any network call (FR-12).
    try:
        validated = validate(payload.address, payload.chain)
    except InvalidAddressError as exc:
        raise InvalidAddress(str(exc), field="address") from exc

    chain = await session.scalar(select(Chain).where(Chain.code == validated.chain))
    if chain is None:
        raise NotFound(f"Chain {validated.chain} is not configured")

    address = await session.scalar(
        select(Address).where(Address.chain_id == chain.id, Address.address == validated.canonical)
    )
    if address is None:
        address = Address(chain_id=chain.id, address=validated.canonical)
        session.add(address)
        await session.flush()

    # Surfaced at intake, not later: another officer may already be working this address.
    matches = await session.execute(
        select(Case.id, Case.case_number, Case.owner_id)
        .join(CaseAddress, CaseAddress.case_id == Case.id)
        .where(CaseAddress.address_id == address.id, Case.id != case_id)
        .distinct()
    )

    case_address = CaseAddress(
        case_id=case_id,
        address_id=address.id,
        role=payload.role,
        reported_amount_raw=None,
        reported_at=payload.reported_at,
        notes=payload.notes,
        added_by=user.id,
    )
    session.add(case_address)
    session.add(
        CaseTimelineEvent(
            case_id=case_id,
            actor_id=user.id,
            event_type="address.added",
            payload={"address": validated.canonical, "chain": validated.chain},
        )
    )
    await session.commit()
    await session.refresh(case_address)

    return CaseAddressOut(
        id=case_address.id,
        address=validated.canonical,
        display_address=validated.display,
        chain=validated.chain,
        is_contract=address.is_contract,
        role=case_address.role,
        reported_at=case_address.reported_at,
        added_at=case_address.added_at,
        cross_case_matches=[
            CrossCaseMatch(case_id=m.id, case_number=m.case_number, owner_id=m.owner_id)
            for m in matches
        ],
    )


@router.get("", response_model=list[CaseAddressOut])
async def list_addresses(
    case_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[CaseAddressOut]:
    await get_accessible_case(case_id, user, session)
    rows = await session.execute(
        select(CaseAddress, Address, Chain)
        .join(Address, Address.id == CaseAddress.address_id)
        .join(Chain, Chain.id == Address.chain_id)
        .where(CaseAddress.case_id == case_id)
        .order_by(CaseAddress.added_at)
    )
    out = []
    for case_address, address, chain in rows:
        adapter = get_adapter(chain.code)
        out.append(
            CaseAddressOut(
                id=case_address.id,
                address=address.address,
                display_address=adapter.validate_address(address.address).display,
                chain=chain.code,
                is_contract=address.is_contract,
                role=case_address.role,
                reported_at=case_address.reported_at,
                added_at=case_address.added_at,
            )
        )
    return out


@router.delete("/{case_address_id}", status_code=204)
async def remove_address(
    case_id: uuid.UUID, case_address_id: int, user: Investigator, session: SessionDep
) -> Response:
    await get_accessible_case(case_id, user, session)
    row = await session.scalar(
        select(CaseAddress).where(CaseAddress.id == case_address_id, CaseAddress.case_id == case_id)
    )
    if row is None:
        raise NotFound("Address not found on this case")
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)
