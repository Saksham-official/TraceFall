# System Architecture — TraceFall

---

## 1. Architectural decision: modular monolith + async job queue

### Options considered

| Option | Assessment |
|---|---|
| **A. Modular monolith + async worker** — one FastAPI app, strict internal module boundaries, a job queue for the analysis pipeline | One process to run, debug, and demo. Module boundaries are enforced by interface discipline, not by network calls. Extracting any module into a service later is a mechanical change because the interfaces already exist. **Chosen.** |
| **B. Microservices** — separate services for ingestion, tracing, graph, risk, attribution | Buys independent scaling we do not need and costs service discovery, inter-service auth, distributed tracing, N deployment units, and a demo that fails if any one container misbehaves. Serious over-engineering for a system whose peak load is a handful of concurrent investigations. |
| **C. Fully synchronous monolith** — no queue, analysis runs inside the HTTP request | Simplest of all, and wrong: a live multi-hop trace takes 30–120 seconds against rate-limited public APIs. HTTP timeouts, no progress feedback, no cancellation, no concurrency. |
| **D. Event-driven (Kafka/NATS)** | The right shape for continuously monitoring thousands of addresses. That is `FUTURE_SCOPE.md`, not the MVP. |

**Chosen: A.** The async worker is not optional — it is forced by the 30–120 s pipeline
duration. Everything beyond it is deferred until measurement says otherwise.

### The rule that keeps this honest

Modules communicate **only through their declared interfaces**. No module reaches into
another's internals or its database tables. A module that needs another module's data calls
its function. This is what makes NFR-17 (add a chain by writing one adapter) achievable and
what makes any later extraction to a service a refactor rather than a rewrite.

---

## 2. High-level view

```
┌──────────────────────────────────────────────────────────┐
│  React + TypeScript SPA                                   │
│  Dashboard · Investigation Workspace · Graph · Report     │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTPS / REST / JSON
┌────────────────────────▼─────────────────────────────────┐
│  FastAPI application                                      │
│  auth · RBAC · request validation · rate limit · audit    │
└────────────────────────┬─────────────────────────────────┘
                         │
        ┌────────────────▼────────────────┐
        │  Investigation Orchestrator     │
        │  (enqueue · stage sequencing ·  │
        │   progress · degradation)       │
        └────────────────┬────────────────┘
                         │  (Redis queue → worker process)
   ┌─────────────────────┼─────────────────────────────────┐
   │                     │                                 │
┌──▼──────────┐  ┌───────▼────────┐  ┌────────────┐  ┌─────▼──────┐
│ Blockchain  │  │  Transaction   │  │  Address   │  │  Tracing   │
│ Data Svc    │──▶  Normalizer    │──▶ Intelligence│─▶  Engine    │
│ (adapters,  │  │  (→ Transfer)  │  │  (features,│  │ (haircut,  │
│  cache,     │  │                │  │   labels)  │  │  pruning)  │
│  provenance)│  └────────────────┘  └────────────┘  └─────┬──────┘
└──────┬──────┘                                            │
       │ raw responses                              ┌──────▼──────┐
       │                                            │   Graph     │
       ▼                                            │   Engine    │
  evidence store                                    └──────┬──────┘
                                    ┌──────────────────────┼──────────────┐
                              ┌─────▼──────┐   ┌───────────▼──┐   ┌───────▼──────┐
                              │  Pattern   │   │  Attribution │   │    Risk      │
                              │  Detection │   │  Engine      │   │    Engine    │
                              └─────┬──────┘   └───────┬──────┘   └───────┬──────┘
                                    └────────┬─────────┴──────────────────┘
                                             ▼
                                   ┌──────────────────┐
                                   │ Report Generator │
                                   └────────┬─────────┘
                                            ▼
                         ┌──────────────────────────────────────┐
                         │ PostgreSQL  ·  Redis  ·  File store  │
                         └──────────────────────────────────────┘
```

External dependencies: TronGrid / TronScan, Etherscan / Blockscout, label datasets, optional
price API, optional LLM API. All are behind adapters; all are optional at runtime.

---

## 3. Module reference

Each module below is a Python package under `backend/app/`. Format: responsibility, in, out,
depends on, failure modes, scaling path.

### 3.1 `api/` — HTTP layer

**Responsibility.** Route, authenticate, authorise, validate, serialise. **No business logic
whatsoever** — a router function's body should be short enough to read at a glance.
**In.** HTTP requests. **Out.** JSON responses.
**Depends on.** `core` (auth, config), every service module it exposes.
**Failure modes.** Invalid input → 422 with field detail. Unauthorised → 401/403. Unknown
resource → 404. Unhandled exception → 500 with a correlation ID and nothing else (never a
stack trace to the client).
**Scaling.** Stateless; run N replicas behind a load balancer.

### 3.2 `orchestrator/` — Investigation Orchestrator

**Responsibility.** Own the analysis pipeline: enqueue jobs, sequence stages, track progress,
decide what a stage failure means, persist results per stage.

**In.** `(case_id, address_id, trace parameters)`.
**Out.** Job status, stage progress, persisted results, a degradation record listing any stage
that ran partially or not at all.
**Depends on.** Every engine module. Nothing depends on it except `api`.

**The stage contract.** Each stage declares whether it is *required* or *degradable*.

| Stage | Required? | If it fails |
|---|---|---|
| Retrieval | Required | Job fails — with no data there is nothing to analyse |
| Normalization | Required | Job fails |
| Enrichment | Degradable | Continue without labels; attribution drops to behavioural signals only |
| Tracing | Required | Job fails |
| Graph | Required | Job fails |
| Patterns | Degradable | Continue; report notes patterns were not evaluated |
| Attribution | Degradable | Everything becomes `UNATTRIBUTED`; that is an honest answer |
| Risk | Degradable | Report omits score rather than showing a wrong one |
| Alerts | Degradable | Continue |

**Failure modes.** Worker crash mid-job → job marked failed on restart via a heartbeat
timeout; partial stage results already persisted remain valid and visible. Queue unavailable
→ API returns 503 for new analyses and stays fully functional for reading existing results.
**Scaling.** Add worker processes; the queue is the coordination point.

### 3.3 `chains/` — Chain adapters

**Responsibility.** Everything chain-specific, isolated. One module per chain implementing a
single `ChainAdapter` interface: `validate_address`, `is_contract`, `fetch_native_transfers`,
`fetch_token_transfers`, `fetch_transaction`, `get_balance`, `normalize`.

**In.** Address, window, pagination cursor. **Out.** Raw provider payloads and, via
`normalize`, canonical `Transfer` objects.
**Depends on.** HTTP client, config. **Nothing depends on chain internals** — this is the
boundary that makes NFR-17 real.
**Failure modes.** Provider 4xx → surface as a typed error. 429 → backoff. 5xx → failover to
secondary. Malformed payload → typed parse error, raw payload retained for diagnosis.
**Scaling.** Per-provider rate limiters and connection pools; the adapter is where a paid API
key would slot in with no other change.

### 3.4 `ingestion/` — Blockchain Data Service

**Responsibility.** Orchestrate retrieval across adapters. Pagination, caching, rate limiting,
failover, `LIVE_MODE` switching, and **evidence persistence** (raw response + SHA-256 +
timestamp + provider, written before anything else happens to it).

**In.** `(chain, address, window)`. **Out.** Raw responses + a completeness flag.
**Depends on.** `chains`, cache, evidence store.
**Failure modes.** All exhausted → returns partial data with `complete=false` and a reason;
never raises past the orchestrator's degradation handling.
**Scaling.** Cache hit-rate is the lever. Shared Redis cache across workers.

### 3.5 `normalize/` — Transaction Processor

**Responsibility.** Raw → `Transfer`. Decimal handling, multi-transfer expansion, failed-tx
retention, deduplication, optional USD valuation.
**In.** Raw responses. **Out.** `Transfer` rows.
**Depends on.** `chains` (for the normalize implementations), token metadata cache.
**Failure modes.** Unknown token → `asset=UNKNOWN` with contract recorded, not dropped.
Missing price → `usd_value=null`, marked. **Never guesses a decimal count** — an unknown
decimals value means the raw amount is stored and display is suppressed rather than wrong by
a factor of a million.

### 3.6 `intel/` — Address Intelligence Engine

**Responsibility.** Everything the system knows about a single address: aggregate statistics,
behavioural features, label-dataset matches, and behavioural clustering signals.
**In.** Address + its transfers + label datasets. **Out.** An `AddressProfile` — features,
label matches, cluster hints.
**Depends on.** `labels`, `normalize` output.
**Failure modes.** Label dataset missing → profile returns with `labels=[]`; downstream
attribution degrades to Tier B/`UNATTRIBUTED`, correctly.
**Scaling.** Profiles are cached per (address, data version).

### 3.7 `tracing/` — Tracing Engine

**Responsibility.** The BFS fund-flow trace with haircut taint, pruning, fan-out caps, edge
budget, and service-boundary stopping. Pure computation over `Transfer` data — **no network
calls of its own**; it asks the orchestrator for more data via a callback, which is what makes
it unit-testable offline (NFR-12).
**In.** Root, anchor transaction, depth, thresholds, window. **Out.** `Trace` — nodes, edges,
taint shares, termination reasons, ranked paths.
**Depends on.** `intel` (to know what is a service boundary), a data-fetch callback.
**Failure modes.** Edge budget exhausted → returns what it has, marks nodes `EDGE_BUDGET`.
No outflow → single-node trace. Both are results, not errors.
**Scaling.** Bounded by construction — depth × fan-out cap × edge budget. Worst case is a
known constant, not a function of chain size.

### 3.8 `graph/` — Graph Analytics Engine

**Responsibility.** Build the NetworkX graph, compute paths, centrality, components; produce a
render-capped serialisation for the frontend.
**In.** `Trace`. **Out.** Graph JSON + derived measures.
**Depends on.** NetworkX.
**Failure modes.** Graph exceeds render cap → returns top-N by taint with an explicit
"expandable" marker rather than truncating silently.
**Scaling.** Subgraphs are small by construction. If they stop being small, this module is
the one that moves to Neo4j — and only this one.

### 3.9 `patterns/` — Pattern Detection Engine

**Responsibility.** Run each detector over the graph and transfers; emit findings with
triggering transactions and false-positive disclosure.
**In.** Graph + transfers. **Out.** `PatternFinding[]`.
**Depends on.** `graph`.
**Failure modes.** A detector raising must not kill the stage — detectors run independently
and a failure is logged and reported as "detector unavailable".
**Design note.** Each detector is a self-contained function with a declared config block, so
adding one is adding a file.

### 3.10 `attribution/` — VASP Attribution Engine

**Responsibility.** Assign entity type, entity name, tier, confidence, and evidence to each
node. Owns the three-tier discipline.
**In.** `AddressProfile` + graph context. **Out.** `Attribution` records.
**Depends on.** `labels`, `intel`, optionally `ml` (deposit-address classifier).
**Failure modes.** Classifier unavailable → falls back to the deterministic funnel heuristic
with a lower confidence ceiling, and records that it did so. Datasets stale → tier stays
`CONFIRMED` but the dataset date is surfaced so the investigator can judge.
**Non-negotiable.** The tier is set here and nowhere else. No other module may upgrade a
tier.

### 3.11 `risk/` — Risk Engine

**Responsibility.** Deterministic weighted scoring with a full signal breakdown.
**In.** Profile, patterns, attributions, trace structure. **Out.** `RiskAssessment` — score,
band, confidence, itemised signals, config version.
**Depends on.** Everything upstream; **nothing depends on it** except reporting and the UI.
**Failure modes.** Missing inputs reduce confidence, never silently reduce the score. A signal
that cannot be computed is reported as "not evaluated", not as zero.
**Determinism.** Same input + same config version = same score, always (NFR-14, FR-86).

### 3.12 `ml/` — Machine Learning

**Responsibility.** Exactly two models: the deposit-address classifier and optional anomaly
detection. Training scripts live here; inference is a pure function.
**In.** Feature vectors. **Out.** Probability + feature attribution (SHAP or equivalent).
**Failure modes.** Model file absent or fails to load → module reports unavailable; every
consumer has a deterministic fallback. **The system is fully functional with `ml/` deleted.**
That is the design test.

### 3.13 `reports/` — Report Generator

**Responsibility.** Assemble findings into PDF, JSON, and CSV. Templated facts; optional LLM
narrative.
**In.** Case + all findings. **Out.** Report file + content hash + `report` record.
**Depends on.** ReportLab (or WeasyPrint), a graph image renderer, optionally an LLM adapter.
**Failure modes.** LLM unavailable → templated narrative. Graph image fails → report generates
with a table instead of the picture.
**Non-negotiable.** Facts are templated from the database. The LLM never sees a blank space it
could fill with an address.

### 3.14 `labels/` — Label & Dataset Management

**Responsibility.** Load, version, and query curated address-label datasets. Track source,
URL, licence, and ingestion date per record.
**In.** Dataset files. **Out.** Label lookups.
**Failure modes.** Missing dataset → empty result set, logged loudly at startup, attribution
degrades honestly.

### 3.15 `db/` and `core/`

`db/` holds SQLAlchemy models, migrations, and repository functions. `core/` holds config,
security primitives, logging, and shared exception types. Neither contains business logic.

---

## 4. Data flow through one investigation

```
POST /api/v1/cases/{id}/analyses          → 202 {job_id}
  orchestrator enqueues job
  ├ retrieval    : provider → raw responses → evidence store (hashed)
  ├ normalize    : raw → Transfer rows
  ├ enrich       : Transfer + labels → AddressProfile
  ├ trace        : BFS + haircut → Trace (nodes, edges, terminations)
  │    └ on demand: retrieval + normalize + enrich for each newly reached address
  ├ graph        : Trace → NetworkX → measures → capped JSON
  ├ patterns     : → PatternFinding[]
  ├ attribution  : → Attribution[] (tier set here, once)
  ├ risk         : → RiskAssessment (itemised)
  └ alerts       : → Alert[]
GET /api/v1/analyses/{job_id}             → progress, then results
GET /api/v1/cases/{id}/graph              → render-ready graph
POST /api/v1/cases/{id}/reports           → PDF + hash
```

Note the nested loop: tracing discovers addresses, which need retrieval and enrichment. The
orchestrator provides tracing with a fetch callback rather than tracing calling the network
itself — keeping `tracing/` pure and testable.

---

## 5. Cross-cutting concerns

**Configuration.** Environment-driven via a single Pydantic `Settings` object. Secrets only
from environment or a secrets file, never committed, never logged, never returned by an API.

**Logging.** Structured JSON. A correlation ID is generated per analysis job and threads
through every stage and every log line.

**Audit.** Every state-changing operation writes an append-only `audit_log` row: actor,
action, resource, timestamp, and a request hash. Nothing in the application deletes or updates
audit rows.

**Caching.** Redis for provider responses (TTL-based), address profiles (invalidated by data
version), and job state. Cache is an optimisation only — the system is correct with the cache
flushed.

**Errors.** Typed exceptions per module, mapped to HTTP status at the API boundary. Internal
detail never crosses that boundary.

---

## 6. Failure-mode summary

| Failure | Blast radius | Behaviour |
|---|---|---|
| Blockchain provider down | Retrieval only | Failover → cache → partial result, marked |
| Rate limited | Retrieval throughput | Backoff; analysis slower, not wrong |
| Redis down | Performance + queueing | Reads work; new analyses rejected with 503 |
| PostgreSQL down | Everything | Hard failure — the one true single point of failure; accepted for the MVP, documented |
| ML model missing | Attribution confidence | Deterministic fallback, recorded |
| LLM unavailable | Report prose | Templated narrative |
| Label dataset stale | Attribution coverage | Dataset date surfaced; investigator judges |
| Worker crash | One job | Heartbeat timeout marks it failed; partial results retained |
| Graph too large | One trace | Capped, marked expandable |

---

## 7. Scalability considerations

**Current design target:** an SIH demo and a realistic pilot — tens of concurrent
investigations, thousands of addresses.

**The real bottleneck is not compute — it is third-party API rate limits.** No amount of
horizontal scaling fixes a 5-requests-per-second free tier. The levers, in order of value:
aggressive caching, a shared address-profile cache across cases, request coalescing for hot
addresses, and finally paid API tiers or a self-hosted node.

**Ordered scale-out path**, each step taken only when measurement demands it:
1. More worker processes (queue already supports it).
2. PostgreSQL read replicas for dashboard queries.
3. Extract `ingestion/` into its own service with a global rate-limit coordinator — the first
   module worth splitting, because rate limits are inherently a shared global resource.
4. Neo4j for `graph/` if traces routinely exceed ~50k nodes.
5. Event-driven continuous monitoring (`FUTURE_SCOPE.md`).

**Explicitly not doing now:** Kubernetes, service mesh, sharding, multi-region. None of these
address the actual bottleneck.

---

## 8. Deployment shape

`docker compose up` brings up: `api` (FastAPI), `worker` (queue consumer), `postgres`,
`redis`, and `web` (built React SPA behind nginx). One command, five containers, no manual
steps beyond an `.env` file (NFR-11). Details in [DEPLOYMENT.md](DEPLOYMENT.md).
