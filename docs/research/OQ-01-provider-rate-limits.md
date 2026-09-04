# OQ-01 · Measured provider rate limits, latency, and trace-time projection

*Research note. Not an ADR. Resolving OQ-01/02/03 requires ADRs written on top of this.*
**Measured:** 2026-09-05, from one residential IP in India, no API keys held (`.env` has
`TRONGRID_API_KEY=` and `ETHERSCAN_API_KEY=` empty). Scripts were throwaway, stdlib-only, and
kept to roughly 190 TronGrid / 225 Blockscout / 32 TronScan requests in total.

Everything below is labelled **measured** or **documented**. Nothing documented is presented as
measured.

---

## Verdict

1. **NFR-01 (under 120 s) is not achievable as specified.** TronGrid without an API key enforces
   `allowed_rps(1)` **per RPC method** with **zero burst tolerance**; the safe sustained rate is
   **0.5 req/s per method** (measured). The 200-address / 400-request trace in
   [DATA_SOURCES.md §1](../DATA_SOURCES.md) takes **~400 s**, 3.3× the target. 120 s buys
   **60 uncached addresses** on TronGrid alone, or **120** if TRC-20 fetches are split across
   TronGrid and TronScan.
2. **Etherscan's free tier is sufficient for internal transactions** (`txlistinternal` is not a
   PRO endpoint — documented), **but Blockscout should be primary anyway**: no key required,
   **zero throttling across 195 requests up to 11.8 req/s achieved** (measured), and identical
   internal-transaction coverage. Etherscan could not be measured at all — it now rejects every
   keyless request.
3. **The premise in DATA_SOURCES.md §1 is inverted.** It calls Ethereum "the tighter constraint"
   at ~5 req/s. Measured, **Ethereum via Blockscout is ~20× faster than TRON via TronGrid**.
   TRON — our primary chain by ADR-001 — is the bottleneck, and it is far tighter than any
   published figure suggested.

---

## Measured rate limits

### TronGrid — `https://api.trongrid.io`, no API key

| Property | Value | How measured |
|---|---|---|
| Scope of limit | **Per RPC method, per source IP** | 3 methods driven concurrently at 2.0 s spacing each → **36/36 HTTP 200**, aggregate 1.57 req/s wall |
| Stated limit | `allowed_rps(1)` | Quoted verbatim in the 429 body |
| Burst tolerance | **Zero** | 3 concurrent requests after 8 s idle → `[429, 429, 200]`. Idle time accrues no tokens |
| Sustained, 2.0 s spacing | **100%** (15/15, then 12/12) | Two independent runs, fixed start-time spacing |
| Sustained, 1.2 s spacing | 67% (10/15) | Same harness |
| Sustained, 1.0 s spacing | 40% (10/25) | Same harness |
| **Safe sustained rate** | **0.5 req/s per method** | 2.0 s spacing is the fastest spacing measured with zero errors |
| Throttle duration | **5.0 s**, per method | After tripping, polled every ~0.78 s: 429 at t+0.50 … t+4.46, first 200 at **t+5.51 s** |
| Throttle isolation | **Per method** | While `trc20` was suspended, `/transactions` (native) returned 200; `trc20` still 429 |
| Retrying during throttle | Does **not** extend it | 6 failed retries inside the window; recovery still landed at ~5.1 s from the trip |

Documented, for contrast: TronGrid's own rate-limit page publishes **no numbers** and states
*"Specific quota and QPS may change depending on plan, network, endpoint type, and service
policy. Do not hard-code fixed limits into business logic."*
([developers.tron.network/reference/rate-limits](https://developers.tron.network/reference/rate-limits))

### TronScan — `https://apilist.tronscan.org`, no API key

| Property | Value | How measured |
|---|---|---|
| Sustained, 2.0 s spacing | **12/12 HTTP 200** | `token_trc20/transfers?limit=20` |
| At 1 req/s | 4/5 — **one 30 s read timeout** | Ramp harness, 5 requests |
| 429 behaviour | **Never observed** | Failure mode is a timeout, not a 429 |
| Practical ceiling | **~0.5 req/s**, low confidence | Small sample; unreliable rather than throttled |

Useful as a **second, independent pool** for TRC-20 transfers, not as a high-rate source.

### Blockscout — `https://eth.blockscout.com`, no API key

| Target rate | Requests | Achieved (wall) | Codes | ok median | ok p95 |
|---|---|---|---|---|---|
| 1/s | 5 | 0.9/s | 200×5 | 1589 ms | 1625 ms |
| 2/s | 10 | 1.7/s | 200×10 | 1554 ms | 1642 ms |
| 4/s | 20 | 3.1/s | 200×20 | 1570 ms | 2079 ms |
| 8/s | 40 | 6.2/s | 200×40 | 1562 ms | 1712 ms |
| 12/s | 48 | 8.6/s | 200×48 | 1698 ms | 2312 ms |
| 18/s | 72 | 11.8/s | 200×72 | 1924 ms | 2294 ms |

**Zero non-200 responses in 195 requests.** Achieved rate was bounded by my own client (40
worker threads × ~1.6–1.9 s latency), not by the server. Latency rose only ~20% from 1/s to
18/s, so no shadow-throttling was visible either. **I stopped at 18/s rather than find the
ceiling** — pushing a free public instance harder would be discourteous, and 11.8 req/s already
exceeds every requirement in this project by an order of magnitude.
Blockscout's own docs do not publish a public-instance rate limit
([docs.blockscout.com/devs/apis](https://docs.blockscout.com/devs/apis)).

### Etherscan — **could not measure**

| Attempt | Result |
|---|---|
| `GET https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address=0xd8dA…6045&…` | HTTP **200**, body `{"status":"0","message":"NOTOK","result":"Missing/Invalid API Key"}` |
| `GET https://api.etherscan.io/api?module=account&action=txlist&address=0xd8dA…6045&…` (V1) | HTTP **200**, body `{"status":"0","message":"NOTOK","result":"You are using a deprecated V1 endpoint, switch to Etherscan API V2 …"}` |

No key exists in the repo and none was created for this measurement. Every Etherscan figure
below is **documented only**:

| Tier | Rate limit | PRO endpoints |
|---|---|---|
| **Free** | **3 calls/second**, up to 100,000/day, selected chains only | Not available |
| Lite | 5 calls/second, 100,000/day | Not available |
| Standard | 10 calls/second, 200,000/day | Available |

Source: [docs.etherscan.io/rate-limits](https://docs.etherscan.io/rate-limits). **Note this is
3 req/s, not the ~5 req/s asserted in [DATA_SOURCES.md §1](../DATA_SOURCES.md).**

---

## Latency

Realistic calls, sequential with a fixed gap so the limiter never fires.

| Provider · endpoint | n | Median | p95 | Min / Max | Response bytes |
|---|---|---|---|---|---|
| TronGrid `/v1/accounts/{a}/transactions/trc20?limit=200` | 20 | **938 ms** | **1060 ms** | 778 / 1320 | 71,857 |
| TronGrid `/v1/accounts/{a}/transactions?limit=200` (native) | 1 | 1.0 s | — | — | 322,821 |
| TronGrid `/v1/accounts/{a}` | 1 | ~0.9 s | — | — | 32,952 |
| TronScan `/api/token_trc20/transfers?limit=50` | 15 | **430 ms** | **1225 ms** | 395 / 1643 | 92,832 |
| TronScan `/api/token_trc20/transfers?limit=20` | 12 | 555 ms | 1397 ms | — | ~40 KB |
| Blockscout `?action=txlist&offset=200` | 15 | **641 ms** | **1638 ms** | 607 / 1833 | 150,033 |
| Blockscout `?action=txlistinternal` | 10 | **1488 ms** | **2118 ms** | 1424 / 2118 | 525 |
| Blockscout `/api/v2/addresses/{a}/transactions` | 1 | 2.58 s | — | — | 537,004 |
| Etherscan | — | **could not measure** | — | — | — |

Test address for TRON: `TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9` (Binance-Cold 1 per
[OQ-08 §4](OQ-08-tron-label-coverage.md), 2,086 txs, 546 TRC-20 transfers — moderately active,
not a hot wallet).
Test address for Ethereum: `0x098B716B8Aaf21512996dC57EB0615e2383E2f96` (Ronin Bridge exploiter,
OFAC SDN, 430 normal txs).

**Latency does not bind.** At 2.0 s spacing the median TronGrid request (938 ms) finishes with
1.06 s of slack. The limiter is the constraint; the network is not. Increasing concurrency does
not help on TronGrid and is not needed on Blockscout.

---

## Trace time projection

Baseline from [DATA_SOURCES.md §1](../DATA_SOURCES.md): 5 hops, ~200 new addresses, ~400
requests (native + token per address).

### TRON via TronGrid, no API key

```
per address:  1× trc20 request  (bucket A, 0.5 req/s)
              1× native request (bucket B, 0.5 req/s)
              1× account request(bucket C, 0.5 req/s)   ← measured independent

bucket A: 200 requests ÷ 0.5 req/s = 400 s
bucket B: 200 requests ÷ 0.5 req/s = 400 s   } run concurrently — measured 36/36 OK
bucket C: 200 requests ÷ 0.5 req/s = 400 s   }

wall time = 400 s  ≈ 6 min 40 s        NFR-01 target = 120 s        overrun = 3.3×
```

Adding TronScan as a second pool for TRC-20 (0.5 req/s, measured) halves that bucket:

```
trc20 across TronGrid + TronScan: 200 ÷ 1.0 req/s = 200 s
native on TronGrid alone:         200 ÷ 0.5 req/s = 400 s   ← still binds
wall time = 400 s unless native fetches are dropped or also split
```

### What actually fits in 120 s

| Configuration | Uncached addresses in 120 s |
|---|---|
| TronGrid only, 2 requests/address | **60** |
| TronGrid + TronScan for TRC-20, native dropped | **120** |
| Ethereum via Blockscout at a self-imposed 5 req/s | **300** (2 requests each) |
| Fixture mode (ADR-009) | unbounded — no network |

### What would make NFR-01 achievable

| Lever | Effect | Verdict |
|---|---|---|
| Address budget 200 → **60** | 400 s → 120 s | **Works.** Cheapest, most honest fix |
| Cache hit rate ≥ **70%** | 200 addresses → 60 misses | Works for *repeat* traces only. A first trace of a fresh case has a 0% hit rate — caching cannot rescue the demo's first run |
| Depth 5 → **3**, fan-out 20 → **8** | fewer addresses reached | Works, and is the mechanism that delivers the 60-address budget |
| TronGrid API key | unknown | **Unmeasurable.** TronGrid publishes no numbers and explicitly says not to hard-code them. The 429 body itself recommends getting a key. This must be measured once a key exists — it is the single highest-value unknown remaining |
| Paid tier | unknown | Same problem; TronGrid's paid limits are quoted per customer |
| Fixture mode | 400 s → ~0 s | Already the demo path (ADR-009). **This is why the demo will look fine and the live path will not.** Say so in the demo, do not hide it |

**The honest framing for a judge:** live tracing on free public infrastructure is rate-limited to
roughly one address every two seconds. TraceFall's 120-second promise holds for a 60-address
trace, for any cached re-trace, and for the fixture-backed demo. It does not hold for a cold
200-address live trace, and the UI should show progress and a partial-result flag rather than
pretend otherwise.

---

## 429 behaviour

Write the backoff against this, not against the generic ladder in
[BLOCKCHAIN_ANALYTICS.md §3](../BLOCKCHAIN_ANALYTICS.md).

### TronGrid — measured

```
HTTP/1.1 429
Date: Fri, 04 Sep 2026 22:31:10 GMT
Content-Type: application/json
Transfer-Encoding: chunked
Connection: close
Server: openresty
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: *

{"Error":"request rate of (getTrc20TransactionsByAccount) exceeded the allowed_rps(1),
and the query server is suspended for 5 s. To obtain higher request quotas and a more
stable service, it is recommended to authenticate with an API Key. Please refer to the
documentation: https://developers.tron.network/reference/select-network#how-to-get-an-api-key"}
```

- **No `Retry-After`.** No `X-RateLimit-*`, no `X-Remaining-*`. Those are the complete headers.
- The recovery interval is **only** available by parsing `"suspended for N s"` out of the prose,
  or by hard-coding 5 s. Measured recovery: **5.51 s** from the trip.
- The JSON key is capital-`E` **`Error`**, and there is no `success` or `statusCode` field —
  which **differs from the shape TronGrid documents** for V1
  (`{"success": false, "error": "…", "statusCode": 429}`). Parse defensively; do not key on
  either field name alone. Key on HTTP status.
- The suspension is **per RPC method**. Failing over the whole provider on one method's 429
  throws away the other two-thirds of available throughput.

**Consequence for the backoff design:** the documented `1s, 2s, 4s` ladder in
BLOCKCHAIN_ANALYTICS.md §3 spends all three attempts *inside* the 5-second suspension window
(1 + 2 + 4 = 7 s of sleep, but the first two retries land at t+1 s and t+3 s and both fail),
then fails over unnecessarily. Correct behaviour: **park that method's bucket for 5.5 s + jitter,
then retry once.** Fail over only after that.

### Blockscout — could not measure

No 429 was produced in 195 requests at up to 11.8 req/s achieved. I stopped rather than escalate
further. **Assume one exists**, honour `Retry-After` if present, and fall back to exponential
backoff with jitter — but do not tune for it, because it was not reachable at any rate this
project will use.

### TronScan — could not measure

No 429 observed. The observed failure mode is a **30 s read timeout** at 1 req/s. Treat timeouts,
not 429s, as TronScan's throttle signal.

### Etherscan — documented, and a real implementation trap

> "An API call that encounters an error will return 0 as its `status code` and display the cause
> of the error under the `result` field."
> ```json
> {"status":"0","message":"NOTOK","result":"Max rate limit reached, please use API Key for higher rate limit"}
> ```

Source: [docs.etherscan.io/common-error-messages](https://docs.etherscan.io/common-error-messages).
Confirmed in shape by my keyless calls, both of which were **HTTP 200** carrying `status:"0"`.

**A backoff keyed on HTTP 429 will never fire against Etherscan.** The rate-limit signal is
in-band at HTTP 200. Any Etherscan adapter must inspect the body. Also documented: more than 5
invalid API-key attempts in 30 seconds throttles the source IP for 30 seconds.

---

## Internal transactions (OQ-02)

### Availability

| Provider | Endpoint | Free tier? | Evidence |
|---|---|---|---|
| Etherscan | `module=account&action=txlistinternal` | **Yes** | [endpoint-overview](https://docs.etherscan.io/endpoint-overview) marks PRO endpoints with a `<Pro />` badge and states *"Endpoints marked PRO are available to the Standard plan and above. All others are available on the free plan."* `Get Internal Transactions by Address` carries **no** badge. **Documented, not measured** — no key |
| Etherscan | `txlistinternal` by tx hash | Yes | No `<Pro />` badge |
| Etherscan | `txlistinternal` by **block range** | **No — PRO** | Carries `<Pro />` |
| Blockscout | `?module=account&action=txlistinternal` | **Yes, verified live** | HTTP 200, correct data |
| Blockscout | `/api/v2/addresses/{a}/internal-transactions` | **Yes, verified live** | HTTP 200, cursor pagination |

Also worth knowing: Etherscan's `getaddresstag` (name tags / address metadata) **is** a PRO
endpoint. That independently confirms [DATA_SOURCES.md §1](../DATA_SOURCES.md)'s position that
Etherscan gives us transactions and not labels.

### Worked example — Ronin Bridge, 173,600 ETH invisible to `txlist`

Address `0x098B716B8Aaf21512996dC57EB0615e2383E2f96` (Ronin Bridge exploiter, OFAC SDN).
Both requests made live against Blockscout on 2026-09-05:

```
GET https://eth.blockscout.com/api?module=account&action=txlist&address=0x098B…2f96
GET https://eth.blockscout.com/api?module=account&action=txlistinternal&address=0x098B…2f96
```

| Source | Records | ETH in | ETH out |
|---|---|---|---|
| `txlist` (normal) | 430 | **8,667.91** | 182,165.96 |
| `txlistinternal` | 1 | **173,600.00** | 0 |

The single internal record:

```
block 14442835   tx 0xc28fad5e8d5e0ce6a2eaf67b6687be5d58113e16be590824d6cfa1a94467d0b7
from 0x1a2a1c938ce3ec39b6d47113c7955baa9dd454f2  (Ronin Bridge, MainchainGatewayManager)
to   0x098b716b8aaf21512996dc57eb0615e2383e2f96
value 173600.0 ETH
```

**That transaction hash is present in `txlist` too** — and this is the whole point. In the
normal-transaction list it appears as:

```
from  0x098b716b8aaf21512996dc57eb0615e2383e2f96   (the exploiter)
to    0x1a2a1c938ce3ec39b6d47113c7955baa9dd454f2   (the bridge)
value "0"                                          isError "0"
```

Direction reversed, **value zero**. A tracer built on normal transactions alone does not merely
miss the transfer — it sees the transaction, records it as a zero-value outbound call, and
produces a graph in which the largest single inbound movement is 3,390 ETH. It misses
**95.2%** of the ETH that entered the address, and gets the direction of the largest edge
backwards. Exactly the "looks complete and is not" failure OQ-02 names.

### Pagination and caps

| Provider | Behaviour | Evidence |
|---|---|---|
| Blockscout, etherscan-compat | `offset` honoured; `offset=200` → 200 rows, `offset=1000` and `offset=10000` → all 430 rows. No cap reached | Three live requests |
| Blockscout, v2 | Cursor via `next_page_params`; `null` when exhausted | Live |
| Blockscout, both | Returns `"message": "Some internal transactions within this block range have not yet been processed"` **alongside HTTP 200 and valid data**. Seen on 3 of 3 internal-tx requests | Live. **Must surface as `complete=false`** — silently trusting a 200 here is the same class of error OQ-02 warns about |
| Etherscan | `page` + `offset`, documented, no maximum stated in the OpenAPI schema | Documented |
| Etherscan record cap | Historically 10,000 per request. Web search results claim a reduction to **1,000 for Free tier from 2026-07-01**. **I could not confirm this in Etherscan's primary documentation** (`txlist.md`, `txlistinternal.md`, `rate-limits.md`, `best-practices.md` mention no cap at all) and could not test it without a key. **Verify before relying on it** — if true, the 10,000-transfer hard cap in [BLOCKCHAIN_ANALYTICS.md §3](../BLOCKCHAIN_ANALYTICS.md) is 10× too optimistic on Ethereum |

### Verdict on OQ-02

Etherscan's free tier **is** sufficient for internal transactions, on documentation. But
**Blockscout must be primary for Ethereum**, on measurement:

- no API key required (Etherscan now rejects every keyless request outright);
- measured ≥11.8 req/s vs Etherscan's documented 3 req/s free tier — **4× better, and measured
  against documented**;
- identical internal-transaction coverage, plus entity metadata in the v2 response (the Ronin
  Bridge address came back tagged `Ronin Network` / `Axie Infinity`) that Etherscan puts behind
  a PRO endpoint;
- no `page`/`offset` cap observed;
- one cost: Blockscout returns the "not yet processed" partial-data warning, which Etherscan does
  not. That is a feature if honoured and a silent corruption if ignored.

The failover therefore does **not** silently lose internal transactions in either direction —
provided both adapters call `txlistinternal` and both normalise the partial-data warning.

---

## Fixture size (OQ-03)

Measured on `TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9` — full TRC-20 history, 3 pages at `limit=200`.

| Payload | Records | Raw bytes | gzip -9 | Ratio | Bytes/record raw | Bytes/record gz |
|---|---|---|---|---|---|---|
| TRC-20 transfers, **full history** | 546 | **194,614** | **51,270** | 3.80:1 | **356** | 94 |
| Native transactions, 1 page | 200 | **322,821** | 57,348 | 5.63:1 | **1,614** | 287 |
| Account metadata | 1 | **32,952** | 11,324 | 2.91:1 | — | — |

Native TRON transactions cost **4.5× more bytes per record** than TRC-20 transfers, because the
response embeds full `raw_data`. That matters: the fraud is in the TRC-20 transfers.

### Extrapolation to a 200-address trace

| Scenario | Per address | 200 addresses raw | 200 addresses gzipped |
|---|---|---|---|
| Lean — 50 TRC-20 + 20 native + account | 53 KB | **10.6 MB** | **~2.3 MB** |
| Realistic — 200 TRC-20 + 100 native + account | 243 KB | **48.7 MB** | **~9 MB** |
| One service node at the 10,000-record cap | 19.7 MB | — | ~3.6 MB **each** |

For 3–5 demo cases traced 5 hops: **10–50 MB raw, 2–10 MB gzipped**, before deduplication.
Deduplication matters more than compression here — demo cases converge on the same exchange hot
wallets, so key the fixture store on `(provider, chain, address, window, cursor)` (the cache key
already specified in [BLOCKCHAIN_ANALYTICS.md §3](../BLOCKCHAIN_ANALYTICS.md)) and the overlap
collapses.

### Git recommendation

**Commit gzipped fixtures directly. No Git LFS.** A 2–10 MB compressed fixture set is well inside
what git handles comfortably, and LFS's failure mode — a setup step that breaks on an unfamiliar
machine, on demo day — is exactly the risk OQ-03 flags. This is OQ-03's third option and it is
the right one.

Three caveats that change the arithmetic if ignored:

1. **Gzipped blobs do not delta-compress in git.** Every re-capture writes a full copy into
   history. Re-capture rarely; squash the fixture commits.
2. **Cap fixture capture at ~2,000 records per address, not 10,000.** One un-capped exchange hot
   wallet costs more than the entire rest of the fixture set. Record the truncation — a truncated
   result is itself a finding (BLOCKCHAIN_ANALYTICS.md §3).
3. **Skip native TRX pages for addresses with no TRC-20 activity on the traced path.** 4.5× the
   bytes per record for the asset class that is usually not the fraud.

Evidence integrity is unaffected: gzip is lossless, so SHA-256 of the decompressed body equals
the hash captured at retrieval time (FR-22).

---

## Recommendations

### Trace parameters

| Setting | Current | Recommended | Reason |
|---|---|---|---|
| `TRACE_MAX_DEPTH` | 5 | **5 in fixture mode, 3 in live mode** | Depth costs nothing when there is no network. Live, depth 5 with any real fan-out overruns 120 s by 3×+ |
| `TRACE_FANOUT_CAP` | 20 | **20 fixture, 8 live** | With depth 3 and fan-out 8 the worst case is 1+8+64 = 73 addresses, close to the measured 60-address / 120-second budget |
| **New: `TRACE_ADDRESS_BUDGET`** | — | **60** (TronGrid only) / **120** (TronGrid + TronScan) | This is the parameter that actually enforces NFR-01. Depth and fan-out are proxies for it; measure and cap the real quantity. On exhaustion return `complete=false, reason=ADDRESS_BUDGET` alongside the existing `PAGE_LIMIT` flag (FR-27) |
| `TRACE_EDGE_BUDGET` | — | keep, subordinate to the address budget | Edges are cheap; requests are not |

### Cache

| Setting | Current | Recommended | Reason |
|---|---|---|---|
| Default TTL | 1 h | **24 h for closed block ranges; 5 min for open-ended "latest" queries only** | Historic transfers are immutable. A 1-hour TTL re-fetches immutable data during a single working session — at 0.5 req/s that is the most expensive mistake available. This is the highest-leverage single change in this document |
| Fixture mode | never expires | unchanged | Correct already |
| Request coalescing | specified | **build it in Phase 3, not later** | With a per-method bucket of 0.5 req/s, two concurrent jobs asking for the same hot wallet cost 4 seconds of the trace's entire budget |

### Rate limiter

| Provider | Configuration |
|---|---|
| **TronGrid** | Token bucket **per `(provider, rpc_method)`** — not per provider. **Capacity 1** (burst tolerance is measurably zero), **refill 0.5/s**. A single provider-wide bucket would discard two-thirds of the measured throughput |
| **TronGrid 429** | Park **that method's** bucket for **5.5 s + jitter(0–1 s)**, retry once, then fail over. Do **not** use 1/2/4 s — every retry lands inside the 5 s suspension. Do **not** fail over the whole provider; the other methods are unaffected (measured) |
| **TronScan** | Capacity 1, refill 0.5/s. Treat a **timeout** as the throttle signal; no 429 was ever observed. Request timeout 15 s, not 30 s — a 30 s hang costs 15 requests' worth of budget |
| **Blockscout** | Capacity 5, refill **5/s** — a self-imposed limit well under the ≥11.8 req/s measured, chosen out of courtesy to a free public instance rather than necessity. Honour `Retry-After` if a 429 ever appears |
| **Etherscan** | Capacity 3, refill **3/s** (documented free tier — *not* the ~5 req/s in DATA_SOURCES.md §1). **Detect throttling in the response body**, not the HTTP status: `status == "0"` and `result` containing `Max rate limit reached`. An HTTP-429-only backoff is dead code against Etherscan |
| All | 30 s hard timeout per request (NFR-05) is fine for Blockscout; tighten to 15 s for TronScan |

### Documents to correct

- **[DATA_SOURCES.md §1](../DATA_SOURCES.md)** — "TronGrid … generous free tier; adequate for the
  MVP" is wrong for the keyless case (measured 0.5 req/s per method). "Etherscan ~5 req/s" is
  wrong (documented 3). "The Ethereum free tier at ~5 req/s is the tighter constraint" is
  inverted: TRON is ~20× tighter than Ethereum via Blockscout.
- **[BLOCKCHAIN_ANALYTICS.md §3](../BLOCKCHAIN_ANALYTICS.md)** — the `1s, 2s, 4s` backoff and
  "on 429 → three attempts, then failover" do not match TronGrid's actual 5 s per-method
  suspension. The provider table's "Free-tier reality" column needs the measured numbers.
- **NFR-01** — either restate as "under 120 s for a trace of up to 60 uncached addresses, or any
  cached or fixture-backed trace", or accept it is met only in fixture mode. The first is honest
  and still a good claim.

### Follow-ups

1. **Obtain a free TronGrid API key and re-run this measurement.** It is the one lever that could
   restore the original 200-address / 120-second target, and it is currently unquantified — the
   limits are not published and TronGrid says not to hard-code them. Highest-value open unknown.
2. **Verify the Etherscan free-tier record cap** (10,000 vs 1,000 from 2026-07-01). Unconfirmed
   in primary documentation; unmeasurable without a key. If 1,000 is real, the 10,000-transfer
   hard cap in BLOCKCHAIN_ANALYTICS.md §3 is wrong for Ethereum.
3. **Feeds OQ-17** (should the MVP ship Ethereum at all): measured, Ethereum via Blockscout is
   the *easier* chain to ingest — no key, no measurable throttling, richer metadata. The rate
   limits are not an argument against Ethereum; they are an argument against TronGrid.
4. **Feeds OQ-06** (are the default thresholds right): depth 5 / fan-out 20 is not merely
   unvalidated against real case sizes, it is unreachable inside NFR-01 on the live path.

---

## Reproduction

```bash
# TronGrid: trip the limiter and read the message
curl -s "https://api.trongrid.io/v1/accounts/TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9/transactions/trc20?limit=20" &
curl -s "https://api.trongrid.io/v1/accounts/TMuA6YqfCeX8EhbfYEg5y7S4DqzSJireY9/transactions/trc20?limit=20" &
wait   # one 200, one 429 with allowed_rps(1)

# Ronin: 173,600 ETH visible only in the internal-transaction list
curl -s "https://eth.blockscout.com/api?module=account&action=txlist&address=0x098B716B8Aaf21512996dC57EB0615e2383E2f96"
curl -s "https://eth.blockscout.com/api?module=account&action=txlistinternal&address=0x098B716B8Aaf21512996dC57EB0615e2383E2f96"

# Etherscan without a key
curl -s "https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address=0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
```

Measurement harness was a throwaway stdlib-only script (fixed-start-time spacing, thread pool for
concurrency tests) kept outside the repository, as OQ-01 specifies.
