"""Canonical-layer persistence.

Writes `Transaction`, `Transfer` and `Asset` rows from parsed transfers. Every insert is
`ON CONFLICT DO NOTHING` against a unique constraint the database already enforces, so
re-ingesting the same chain data changes nothing without this module ever having to ask
first — the check-then-insert version of that is a race, not an optimisation.

USD valuation is deliberately absent: a missing price must be null and never a guess
(BLOCKCHAIN_ANALYTICS.md section 5, rule 7), and no price source is wired up yet.
"""

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.blockchain import Address, Asset, Chain, Transaction, Transfer
from app.db.models.enums import ChainCode
from app.ingestion.service import AddressData
from app.normalize import parsers
from app.normalize.transfer import NormalizedTransfer

log = logging.getLogger(__name__)

# asyncpg caps a statement at 32767 parameters; a busy address can produce 10,000
# transfers, so writes are chunked well inside that.
CHUNK = 500


@dataclass
class NormalizationSummary:
    parsed: int
    transfers_written: int
    transactions_written: int
    assets_written: int

    def as_dict(self) -> dict[str, int]:
        return {
            "parsed": self.parsed,
            "transfers_written": self.transfers_written,
            "transactions_written": self.transactions_written,
            "assets_written": self.assets_written,
        }


async def normalize_address_data(session: AsyncSession, data: AddressData) -> NormalizationSummary:
    """Parse one address's retrieved payloads and persist the canonical rows."""
    transfers = parsers.parse(data)
    summary = await persist(session, data.chain, transfers)
    log.info("normalized %s %s: %s", data.chain, data.address, summary.as_dict())
    return summary


async def persist(
    session: AsyncSession, chain: ChainCode, transfers: Sequence[NormalizedTransfer]
) -> NormalizationSummary:
    if not transfers:
        return NormalizationSummary(0, 0, 0, 0)

    chain_id = await _chain_id(session, chain)
    addresses = await _upsert_addresses(session, chain_id, transfers)
    assets, assets_written = await _upsert_assets(session, chain_id, transfers)
    transactions, transactions_written = await _upsert_transactions(
        session, chain_id, transfers, addresses
    )

    rows = [
        {
            "transaction_id": transactions[t.tx_hash],
            "chain_id": chain_id,
            "tx_hash": t.tx_hash,
            "transfer_index": t.transfer_index,
            "block_number": t.block_number,
            "block_time": t.block_time,
            "from_address_id": addresses[t.from_address],
            "to_address_id": addresses[t.to_address],
            "asset_id": assets[t.asset_contract],
            # Decimal(int) is exact; the column is NUMERIC(78, 0). No float, ever.
            "amount_raw": Decimal(t.amount_raw),
            # Denormalised at write time so later metadata changes cannot rewrite history.
            "decimals": t.decimals,
            "status": t.status,
            "is_internal": t.is_internal,
        }
        for t in transfers
    ]
    written = await _insert(session, Transfer, rows, ["chain_id", "tx_hash", "transfer_index"])
    await session.commit()
    return NormalizationSummary(
        parsed=len(transfers),
        transfers_written=written,
        transactions_written=transactions_written,
        assets_written=assets_written,
    )


# --- Reference rows ---------------------------------------------------------------


async def _chain_id(session: AsyncSession, chain: ChainCode) -> int:
    chain_id = await session.scalar(select(Chain.id).where(Chain.code == chain))
    if chain_id is None:
        raise RuntimeError(f"chain {chain} is missing from the chains table")
    return int(chain_id)


async def _upsert_addresses(
    session: AsyncSession, chain_id: int, transfers: Sequence[NormalizedTransfer]
) -> dict[str, int]:
    seen = {t.from_address for t in transfers} | {t.to_address for t in transfers}
    await _insert(
        session,
        Address,
        [{"chain_id": chain_id, "address": a} for a in sorted(seen)],
        ["chain_id", "address"],
    )
    rows = await _select_chunked(
        session,
        select(Address.address, Address.id).where(Address.chain_id == chain_id),
        sorted(seen),
        Address.address,
    )
    return {address: row_id for address, row_id in rows}


async def _upsert_assets(
    session: AsyncSession, chain_id: int, transfers: Sequence[NormalizedTransfer]
) -> tuple[dict[str | None, int], int]:
    """Assets are recorded on first sight and not rewritten afterwards.

    An unknown token keeps `decimals = NULL` and its contract address: guessing 18 for a
    6-decimal token understates the amount by a factor of a trillion.
    """
    first: dict[str | None, NormalizedTransfer] = {}
    for transfer in transfers:
        first.setdefault(transfer.asset_contract, transfer)

    written = await _insert(
        session,
        Asset,
        [
            {
                "chain_id": chain_id,
                "contract_address": contract,
                "symbol": t.asset_symbol,
                "decimals": t.decimals,
                "first_seen_at": t.block_time,
            }
            for contract, t in sorted(first.items(), key=lambda kv: kv[0] or "")
            if contract is not None
        ],
        ["chain_id", "contract_address"],
    )

    ids: dict[str | None, int] = {}
    if None in first:
        # The native asset is seeded per chain and guarded by a partial unique index, so
        # it is looked up rather than upserted.
        native = await session.scalar(
            select(Asset.id).where(Asset.chain_id == chain_id, Asset.is_native.is_(True))
        )
        if native is None:
            raise RuntimeError(f"chain {chain_id} has no native asset row")
        ids[None] = int(native)

    contracts = [c for c in first if c is not None]
    rows = await _select_chunked(
        session,
        select(Asset.contract_address, Asset.id).where(Asset.chain_id == chain_id),
        contracts,
        Asset.contract_address,
    )
    ids.update({contract: row_id for contract, row_id in rows})
    return ids, written


async def _upsert_transactions(
    session: AsyncSession,
    chain_id: int,
    transfers: Sequence[NormalizedTransfer],
    addresses: dict[str, int],
) -> tuple[dict[str, int], int]:
    """One row per transaction, built from its first parsed transfer.

    For a transaction seen only through a token event the participants are the token
    sender and recipient rather than the transaction's own from/to — the provider does not
    report the latter on that endpoint. The transfer rows, which are what analysis reads,
    are unaffected.
    """
    first: dict[str, NormalizedTransfer] = {}
    fees: dict[str, int] = {}
    for transfer in transfers:
        first.setdefault(transfer.tx_hash, transfer)
        if transfer.fee_raw is not None:
            fees.setdefault(transfer.tx_hash, transfer.fee_raw)

    written = await _insert(
        session,
        Transaction,
        [
            {
                "chain_id": chain_id,
                "tx_hash": tx_hash,
                "block_number": t.block_number,
                "block_time": t.block_time,
                "from_address_id": addresses[t.from_address],
                "to_address_id": addresses[t.to_address],
                "fee_raw": Decimal(fees[tx_hash]) if tx_hash in fees else None,
                "status": t.status,
            }
            for tx_hash, t in first.items()
        ],
        ["chain_id", "tx_hash"],
    )

    rows = await _select_chunked(
        session,
        select(Transaction.tx_hash, Transaction.id).where(Transaction.chain_id == chain_id),
        list(first),
        Transaction.tx_hash,
    )
    return {tx_hash: row_id for tx_hash, row_id in rows}, written


# --- Chunked statements -----------------------------------------------------------


def _chunks(values: Sequence[Any]) -> Iterator[Sequence[Any]]:
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


async def _insert(
    session: AsyncSession, model: type[Any], rows: Sequence[dict[str, Any]], conflict: list[str]
) -> int:
    """Insert, letting the unique constraint absorb what is already there.

    DO NOTHING returns only the rows it actually inserted, which is the count of what was
    new — and re-ingesting identical data therefore returns zero.
    """
    written = 0
    for chunk in _chunks(rows):
        result = await session.execute(
            insert(model)
            .values(list(chunk))
            .on_conflict_do_nothing(index_elements=conflict)
            .returning(model.id)
        )
        written += len(result.all())
    return written


async def _select_chunked(
    session: AsyncSession, statement: Any, values: Sequence[Any], column: Any
) -> list[tuple[Any, int]]:
    found: list[tuple[Any, int]] = []
    for chunk in _chunks(values):
        result = await session.execute(statement.where(column.in_(list(chunk))))
        found.extend((key, int(row_id)) for key, row_id in result.all())
    return found
