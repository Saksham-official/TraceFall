"""Persisting a trace.

Kept separate from the engine so the algorithm stays pure and offline-testable: the
engine never touches a database. Reading transfers back out of the canonical layer lives
in `intel/service.py`, which every consumer shares rather than each keeping its own copy.
"""

import logging
import uuid
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import addresses as addresses_repo
from app.db.models.analysis import AnalysisRun, Trace, TraceEdge, TraceNode
from app.db.models.blockchain import Address, Asset, Chain
from app.db.models.enums import ChainCode, TaintModel
from app.tracing.models import PrunedBranch, TraceParams, TraceResult
from app.tracing.models import TraceEdge as ResultEdge
from app.tracing.models import TraceNode as ResultNode

log = logging.getLogger(__name__)


async def load(session: AsyncSession, analysis_run_id: uuid.UUID) -> TraceResult | None:
    """Rebuild a stored trace, so the graph is derived on read rather than kept twice.

    Taint comes back as an integer raw amount rather than the exact `Fraction` the engine
    carried — the fractional part was rounded once, at the storage boundary, which is
    where rounding belongs. Everything an investigator is shown, including the branches
    that were pruned and the addresses that could not be retrieved, survives the round
    trip.
    """
    trace = await session.scalar(
        select(Trace)
        .where(Trace.analysis_run_id == analysis_run_id)
        .order_by(Trace.computed_at.desc())
    )
    if trace is None:
        return None

    names = {
        row_id: address
        for row_id, address in await session.execute(select(Address.id, Address.address))
    }
    assets = {
        row_id: (contract, symbol, decimals)
        for row_id, contract, symbol, decimals in await session.execute(
            select(Asset.id, Asset.contract_address, Asset.symbol, Asset.decimals)
        )
    }
    chain_code = await session.scalar(
        select(Chain.code)
        .join(Address, Address.chain_id == Chain.id)
        .where(Address.id == trace.root_address_id)
    )

    result = TraceResult(
        root=names[trace.root_address_id],
        original_amount=Fraction(int(trace.total_traced_raw or 0)),
        anchor_tx_hash=trace.anchor_tx_hash,
        params=TraceParams(
            max_depth=trace.max_depth,
            edge_budget=trace.edge_budget,
            direction=trace.direction,
        ),
        pruned=[
            PrunedBranch(
                from_address=branch["from"],
                to_address=branch["to"],
                asset_key=branch["asset_key"],
                total_amount_raw=int(branch["total_amount_raw"]),
                tainted_amount=Fraction(int(branch["tainted_amount_raw"])),
                reason=branch["reason"],
            )
            for branch in trace.pruned
        ],
        unavailable=list(trace.unavailable),
    )

    for node_row in await session.scalars(select(TraceNode).where(TraceNode.trace_id == trace.id)):
        result.nodes[names[node_row.address_id]] = ResultNode(
            address=names[node_row.address_id],
            depth=node_row.depth,
            tainted_in=Fraction(int(node_row.tainted_amount_raw)),
            pruned_out=Fraction(int(node_row.pruned_amount_raw)),
            is_terminal=node_row.is_terminal,
            termination_reason=node_row.termination_reason,
            first_reached_at=node_row.first_reached_at,
        )

    for row in await session.scalars(select(TraceEdge).where(TraceEdge.trace_id == trace.id)):
        contract, symbol, decimals = assets[row.asset_id]
        source, target = names[row.from_address_id], names[row.to_address_id]
        # Nullable in the schema, but `save` always writes both: an aggregated edge is
        # built from at least one transfer, and a transfer always has a block time.
        assert row.first_transfer_at is not None and row.last_transfer_at is not None
        result.edges.append(
            ResultEdge(
                from_address=source,
                to_address=target,
                asset_key=f"{chain_code}:{contract or 'native'}",
                asset_symbol=symbol,
                asset_contract=contract,
                decimals=decimals,
                total_amount_raw=int(row.total_amount_raw),
                tainted_amount=Fraction(int(row.tainted_amount_raw)),
                transfer_count=row.transfer_count,
                first_transfer_at=row.first_transfer_at,
                last_transfer_at=row.last_transfer_at,
                tx_hashes=list(row.tx_hashes),
            )
        )
        # attributed_out is what the engine sent onward; rebuilt from the stored edges so
        # a reloaded node still accounts for its value.
        if source in result.nodes:
            result.nodes[source].attributed_out += Fraction(int(row.tainted_amount_raw))

    result.params = TraceParams(
        asset_key=result.edges[0].asset_key if result.edges else None,
        max_depth=trace.max_depth,
        edge_budget=trace.edge_budget,
        direction=trace.direction,
    )
    return result


async def save(
    session: AsyncSession, run: AnalysisRun, result: TraceResult, chain: ChainCode
) -> Trace:
    """Write the trace, its nodes and its aggregated edges."""
    chain_row = await session.scalar(select(Chain).where(Chain.code == chain))
    if chain_row is None:
        raise RuntimeError(f"chain {chain} is not configured")

    ids = await addresses_repo.ids_for(session, chain_row.id, result.nodes)
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
        pruned=[
            {
                "from": branch.from_address,
                "to": branch.to_address,
                "asset_key": branch.asset_key,
                "reason": branch.reason,
                "total_amount_raw": str(branch.total_amount_raw),
                "tainted_amount_raw": str(branch.tainted_raw),
            }
            for branch in result.pruned
        ],
        unavailable=list(result.unavailable),
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
                pruned_amount_raw=Decimal(int(node.pruned_out)),
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
