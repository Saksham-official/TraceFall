# Implementation Plan

**The master roadmap.** A future Claude Code session or teammate picks a phase, reads its
section, and implements it.

**Rules for every phase:** update this file's status when a phase completes · do not start a
phase whose dependencies are unmet · if you must deviate from the architecture, record it in
[DECISIONS.md](DECISIONS.md) first · every phase ends with its tests passing.

**Status legend:** ☐ not started · ◐ in progress · ☑ complete

---

## Phase status overview

| Phase | Name | Status | Depends on |
|---|---|---|---|
| 0 | Planning & architecture | ☑ | — |
| 1 | Repository foundation | ☑ | 0 |
| 2 | Backend foundation | ☑ | 1 |
| 3 | Blockchain ingestion | ☑ | 2 |
| 4 | Transaction normalization | ☑ | 3 |
| 5 | Wallet tracing | ☑ | 4 |
| 6 | Graph analytics & pattern detection | ☑ | 5 |
| 7 | VASP attribution | ◐ | 4 (5 for full value) |
| 8 | Risk engine | ☑ | 6, 7 |
| 9 | AI / ML | ☐ | 7 |
| 10 | Frontend dashboard | ◐ | 2 (mocks), 6/7/8 (real data) |
| 11 | Investigation reports | ☑ | 8 |
| 12 | Security hardening | ☐ | 2, 10 |
| 13 | Testing & QA | ☐ | all |
| 14 | Deployment | ☐ | 10 |
| 15 | SIH demo hardening | ☐ | 13, 14 |

---

## Parallelisation

Sequential critical path: **1 → 2 → 3 → 4 → 5 → 6 → 8 → 11 → 15**

Work that can run concurrently once its dependencies are met:

| After | These can run in parallel |
|---|---|
| Phase 2 | **Phase 10** (frontend against mocked API contracts) — start immediately, it is the longest UI-bound track |
| Phase 4 | **Phase 7** (attribution — needs transfers, not traces) and **Phase 5** (tracing) |
| Phase 7 | **Phase 9** (ML classifier) |
| Phase 2 | **Phase 12** (security) can begin incrementally rather than waiting |
| Throughout | **Phase 13** (tests written alongside each phase, not after) |

**Recommended team split (4 people):**
- **A — data track:** Phases 3, 4, 5 (the correctness core; the most demanding work)
- **B — intelligence track:** Phases 7, 8, 9 (attribution and risk)
- **C — frontend track:** Phase 10 from the start, against the API contract
- **D — platform track:** Phases 1, 2, 6, 11, 12, 14

Phase 15 is everyone.

---

## Phase 0 — Planning & architecture ☑

**Goal.** A complete, implementation-ready specification.
**Output.** `CLAUDE.md`, `README.md`, and 29 documents in `docs/`.
**Done when.** All documents exist, are internally consistent, and
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) records every unresolved decision.

---

## Phase 1 — Repository foundation ☑

**Goal.** A repository skeleton that runs, lints, and tests — with no features.

**Tasks.** `git init` · monorepo layout · Python project with ruff, mypy, pytest · Vite + React
+ TypeScript project with eslint and vitest · Dockerfiles · `docker-compose.yml` ·
`.env.example` · `.gitignore` (`.env*`, models, evidence, `__pycache__`, `node_modules`) ·
pre-commit hooks including secret scanning · CI workflow · `scripts/generate-secret.sh`.

**Files.**
```
backend/{pyproject.toml,Dockerfile,app/__init__.py,app/main.py}
frontend/{package.json,vite.config.ts,tsconfig.json,Dockerfile,src/main.tsx}
docker-compose.yml  .env.example  .gitignore  .pre-commit-config.yaml
.github/workflows/ci.yml  scripts/generate-secret.sh
```

**Acceptance.** `docker compose up` starts all five services healthy · `GET /health` returns
200 · the frontend serves a placeholder page · lint, type check, and an empty test suite pass ·
CI is green.
**Tests.** One health-endpoint test; one frontend smoke test.
**DoD.** A fresh clone reaches a running stack in under five minutes following
[DEPLOYMENT.md](DEPLOYMENT.md).

**Verified 2026-09-05.** Backend: ruff, `ruff format --check`, mypy `strict`, and 7 pytest
tests all pass; the API boots against a real `.env` and `GET /api/v1/health` returns 200 with
`{status, version, live_mode, providers}`. Frontend: eslint, `tsc -b`, 2 vitest tests, and
`vite build` all pass. Compose defines the five services with healthchecks; the worker
heartbeat healthcheck was verified directly (exit 1 stale, exit 0 live).

**Outstanding.** `docker compose up` has **not** been run — Docker is not installed on the
development machine. Run it on a machine with Docker and confirm all five containers report
healthy. Everything else in the acceptance list passes, and the images build from the same
sources CI builds.

---

## Phase 2 — Backend foundation ☑
**Depends on:** 1

**Goal.** Auth, database, case CRUD, and the async job scaffold — everything the pipeline
plugs into.

**Tasks.** Pydantic `Settings` · SQLAlchemy async setup · Alembic · implement the schema from
[DATABASE_DESIGN.md](DATABASE_DESIGN.md) **including the CHECK constraints in §9** · Argon2
password hashing · JWT issue/refresh/revoke · RBAC dependencies · case-isolation query filters ·
case and address CRUD · address validation for both chains · audit-log middleware · structured
JSON logging with correlation IDs · Redis job queue and worker entrypoint · `analysis_runs`
state machine · error envelope and exception handlers · `cli.py` with `create-admin`.

**Files.**
```
backend/app/core/{config,security,logging,exceptions,deps}.py
backend/app/db/{session,models/*.py,repositories/*.py}
backend/app/api/v1/{auth,cases,addresses,analyses,health}.py
backend/app/orchestrator/{queue,worker,runner,stages}.py
backend/app/chains/{base,tron,ethereum}.py   # validation only at this phase
backend/app/cli.py
backend/alembic/versions/*.py
```

**In.** Schema and API specifications. **Out.** A working authenticated CRUD API with job
enqueueing.

**Acceptance.** Migrations apply cleanly · admin creation works and **no default credentials
exist** · login returns a JWT; expiry and refresh work · case CRUD enforces isolation ·
**user A cannot reach user B's case, and receives 404 not 403** · address validation rejects
bad checksums · a stub job enqueues, runs, and reports status · every mutation writes an audit
row · the `attributions` and `risk_assessments` CHECK constraints reject invalid rows.

**Tests.** Auth (valid, invalid, expired, refresh, revoke) · RBAC per role · **case isolation
across every case-scoped endpoint** · address validation table-driven · job lifecycle · audit
completeness · constraint rejection.
**DoD.** Auth and case management fully functional; ≥ 80% coverage on `core/` and `db/`.

**Verified 2026-09-05.** 100 tests pass against a real PostgreSQL 16 and Redis 7; ruff,
`ruff format --check`, and mypy `strict` all clean across 43 source files.

Confirmed directly:
- 28 tables, all timestamps `timestamptz`, all four CHECK constraints live.
- The attribution tier constraint rejects all seven inconsistent shapes (confirmed without an
  entity, probable without confidence or evidence, unattributed carrying an entity, and so on).
- `audit_log` rejects UPDATE and DELETE at the database level.
- A second investigator receives **404, never 403**, on every case-scoped endpoint; the
  admin-only DELETE returns an identical 403 whether the case exists or not, so it leaks
  nothing either.
- Enqueue → worker claim → complete, plus cancellation and stale-run reclamation.
- `create-admin` rejects short, mismatched, common, and duplicate credentials. No default
  credentials exist in any build.

**Deviations from this plan**, both recorded as ADRs: no `db/repositories/` layer (ADR-014)
and append-only enforced by triggers rather than role grants (ADR-015). All migrations are
front-loaded here, so no later phase generates one concurrently and forks the chain.

---

## Phase 3 — Blockchain ingestion ☑
**Depends on:** 2 · **Enables:** 4

**Goal.** Retrieve real chain data reliably, and capture evidence.

**Tasks.** `ChainAdapter` interface · TRON adapter (TronGrid: account, TRX transfers, TRC-20
transfers, transaction detail; base58↔hex) · Ethereum adapter (Etherscan: normal, internal,
ERC-20; Blockscout failover) · pagination · token-bucket rate limiter per provider ·
exponential backoff with jitter · provider failover · Redis response cache · **evidence
persistence with SHA-256 before parsing** · **fixture cache and `LIVE_MODE`** ·
`scripts/capture_fixtures.py` · completeness/truncation flags.

**Files.**
```
backend/app/chains/{base,tron,ethereum,registry}.py
backend/app/ingestion/{service,cache,ratelimit,evidence,fixtures}.py
backend/app/db/models/evidence.py
scripts/capture_fixtures.py
tests/fixtures/chain_data/**
```

**In.** Address + chain + window. **Out.** Raw responses, hashed and stored, plus completeness
metadata.

**Acceptance.** Both adapters retrieve real data in live mode · pagination assembles complete
results · 429 triggers backoff and recovers · primary failure fails over · total failure
returns partial data with a reason and **never raises** · evidence rows carry correct hashes ·
**`LIVE_MODE=false` serves everything from fixtures with the network disconnected** ·
truncation is flagged at the page cap.

**Tests.** Adapter unit tests (respx) · pagination · rate-limit and backoff · failover ·
partial-result path · evidence hash correctness · fixture mode offline · the four named cases in
[TESTING_STRATEGY.md §2](TESTING_STRATEGY.md).
**DoD.** Real data retrievable for both chains; fixtures captured for the demo addresses; the
suite passes with no network.

**Verified 2026-09-05.** 136 tests pass; ruff, `ruff format --check` and mypy `strict` clean
across 52 source files.

Confirmed directly:
- Real TronGrid data retrieved live without an API key, captured as fixtures, and replayed
  **with the network blocked at the proxy** — the offline demo path works.
- Etherscan's HTTP-200 rate-limit response is detected by the adapter and raised as a rate
  limit; missing it would silently truncate a trace.
- Failover from Etherscan to Blockscout, with one parser for both.
- 429 and 5xx retried with jittered backoff honouring `Retry-After`; 4xx not retried.
- Total provider failure returns a **partial result and never raises**; a partial failure keeps
  what succeeded and records why the rest is missing.
- Evidence written and SHA-256 hashed before parsing; paths built from server UUIDs only.
- A missing fixture **fails the run loudly** rather than reporting an address with no activity.

**Deviations and findings:**
- **TronGrid's real unauthenticated limit is 3 rps**, not the figure NFR-01 was derived from.
  The default is now 3.0. See OQ-01.
- **TRON has no failover.** TronScan's terms could not be read (OQ-07), and building against
  unread terms is not acceptable here. Documented as a gap, not shipped as a guess.
- Fixture keys exclude time-derived parameters (ADR-016), so fixture mode serves one snapshot
  per address regardless of the requested window.

---

## Phase 4 — Transaction normalization ☑
**Depends on:** 3 · **Enables:** 5, 7

**Goal.** One chain-agnostic transfer model.

**Tasks.** `Transfer` model and persistence · TRON and Ethereum normalizers · **integer-exact
decimal handling** · multi-transfer expansion · failed-transfer retention · token metadata
lookup and cache · **unknown-token handling that never guesses decimals** · UTC timestamp
normalisation · idempotent upsert on `(chain, tx_hash, transfer_index)` · optional USD
valuation, marked approximate · address canonicalisation at the boundary.

**Files.**
```
backend/app/normalize/{service,transfer,decimals,tokens,pricing}.py
backend/app/db/models/{transaction,transfer,asset}.py
```

**Acceptance.** Raw responses from both chains produce correct `Transfer` rows · a 6-decimal
TRC-20 and an 18-decimal ERC-20 both display correctly · unknown tokens retain raw amounts with
display suppressed · a four-transfer transaction produces four rows · failed transfers are
retained and flagged · re-ingestion is a no-op · **no float appears anywhere in the amount
path**.

**Tests.** Everything in [TESTING_STRATEGY.md §3](TESTING_STRATEGY.md), including the
large-amount round-trip property test.
**DoD.** Both chains normalize identically; ≥ 85% coverage on `normalize/`.

**Verified 2026-09-05.** 239 tests pass; ruff, `ruff format --check` and mypy `strict` clean
across 63 source files. Both chains produce identical `Transfer` rows through one persistence
path; amounts stay integer-exact end to end (`RawAmount`, no float in the amount path); a token
with unknown decimals keeps its raw amount with display suppressed rather than guessing;
multi-transfer transactions expand to one row each; failed transfers are retained and flagged;
re-ingestion upserts on `(chain, tx_hash, transfer_index)` and is a no-op. The worker runs
NORMALIZATION as its second stage.

**Outstanding.** `pytest-cov` is not installed, so the ≥ 85% coverage figure is asserted by the
test set, not measured. Install it and record the number.

---

## Phase 5 — Wallet tracing ☑
**Depends on:** 4 · **Enables:** 6

**Goal.** The correctness core: multi-hop fund flow tracing.

**Tasks.** BFS traversal with a value-ordered frontier · **haircut taint attribution** ·
depth limit · taint threshold with pruning records · fan-out cap · edge budget · time window ·
**service-boundary stopping** · termination reasons · anchor-transaction resolution ·
cycle safety · path ranking · backward tracing (`SHOULD`) · **the accounting invariant asserted
after every trace, in production, not only in tests** · trace persistence.

**Files.**
```
backend/app/tracing/{engine,taint,frontier,termination,anchor,paths,invariants}.py
backend/app/db/models/{trace,trace_node,trace_edge}.py
tests/fixtures/traces/**   # the eight named scenarios
```

**In.** Root, anchor, parameters, and a data-fetch callback (tracing makes no network calls
itself). **Out.** A persisted `Trace`.

**Acceptance.** All five correctness properties hold ([WALLET_TRACING.md §10](WALLET_TRACING.md))
· all six termination reasons are produced correctly · haircut arithmetic matches hand-computed
examples · anchoring works with exact, multiple, and no matches · the eight named fixture
scenarios produce expected results · a 5-hop trace on a real address completes within budget.

**Tests.** The full suite in [TESTING_STRATEGY.md §4](TESTING_STRATEGY.md) — the largest and
most important test file in the project.
**DoD.** Deterministic, correct, fully offline-testable; ≥ 90% coverage on `tracing/`.

**Verified 2026-09-05.** 85 tests across `test_tracing_{anchor,haircut,persistence,properties,
scenarios}.py` and `test_transfer_model.py`. Haircut taint with the accounting invariant
asserted in production, not only in tests · all six termination reasons produced · eleven named
scenarios including fan-out, peel chain, cycle, mixer, dust flood, and no-outflow · anchor
resolution for exact, multiple, and no matches, rejecting ambiguous token symbols · path
ranking · persistence to `traces` / `trace_nodes` / `trace_edges`.

**Outstanding.**
- **Not wired into the pipeline.** `worker.py` runs RETRIEVAL → NORMALIZATION and stops;
  `app.tracing` is imported nowhere outside its own package, and `orchestrator/` has only
  `queue.py`. Add the TRACING stage.
- `engine.trace(is_service_boundary=...)` defaults to `None`. The real implementation is
  Phase 7 attribution; until then no trace stops at a service boundary.
- Backward tracing (a `SHOULD`) is not implemented.
- Coverage unmeasured — `pytest-cov` is not installed.

---

## Phase 6 — Graph analytics & pattern detection ☑
**Depends on:** 5 · **Enables:** 8, 10

**Goal.** Turn traces into the object investigators reason with, and name the behaviours in it.

**Tasks — graph.** Trace → NetworkX conversion · edge aggregation per `(from, to, asset)` ·
node and edge metadata · highest-value path (negative-log-weight shortest path) · shortest path
between two nodes · betweenness centrality on the tainted subgraph · connected components ·
cycle detection · **render cap with root, terminals, and service nodes always retained** ·
`truncated` flag · progressive expansion · serialisation.

**Tasks — patterns.** Detector framework where each detector is an independent function with a
declared config block and **a mandatory `false_positive_note`** · `FAN_OUT`, `FAN_IN`,
`RAPID_TRANSFER` (MVP must-have) · `PEEL_CHAIN`, `DORMANCY_BURST`, `STRUCTURING` (`SHOULD`) ·
trigger-transaction capture · plain-language explanation generation · **detector isolation** so
one raising an exception degrades to "detector unavailable" rather than killing the stage ·
finding persistence.

**Files.**
```
backend/app/graph/{builder,algorithms,centrality,serialize,cap}.py
backend/app/patterns/{registry,base,fan_out,fan_in,rapid_transfer,
                      peel_chain,dormancy_burst,structuring}.py
backend/app/db/models/pattern_finding.py
backend/app/api/v1/{graph,patterns}.py
```

**In.** A persisted `Trace` plus its underlying transfers. **Out.** A render-ready graph with
derived measures, and `PatternFinding[]`.

**Acceptance — graph.** Conversion preserves all nodes and edges · parallel transfers aggregate
correctly · highest-value path matches a hand-computed example · betweenness identifies the
known chokepoint in a fixture graph · the cap returns exactly `max_nodes`, always including root
and terminals, and sets `truncated` · all operations complete within the
[GRAPH_ANALYTICS.md §6](GRAPH_ANALYTICS.md) budgets.

**Acceptance — patterns.** All three must-have detectors fire correctly on fixture data ·
**every finding carries a non-empty `false_positive_note`, asserted generically so a new
detector cannot ship without one** · every finding cites its triggering transactions · a
detector raising an exception degrades the finding, not the stage · **no detector fires on its
paired negative fixture** ([TESTING_STRATEGY.md §6](TESTING_STRATEGY.md)).

**Tests.** [TESTING_STRATEGY.md §5 and §6](TESTING_STRATEGY.md) — one positive **and one
false-positive** test per detector.
**DoD.** Graph API returns render-ready data within budget; pattern findings are explainable
and honest about their limits.

**Engines built 2026-09-05.** 337 tests pass; ruff, `ruff format --check` and mypy `strict`
clean across 80 source files. 44 new tests in `test_graph.py` and `test_patterns.py`.

Built and confirmed directly:
- `graph/{builder,algorithms,serialize}.py` over NetworkX. A `DiGraph`, not a `MultiDiGraph`,
  because a trace follows one asset (ADR-017) — at most one aggregated edge per address pair.
  Every edge keeps its `tx_hashes`, so no finding is more than a click from raw evidence, and
  pruned branches are recorded on the node they left rather than vanishing.
- Highest-value path as the negative-log-weight shortest path, **ending at a terminal** — every
  prefix of a path retains at least as much as the path, so an unconstrained endpoint would
  always pick the first hop. Verified against a hand-computed 90/10 split.
- Betweenness over the tainted subgraph identifies the chokepoint in a four-branch fixture;
  weakly connected components; bounded cycle detection; degrees. An edge that carried no
  tainted value is excluded from every path and lends no centrality.
- The render cap keeps the root, every terminal and every **confirmed** service
  unconditionally, returns exactly `max_nodes` when it can, sets `truncated`, and records
  `omitted_successors` per node for the "+N more" affordance. When the mandatory set alone
  exceeds the cap it returns all of it — an over-large graph beats one missing its answer.
  Raw amounts serialise as strings; a JSON number cannot hold an 18-decimal amount exactly.
- `patterns/{base,detectors,persistence}.py`. **A detector with an empty
  `false_positive_note` raises at registration**, so FR-66 is enforced by the registry rather
  than by review — and again by the NOT NULL column. All six detectors ship (FAN_OUT, FAN_IN,
  RAPID_TRANSFER, PEEL_CHAIN, DORMANCY_BURST, STRUCTURING), each with a positive fixture **and
  a paired negative one**, plus a test that an ordinary two-hop trace stays silent. A detector
  that raises is recorded as unavailable and the other five still run.

**Cleanup.** `tracing/persistence.load_transfers` was a second copy of the canonical-layer
reader that scanned every transfer on the chain per call. Removed; `intel/service.py`'s indexed
batch loader is now the only one.

**Completed 2026-09-05.** `api/v1/results.py` serves `GET /analyses/{id}/graph`,
`/attributions` and `/patterns`, and the pipeline runs the stages that fill them. The graph is
rebuilt from the stored trace on read rather than cached, so it cannot drift from the trace it
came from.

**Found while wiring, and fixed:**
- **`truncated` was set whenever a cap was applied, even when nothing was dropped.** A flag
  that cries wolf is a flag investigators learn to ignore, and this is the one flag they must
  not. It now reports what actually happened.
- **A trace's pruned branches and unreachable addresses were lost on save**, so a graph rebuilt
  from the database showed a smaller answer than the trace found — and the accounting invariant
  could not be re-checked from stored rows. Migration `0006_pruned_branches` keeps both, and a
  round-trip test asserts the invariant still holds after a reload.

**Outstanding, both deliberate.**
1. Louvain community detection (`NICE TO HAVE`, GRAPH_ANALYTICS.md §3) is not built.
2. Risk scoring does not yet populate `risk_score` / `risk_band` on nodes — that is Phase 8.

---

## Phase 7 — VASP attribution ◐
**Depends on:** 4 · **Enables:** 8, 9 · **Runs in parallel with:** 5, 6

**Goal.** Answer PS26183, with the three-tier discipline intact.

**Tasks.** Label dataset loader with source, licence, and date tracking · **hand-curate and
commit the label set: OFAC crypto addresses plus 50–100 verified major TRON and Ethereum
exchange hot wallets** · `entities` seed data · address feature extraction (the
[VASP_IDENTIFICATION.md §4](VASP_IDENTIFICATION.md) signals) · dataset matching →
`CONFIRMED` · deposit-funnel heuristic → `PROBABLE` · **confidence propagation through the
chained inference** · contract classification · entity typing · the §7 decision procedure ·
evidence-list generation · conflicting-label surfacing · investigator override (`SHOULD`).

**Files.**
```
backend/app/labels/{loader,sources,matcher}.py
backend/app/intel/{profile,features,service}.py
backend/app/attribution/{engine,heuristics,evidence,decision}.py
backend/app/db/models/{entity,address_label,label_source,attribution}.py
data/labels/{ofac_crypto.json,exchanges_tron.json,exchanges_ethereum.json,mixers.json,bridges.json}
```

**Acceptance.** Dataset match yields `CONFIRMED` with source name, URL, and date · the funnel
heuristic identifies deposit addresses in fixture data · **confidence propagates downward
through a `PROBABLE` sweep destination** · insufficient activity yields `UNATTRIBUTED` ·
conflicting labels are both surfaced · **precision ≥ 0.95 on `PROBABLE` at the 0.7 threshold**
against the labelled hold-out set · the database rejects a tier-inconsistent row.

**Tests.** [TESTING_STRATEGY.md §7](TESTING_STRATEGY.md) — the integrity suite.
**DoD.** Attribution works end to end with the three tiers strictly separated; label datasets
committed with documented licences.

> **This phase carries the most project risk.** The label curation is not a scripted import —
> it is careful manual work, and its quality determines whether the demo has an answer.
> See [MVP_SCOPE.md §6](MVP_SCOPE.md).

**Engine built 2026-09-05.** 293 tests pass; ruff, `ruff format --check` and mypy `strict`
clean across 72 source files. 54 new tests across `test_labels.py`, `test_intel_features.py`,
`test_attribution.py` (the pure integrity suite) and `test_attribution_engine.py`.

Built and confirmed directly:
- `labels/{loader,matcher}.py` — datasets are self-describing JSON carrying source name, URL,
  licence, reliability and date; a dataset with no licence **fails to parse**, so OQ-07's rule
  that nothing is ingested until its licence is written down is enforced by the schema. Every
  address is base58check / EIP-55 validated on ingest (the mandatory OQ-08 lesson); a malformed
  row is rejected and reported, and costs its own label rather than the dataset. Re-ingestion is
  a no-op; a refreshed dataset date is picked up.
- **`data/labels/ofac_sanctioned.json` — 405 real sanctioned addresses (281 TRON, 124
  Ethereum)**, regenerable by `scripts/fetch_ofac_labels.py` from the MIT-licensed `0xB10C`
  extraction of OFAC's SDN list. Zero addresses in it failed validation. `tracefall load-labels`
  ingests it.
- `intel/{features,service}.py` — the §4 behavioural signals over stored transfers. Ratios are
  `Fraction`, never float; value-weighted signals are scoped to one asset for the same reason a
  trace is; failed transfers are excluded from behaviour; an unmeasurable signal is `None`, never
  zero. Profiles are stored and not recomputed for unchanged data.
- `attribution/{decision,engine}.py` — the §7 procedure, pure and database-free. Dataset match →
  `CONFIRMED` citing source and date. **Conflicting sources produce `PROBABLE` with both claims
  and neither entity** — the measured MaskEX/UEEx case. Deposit funnel → `PROBABLE`, with
  confidence multiplied by a `PROBABLE` destination's own confidence and capped at 0.95, never
  1.0. Insufficient activity, a contract, and no service behaviour each end `UNATTRIBUTED` with a
  named reason. Every finding carries its evidence and its look-alikes.
- `ServiceBoundaryChecker` supplies the callback Phase 5 shipped without — and **only a
  `CONFIRMED` service stops a trace**, so a sanctioned personal wallet is a finding rather than a
  boundary.

**Outstanding — this phase is not done.**
1. **The exchange label set does not exist yet.** Without it every `CONFIRMED` is a sanctions
   hit, and the chained inference has nothing to sweep *to*: a deposit address resolves to "a
   deposit address for an unidentified service". This is the single highest-leverage hour of work
   in the project ([MVP_SCOPE.md §6](MVP_SCOPE.md)) and the engine is ready to receive it.
   It is gated on two things named in
   [research/OQ-08-tron-label-coverage.md §6](research/OQ-08-tron-label-coverage.md): **an ADR
   with a named signer** resolving OQ-07's facts-versus-compilation judgement, and **reading
   TronScan's terms of service in a browser**.
2. **Contract classification (§7 step 2) is not implemented.** A contract is currently
   `UNATTRIBUTED` with reason `UNIDENTIFIED_CONTRACT` rather than typed, and `is_contract` is
   never populated — no caller passes it.
3. **The precision ≥ 0.95 gate is unmeasured.** It needs the labelled hold-out set, which needs
   item 1. The thresholds are OQ-09's reasoned defaults, not calibrated ones.
4. **Investigator override (`SHOULD`)** — the table exists, no endpoint does.
5. ~~Attribution is not called by the pipeline.~~ **Done 2026-09-05** — the pipeline runs
   RETRIEVAL → NORMALIZATION → TRACING → GRAPH → PATTERNS → ATTRIBUTION, and
   `GET /analyses/{id}/attributions` serves the result.

**Found while wiring, and fixed:** the chained inference was skipped whenever a deposit
address's sweep destination was itself one of the addresses being attributed — which is the
*common* case, since the trace followed the money there. The deposit address reported "a
deposit address for an unidentified service" while its `CONFIRMED` exchange sat one hop away in
the same result. Regression test added.

**Verified end to end 2026-09-05** through the HTTP API, offline: case → address → analysis →
worker → `GET /analyses/{id}/graph`. A suspect address sweeping to a labelled exchange returns
`PROBABLE — <exchange>, 0.80` by `DEPOSIT_HEURISTIC` with ten evidence items, the exchange
itself returns `CONFIRMED` with no confidence number, and the run completes at 100%.

---

## Phase 8 — Risk engine ☑
**Depends on:** 6, 7

**Goal.** A transparent, defensible score.

**Tasks.** `config/risk_weights.yaml` with the [RISK_ENGINE.md §3](RISK_ENGINE.md) catalogue ·
one independent evaluator function per signal · hop-decay for Group A signals · weighted
aggregation with clamping · band mapping · **confidence computed and returned separately** ·
`not_evaluated` tracking · itemised breakdown assembly · node-level and root-level scoring ·
config versioning · alert generation.

**Files.** `backend/app/risk/{engine,signals/*.py,config,confidence,bands}.py` ·
`backend/app/api/v1/risk.py` · `config/risk_weights.yaml`

**Acceptance.** Scores are deterministic and reproducible · **monotonicity holds** · bands map
at the exact boundaries · every non-zero score has at least one populated signal description ·
missing inputs land in `not_evaluated`, never as silent zeros · confidence is never folded into
the score · **all four sanity anchors pass — including the exchange hot wallet not scoring
`HIGH`** · alerts fire for sanctioned and mixer contact.
**Tests.** [TESTING_STRATEGY.md §8](TESTING_STRATEGY.md), including the property-based
monotonicity test.
**DoD.** Every score fully explainable from its breakdown.

**Verified 2026-09-05.** 394 tests pass; ruff, `ruff format --check` and mypy `strict` clean
across 86 source files. 31 new tests in `test_risk.py` plus pipeline and endpoint coverage.

Built and confirmed directly:
- `config/risk_weights.yaml` — all 19 signals from §3, versioned `risk-weights-v1.0`, with the
  weights marked in the file itself as expert-reasoned rather than calibrated. Loading
  validates: a band gap, an out-of-range weight, or confidence weights that do not sum to 1.0
  all fail on load rather than silently changing every score in the system.
- `risk/signals.py` — one pure evaluator per signal, no interaction between them, so the
  breakdown adds up by hand. Every signal states its raw value and a description with concrete
  numbers; contact signals cite their transaction hashes.
- `risk/engine.py` — hop-decayed Group A, `min(100, round(Σ points))`, band mapping asserted at
  every boundary, and **confidence computed separately and never multiplied in**.
- Four signals are honestly `not_evaluated` by default and say why: `darknet_contact` (no such
  label set), `high_risk_jurisdiction_vasp` (no jurisdiction data), `no_legitimate_activity`
  (contract interaction is not derivable from transfers), `victim_count` (backward tracing is
  not built). Asking the cross-case question and getting "no" is distinguished from not asking.
- Alerts fire on sanctioned contact, mixer contact, and a `CRITICAL` band.
- `GET /analyses/{id}/risk` returns root plus every node, with the breakdown and the disclaimer.

**The sanity anchors all pass, including the one that matters.** An exchange hot wallet scored
`HIGH` on the first run — it has every behavioural marker the heuristics look for. That is the
documented easy way to be broken, so **Groups B and C are reported as `not_evaluated` for an
address `CONFIRMED` as an exchange or merchant**, each with the reason stated on the signal.
This is a scoping rule about whose behaviour is being judged, not a conditional weight: signals
still never interact. Groups A and D still apply, so a service that itself touches a sanctioned
address is still a finding, and a merely `PROBABLE` exchange is still scored on behaviour —
the exemption rests on a dataset match, never on an inference.

**Verified end to end** through the HTTP API, offline: the suspect scores 23 `LOW` from
`rapid_transfer` 11.97/12, `pass_through_ratio` 8/8, `velocity` 1.96/6 and `value_magnitude`
1.35/5 — 23.28, checkable by hand — while the confirmed exchange one hop away scores 1 with
fifteen signals listed as not evaluated.

**Outstanding.** The weights are uncalibrated by design and LIMITATIONS.md says so; calibrating
them needs adjudicated outcome data that does not exist publicly.

---

## Phase 9 — AI / ML ☐
**Depends on:** 7 · **Optional — cut first if time is short**

**Goal.** The deposit-address classifier, with a working fallback.

**Tasks.** Training-data assembly from confirmed sweep destinations · hard-negative collection ·
synthetic generator for structural augmentation · LightGBM training script with a fixed seed ·
evaluation reporting **real and synthetic metrics separately** · SHAP explainability · inference
wrapper · **fallback to the deterministic heuristic when the model is absent** · model
versioning · optional Isolation Forest anomaly detection (`NICE`).

**Files.** `backend/app/ml/{classifier,features,explain,inference,fallback}.py` ·
`backend/app/ml/synthetic/generate.py` · `backend/app/ml/train/{train_classifier.py,evaluate.py}`

**Acceptance.** Classifier trains reproducibly from a seed · precision ≥ 0.95 at the operating
threshold on real held-out data · SHAP produces a renderable evidence list · **deleting the
model file leaves the full pipeline working**, with `method=DEPOSIT_HEURISTIC` recorded ·
synthetic metrics are reported separately and never as overall performance.
**Tests.** [TESTING_STRATEGY.md §9](TESTING_STRATEGY.md), including the delete-`ml/` test.
**DoD.** The classifier improves attribution confidence and the system is unaffected by its
absence.

---

## Phase 10 — Frontend dashboard ◐
**Depends on:** 2 for contracts; 6/7/8 for real data · **Start early against mocks**

**Goal.** The investigator interface.

**Tasks.** Vite + React + TS + Tailwind setup · TanStack Query API client with generated types ·
auth flow and protected routes · design tokens and the **three-tier attribution treatments** ·
dashboard · new case and address intake with live validation · analysis progress with streaming
stages · investigation workspace with six tabs · **Cytoscape graph with hierarchical layout,
tier-distinct borders, risk colouring** · timeline scrubber (`SHOULD`) · transaction table ·
pattern cards with false-positive notes · attribution cards in all three variants · risk
breakdown · evidence table · report page · all states from
[FRONTEND_SPEC.md §9](FRONTEND_SPEC.md) · accessibility pass.

**Files.**
```
frontend/src/{api,components,pages,hooks,types,styles}/**
frontend/src/components/{AddressChip,AttributionCard,RiskBadge,RiskBreakdown,
                         AmountDisplay,TransactionTable,FlowGraph,TimelineScrubber,
                         PatternCard,StageProgress,EvidenceTable,TruncationBanner}.tsx
```

**Acceptance.** All screens implemented per spec · **the three attribution tiers are visually
and textually distinct, verified without colour** · the graph renders 500 nodes interactively ·
risk breakdown shows every signal · every state in §9 is handled — including fixture-mode and
truncation banners · keyboard navigation works throughout · axe-core reports no critical issues
· usable at 1366×768 in both themes.
**Tests.** [TESTING_STRATEGY.md §11](TESTING_STRATEGY.md).
**DoD.** A complete investigation is workable end to end through the UI.

**Partially delivered 2026-09-05.** Built against the endpoints that exist, deliberately, so
nothing is mock-driven and gets reworked: design tokens with light/dark palettes; the integrity
components (`TierBadge`, `AddressChip`, `RiskBadge`, `AttributionCard`, `AmountDisplay`); auth
with tokens held in module memory and never in web storage; dashboard with filters and honest
empty states; the two-step case and address intake with live validation and the cross-case
banner; the analysis progress screen; and the case-detail shell whose later-phase tabs say so
rather than showing fabricated data. 32 frontend tests; eslint, `tsc -b`, vitest and `vite build`
all pass.

**Still to build** (waiting on their APIs): the Cytoscape graph, timeline scrubber, transactions
table, patterns, attribution tab contents, evidence tab, report page, Quick Trace, and global
address search.

**Blocked on a backend change:** the refresh token is returned in the response body, so holding
it only in memory means a page reload signs the user out. Issuing it as an httpOnly cookie is a
Phase 12 item that is worth pulling forward — the client already sends `credentials: 'include'`.

---

## Phase 11 — Investigation reports ☑
**Depends on:** 8

**Goal.** A document that can be attached to a case file.

**Tasks.** Report data assembly · PDF template (ReportLab or WeasyPrint) covering every section
in [PRODUCT_SPEC.md](PRODUCT_SPEC.md) stage 13 · graph image rendering · evidence appendix ·
**limitations and disclaimer section generated from `LIMITATIONS.md`** · content hashing and
`reports` record · JSON and CSV export · **LLM narrative with placeholder validation, regex
rejection of model-produced addresses and hashes, tier-language checking, and template
fallback** · pinned findings surfaced first.

**Files.** `backend/app/reports/{generator,pdf,templates/*,graph_image,narrative,validation,export}.py`

**Acceptance.** PDF generates with every required section · all facts match the database
exactly · the graph image renders · the evidence appendix lists every transaction hash ·
disclaimers are present · the content hash is recorded and verifiable · **LLM output that
introduces an address or upgrades attribution language is rejected and the template is used** ·
**an unavailable LLM produces a complete report** · `narrative_source` is recorded and printed.
**Tests.** Section presence · fact-accuracy comparison against the database · hash verification
· LLM validation rejection cases · fallback path · export formats.
**DoD.** A report is generated that an investigator could genuinely attach to a case file.

**Verified 2026-09-05.** 408 tests pass; ruff, `ruff format --check` and mypy `strict` clean
across 92 source files. 14 new tests in `test_reports.py`.

**Two open questions were closed to build this**, both recorded as ADRs:
- **ADR-020 — ReportLab, not WeasyPrint (OQ-12).** WeasyPrint needs Pango, Cairo and
  GDK-PixBuf as system packages. ReportLab is `pip install` and nothing else, so a fresh clone
  generates a report with no system setup — the same property that makes `LIVE_MODE=false` the
  default. The iteration-speed argument for WeasyPrint was the stronger one on paper; it loses
  because this report is a form with a fixed structure, not a design surface.
- **ADR-021 — templated narrative, no LLM (OQ-13).** LIMITATIONS.md already recommends template
  mode for anything entering a case file, so the LLM path would exist only for the case where
  that recommendation is ignored — and it would need the whole safety apparatus (address and
  hash rejection, tier-language checking, fallback) to protect prose nobody should use.
  MVP_SCOPE.md §6 lists it as the second thing to cut; this is that cut, taken deliberately
  rather than under deadline. `NarrativeSource.LLM` stays in the schema and nothing writes it.

Built and confirmed directly:
- `reports/assemble.py` reads every fact from stored rows and re-derives nothing, so the report
  cannot disagree with the screen it came from. A test compares its output against the database
  row by row.
- `reports/pdf.py` renders all eight sections from PRODUCT_SPEC.md stage 13. **The attribution
  tier is printed as a word, never encoded as colour** — a report photocopied in greyscale must
  keep the distinction. Risk signals print with points, maximum and a plain-language reason, and
  `not_evaluated` is printed as its own table so a missing signal never reads as a zero. Every
  pattern prints its `false_positive_note` beside it.
- `reports/generator.py` hashes **exactly the bytes written to disk** before storing them, and
  `verify()` re-hashes. A tampered file fails verification; there is a test that appends a byte.
- PDF, JSON and CSV all generate; the evidence appendix lists every transaction hash the
  findings rest on; the six disclaimers from LIMITATIONS.md §13 print in full.
- `POST /cases/{id}/reports`, `GET /cases/{id}/reports`, `GET /reports/{id}` and
  `GET /reports/{id}/download`, all case-isolated with 404 rather than 403.

**Found while rendering, and fixed:** a raw amount printed as `5.000E+7`. `str()` on a NUMERIC
returns scientific notation, which is not an acceptable way to show an exact integer in a
document that goes into a case file. Amounts now print as plain digits, asserted by a test.

**Deviation from the plan, deliberate.** API_SPEC.md describes report generation as
202-and-poll. It is synchronous here: every fact is already in the database and generation takes
well under a second, so a poll loop would be machinery with no user waiting on it. If generation
ever grows heavy it moves onto the existing job queue rather than growing a second one.

**Outstanding.** Graph image rendering is not built — the PDF describes the flow in tables
rather than embedding a picture of it. Pinned findings are not surfaced first, because pinning
is not implemented.

---

## Phase 12 — Security hardening ☐
**Depends on:** 2, 10 · **Begin incrementally from Phase 2**

**Goal.** Everything in [SECURITY.md](SECURITY.md), verified rather than assumed.

**Tasks.** Rate limiting per user and per IP · security headers and CSP · CORS lockdown ·
comprehensive input validation review · SSRF protection on `callback_url` · audit-log
completeness including reads · **append-only database grants for `audit_log` and
`evidence_items`** · secret redaction in log formatters · token storage review (httpOnly
cookie, not `localStorage`) · TOTP MFA (`SHOULD`) · API key management for the integration
endpoint · dependency and secret scanning in CI · production config hardening.

**Files.** `backend/app/core/{ratelimit,headers,validation}.py` · `backend/app/api/middleware/*` ·
`backend/alembic/versions/*_grants.py`

**Acceptance.** All Phase 12 checks in [SECURITY.md §12](SECURITY.md) pass · **case isolation
verified across every endpoint** · no secret appears in any log, response, or image layer · no
default credentials in any build · rate limits enforced · error responses leak nothing ·
security scans clean.
**Tests.** [TESTING_STRATEGY.md §10](TESTING_STRATEGY.md) plus the security suite.
**DoD.** Security tests pass; a manual review against `SECURITY.md` finds no gaps.

---

## Phase 13 — Testing & QA ☐
**Depends on:** all · **Written alongside each phase, consolidated here**

**Goal.** The full pyramid, with the golden case locked.

**Tasks.** Consolidate unit and integration suites · API contract tests for every endpoint ·
Playwright E2E for all seven flows · **the golden-case end-to-end regression with committed
expected values** · attribution precision CI gate · coverage gates · performance verification
against NFR-01/02/03 · load check at five concurrent analyses · CI wiring.

**Files.** `backend/tests/{unit,integration,api,e2e}/**` ·
`frontend/tests/{unit,e2e}/**` · `tests/golden/**`

**Acceptance.** Full suite passes offline · coverage ≥ 80% on `tracing/`, `attribution/`,
`risk/` · every named test case in [TESTING_STRATEGY.md](TESTING_STRATEGY.md) implemented ·
**the golden case produces bit-identical expected output** · precision gate enforced ·
performance targets met.
**DoD.** CI green; the golden case locks the numbers that go into reports.

---

## Phase 14 — Deployment ☐
**Depends on:** 10

**Goal.** `docker compose up` and it works (NFR-11).

**Tasks.** Production Dockerfiles (multi-stage, non-root) · compose with healthchecks and
dependency ordering · nginx config and API proxying · volume configuration · `.env.example`
completeness · migration and seed commands · `create-admin` CLI · fixture verification script ·
backup and restore documentation · CI image publication.

**Acceptance.** A fresh clone reaches a working system in seven documented commands · all
healthchecks pass · only `web` is exposed · data persists across restarts · **the system runs
fully with the network disconnected in fixture mode** · no secret is baked into any image.
**DoD.** [DEPLOYMENT.md](DEPLOYMENT.md) is accurate; a teammate can deploy from it unaided.

---

## Phase 15 — SIH demo hardening ☐
**Depends on:** 13, 14

**Goal.** A demo that cannot fail.

**Tasks.** **Select 3–5 real, publicly documented fraud-linked addresses with genuinely
interesting fund flows** — multi-hop, at least one terminating at an identifiable exchange, at
least one honestly unattributable · capture and commit complete fixtures · verify every demo
path end to end offline · UI polish on the demo path · error-state review · **the walkthrough
run with the network physically disconnected** · presentation-laptop verification at 1366×768
in both themes · fallback screen recording · demo script with timings · Q&A preparation against
[LIMITATIONS.md §13](LIMITATIONS.md) · final consistency pass over all documentation.

**Acceptance.** The full demo runs offline in under three minutes · every screen is polished ·
no error state is reachable on the demo path · **the `UNATTRIBUTED` example is present and
prominent** · the recording exists · every presentation claim is checkable against
`LIMITATIONS.md §13`.
**DoD.** The demo has been rehearsed end to end, on the presentation machine, offline, more
than once.

---

## Requirements coverage

Every requirement in [REQUIREMENTS.md](REQUIREMENTS.md) is claimed by exactly one phase. Use
this table to check that nothing has been dropped.

| Requirements | Phase | Area |
|---|---|---|
| FR-01, FR-02, FR-03, FR-04, FR-05 | 2 | Case management |
| FR-06 | 2 (API) + 10 (UI) | Notes and finding pinning |
| FR-07 | 7 | Cross-case correlation (needs the shared address index) |
| FR-10, FR-11, FR-12, FR-14 | 2 | Address validation and canonicalisation |
| FR-13 | 3 | Contract vs EOA detection (needs a chain call) |
| FR-20 – FR-27 | 3 | Retrieval, pagination, rate limits, evidence, fixtures |
| FR-30 – FR-34 | 4 | Normalization |
| FR-40 – FR-50 | 5 | Tracing |
| FR-60 – FR-66 | 6 | Pattern detection |
| FR-70 – FR-78 | 7 | VASP attribution |
| FR-80 – FR-86 | 8 | Risk engine |
| FR-90 – FR-96 | 6 | Graph |
| FR-100, FR-101 | 8 | Alert generation |
| FR-102 | 10 | Alert acknowledgement |
| FR-110 – FR-116 | 11 | Reports |
| FR-120 – FR-124 | 2 | Orchestration and job lifecycle |
| FR-130, FR-131 | 12 | Integration surface (built with its API-key security) |
| NFR-01, NFR-02, NFR-03, NFR-04 | 13 | Performance verification |
| NFR-05 | 3 | Retry and timeout |
| NFR-06, NFR-07, NFR-08, NFR-09 | 2, then hardened in 12 | Security fundamentals |
| NFR-10 | 3 | Evidence hashing |
| NFR-11 | 14 | Single-command deployment |
| NFR-12, NFR-13, NFR-14 | Each engine's own phase; verified in 13 | Testability and determinism |
| NFR-15 | 10 | Synthetic and fixture labelling in the UI |
| NFR-16 | 2 | Structured logging with correlation IDs |
| NFR-17 | 3 | Chain adapter abstraction |
| NFR-18 | 10 | Accessibility |

**Check before declaring a phase done:** every requirement listed against it is implemented, or
is explicitly deferred with a note in [MVP_SCOPE.md](MVP_SCOPE.md).

---

## Estimation

Rough, for a four-person team. Treat as ordering guidance, not a schedule.

| Phase | Effort | Notes |
|---|---|---|
| 1 | S | |
| 2 | L | Foundation work that everything depends on |
| 3 | L | API integration is always slower than expected |
| 4 | M | |
| 5 | **XL** | The correctness core. Do not rush this |
| 6 | L | NetworkX does the graph work; the detectors and their negative tests are the bulk |
| 7 | **XL** | Includes manual label curation |
| 8 | M | Deliberately simple |
| 9 | M | Optional |
| 10 | **XL** | The largest single track; start it earliest |
| 11 | L | PDF layout always takes longer than estimated |
| 12 | M | Incremental throughout |
| 13 | L | Written alongside, consolidated at the end |
| 14 | M | |
| 15 | M | Do not compress this one |

**The two phases most likely to be underestimated are 5 and 7.** They are also the two that
determine whether the product answers its problem statement.
