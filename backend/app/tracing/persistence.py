"""Persisting a trace, and loading the transfers it runs on.

Kept separate from the engine so the algorithm stays pure and offline-testable: the
engine never touches a database.
"""

import logging
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisRun, Trace, TraceEdge, TraceNode
from app.db.models.blockchain import Address, Asset, Chain, Transfer
from app.db.models.enums import ChainCode, TaintModel
from app.normalize.transfer import NormalizedTransfer
from app.tracing.models import TraceResult

log = logging.getLogger(__name__)


async def load_transfers(
    session: AsyncSession, chain: ChainCode, address: str
) -> list[NormalizedTransfer]:
    """Read one address's normalized transfers back out of the canonical layer."""
    rows = await session.execute(
        select(Transfer, Address.address, Asset)
        .join(Chain, Chain.id == Transfer.chain_id)
        .join(Asset, Asset.id == Transfer.asset_id)
        .join(Address, Address.id == Transfer.from_address_id)
        .where(Chain.code == chain)
    )
    # Resolving both endpoints needs a second lookup; build an id->address map once
    # rather than joining the address table twice.
    address_rows = await session.execute(select(Address.id, Address.address))
    names: dict[int, str] = {row_id: name for row_id, name in address_rows.all()}

    out: list[NormalizedTransfer] = []
    for transfer, _from_name, asset in rows:
        sender = names.get(transfer.from_address_id)
        recipient = names.get(transfer.to_address_id)
        if sender is None or recipient is None:
            continue
        if address not in (sender, recipient):
            continue
        out.append(
            NormalizedTransfer(
                chain=chain,
                tx_hash=transfer.tx_hash,
                transfer_index=transfer.transfer_index,
                block_number=transfer.block_number,
                block_time=transfer.block_time,
                from_address=sender,
                to_address=recipient,
                amount_raw=int(transfer.amount_raw),
                status=transfer.status,
                asset_symbol=asset.symbol,
                asset_contract=asset.contract_address,
                decimals=transfer.decimals,
                is_internal=transfer.is_internal,
            )
        )
    return out


async def _address_ids(
    session: AsyncSession, chain_id: int, addresses: Sequence[str]
) -> dict[str, int]:
    """Upsert every address the trace touched, so edges have something to point at."""
    existing = await session.execute(
        select(Address.address, Address.id).where(
            Address.chain_id == chain_id, Address.address.in_(addresses)
        )
    )
    ids: dict[str, int] = {name: row_id for name, row_id in existing.all()}
    missing = [a for a in addresses if a not in ids]
    for address in missing:
        row = Address(chain_id=chain_id, address=address)
        session.add(row)
    if missing:
        await session.flush()
        refreshed = await session.execute(
            select(Address.address, Address.id).where(
                Address.chain_id == chain_id, Address.address.in_(missing)
            )
        )
        ids.update({name: row_id for name, row_id in refreshed.all()})
    return ids


async def save(
    session: AsyncSession, run: AnalysisRun, result: TraceResult, chain: ChainCode
) -> Trace:
    """Write the trace, its nodes and its aggregated edges."""
    chain_row = await session.scalar(select(Chain).where(Chain.code == chain))
    if chain_row is None:
        raise RuntimeError(f"chain {chain} is not configured")

    ids = await _address_ids(session, chain_row.id, list(result.nodes))
    asset_rows = await session.execute(select(Asset.contract_address, Asset.id))
    asset_ids: dict[str | None, int] = {c: i for c, i in asset_rows.all()}

    trace = Trace(
        analysis_run_id=run.id,
        root_address_id=ids[result.root],
        direction=result.params.direction,
        anchor_tx_hash=result.anchor_tx_hash,
        max_depth=result.params.max_depth,
        taint_threshold=Decimal(result.params.taint_threshold.numerator)
        / Decimal(result.params.taint_threshold.denominator),
        edge_budget=result.params.edge_budget,
        taint_model=TaintModel.HAIRCUT,
        node_count=len(result.nodes),
        edge_count=len(result.edges),
        total_traced_raw=Decimal(int(result.original_amount)),
    )
    session.add(trace)
    await session.flush()

    for node in result.nodes.values():
        session.add(
            TraceNode(
                trace_id=trace.id,
                address_id=ids[node.address],
                depth=node.depth,
                taint_share=Decimal(node.tainted_in.numerator)
                / Decimal(node.tainted_in.denominator or 1)
                / Decimal(int(result.original_amount) or 1),
                tainted_amount_raw=Decimal(node.tainted_raw),
                is_terminal=node.is_terminal,
                termination_reason=node.termination_reason,
                first_reached_at=node.first_reached_at,
            )
        )

    for edge in result.edges:
        asset_id = asset_ids.get(edge.asset_contract)
        if asset_id is None:
            log.warning("skipping edge with unknown asset %s", edge.asset_key)
            continue
        session.add(
            TraceEdge(
                trace_id=trace.id,
                from_address_id=ids[edge.from_address],
                to_address_id=ids[edge.to_address],
                asset_id=asset_id,
                total_amount_raw=Decimal(edge.total_amount_raw),
                tainted_amount_raw=Decimal(edge.tainted_raw),
                transfer_count=edge.transfer_count,
                first_transfer_at=edge.first_transfer_at,
                last_transfer_at=edge.last_transfer_at,
                tx_hashes=edge.tx_hashes,
            )
        )

    await session.commit()
    return trace
