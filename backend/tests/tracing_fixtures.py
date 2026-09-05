"""Hand-built transfer graphs for tracing tests.

In-memory and deterministic: the engine does no I/O, so its tests need no database,
no network and no fixtures on disk.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from app.db.models.enums import ChainCode, TransferStatus
from app.normalize.transfer import NormalizedTransfer

BASE_TIME = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
_counter = {"n": 0}


def tx(
    frm: str,
    to: str,
    amount: int,
    minutes: int = 0,
    *,
    contract: str | None = USDT,
    decimals: int | None = 6,
    status: TransferStatus = TransferStatus.SUCCESS,
) -> NormalizedTransfer:
    _counter["n"] += 1
    return NormalizedTransfer(
        chain=ChainCode.TRON,
        tx_hash=f"{_counter['n']:064x}",
        transfer_index=0,
        block_number=1000 + _counter["n"],
        block_time=BASE_TIME + timedelta(minutes=minutes),
        from_address=frm,
        to_address=to,
        amount_raw=amount,
        status=status,
        asset_symbol="USDT" if contract else "TRX",
        asset_contract=contract,
        decimals=decimals,
    )


def fetcher(transfers: list[NormalizedTransfer]) -> Callable[[str], Awaitable[list]]:
    """Serves every transfer touching an address, the way retrieval would."""

    async def fetch(address: str) -> list[NormalizedTransfer]:
        return [t for t in transfers if address in (t.from_address, t.to_address)]

    return fetch


def services(*addresses: str) -> Callable[[str], Awaitable[bool]]:
    known = set(addresses)

    async def is_service(address: str) -> bool:
        return address in known

    return is_service


ASSET = f"{ChainCode.TRON}:{USDT}"
