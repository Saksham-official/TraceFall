"""Addresses that appear in more than one case.

The single-case view answers one victim's question. This answers the department's: the
same scam rarely produces one report, and ten victims paying into ten different suspect
wallets that all sweep into **one** deposit address is one case, not ten. Finding that
address is what turns ten small reports into one actionable freeze request.

**Confirmed service addresses are excluded, and that exclusion is the whole feature.**
An exchange hot wallet appears in nearly every trace ever run — reporting it as a link
between cases would bury the one address that actually matters under a list of addresses
that correlate with everything. A shared *deposit* address is a finding; a shared *hot
wallet* is a tautology.

Case isolation is not weakened to do this: the query only ever reaches cases the user can
already open, through the same `visible_cases` policy the case list uses. An investigator
sees links across their own cases; an I4C analyst, who already reads globally, sees links
across the department — which is the role that needs them.

This is Tier B intelligence: a shared address is an observed on-chain fact, but "these
cases are the same fraud" is an inference the investigator makes, not one we assert.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.attribution.decision import SERVICE_TYPES
from app.db.models.analysis import AnalysisRun, Trace, TraceNode
from app.db.models.blockchain import Address, Chain
from app.db.models.case import Case
from app.db.models.entity import Attribution
from app.db.models.enums import AttributionTier

# A trace is bounded by the edge budget and a department's case load is not, so the join
# is bounded rather than assumed small. Well past anything an investigator would read.
ROW_CAP = 5_000


@dataclass
class LinkedCase:
    case_id: uuid.UUID
    case_number: str
    title: str
    reported_loss_inr: Decimal | None


@dataclass
class SharedAddress:
    """One address this case has in common with others, and which others."""

    address: str
    chain: str
    cases: list[LinkedCase] = field(default_factory=list)

    @property
    def case_count(self) -> int:
        return len(self.cases)

    @property
    def combined_reported_loss_inr(self) -> Decimal | None:
        """Summed across the linked cases only, and None when none of them recorded one.

        Deliberately excludes the case being viewed: this is what the *other* reports add,
        which is the number that argues for pooling them.
        """
        amounts = [c.reported_loss_inr for c in self.cases if c.reported_loss_inr is not None]
        return sum(amounts, Decimal(0)) if amounts else None


def _case_addresses(case_id: uuid.UUID) -> Select[tuple[int]]:
    """Every address any trace in this case reached."""
    return (
        select(TraceNode.address_id)
        .join(Trace, Trace.id == TraceNode.trace_id)
        .join(AnalysisRun, AnalysisRun.id == Trace.analysis_run_id)
        .where(AnalysisRun.case_id == case_id)
        .distinct()
    )


def _is_confirmed_service(address_id_column: object) -> Select[tuple[int]]:
    """Addresses a named dataset confirms are a service — excluded, see the module docstring."""
    return select(Attribution.id).where(
        Attribution.address_id == address_id_column,
        Attribution.tier == AttributionTier.CONFIRMED,
        Attribution.entity_type.in_(SERVICE_TYPES),
    )


async def shared_addresses(
    session: AsyncSession,
    case_id: uuid.UUID,
    visible: Select[tuple[uuid.UUID]],
) -> list[SharedAddress]:
    """Addresses this case shares with other cases the caller can already open.

    `visible` carries the caller's case visibility, so this module never decides who may
    see what — it only asks.
    """
    stmt = (
        select(
            Address.address,
            Chain.code,
            Case.id,
            Case.case_number,
            Case.title,
            Case.reported_loss_inr,
        )
        .select_from(TraceNode)
        .join(Trace, Trace.id == TraceNode.trace_id)
        .join(AnalysisRun, AnalysisRun.id == Trace.analysis_run_id)
        .join(Case, Case.id == AnalysisRun.case_id)
        .join(Address, Address.id == TraceNode.address_id)
        .join(Chain, Chain.id == Address.chain_id)
        .where(
            TraceNode.address_id.in_(_case_addresses(case_id)),
            AnalysisRun.case_id != case_id,
            AnalysisRun.case_id.in_(visible),
            ~_is_confirmed_service(TraceNode.address_id).exists(),
        )
        .distinct()
        .limit(ROW_CAP)
    )

    found: dict[str, SharedAddress] = {}
    for address, chain, linked_id, number, title, loss in await session.execute(stmt):
        shared = found.setdefault(address, SharedAddress(address=address, chain=str(chain)))
        shared.cases.append(LinkedCase(linked_id, number, title, loss))

    # Most-shared first: the address twelve cases have in common is the one to act on.
    return sorted(found.values(), key=lambda s: (-s.case_count, s.address))
