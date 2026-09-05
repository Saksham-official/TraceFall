"""Normalization — raw provider payloads to the canonical transfer.

The test that matters most is the one against the committed fixtures: they are real
TronGrid responses, and real-world messiness is what breaks a parser written against an
invented payload.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.base import FetchResult, RawResponse, TimeWindow
from app.db.models.blockchain import Asset, Transaction, Transfer
from app.db.models.enums import ChainCode, TransferStatus
from app.ingestion import service as ingestion
from app.ingestion.service import AddressData
from app.normalize import parsers
from app.normalize import service as normalize
from app.normalize.transfer import NormalizedTransfer

FIXTURED_TRON_ADDRESS = "TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9"
USDT_TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_ERC20 = "0xdac17f958d2ee523a2206206994597c13d831ec7"
ALICE = "0x" + "a1" * 20
BOB = "0x" + "b0" * 20
TX = "0x" + "cd" * 32


def _result(body: object) -> FetchResult:
    return FetchResult(
        responses=[
            RawResponse(
                provider="test",
                endpoint="test",
                params={},
                status=200,
                body=json.dumps(body).encode(),
                retrieved_at=datetime.now(UTC),
            )
        ]
    )


def _tron(native: list[dict] | None = None, token: list[dict] | None = None) -> AddressData:
    return AddressData(
        chain=ChainCode.TRON,
        address=FIXTURED_TRON_ADDRESS,
        native=_result({"data": native or []}),
        token=_result({"data": token or []}),
    )


def _eth(
    native: list[dict] | None = None,
    token: list[dict] | None = None,
    internal: list[dict] | None = None,
) -> AddressData:
    return AddressData(
        chain=ChainCode.ETHEREUM,
        address=ALICE,
        native=_result({"status": "1", "result": native or []}),
        token=_result({"status": "1", "result": token or []}),
        internal=_result({"status": "1", "result": internal or []}),
    )


def _eth_token_row(**overrides: object) -> dict:
    row = {
        "hash": TX,
        "blockNumber": "18000000",
        "timeStamp": "1700000000",
        "from": ALICE,
        "to": BOB,
        "value": "1500000",
        "contractAddress": USDT_ERC20,
        "tokenSymbol": "USDT",
        "tokenDecimal": "6",
    }
    row.update(overrides)  # type: ignore[arg-type]
    return row


def _trc20_row(**overrides: object) -> dict:
    row = {
        "transaction_id": "a" * 64,
        "block_timestamp": 1700000000000,
        "from": "TJQQLsfYvwK1gJyET4C7hvPdJ2YyNcAUbL",
        "to": FIXTURED_TRON_ADDRESS,
        "type": "Transfer",
        "value": "2000000",
        "token_info": {"address": USDT_TRC20, "decimals": 6, "symbol": "USDT", "name": "Tether"},
    }
    row.update(overrides)  # type: ignore[arg-type]
    return row


def _tron_native_row(contracts: list[dict], **overrides: object) -> dict:
    row = {
        "txID": "b" * 64,
        "blockNumber": 75657646,
        "block_timestamp": 1700000000000,
        "ret": [{"contractRet": "SUCCESS", "fee": 268000}],
        "raw_data": {"contract": contracts},
    }
    row.update(overrides)  # type: ignore[arg-type]
    return row


def _transfer_contract(amount: int) -> dict:
    return {
        "type": "TransferContract",
        "parameter": {
            "value": {
                # Hex form, exactly as TronGrid returns it on this endpoint.
                "owner_address": "41238ce912167c221a781e04ea43f77fc8b8bc0f33",
                "to_address": "4182dd6b9966724ae2fdc79b416c7588da67ff1b35",
                "amount": amount,
            }
        },
    }


# --- Amounts and decimals ---------------------------------------------------------


def test_trc20_six_decimal_amount_converts_correctly() -> None:
    (transfer,) = parsers.parse(_tron(token=[_trc20_row()]))
    assert transfer.amount_raw == 2_000_000
    assert transfer.decimals == 6
    assert transfer.amount == Decimal("2")
    assert transfer.asset_contract == USDT_TRC20


def test_erc20_eighteen_decimal_amount_converts_correctly() -> None:
    (transfer,) = parsers.parse(
        _eth(token=[_eth_token_row(value=str(10**18), tokenDecimal="18", tokenSymbol="DAI")])
    )
    assert transfer.amount_raw == 10**18
    assert transfer.amount == Decimal("1")


def test_unknown_token_keeps_the_raw_amount_and_never_guesses_decimals() -> None:
    """The most damaging normalization bug would be a wrong decimal count in a report."""
    eth_row = _eth_token_row(value="123456789", tokenDecimal="", tokenSymbol="")
    (from_eth,) = parsers.parse(_eth(token=[eth_row]))
    (from_tron,) = parsers.parse(_tron(token=[_trc20_row(token_info={"address": USDT_TRC20})]))

    for transfer in (from_eth, from_tron):
        assert transfer.decimals is None
        assert transfer.amount is None
        assert transfer.asset_contract is not None
    assert from_eth.amount_raw == 123456789
    assert from_tron.amount_raw == 2_000_000


def test_a_float_amount_is_rejected_rather_than_converted() -> None:
    """By the time an amount is a float its precision is already gone."""
    assert parsers.parse(_eth(token=[_eth_token_row(value=1.5e18)])) == []


def test_amounts_are_integers_all_the_way_through() -> None:
    transfers = parsers.parse(
        _tron(native=[_tron_native_row([_transfer_contract(8333333)])], token=[_trc20_row()])
    )
    assert transfers
    assert all(isinstance(t.amount_raw, int) for t in transfers)
    assert all(not isinstance(t.amount_raw, bool) for t in transfers)


# --- Structure --------------------------------------------------------------------


def test_one_transaction_with_four_transfers_becomes_four_rows() -> None:
    data = _eth(
        native=[
            {
                "hash": TX,
                "blockNumber": "18000000",
                "timeStamp": "1700000000",
                "from": ALICE,
                "to": BOB,
                "value": "1000",
                "gasUsed": "21000",
                "gasPrice": "20000000000",
                "isError": "0",
                "txreceipt_status": "1",
            }
        ],
        token=[
            _eth_token_row(value="1"),
            _eth_token_row(value="2"),
            _eth_token_row(value="3"),
        ],
    )
    transfers = parsers.parse(data)
    assert len(transfers) == 4
    assert {t.tx_hash for t in transfers} == {TX}
    assert [t.transfer_index for t in transfers] == [0, 1, 2, 3]
    # The fee belongs to the transaction, so only the first transfer carries it.
    assert transfers[0].fee_raw == 21000 * 20000000000
    assert [t.fee_raw for t in transfers[1:]] == [None, None, None]


def test_zero_value_contract_calls_are_not_value_movements() -> None:
    data = _eth(
        native=[
            {
                "hash": TX,
                "blockNumber": "1",
                "timeStamp": "1700000000",
                "from": ALICE,
                "to": BOB,
                "value": "0",
                "isError": "0",
            }
        ]
    )
    assert parsers.parse(data) == []


def test_ethereum_internal_transfers_are_retained_and_flagged() -> None:
    """Omitting these produces a trace that looks complete and is not."""
    data = _eth(
        internal=[
            {
                "hash": TX,
                "blockNumber": "18000000",
                "timeStamp": "1700000000",
                "from": ALICE,
                "to": BOB,
                "value": "500",
                "isError": "0",
                "type": "call",
            }
        ]
    )
    (transfer,) = parsers.parse(data)
    assert transfer.is_internal is True
    assert transfer.amount_raw == 500
    # Only the outer transaction pays gas.
    assert transfer.fee_raw is None


def test_tron_internal_transfers_ride_along_with_the_native_rows() -> None:
    row = _tron_native_row(
        [],
        internal_transactions=[
            {
                "caller_address": "41238ce912167c221a781e04ea43f77fc8b8bc0f33",
                "transferTo_address": "4182dd6b9966724ae2fdc79b416c7588da67ff1b35",
                "callValueInfo": [{"callValue": 12345}],
                "rejected": False,
            }
        ],
    )
    (transfer,) = parsers.parse(_tron(native=[row]))
    assert transfer.is_internal is True
    assert transfer.amount_raw == 12345
    assert transfer.asset_symbol == "TRX"


# --- Failure retention ------------------------------------------------------------


def test_failed_and_reverted_transfers_are_retained_and_flagged() -> None:
    """A scammer's failed transaction reveals intent, destination and timing."""
    base = {
        "hash": TX,
        "blockNumber": "18000000",
        "timeStamp": "1700000000",
        "from": ALICE,
        "to": BOB,
        "value": "777",
    }
    reverted, failed = parsers.parse(
        _eth(
            native=[
                {**base, "isError": "1", "txreceipt_status": "0"},
                # Pre-Byzantium transactions have no receipt status at all.
                {**base, "isError": "1", "txreceipt_status": ""},
            ]
        )
    )
    assert reverted.status is TransferStatus.REVERTED
    assert failed.status is TransferStatus.FAILED
    assert reverted.amount_raw == 777 and not reverted.succeeded


def test_tron_uses_its_own_failure_field() -> None:
    rows = [
        _tron_native_row([_transfer_contract(1)], ret=[{"contractRet": "REVERT"}]),
        _tron_native_row([_transfer_contract(2)], ret=[{"contractRet": "OUT_OF_ENERGY"}]),
        # No outcome reported: PENDING says so rather than claiming either way.
        _tron_native_row([_transfer_contract(3)], ret=[]),
    ]
    statuses = [t.status for t in parsers.parse(_tron(native=rows))]
    assert statuses == [TransferStatus.REVERTED, TransferStatus.FAILED, TransferStatus.PENDING]


# --- Timestamps and addresses -----------------------------------------------------


def test_tron_milliseconds_and_ethereum_seconds_reach_the_same_utc_instant() -> None:
    (tron_transfer,) = parsers.parse(_tron(token=[_trc20_row(block_timestamp=1700000000000)]))
    (eth_transfer,) = parsers.parse(_eth(token=[_eth_token_row(timeStamp="1700000000")]))
    assert tron_transfer.block_time == eth_transfer.block_time
    assert tron_transfer.block_time == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    assert tron_transfer.block_time.tzinfo is not None
    assert eth_transfer.block_time.utcoffset() == UTC.utcoffset(None)


def test_tron_hex_addresses_are_canonicalised_to_base58() -> None:
    (transfer,) = parsers.parse(_tron(native=[_tron_native_row([_transfer_contract(1)])]))
    assert transfer.from_address == "TDDBTQF2Xu3ALd1hZVqQmPmJ62xMUYYWf2"
    assert transfer.to_address == FIXTURED_TRON_ADDRESS


def test_ethereum_addresses_are_canonicalised_to_lowercase() -> None:
    checksummed = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    (transfer,) = parsers.parse(_eth(token=[_eth_token_row(contractAddress=checksummed)]))
    assert transfer.asset_contract == USDT_ERC20


# --- The committed fixtures: real data, real messiness ----------------------------


async def test_real_trongrid_fixtures_parse_into_sane_transfers(clean_database: None) -> None:
    data = await ingestion.retrieve_address(
        ChainCode.TRON, FIXTURED_TRON_ADDRESS, TimeWindow.last_days(90)
    )
    transfers = parsers.parse(data)

    assert transfers
    for transfer in transfers:
        assert isinstance(transfer.amount_raw, int) and transfer.amount_raw > 0
        assert transfer.block_time.tzinfo is not None
        assert transfer.from_address.startswith("T") and len(transfer.from_address) == 34
        assert transfer.to_address.startswith("T") and len(transfer.to_address) == 34
        assert transfer.tx_hash and transfer.transfer_index >= 0

    by_asset = {t.asset_contract: t for t in transfers}
    # Real USDT, six decimals, 2 USDT received.
    assert by_asset[USDT_TRC20].decimals == 6
    assert by_asset[USDT_TRC20].amount == Decimal("2")
    # The captured account's only actual TRX movement; the rest of the native endpoint is
    # resource delegation, which moves no value.
    native = [t for t in transfers if t.asset_contract is None]
    assert [t.amount_raw for t in native] == [8333333]
    assert native[0].asset_symbol == "TRX"


async def test_real_fixtures_survive_a_round_trip_through_the_database(
    session: AsyncSession,
) -> None:
    data = await ingestion.retrieve_address(ChainCode.TRON, FIXTURED_TRON_ADDRESS)
    summary = await normalize.normalize_address_data(session, data)

    assert summary.parsed == summary.transfers_written > 0
    stored = (await session.scalars(select(Transfer))).all()
    assert len(stored) == summary.parsed
    assert all(isinstance(t.amount_raw, Decimal) for t in stored)
    # A scam lookalike in the captured data: "USDT Teller", sixteen decimals.
    teller = await session.scalar(select(Asset).where(Asset.symbol == "USDTT"))
    assert teller is not None and teller.decimals == 16


# --- Persistence ------------------------------------------------------------------


def _built(**overrides: object) -> NormalizedTransfer:
    fields: dict = {
        "chain": ChainCode.ETHEREUM,
        "tx_hash": TX,
        "transfer_index": 0,
        "block_number": 18_000_000,
        "block_time": datetime(2026, 8, 14, 9, 32, tzinfo=UTC),
        "from_address": ALICE,
        "to_address": BOB,
        "amount_raw": 1_000_000,
        "status": TransferStatus.SUCCESS,
    }
    fields.update(overrides)
    return NormalizedTransfer(**fields)


async def test_reingesting_identical_data_changes_nothing(session: AsyncSession) -> None:
    transfers = [_built(), _built(transfer_index=1, amount_raw=5)]

    first = await normalize.persist(session, ChainCode.ETHEREUM, transfers)
    counts = await _counts(session)
    second = await normalize.persist(session, ChainCode.ETHEREUM, transfers)

    assert first.transfers_written == 2
    assert second.transfers_written == 0
    assert second.transactions_written == 0
    assert await _counts(session) == counts


async def test_a_very_large_amount_survives_storage_exactly(session: AsyncSession) -> None:
    """A float anywhere in this path would silently round this to something else."""
    huge = 2**200
    await normalize.persist(session, ChainCode.ETHEREUM, [_built(amount_raw=huge)])
    stored = await session.scalar(select(Transfer.amount_raw))
    assert stored == Decimal(huge)
    assert int(stored) == huge  # type: ignore[arg-type]


async def test_an_unknown_token_is_stored_with_null_decimals(session: AsyncSession) -> None:
    unknown = "0x" + "ee" * 20
    await normalize.persist(
        session,
        ChainCode.ETHEREUM,
        [_built(asset_contract=unknown, asset_symbol=None, decimals=None, amount_raw=42)],
    )
    transfer = await session.scalar(select(Transfer))
    asset = await session.scalar(select(Asset).where(Asset.contract_address == unknown))
    assert transfer is not None and transfer.decimals is None
    assert transfer.amount_raw == Decimal(42)
    assert asset is not None and asset.decimals is None and asset.symbol is None


async def test_native_transfers_reuse_the_seeded_asset_row(session: AsyncSession) -> None:
    await normalize.persist(session, ChainCode.ETHEREUM, [_built(asset_symbol="ETH", decimals=18)])
    transfer = await session.scalar(select(Transfer))
    assert transfer is not None
    asset = await session.get(Asset, transfer.asset_id)
    assert asset is not None and asset.is_native and asset.symbol == "ETH"


async def test_the_transaction_row_carries_the_fee_once(session: AsyncSession) -> None:
    await normalize.persist(
        session,
        ChainCode.ETHEREUM,
        [_built(fee_raw=420_000), _built(transfer_index=1)],
    )
    transactions = (await session.scalars(select(Transaction))).all()
    assert len(transactions) == 1
    assert transactions[0].fee_raw == Decimal(420_000)


async def _counts(session: AsyncSession) -> tuple[int, int, int]:
    return (
        int(await session.scalar(select(func.count()).select_from(Transfer)) or 0),
        int(await session.scalar(select(func.count()).select_from(Transaction)) or 0),
        int(await session.scalar(select(func.count()).select_from(Asset)) or 0),
    )
