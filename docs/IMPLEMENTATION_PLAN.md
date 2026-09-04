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
| 1 | Repository foundation | ☐ | 0 |
| 2 | Backend foundation | ☐ | 1 |
| 3 | Blockchain ingestion | ☐ | 2 |
| 4 | Transaction normalization | ☐ | 3 |
| 5 | Wallet tracing | ☐ | 4 |
| 6 | Graph analytics & pattern detection | ☐ | 5 |
| 7 | VASP attribution | ☐ | 4 (5 for full value) |
| 8 | Risk engine | ☐ | 6, 7 |
| 9 | AI / ML | ☐ | 7 |
| 10 | Frontend dashboard | ☐ | 2 (mocks), 6/7/8 (real data) |
| 11 | Investigation reports | ☐ | 8 |
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

## Phase 1 — Repository foundation ☐

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

---

## Phase 2 — Backend foundation ☐
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

---

## Phase 3 — Blockchain ingestion ☐
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

---

## Phase 4 — Transaction normalization ☐
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

---

## Phase 5 — Wallet tracing ☐
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

---

## Phase 6 — Graph analytics & pattern detection ☐
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

---

## Phase 7 — VASP attribution ☐
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

---

## Phase 8 — Risk engine ☐
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

## Phase 10 — Frontend dashboard ☐
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

---

## Phase 11 — Investigation reports ☐
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
