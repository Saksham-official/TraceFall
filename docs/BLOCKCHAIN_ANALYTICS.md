# Blockchain Analytics — Data Layer Design

How TraceFall obtains, validates, and normalizes on-chain data. Implemented by `chains/`,
`ingestion/`, and `normalize/` ([SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) §3.3–3.5).

---

## 1. Chain selection — and why not "all chains"

**MVP supports TRON and Ethereum. Nothing else.**

### Why TRON is first, not second

The uncomfortable truth about Indian crypto investment fraud is that it is overwhelmingly a
**USDT-on-TRON** phenomenon. TRC-20 USDT is what scam operators ask victims to send, because
transaction fees are near-zero, confirmation is seconds, liquidity is deep, and it is a
dollar-pegged instrument that does not lose value while being laundered. A tool for Indian
investigators that leads with Ethereum is solving a problem its users mostly do not have.

TRON is also analytically convenient: TronGrid provides a free, generously rate-limited API
covering both native TRX and TRC-20 transfers, and the account model makes the exchange
deposit-address funnel pattern — the exact signal PS26183 needs — highly visible.

### Why Ethereum second

Second-largest USDT/USDC corridor; the richest public tooling and the best free
address-label datasets; and — importantly for architecture — it validates the chain-adapter
abstraction. A design that works for exactly one chain is not a design.

### Why not Bitcoin in the MVP

Bitcoin's UTXO model would give us the common-input-ownership heuristic, the strongest wallet
clustering signal in the field. It is genuinely tempting. We are not doing it because:
- it is a **different data model end to end** — inputs and outputs rather than from/to, change
  address detection, no account balance — roughly doubling the ingestion, normalization, and
  tracing work;
- it is **not where the money in Indian cyber-fraud complaints goes**;
- a shallow Bitcoin implementation alongside a shallow TRON one is worse than one good TRON
  implementation.

Bitcoin is the first item in [FUTURE_SCOPE.md](FUTURE_SCOPE.md), and the adapter interface is
designed so UTXO chains can be added — `normalize()` returns transfers, and a UTXO transaction
simply produces more of them.

### Why not BSC, Polygon, Solana, and the rest

Each additional chain adds a provider integration, a rate limit to manage, a label dataset to
curate, and a set of edge cases — while adding little to the demonstration. Breadth is the
easiest thing to claim and the least convincing thing to show. Two chains done properly beats
eight done badly, and the adapter interface makes the ninth cheap when it is actually needed.

---

## 2. Address validation (FR-10..14)

Validation happens **before any network call**, always.

### TRON
- Base58check: 34 characters, leading `T`.
- Decode base58 → 25 bytes: `0x41` version byte + 20-byte address + 4-byte checksum.
- Checksum = first 4 bytes of `SHA256(SHA256(version||address))`. Mismatch → reject.
- Internal hex form (`41` + 40 hex) is used by some endpoints; conversion is confined to the
  TRON adapter. Nothing above `chains/` sees hex TRON addresses.

### Ethereum
- `0x` + 40 hex characters.
- **All-lowercase or all-uppercase:** valid, checksum not asserted.
- **Mixed case:** EIP-55 checksum is verified. A mixed-case address with a bad checksum is a
  typo and is rejected — this catches real transcription errors from victim statements, which
  is exactly the input this system receives.
- Stored lowercase; displayed in EIP-55 form.

### Chain auto-detection
Format is unambiguous between the two supported chains (`T`+base58 vs `0x`+hex), so detection
is deterministic. An address matching neither returns `UNSUPPORTED_CHAIN` with a helpful
message — recognising a Bitcoin or Solana address and saying "this looks like Bitcoin, which
we don't support yet" is far better than "invalid address".

### Contract vs EOA
Determined by a code-size lookup (`eth_getCode` on Ethereum; account-type field on TRON), and
cached. Contracts are traced differently — a token contract address appearing as a
counterparty is not a wallet and must never be attributed as one.

---

## 3. Data retrieval (FR-20..27)

### Providers

| Chain | Primary | Failover | Auth | Free-tier reality |
|---|---|---|---|---|
| TRON | TronGrid REST | **none yet** (see below) | Optional; works with no key | **Measured: 3 req/s unauthenticated**, then a 5-second suspension |
| Ethereum | **Blockscout** | Etherscan (only with a key) | None needed | No throttling observed up to 11.8 req/s |

**TRON has no failover today.** TronScan was the planned secondary, but its terms of service
could not be retrieved (OQ-07), and building against unread terms is not acceptable for a
Ministry of Home Affairs problem statement. A TRON provider outage currently degrades the
analysis rather than failing over.

**Blockscout leads on Ethereum.** It implements the Etherscan API shape, so one parser serves
both hosts, but it needs no API key and measured far faster. Etherscan now rejects keyless
requests entirely, so it is only attempted when a key is configured.

**Blockscout has its own trap:** while still indexing it returns HTTP 200, `status: "1"`, valid
rows, **and** a message saying some internal transactions have not been processed. Reading only
the rows would report a complete answer over incomplete data — the exact failure internal
transactions exist to prevent, wearing the disguise of success. The adapter maps that message to
`complete=false`.

**One Etherscan quirk matters more than its rate limit:** it reports throttling as **HTTP 200**
with `{"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}`. Transport-level
retry never sees it, so the adapter inspects the payload and raises a rate-limit error itself.
Missing this would silently truncate a trace.

Details, licensing, and bottleneck analysis: [DATA_SOURCES.md](DATA_SOURCES.md).

### What we retrieve per address
1. **Native transfers** (TRX / ETH) — value movements of the chain's own currency.
2. **Token transfers** (TRC-20 / ERC-20) — this is where the fraud money actually is.
3. **Account metadata** — balance, first/last activity, contract status.
4. **Internal transactions** (Ethereum) — value moved by contract execution. Frequently
   omitted by naive tooling, and frequently where funds actually went.

Token transfers are fetched first: a trace of a USDT fraud that starts by pulling TRX
transfers is starting with the noise.

### Pagination
Cursor or offset per provider, normalized behind the adapter. Hard caps: 10,000 transfers per
address, 200 pages per request cycle. On hitting a cap the result is marked
`complete=false, reason=PAGE_LIMIT` and surfaced to the investigator (FR-27).

**A truncated result is itself a finding.** An address with more than 10,000 transfers is
almost certainly a service, not a personal wallet — the truncation flag feeds the attribution
engine as a positive signal rather than being treated as a failure.

### Rate limiting and backoff
- Token-bucket limiter per provider, configured below the published limit.
- On `429`: exponential backoff with jitter (1s, 2s, 4s), honouring `Retry-After`. Three
  attempts, then failover, then partial result.
- On `5xx`: immediate failover to secondary.
- Hard 30-second timeout per request (NFR-05).
- **Request coalescing:** concurrent jobs asking for the same address share one in-flight
  request. Hot addresses (exchange hot wallets) are requested constantly during tracing, and
  this single measure is worth more than any other rate-limit optimisation.

### Caching
Keyed `(provider, chain, address, window, cursor)`. Default TTL 1 hour live. In fixture mode,
the cache is the committed snapshot and never expires
([DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md) §8).

### Evidence capture
Every response is written to the evidence store — body, SHA-256, provider, endpoint, request
params, HTTP status, retrieval timestamp — **before parsing** (FR-22). A parse failure must
never lose the evidence that would explain it.

---

## 4. What a transfer actually looks like on each chain

The differences the normalizer has to absorb:

| Concern | TRON | Ethereum |
|---|---|---|
| Native transfer | `TransferContract` in the tx contract list | `value` field on the transaction |
| Token transfer | TRC-20 `Transfer` event; TronGrid exposes a dedicated endpoint | ERC-20 `Transfer` log topic |
| Amounts | Integer, `sun` for TRX (6 dp); token decimals from the contract | Integer, `wei` for ETH (18 dp); token decimals from the contract |
| Fees | Bandwidth/energy model — often **zero fee** for the sender | Gas price × gas used, always non-zero |
| Timestamps | Block timestamp, milliseconds | Block timestamp, seconds |
| Failure | `contractRet` field | `status` field in the receipt |
| Internal transfers | Internal transactions endpoint | Trace/internal-tx endpoint |
| Multiple transfers per tx | Common | Common |

Note the fee difference: TRON's resource model means a scammer can move funds at essentially
zero cost, which is part of why TRON is the corridor of choice. It also means "fee paid" is a
much weaker behavioural signal on TRON than on Ethereum — the risk engine must not weight it
identically across chains.

---

## 5. Normalization (FR-30..34)

Everything above becomes a single `Transfer` model
([DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md) §3).

**Rules, each of which exists because violating it produces a wrong number in a police report:**

1. **Integer arithmetic only.** Amounts stay integers at raw precision. Decimal conversion
   happens once, at display. There is no floating-point arithmetic anywhere in this path.
2. **Decimals are never guessed.** Unknown token → store raw amount, suppress display, record
   the contract. A token with 6 decimals displayed as if it had 18 understates the amount by a
   factor of a trillion.
3. **Failed transfers are retained and flagged.** A scammer's failed transaction reveals intent,
   destination, and timing.
4. **One row per value movement**, sharing `tx_hash` with a `transfer_index`.
5. **Timestamps normalized to UTC `timestamptz`.** TRON milliseconds and Ethereum seconds both
   become the same thing.
6. **Idempotent.** `(chain, tx_hash, transfer_index)` is unique; re-ingestion is a no-op.
7. **USD valuation is optional and marked approximate.** A missing price yields `null`, never a
   guess. Historical price accuracy is not something we can guarantee, so we do not pretend to.

---

## 6. Confirmation and finality

| Chain | Treated as confirmed | Note |
|---|---|---|
| TRON | 19+ blocks (~57 s) | Solidified-block concept; TronGrid exposes it |
| Ethereum | 12+ blocks (~2.5 min); finalised checkpoint where available | |

Unconfirmed transfers are ingested and marked `PENDING`. They appear in the UI with a distinct
treatment and are **excluded from risk scoring** — a pending transaction can still be dropped,
and a risk score that changes when a transaction fails to confirm is a score no one can defend.

---

## 7. Failure handling summary (FR-25)

| Failure | Response |
|---|---|
| 429 rate limited | Backoff → retry ×3 → failover → partial, marked |
| 5xx / timeout | Immediate failover → cache → partial, marked |
| Provider schema change | Typed parse error; raw evidence retained; stage degraded, not crashed |
| Address not found | Valid result: "address exists but has no activity" |
| >10,000 transfers | Truncate, mark, and feed the truncation to attribution as a service signal |
| No network (demo) | Fixture cache serves everything |

**Governing principle:** the analysis never silently produces a smaller answer. Every
incompleteness is recorded, propagated to the API, shown in the UI, and printed in the report.
An investigator acting on a partial trace must know it is partial.

---

## 8. Multi-chain and cross-chain

**Multi-chain** — analysing TRON and Ethereum independently — is supported. The `Transfer`
model is chain-agnostic and a case may hold addresses on both.

**Cross-chain tracing — following value *through* a bridge — is explicitly out of scope for
the MVP.** What we do instead:

1. Detect that funds reached a known bridge contract.
2. Terminate the trace at that node with `termination_reason = SERVICE_BOUNDARY`.
3. Report the bridge by name and, where the destination chain is determinable from the
   transaction, name it.
4. State plainly that continuation would require analysis on the destination chain, and that
   correlating the two sides is a manual step.

Automated bridge correlation — matching an outbound bridge deposit to an inbound mint on
another chain by amount and timing — is genuinely doable and genuinely error-prone, especially
with batching and aggregators. It belongs in [FUTURE_SCOPE.md](FUTURE_SCOPE.md), not in a
system whose output goes into a case file.

---

## 9. Adding a chain later (NFR-17)

The full checklist, which should stay this short:

1. Implement `ChainAdapter` in `chains/<name>.py`: `validate_address`, `is_contract`,
   `fetch_native_transfers`, `fetch_token_transfers`, `fetch_transaction`, `get_balance`,
   `normalize`.
2. Add a row to `chains` and a provider configuration entry.
3. Add label datasets for that chain to `labels/`.
4. Capture fixtures for tests.

**No changes to `tracing/`, `graph/`, `patterns/`, `risk/`, `reports/`, or the frontend.** If a
new chain requires touching those, the abstraction has leaked and that is the bug to fix.
