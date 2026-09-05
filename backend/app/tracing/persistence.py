"""Persisting a trace.

Kept separate from the engine so the algorithm stays pure and offline-testable: the
engine never touches a database. Reading transfers back out of the canonical layer lives
in `intel/service.py`, which every consumer shares rather than each keeping its own copy.
"""

import logging
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisRun, Trace, TraceEdge, TraceNode
from app.db.models.blockchain import Address, Asset, Chain
from app.db.models.enums import ChainCode, TaintModel
from app.tracing.models import TraceResult

log = logging.getLogger(__name__)


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
