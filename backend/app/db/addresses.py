"""Address rows for a set of addresses, creating any that do not exist yet.

Four stages needed this and four had written their own copy; three of them shared a bug.
An `IN (...)` or a multi-row `INSERT` sends one bind parameter per value, and PostgreSQL's
wire protocol caps a statement at **32,767 parameters**. A pattern finding on a service
address involves every counterparty it saw — tens of thousands on a busy one — so the
pattern stage failed with `InterfaceError: the number of query arguments cannot exceed
32767` on exactly the traces that matter most, and the run degraded to PARTIAL with no
findings at all.

So this chunks, and it is the only implementation.

An address may need a row without ever having appeared in a stored transfer — an
unattributed one, most obviously. Dropping its finding for want of a row would lose exactly
the honest "we do not know" answer the tiers exist to make sayable.
"""

from collections.abc import Iterable, Iterator, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.blockchain import Address, Chain
from app.db.models.enums import ChainCode

# Two parameters per inserted row, one per address in the SELECT: 500 keeps every statement
# an order of magnitude inside the 32,767 limit.
CHUNK = 500


def _chunks(values: Sequence[str]) -> Iterator[Sequence[str]]:
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


async def chain_id(session: AsyncSession, chain: ChainCode) -> int:
    row_id = await session.scalar(select(Chain.id).where(Chain.code == chain))
    assert row_id is not None, f"chain {chain} is missing from the chains table"
    return int(row_id)


async def ids_for(
    session: AsyncSession, chain: ChainCode | int, addresses: Iterable[str]
) -> dict[str, int]:
    """Map every address to its row id, inserting the ones that are new.

    `chain` takes the code or an already-resolved `chains.id`, because the tracing stage
    holds the row and the rest hold the code.
    """
    resolved = chain if isinstance(chain, int) else await chain_id(session, chain)
    wanted = sorted(set(addresses))
    if not wanted:
        return {}

    for chunk in _chunks(wanted):
        await session.execute(
            insert(Address)
            .values([{"chain_id": resolved, "address": address} for address in chunk])
            .on_conflict_do_nothing(constraint="chain_id_address")
        )

    found: dict[str, int] = {}
    for chunk in _chunks(wanted):
        rows = await session.execute(
            select(Address.address, Address.id).where(
                Address.chain_id == resolved, Address.address.in_(list(chunk))
            )
        )
        found.update({address: int(row_id) for address, row_id in rows})
    return found
