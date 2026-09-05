"""Provider payloads become canonical transfers.

Two chains and four provider shapes collapse into one model here, once, so that nothing
downstream is ever chain-aware (DATA_ARCHITECTURE.md section 3).

The rules are BLOCKCHAIN_ANALYTICS.md section 5 and they are not stylistic — each one
exists because breaking it puts a wrong number in a police report:

* amounts stay integers at raw precision, and a float in an amount field is rejected
  rather than converted, because by then the precision is already gone;
* decimals are copied from the payload or left unknown — never defaulted;
* failed and reverted transfers are kept and flagged;
* timestamps become timezone-aware UTC, from TRON milliseconds or Ethereum seconds.

A row this module cannot make sense of is skipped and logged, never guessed at: the
stage degrades, it does not invent a movement.
"""

import logging
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from app.chains.ethereum import EthereumAdapter
from app.chains.tron import TronAdapter
from app.db.models.enums import ChainCode, TransferStatus
from app.ingestion.service import AddressData
from app.normalize.transfer import NormalizedTransfer

log = logging.getLogger(__name__)

# Hex conversion and canonicalisation are adapter concerns; the ChainAdapter protocol
# exposes only validation, so the concrete adapters are used directly here.
_tron = TronAdapter()
_ethereum = EthereumAdapter()

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# Chain constants, not token metadata: these are fixed by the protocol and already seeded
# in the assets table. Nothing here is a guess about an unknown token.
_NATIVE = {
    ChainCode.TRON: ("TRX", 6),
    ChainCode.ETHEREUM: ("ETH", 18),
}


class RowError(ValueError):
    """A row that cannot be parsed. Skipped and counted, never guessed at."""


def parse(data: AddressData) -> list[NormalizedTransfer]:
    """Turn one address's retrieved payloads into canonical transfers.

    The analysis time window is deliberately *not* applied here. The canonical layer
    records what was observed; the window is a tracing boundary with its own termination
    reason (WALLET_TRACING.md). Filtering here would also empty the demo, since fixture
    mode serves one captured snapshot whose transfers are older than any live window.
    """
    parser = _parse_tron if data.chain is ChainCode.TRON else _parse_ethereum
    return _number(parser(data))


# --- Shared helpers ---------------------------------------------------------------


def _rows(result: Any, key: str) -> Iterator[dict[str, Any]]:
    """Yield the record rows of every page of a fetch result."""
    if result is None:
        return
    for response in result.responses:
        payload = response.json()
        rows = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(rows, list):
            yield from (row for row in rows if isinstance(row, dict))


def _amount(value: object) -> int:
    """Amounts arrive as decimal strings or integers.

    A float is rejected rather than converted: by the time an amount is a float its
    precision is already gone, and silently accepting it would be the exact failure the
    integer-only rule exists to prevent.
    """
    if isinstance(value, bool | float):
        raise RowError(f"amount is not an integer: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    raise RowError(f"amount is not an integer: {value!r}")


def _decimals(value: object) -> int | None:
    """Decimals are copied or left unknown. There is no default (rule 2)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _symbol(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text[:32] or None


def _block_number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise RowError(f"block number is not an integer: {value!r}")
    text = str(value).strip()
    if not text.isdigit():
        # An unmined transaction has no block; retrieval never returns one, so this is a
        # shape we do not recognise rather than a pending transfer.
        raise RowError(f"block number is not an integer: {value!r}")
    return int(text)


def _from_millis(value: object) -> datetime:
    """Integer arithmetic: dividing by 1000 in float would drift by microseconds."""
    return _EPOCH + timedelta(milliseconds=_amount(value))


def _from_seconds(value: object) -> datetime:
    return _EPOCH + timedelta(seconds=_amount(value))


def _number(transfers: list[NormalizedTransfer]) -> list[NormalizedTransfer]:
    """Assign `transfer_index` per transaction, in the order the movements were parsed.

    Parsers emit deterministically — native movements, then internal, then token events —
    so re-parsing the same payloads yields the same indices, which is what makes
    re-ingestion a no-op.

    Known limit: providers return only the events involving the queried address, so
    ingesting the *counterparty* of a multi-event transaction can index the same movement
    differently. No provider exposes a stable per-event ordinal on both chains (TronGrid's
    TRC-20 rows carry none at all), so there is nothing better to key on today.
    """
    seen: defaultdict[str, int] = defaultdict(int)
    numbered = []
    for transfer in transfers:
        index = seen[transfer.tx_hash]
        seen[transfer.tx_hash] += 1
        numbered.append(replace(transfer, transfer_index=index))
    return numbered


def _skip(chain: ChainCode, kind: str, row: dict[str, Any], exc: Exception) -> None:
    log.warning(
        "skipped unparseable %s %s row %s: %s",
        chain,
        kind,
        row.get("txID") or row.get("hash") or row.get("transaction_id"),
        exc,
    )


# --- TRON -------------------------------------------------------------------------


def _tron_address(value: object) -> str:
    """TronGrid returns base58 on the TRC-20 endpoint and 41-prefixed hex elsewhere."""
    if not isinstance(value, str) or not value:
        raise RowError(f"not an address: {value!r}")
    if value.startswith("T"):
        return _tron.validate_address(value).canonical
    try:
        return _tron.from_hex(value)
    except (ValueError, KeyError) as exc:
        raise RowError(f"not a TRON address: {value!r}") from exc


def _tron_status(row: dict[str, Any]) -> TransferStatus:
    rets = row.get("ret") or [{}]
    result = str(rets[0].get("contractRet", "")).upper()
    if result == "SUCCESS":
        return TransferStatus.SUCCESS
    if not result:
        # No result field means we do not know the outcome. PENDING says so; claiming
        # success or failure would be a guess, and PENDING is excluded from scoring.
        return TransferStatus.PENDING
    if "REVERT" in result:
        return TransferStatus.REVERTED
    return TransferStatus.FAILED


def _parse_tron(data: AddressData) -> list[NormalizedTransfer]:
    symbol, decimals = _NATIVE[ChainCode.TRON]
    transfers: list[NormalizedTransfer] = []

    for row in _rows(data.native, "data"):
        try:
            common = {
                "chain": ChainCode.TRON,
                "tx_hash": str(row["txID"]),
                "transfer_index": 0,
                "block_number": _block_number(row.get("blockNumber")),
                "block_time": _from_millis(row["block_timestamp"]),
                "status": _tron_status(row),
                "asset_symbol": symbol,
                "decimals": decimals,
            }
            fee: int | None = _amount((row.get("ret") or [{}])[0].get("fee", 0))
            for contract in row.get("raw_data", {}).get("contract") or []:
                # TRC-10 (TransferAssetContract) is not handled: it is effectively dead on
                # mainnet and its asset id is not a contract address. Resource delegation,
                # votes and contract calls are not value movements at all; TRC-20 value
                # arrives on the dedicated endpoint below.
                if contract.get("type") != "TransferContract":
                    continue
                value = contract["parameter"]["value"]
                transfers.append(
                    NormalizedTransfer(
                        from_address=_tron_address(value["owner_address"]),
                        to_address=_tron_address(value["to_address"]),
                        amount_raw=_amount(value["amount"]),
                        fee_raw=fee,
                        **common,  # type: ignore[arg-type]
                    )
                )
                fee = None  # Transaction-level; attributed to the first transfer only.
            transfers.extend(_tron_internal(row, common))
        except (RowError, KeyError, TypeError, IndexError) as exc:
            _skip(ChainCode.TRON, "native", row, exc)

    for row in _rows(data.token, "data"):
        try:
            if row.get("type") not in (None, "Transfer"):
                continue  # Approvals and the like are not value movements.
            info = row.get("token_info") or {}
            transfers.append(
                NormalizedTransfer(
                    chain=ChainCode.TRON,
                    tx_hash=str(row["transaction_id"]),
                    transfer_index=0,
                    # The TRC-20 endpoint omits the block number; the block time is what
                    # analysis uses, and the transaction row carries the number when the
                    # native endpoint also saw this transaction.
                    block_number=_block_number(row.get("block_number", 0)),
                    block_time=_from_millis(row["block_timestamp"]),
                    from_address=_tron_address(row["from"]),
                    to_address=_tron_address(row["to"]),
                    amount_raw=_amount(row["value"]),
                    # A Transfer event is only emitted by a transaction that succeeded.
                    status=TransferStatus.SUCCESS,
                    asset_symbol=_symbol(info.get("symbol")),
                    asset_contract=_tron_address(info["address"]) if info.get("address") else None,
                    decimals=_decimals(info.get("decimals")),
                )
            )
        except (RowError, KeyError, TypeError) as exc:
            _skip(ChainCode.TRON, "trc20", row, exc)

    return transfers


def _tron_internal(row: dict[str, Any], common: dict[str, Any]) -> Iterator[NormalizedTransfer]:
    """TRX moved by a contract call. TronGrid nests these inside the native rows.

    Omitting them produces a trace that looks complete and is not.
    """
    for internal in row.get("internal_transactions") or []:
        status = TransferStatus.FAILED if internal.get("rejected") else common["status"]
        for call in internal.get("callValueInfo") or []:
            # An entry carrying a tokenId is TRC-10, which this normalizer does not model.
            if call.get("tokenId") or not call.get("callValue"):
                continue
            yield NormalizedTransfer(
                from_address=_tron_address(internal["caller_address"]),
                to_address=_tron_address(internal["transferTo_address"]),
                amount_raw=_amount(call["callValue"]),
                is_internal=True,
                **{**common, "status": status},
            )


# --- Ethereum (Etherscan shape; Blockscout implements the same one) ----------------


def _eth_address(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RowError(f"not an address: {value!r}")
    return _ethereum.validate_address(value).canonical


def _eth_status(row: dict[str, Any]) -> TransferStatus:
    """Two different failure fields: a receipt status of 0 is a revert, `isError` covers
    the pre-Byzantium transactions that have no receipt status."""
    if str(row.get("txreceipt_status", "")) == "0":
        return TransferStatus.REVERTED
    if str(row.get("isError", "")) == "1":
        return TransferStatus.FAILED
    return TransferStatus.SUCCESS


def _parse_ethereum(data: AddressData) -> list[NormalizedTransfer]:
    symbol, decimals = _NATIVE[ChainCode.ETHEREUM]
    transfers: list[NormalizedTransfer] = []

    for kind, result, internal in (
        ("native", data.native, False),
        ("internal", data.internal, True),
    ):
        for row in _rows(result, "result"):
            try:
                amount = _amount(row.get("value", 0))
                # A zero-value transaction is a contract call, not a value movement.
                if amount == 0:
                    continue
                # Contract creation has no `to`; the created address is the destination.
                destination = row.get("to") or row.get("contractAddress")
                gas_price = row.get("gasPrice")
                transfers.append(
                    NormalizedTransfer(
                        chain=ChainCode.ETHEREUM,
                        tx_hash=str(row.get("hash") or row["transactionHash"]),
                        transfer_index=0,
                        block_number=_block_number(row.get("blockNumber")),
                        block_time=_from_seconds(row["timeStamp"]),
                        from_address=_eth_address(row["from"]),
                        to_address=_eth_address(destination),
                        amount_raw=amount,
                        status=_eth_status(row),
                        asset_symbol=symbol,
                        decimals=decimals,
                        # Gas is always non-zero on Ethereum, and only the outer
                        # transaction pays it — an internal transfer has no fee of its own.
                        fee_raw=(
                            _amount(row.get("gasUsed", 0)) * _amount(gas_price)
                            if gas_price and not internal
                            else None
                        ),
                        is_internal=internal,
                    )
                )
            except (RowError, KeyError, TypeError) as exc:
                _skip(ChainCode.ETHEREUM, kind, row, exc)

    for row in _rows(data.token, "result"):
        try:
            transfers.append(
                NormalizedTransfer(
                    chain=ChainCode.ETHEREUM,
                    tx_hash=str(row["hash"]),
                    transfer_index=0,
                    block_number=_block_number(row.get("blockNumber")),
                    block_time=_from_seconds(row["timeStamp"]),
                    from_address=_eth_address(row["from"]),
                    to_address=_eth_address(row["to"]),
                    amount_raw=_amount(row["value"]),
                    # A Transfer log is only emitted by a transaction that succeeded.
                    status=TransferStatus.SUCCESS,
                    asset_symbol=_symbol(row.get("tokenSymbol")),
                    asset_contract=_eth_address(row["contractAddress"]),
                    decimals=_decimals(row.get("tokenDecimal")),
                )
            )
        except (RowError, KeyError, TypeError) as exc:
            _skip(ChainCode.ETHEREUM, "token", row, exc)

    return transfers
