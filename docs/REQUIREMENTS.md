# Requirements — TraceFall (SIH26183)

Every requirement has a stable ID. `IMPLEMENTATION_PLAN.md` claims each one in exactly one
phase; `TESTING_STRATEGY.md` maps tests to these IDs. Priority follows
[MVP_SCOPE.md](MVP_SCOPE.md): **M** = must have (SIH demo blocker), **S** = should have,
**N** = nice to have, **F** = future / post-SIH.

---

## 1. Functional requirements

### 1.1 Case management

| ID | Requirement | Pri |
|---|---|---|
| FR-01 | An authenticated investigator can create a case with a title, an optional NCRP/FIR reference, a description, and a reported loss amount in INR. | M |
| FR-02 | A case can hold one or more suspect addresses, each with an optional victim-transfer amount and timestamp. | M |
| FR-03 | Cases are listed, searchable by reference and address, and filterable by status and risk band. | M |
| FR-04 | Case status progresses through `OPEN → ANALYSING → REVIEW → CLOSED`, set explicitly by the investigator except `ANALYSING`, which the system sets. | M |
| FR-05 | A case records an immutable activity timeline (created, address added, analysis run, report generated, status changed) attributed to a user and timestamp. | M |
| FR-06 | An investigator can add free-text notes and can pin specific findings as "key evidence" for the report. | S |
| FR-07 | The system flags when a submitted address already appears in another case, and links the two (cross-case correlation). | S |

### 1.2 Address intake and validation

| ID | Requirement | Pri |
|---|---|---|
| FR-10 | The system validates address format per chain: TRON base58check (`T` + 33 chars, 4-byte checksum) and Ethereum hex (`0x` + 40 hex, EIP-55 checksum verified when mixed-case). | M |
| FR-11 | The system auto-detects the chain from address format and asks the user to confirm when ambiguous. | M |
| FR-12 | Invalid addresses are rejected before any network call, with a message explaining what was wrong. | M |
| FR-13 | The system distinguishes externally-owned accounts from contract addresses and labels contracts accordingly. | M |
| FR-14 | Addresses are stored in a canonical case form (TRON base58 as-is; Ethereum lowercase hex) so lookups never miss on case differences. | M |

### 1.3 Blockchain data retrieval

| ID | Requirement | Pri |
|---|---|---|
| FR-20 | The system retrieves native-currency transfers (TRX, ETH) and token transfers (TRC-20, ERC-20) for a given address. | M |
| FR-21 | Retrieval paginates through the provider API until the configured limit or time window is reached, respecting provider rate limits with exponential backoff. | M |
| FR-22 | Raw provider responses are persisted verbatim, with a SHA-256 hash and retrieval timestamp, before any transformation. | M |
| FR-23 | Retrieved data is cached; a repeat request within the configured TTL is served from cache without a network call. | M |
| FR-24 | `LIVE_MODE=false` serves entirely from the committed fixture cache, so a demo runs with no network. | M |
| FR-25 | Provider failure degrades gracefully: the analysis completes with the data obtained, and the result is explicitly marked partial with the reason. | M |
| FR-26 | A secondary provider is used as failover when the primary is unavailable. | S |
| FR-27 | The system records, per address, whether data is complete or truncated, and by what limit. | M |

### 1.4 Normalization

| ID | Requirement | Pri |
|---|---|---|
| FR-30 | All chain data is normalized into a single chain-agnostic `Transfer` model: chain, tx hash, block, timestamp, from, to, asset, raw amount, decimals, normalized amount, USD value at time, fee, status, transfer index. | M |
| FR-31 | Token amounts are converted using the token's actual decimals; integer-precision arithmetic is used throughout, never float. | M |
| FR-32 | Failed and reverted transactions are retained and marked, never silently dropped — a failed transfer is investigative signal. | M |
| FR-33 | A transaction producing multiple transfers yields one `Transfer` row per transfer, all sharing the tx hash. | M |
| FR-34 | Approximate USD valuation at transaction time is attached where a price source is available, and marked as approximate. | S |

### 1.5 Fund flow tracing

| ID | Requirement | Pri |
|---|---|---|
| FR-40 | Given a root address, the system traces outbound value flow across multiple hops. | M |
| FR-41 | When the victim's amount and timestamp are supplied, the trace is anchored to that specific inbound transaction rather than to the address generally. | M |
| FR-42 | Trace depth is configurable (default 5, max 10). | M |
| FR-43 | Value attribution across hops uses proportional (haircut) taint; the convention is stated in the UI and the report. | M |
| FR-44 | Branches carrying taint below a configurable threshold (default 1% of the original amount) are pruned and reported as pruned. | M |
| FR-45 | Expansion stops at service boundaries — addresses attributed as exchange, mixer, or bridge are terminal nodes, not expanded. | M |
| FR-46 | The trace enforces a global edge budget (default 5,000) and a per-node fan-out cap (default top 20 by taint) to prevent graph explosion. | M |
| FR-47 | Every terminal node records a termination reason: `MAX_DEPTH`, `BELOW_THRESHOLD`, `SERVICE_BOUNDARY`, `NO_OUTFLOW`, `EDGE_BUDGET`, or `TIME_WINDOW`. | M |
| FR-48 | The system ranks and returns the highest-value paths from root to each terminal node. | M |
| FR-49 | Backward (inbound) tracing from the root is supported, to identify other victims paying the same address. | S |
| FR-50 | A time window constrains which transfers are eligible for tracing. | M |

### 1.6 Pattern detection

| ID | Requirement | Pri |
|---|---|---|
| FR-60 | Detect **fan-out / splitting**: one address distributing to many recipients within a short window. | M |
| FR-61 | Detect **fan-in / consolidation**: many addresses funding one recipient. | M |
| FR-62 | Detect **rapid transfer / layering**: value passing through an address in under a configurable dwell time (default 10 minutes). | M |
| FR-63 | Detect **peel chains**: a repeating sequence where a large balance moves forward while small amounts peel off. | S |
| FR-64 | Detect **dormancy then burst**: an address inactive for a long period that suddenly transacts heavily. | S |
| FR-65 | Detect **structuring**: repeated transfers of similar, round, or just-below-threshold amounts. | S |
| FR-66 | Every finding cites the exact transactions that triggered it and states its own known false-positive modes. | M |

### 1.7 VASP / entity attribution

| ID | Requirement | Pri |
|---|---|---|
| FR-70 | Every attribution carries exactly one tier: `CONFIRMED`, `PROBABLE`, or `UNATTRIBUTED`. | M |
| FR-71 | `CONFIRMED` requires a direct match in a curated known-address dataset, and returns the source name, source URL, and dataset date. | M |
| FR-72 | `PROBABLE` requires a confidence value in [0,1] plus an enumerated list of evidence items, each independently inspectable. | M |
| FR-73 | The system identifies exchange **deposit addresses** via the funnel heuristic (many-in, sweeps to one consistent destination, no independent activity) and attributes them to the exchange owning the sweep destination. | M |
| FR-74 | The system classifies entity type: `EXCHANGE`, `MIXER`, `BRIDGE`, `TOKEN_CONTRACT`, `DEFI`, `GAMBLING`, `SANCTIONED`, `MERCHANT`, `UNKNOWN`. | M |
| FR-75 | Address labels are versioned with their source and ingestion date; conflicting labels from different sources are surfaced rather than silently resolved. | M |
| FR-76 | The system never renders a `PROBABLE` attribution with the same visual weight or wording as a `CONFIRMED` one, in UI or report. | M |
| FR-77 | For an attributed VASP, the system surfaces known jurisdiction and whether it is FIU-IND registered, where that information is available in the curated dataset. | S |
| FR-78 | An investigator can manually override or confirm an attribution; the override is recorded with user, timestamp, and justification, and never overwrites the machine finding. | S |

### 1.8 Risk scoring

| ID | Requirement | Pri |
|---|---|---|
| FR-80 | The system computes a 0–100 risk score for the root address and for each significant node in the trace. | M |
| FR-81 | The score is produced by a transparent weighted rule engine; every contributing signal is returned with its name, its raw value, its weight, and the points it contributed. | M |
| FR-82 | Scores map to bands: `LOW` 0–24, `MEDIUM` 25–49, `HIGH` 50–74, `CRITICAL` 75–100. | M |
| FR-83 | A confidence value accompanies the score, reflecting data completeness, and is reported separately — never multiplied into the score. | M |
| FR-84 | The UI and report state that the score is an investigative prioritisation aid, not a probability of fraud and not evidence of guilt. | M |
| FR-85 | Rule weights live in a versioned configuration file, not in code, and the config version is recorded in every assessment. | M |
| FR-86 | Re-running an assessment on unchanged data with the same config version produces an identical score. | M |

### 1.9 Graph

| ID | Requirement | Pri |
|---|---|---|
| FR-90 | The system produces a directed, weighted, time-aware graph: nodes are addresses, edges are aggregated value flows. | M |
| FR-91 | Node metadata includes entity type, attribution tier, risk band, taint share, balance, first/last seen, and degree. | M |
| FR-92 | Edge metadata includes total value, transfer count, asset, first/last transfer time, and contributing tx hashes. | M |
| FR-93 | Computes shortest and highest-value paths between the root and any selected node. | M |
| FR-94 | Computes betweenness centrality to identify chokepoint addresses through which most tainted value passes. | S |
| FR-95 | Identifies weakly connected components and, where useful, communities within the trace subgraph. | N |
| FR-96 | Graph responses are paginated or capped so the frontend never receives more nodes than it can render (default cap 500 nodes, with a documented expansion action). | M |

### 1.10 Alerts

| ID | Requirement | Pri |
|---|---|---|
| FR-100 | The system raises an alert when a trace reaches a sanctioned address, a mixer, or a `CRITICAL` risk node. | M |
| FR-101 | Alerts are listed per case and globally, with severity, trigger reason, and the finding that caused them. | M |
| FR-102 | Alerts can be acknowledged, with the acknowledging user and time recorded. | S |

### 1.11 Reporting

| ID | Requirement | Pri |
|---|---|---|
| FR-110 | The system generates a PDF investigation report containing case metadata, suspect address details, the fund flow summary, key transactions, VASP findings with tiers, risk findings with signal breakdown, detected patterns, a graph image, and an evidence appendix of transaction hashes. | M |
| FR-111 | The report states its data sources, retrieval timestamps, and the tracing convention used. | M |
| FR-112 | The report carries an explicit limitations and disclaimer section derived from `LIMITATIONS.md`. | M |
| FR-113 | Each report gets an immutable ID and a SHA-256 content hash recorded in the database. | M |
| FR-114 | Findings are also exportable as JSON and CSV for onward processing. | S |
| FR-115 | Report narrative may be LLM-generated from structured findings; all addresses, amounts, hashes, and entity names are templated from data and never produced by the model. | S |
| FR-116 | If the LLM is unavailable, the report generates with templated narrative and is otherwise complete. | S |

### 1.12 Orchestration

| ID | Requirement | Pri |
|---|---|---|
| FR-120 | Analysis runs as an asynchronous job; the API returns a job ID immediately. | M |
| FR-121 | Job status is pollable and reports the current pipeline stage, percentage complete, and any partial results available. | M |
| FR-122 | A failed stage does not fail the whole job where downstream stages can still run on partial data; the degradation is recorded. | M |
| FR-123 | Jobs are cancellable. | S |
| FR-124 | Re-running an analysis creates a new versioned result rather than overwriting the previous one. | S |

### 1.13 Integration surface

| ID | Requirement | Pri |
|---|---|---|
| FR-130 | The system exposes a documented REST API sufficient for an external system (e.g. NCRP/I4C) to submit an address and retrieve results — demonstrating integration readiness without claiming an actual integration. | S |
| FR-131 | A bulk-submission endpoint accepts multiple addresses for triage. | N |

---

## 2. Non-functional requirements

| ID | Requirement | Target | Pri |
|---|---|---|---|
| NFR-01 | First actionable result (trace + attribution + risk) for a typical address | **Revised 2026-09-05:** < 120 s from fixture cache or a warm cache; live cold-cache traces are bounded by `trace_address_budget` (60 uncached addresses) rather than by wall-clock. Measured provider rates make a 200-address cold trace ~400 s. See `research/OQ-01-provider-rate-limits.md`. | M |
| NFR-02 | API response time for reads of already-computed results | p95 < 500 ms | M |
| NFR-03 | Graph render responsive for the default node cap | 500 nodes, interactive | M |
| NFR-04 | Concurrent analyses supported on demo hardware | ≥ 5 | S |
| NFR-05 | Every external API call is retried with exponential backoff and jitter, and has a hard timeout | 3 retries, 30 s timeout | M |
| NFR-06 | No secret, API key, or credential appears in source, logs, or client responses | zero tolerance | M |
| NFR-07 | All API inputs are schema-validated at the boundary before use | Pydantic models | M |
| NFR-08 | Authenticated access with role-based authorisation; a user sees only cases they own or are assigned to | JWT + RBAC | M |
| NFR-09 | Every state-changing action is written to an append-only audit log | complete | M |
| NFR-10 | Raw evidence is stored immutably with content hashes | SHA-256 | M |
| NFR-11 | The system runs end-to-end from `docker compose up` with no manual steps beyond an env file | single command | M |
| NFR-12 | Each engine module is independently unit-testable with no network access | full isolation | M |
| NFR-13 | Test coverage on the tracing, attribution, and risk modules | ≥ 80% | S |
| NFR-14 | The tracing and risk engines are deterministic given identical input and config | bit-identical | M |
| NFR-15 | Synthetic or demo data is visibly marked as such wherever it is displayed or exported | always | M |
| NFR-16 | Structured JSON logging with a correlation ID per analysis job | complete | S |
| NFR-17 | Adding a new chain requires implementing one adapter interface and no changes to tracing, graph, risk, or UI code | one file | S |
| NFR-18 | The UI meets baseline accessibility: keyboard navigable, sufficient contrast, non-colour-only encoding of risk and attribution tier | WCAG 2.1 AA where practical | S |

---

## 3. Explicit non-requirements

Stated so that no future session mistakes them for gaps:

- **No identity resolution.** The system never attempts to name a person behind an address.
- **No automated cross-chain bridge tracing** in the MVP. Bridges are detected and flagged as
  terminal, with the destination chain named where determinable.
- **No de-mixing.** Mixer interaction terminates a trace.
- **No live government-system integration.** Only an integration-ready API surface.
- **No trading, custody, or fund movement.** TraceFall is read-only against blockchains and
  holds no keys.
- **No privacy-coin support.**
- **No claim of fraud.** The system reports suspicion, flow, and evidence.
