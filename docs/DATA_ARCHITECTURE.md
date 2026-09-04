# Data Architecture — TraceFall

How data enters the system, what shape it takes at each stage, and what guarantees hold at
each layer. The physical schema is in [DATABASE_DESIGN.md](DATABASE_DESIGN.md).

---

## 1. The four layers

```
 L0  EVIDENCE     raw provider responses, immutable, hashed
       │          "what the provider actually said, and when"
       ▼
 L1  CANONICAL    normalized Transfer / Transaction rows
       │          "the same facts, chain-agnostic"
       ▼
 L2  DERIVED      profiles, traces, graphs, patterns, attributions, risk
       │          "what we computed from those facts"
       ▼
 L3  PRESENTED    API responses, UI state, PDF reports
                  "what the investigator sees, with tiers attached"
```

**The rule that makes this worth having:** every L3 claim must be traceable down to L0. If an
investigator asks "why do you say this address sent 40,000 USDT to Binance", the system can
walk back: report line → risk signal → attribution → trace edge → transfer rows → raw provider
response → hash and retrieval timestamp. No layer may introduce a fact that did not come from
the layer below it.

---

## 2. L0 — Evidence layer

**Contents.** Verbatim provider responses, exactly as received.

**Guarantees.**
- **Immutable.** Written once, never updated, never deleted by application code.
- **Hashed.** SHA-256 of the response body, stored alongside.
- **Attributed.** Provider name, endpoint, request parameters, HTTP status, retrieval
  timestamp (UTC).
- **Written first.** Persisted before any parsing, so a parse failure never loses evidence.

**Why this exists.** Public blockchain data is reproducible in principle, but the *provider's
view of it at a moment in time* is not. If a report says an address had a certain history on
15 March, the evidence layer is what supports that claim months later. It is also the only
defence against a provider silently changing its API response shape.

**Storage.** Response bodies as compressed files on disk (or object storage), with metadata
rows in `evidence_items` pointing at them. Bodies are not stored in PostgreSQL — they are
large, append-only, and never queried by content.

**Retention.** Retained for the life of the case. See
[PRIVACY_AND_COMPLIANCE.md](PRIVACY_AND_COMPLIANCE.md).

---

## 3. L1 — Canonical layer

**Contents.** `transactions` and `transfers` — the chain-agnostic model everything downstream
reads.

The critical design choice: **one `Transfer` row per value movement**, not per transaction. A
single Ethereum transaction can move ETH and emit three ERC-20 `Transfer` events; that is four
rows sharing one `tx_hash`, distinguished by `transfer_index`. This makes the tracing engine's
job trivially uniform — it only ever sees value movements between two addresses.

**Canonical `Transfer` fields.**

| Field | Notes |
|---|---|
| `chain` | `TRON` \| `ETHEREUM` |
| `tx_hash` | Provider-native form |
| `transfer_index` | Ordinal within the transaction |
| `block_number`, `block_time` | `block_time` is UTC and is the only time used for analysis |
| `from_address`, `to_address` | Canonical form (see §5) |
| `asset_id` | FK to `assets`; native currency is a row like any token |
| `amount_raw` | **String/NUMERIC integer** — never a float |
| `decimals` | Copied from the asset at write time, so historical rows survive metadata changes |
| `amount` | NUMERIC(78,0)-derived decimal for display and comparison |
| `usd_value_approx` | Nullable, explicitly approximate |
| `fee_raw` | Transaction-level; attributed to the first transfer only |
| `status` | `SUCCESS` \| `FAILED` \| `REVERTED` |
| `direction_hint` | Derived per-query, not stored |

**Guarantees.**
- **Idempotent.** `(chain, tx_hash, transfer_index)` is unique. Re-ingesting the same data
  changes nothing.
- **Integer-exact.** All amount arithmetic is integer arithmetic at raw precision. Decimal
  conversion happens once, at display. A float anywhere in this path is a bug.
- **Lossless on failure.** Failed and reverted transfers are retained and flagged. A scammer's
  failed transaction is investigative signal.
- **Append-mostly.** Rows are inserted; the only updates are backfilling `usd_value_approx`
  when a price source becomes available.

**Why L1 exists separately from L0.** Because two chains with two API shapes must become one
model *once*, in one place, so that nothing downstream is ever chain-aware. This is what makes
NFR-17 (one adapter per new chain) achievable.

---

## 4. L2 — Derived layer

**Contents.** `address_profiles`, `traces` (+ `trace_nodes`, `trace_edges`),
`pattern_findings`, `attributions`, `risk_assessments`, `alerts`.

**Guarantees.**
- **Reproducible.** Every derived artefact records the engine version and config version that
  produced it. An old risk score remains explicable even after weights change (FR-85).
- **Versioned, not overwritten.** Re-running an analysis creates a new `analysis_run` and a new
  set of derived rows (FR-124). Comparing runs is then possible, and a report generated last
  week still points at the data it was generated from.
- **Disposable.** L2 can be deleted and recomputed from L1 entirely. This is the test of
  whether the layering is real. Investigator overrides and notes are the sole exception —
  they are human input and live in their own tables, never regenerated.
- **Tier-carrying.** Anything in L2 that represents an inference carries its tier and evidence
  with it. There is no such thing as a bare `PROBABLE` claim in this system.

**Data-version keying.** An `AddressProfile` is cached against a `data_version` derived from
the address's latest ingested block. New data invalidates the profile automatically; stale
profiles are never silently reused.

---

## 5. Address canonicalisation

The single most common source of silent bugs in blockchain tooling. Rules, applied at the
boundary, once:

| Chain | Canonical storage form | Display form |
|---|---|---|
| TRON | base58check as provided (case-sensitive, no transformation) | as stored |
| Ethereum | **lowercase hex** with `0x` prefix | EIP-55 mixed-case checksum form |

Every address entering the system is canonicalised before storage or lookup. Comparison is
always on the canonical form. The EIP-55 checksum is *verified* on input when the user supplies
mixed case (catching typos), then discarded for storage. Displaying the checksum form is a
rendering concern, computed at the edge.

TRON addresses additionally have a hex representation (`41...`) used by some APIs; adapters
convert at the adapter boundary and nothing above `chains/` ever sees the hex form.

---

## 6. Asset handling

Native currency and tokens share one `assets` table — TRX and ETH are rows, not special cases.
This removes an entire class of branching from the tracing and risk engines.

`decimals` is copied onto each transfer at write time rather than joined at read time. Token
metadata can change or be re-reported differently; the historical transfer must not.

**Unknown tokens** are stored with `symbol=NULL` and the contract address recorded. Display
suppresses a decimal amount rather than showing a wrong one. Guessing 18 decimals for a token
that uses 6 misstates the amount by a factor of a trillion, in a police report.

---

## 7. Caching strategy

| What | Where | Key | TTL / invalidation |
|---|---|---|---|
| Provider responses | Redis | `(provider, chain, address, window, cursor)` | TTL, default 1 h live / infinite in fixture mode |
| Address profiles | Redis + `address_profiles` table | `(chain, address, data_version)` | Invalidated by new data |
| Token metadata | Redis | `(chain, contract)` | 24 h |
| Price data | Redis | `(asset, date)` | 24 h |
| Job state | Redis | `job_id` | Until job completion + 1 h, then Postgres is authoritative |

**Correctness invariant:** flushing the entire cache changes performance and nothing else. Any
cache that holds the only copy of something is a bug.

---

## 8. Fixture cache — the demo path

`LIVE_MODE=false` routes all provider calls to a **committed fixture cache**: real provider
responses for a curated set of real addresses, captured once and stored in the repository as
files keyed identically to the live cache.

This is not mock data. It is **real chain data, frozen**. It gives:
- a demo that runs with no network and no rate limits,
- deterministic tests over real-world messiness (NFR-14),
- reproducible bug reports.

**Rules.** Fixtures record their capture timestamp and are displayed in the UI with a visible
"cached snapshot — captured <date>" banner (NFR-15). A fixture is never presented as live data.
Capturing fixtures is a documented script, not a manual process.

---

## 9. Synthetic data

Used only for two purposes: training the deposit-address classifier where real labels are
scarce, and exercising pattern detectors in tests.

**Rules.** Synthetic records are flagged at the row level, never mixed into evidence or
canonical layers for a real case, and are visibly labelled anywhere they surface. A generator
script documents the laundering topologies it produces.
[AI_ML_STRATEGY.md](AI_ML_STRATEGY.md) covers what synthetic data can and cannot teach a model.

---

## 10. Data volume estimates

Sizing the system honestly, for one typical investigation:

| Item | Typical | Worst realistic |
|---|---|---|
| Addresses touched by one trace | 200–2,000 | 10,000 (edge budget cap) |
| Transfers ingested per address | 10–500 | 10,000 (page cap, then truncated) |
| Transfers per investigation | 5k–50k | ~500k |
| Trace graph nodes returned to UI | 50–500 | 500 (render cap, expandable) |
| Raw evidence per investigation | 5–50 MB | ~500 MB |

At these volumes PostgreSQL with correct indexes is comfortable, and the in-memory NetworkX
graph is trivial. This is the arithmetic behind ADR-003 (no Neo4j).
