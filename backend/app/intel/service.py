"""Address profiling — the database side of `intel/`.

Reads canonical transfers back out, runs the pure feature extraction over them, and
stores the result in `address_profiles` so a second analysis of the same address does not
recompute it.

A profile is keyed by `data_version`, the highest block the profile was computed from.
Retrieving newer chain data raises it and produces a new profile; recomputing over the
same data does not.

ponytail: a backfill that only adds *older* blocks leaves `data_version` unchanged, so
that profile is not recomputed. Key on the highest transfer row id if partial-retrieval
backfills become common.
"""

import logging
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models.blockchain import Address, Asset, Chain, Transfer
from app.db.models.entity import AddressProfile
from app.db.models.enums import ChainCode
from app.intel.features import AddressFeatures, extract
from app.normalize.transfer import NormalizedTransfer

log = logging.getLogger(__name__)


async def load_transfers(
    session: AsyncSession, chain: ChainCode, addresses: Sequence[str]
) -> dict[str, list[NormalizedTransfer]]:
    """Every transfer touching each address, as the canonical value object.

    Returning `NormalizedTransfer` rather than ORM rows is what lets the feature
    extraction stay pure and the tracing engine stay chain-agnostic — both consume the
    same object whether it came from a provider or from the database.
    """
    wanted = set(addresses)
    if not wanted:
        return {}

    sender = aliased(Address)
    recipient = aliased(Address)
    result = await session.execute(
        select(
            Transfer.tx_hash,
            Transfer.transfer_index,
            Transfer.block_number,
            Transfer.block_time,
            sender.address,
            recipient.address,
            Transfer.amount_raw,
            Transfer.status,
            Transfer.decimals,
            Transfer.is_internal,
            Asset.symbol,
            Asset.contract_address,
        )
        .join(sender, sender.id == Transfer.from_address_id)
        .join(recipient, recipient.id == Transfer.to_address_id)
        .join(Asset, Asset.id == Transfer.asset_id)
        .join(Chain, Chain.id == Transfer.chain_id)
        .where(Chain.code == chain)
        .where(or_(sender.address.in_(wanted), recipient.address.in_(wanted)))
        .order_by(Transfer.block_time, Transfer.tx_hash, Transfer.transfer_index)
    )

    by_address: dict[str, list[NormalizedTransfer]] = {address: [] for address in wanted}
    for row in result:
        transfer = NormalizedTransfer(
            chain=chain,
            tx_hash=row[0],
            transfer_index=row[1],
            block_number=row[2],
            block_time=row[3],
            from_address=row[4],
            to_address=row[5],
            amount_raw=int(row[6]),
            status=row[7],
            decimals=row[8],
            is_internal=row[9],
            asset_symbol=row[10],
            asset_contract=row[11],
        )
        for address in (transfer.from_address, transfer.to_address):
            if address in by_address:
                by_address[address].append(transfer)
    return by_address


async def build_profiles(
    session: AsyncSession,
    chain: ChainCode,
    addresses: Sequence[str],
    asset_key: str | None = None,
) -> dict[str, AddressFeatures]:
    """Compute and store a behavioural profile for each address.

    Addresses with no retrieved transfers are absent from the result, which the decision
    procedure reads as "no data" — distinct from "no activity".
    """
    transfers = await load_transfers(session, chain, addresses)
    features = {
        address: extract(address, rows, asset_key) for address, rows in transfers.items() if rows
    }
    if features:
        await _persist(session, chain, features, transfers)
    return features


async def _persist(
    session: AsyncSession,
    chain: ChainCode,
    features: dict[str, AddressFeatures],
    transfers: dict[str, list[NormalizedTransfer]],
) -> None:
    address_ids = {
        address: row_id
        for address, row_id in await session.execute(
            select(Address.address, Address.id)
            .join(Chain, Chain.id == Address.chain_id)
            .where(Chain.code == chain, Address.address.in_(set(features)))
        )
    }
    rows = []
    for address, feature in features.items():
        if address not in address_ids:
            continue
        rows_for_address = transfers[address]
        times = sorted(t.block_time for t in rows_for_address)
        rows.append(
            {
                "address_id": address_ids[address],
                "data_version": max(t.block_number for t in rows_for_address),
                "tx_count_in": feature.tx_count_in,
                "tx_count_out": feature.tx_count_out,
                "unique_counterparties_in": feature.counterparty_diversity_in,
                "unique_counterparties_out": feature.counterparty_diversity_out,
                "total_in_raw": Decimal(feature.total_in_raw),
                "total_out_raw": Decimal(feature.total_out_raw),
                "balance_raw": Decimal(feature.total_in_raw - feature.total_out_raw),
                "age_days": (times[-1] - times[0]).days,
                "active_days": len({t.date() for t in times}),
                "median_dwell_seconds": feature.median_dwell_seconds,
                "sweep_ratio": (
                    None if feature.sweep_ratio is None else _quantize(feature.sweep_ratio)
                ),
                "distinct_assets": feature.distinct_assets,
                "features": feature.as_dict(),
            }
        )
    if rows:
        await session.execute(
            insert(AddressProfile)
            .values(rows)
            .on_conflict_do_nothing(constraint="address_id_data_version")
        )
        await session.commit()
        log.info("profiled %d addresses on %s", len(rows), chain)


def _quantize(value: Fraction) -> Decimal:
    """Ratio to the NUMERIC(18, 12) storage form. Ratios only — never an amount."""
    return Decimal(value.numerator) / Decimal(value.denominator)
