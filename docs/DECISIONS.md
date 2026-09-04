# Decision Log

Architectural decision records. **Do not change a decision here without adding a superseding
record explaining why.**

Format: Decision · Context · Options · Chosen · Why · Trade-offs.

---

## ADR-001 — MVP chains: TRON and Ethereum, USDT-first

**Status:** Accepted · **Date:** 2026-09-05

**Context.** PS26183 does not specify a chain. Supporting everything is impossible; supporting
the wrong one makes the tool irrelevant to its users.

**Options.**
1. Ethereum + EVM L2s — richest tooling and best public labels
2. Bitcoin + Ethereum — classic forensics pairing, with real UTXO clustering
3. **TRON + Ethereum, USDT-first**
4. All of the above

**Chosen:** 3.

**Why.** Indian crypto investment fraud runs overwhelmingly on **USDT-TRC20**. Near-zero fees,
seconds to confirm, deep liquidity, dollar-pegged. A tool for Indian investigators that leads
with Ethereum solves a problem its users mostly do not have. Both chains are account-model, so
one tracing engine serves both with two thin adapters. TronGrid's free tier is workable.
Ethereum second for label quality and to prove the adapter abstraction.

**Trade-offs.** We forgo Bitcoin's common-input-ownership heuristic — the strongest clustering
signal in the field — which means all our clustering is behavioural and lands in Tier B
([PROBLEM_ANALYSIS.md §7](PROBLEM_ANALYSIS.md)). We accept weaker clustering in exchange for
covering the corridor the money actually uses. Bitcoin is Tier 1 in
[FUTURE_SCOPE.md](FUTURE_SCOPE.md), and the adapter interface accommodates UTXO chains.

---

## ADR-002 — Modular monolith with an async worker

**Status:** Accepted · **Date:** 2026-09-05

**Context.** The analysis pipeline has eight stages and takes 30–120 seconds against
rate-limited APIs.

**Options.** Microservices · **modular monolith + queue** · synchronous monolith ·
event-driven.

**Chosen:** modular monolith with a Redis-backed job queue.

**Why.** The async worker is forced by the pipeline duration — a synchronous design would hit
HTTP timeouts with no progress feedback. Beyond that, microservices would buy independent
scaling we do not need at the cost of service discovery, inter-service auth, distributed
tracing, and a demo that fails if any container misbehaves. Module boundaries enforced by
interface discipline give the same separation with none of the operational cost, and make later
extraction a refactor rather than a rewrite.

**Trade-offs.** Modules can only be scaled together. Boundary discipline depends on review
rather than the network enforcing it. Both are acceptable at this scale; the first module worth
extracting later is `ingestion/`, because rate limits are inherently a shared global resource.

---

## ADR-003 — PostgreSQL only; no graph database

**Status:** Accepted · **Date:** 2026-09-05

**Context.** The product is graph-centric. The reflex is to reach for Neo4j.

**Options.** PostgreSQL + in-memory NetworkX · PostgreSQL + Neo4j · PostgreSQL + Apache AGE.

**Chosen:** PostgreSQL only, with NetworkX in memory per investigation.

**Why.** The arithmetic settles it. A trace subgraph is 200–2,000 nodes, capped at ~10,000
([DATA_ARCHITECTURE.md §10](DATA_ARCHITECTURE.md)) — trivially in-memory. Every graph operation
we need completes in under two seconds at that scale
([GRAPH_ANALYTICS.md §6](GRAPH_ANALYTICS.md)), against a network-bound stage that takes 30–90.
A second datastore would add dual writes, sync bugs, another backup path, and another container
to fail on demo day, to make a non-bottleneck faster.

**Trade-offs.** Traces beyond ~50k nodes would need a rethink. Cypher path queries are more
expressive than what we write by hand. Accepted: only `graph/` would move, and only when
measurement demands it.

---

## ADR-004 — Proportional (haircut) taint attribution

**Status:** Accepted · **Date:** 2026-09-05

**Context.** On account-model chains, balances are pooled and fungible. Any answer to "how much
of the victim's money left this wallet" is a convention.

**Options.** Poison (taint-all) · FIFO · **haircut (proportional)** · full multi-model support.

**Chosen:** haircut, with the model recorded on every trace.

**Why.** Poison explodes — one deposit taints an entire exchange. FIFO imposes an ordering the
chain does not have on fungible balances: arbitrary precision presented as rigour. Haircut is
symmetric, order-independent, conservative, and — decisively — explainable to a
non-technical reader in one sentence: *"40% of what was in this wallet was traced from the
victim, so we attribute 40% of what left it."* In a system whose output may be questioned by a
lawyer, explainability outranks sophistication.

**Trade-offs.** Some jurisdictions favour FIFO in specific legal contexts. `taint_model` is
stored per trace so a future FIFO option remains distinguishable and old traces stay explicable.

---

## ADR-005 — Three-tier attribution, enforced in the database

**Status:** Accepted · **Date:** 2026-09-05

**Context.** The product's central claim is exchange identification, and most of it is
heuristic.

**Options.** A single confidence number · a binary attributed/unattributed flag ·
**three tiers with evidence** · tiers enforced only in application code.

**Chosen:** `CONFIRMED` / `PROBABLE` / `UNATTRIBUTED`, with CHECK constraints in the database.

**Why.** A bare confidence number invites collapse — 0.87 reads as "yes" in a hurried UI. The
distinction between *"this address is in a published dataset"* and *"this address behaves like
one"* is categorical, not a difference of degree, and an investigator acting on the second as
though it were the first may send a legal request to the wrong institution. Enforcing it in the
database rather than in code means no future change can quietly bypass it — application
discipline erodes, constraints do not.

**Trade-offs.** More complex than a single score, in the schema, the API, and the UI. That
complexity is the product's core integrity guarantee and is worth its cost.

---

## ADR-006 — Deterministic rule-based risk scoring, not ML

**Status:** Accepted · **Date:** 2026-09-05

**Context.** SIH rewards AI/ML. A learned fraud score would benchmark better.

**Options.** Supervised classifier · **weighted rule engine** · hybrid · unsupervised anomaly
score.

**Chosen:** a transparent weighted rule engine with a full per-signal breakdown.

**Why.** An investigator must be able to answer *"why did your system flag this address?"* in
one sentence, in a courtroom, without a data scientist present. A rule engine can. A model
cannot. Additionally, we have no labelled outcome data to train a credible fraud model on —
one built anyway would be a confident-sounding artefact of its own assumptions.

**Trade-offs.** Weights are expert-reasoned rather than empirically calibrated, and we say so
([LIMITATIONS.md §6](LIMITATIONS.md)). We likely lose some discriminative accuracy. Defensibility
is worth more than accuracy here, and it is also the more interesting answer to give a judge who
asks why there is no model in the scoring path.

---

## ADR-007 — ML confined to deposit-address classification

**Status:** Accepted · **Date:** 2026-09-05

**Context.** Where, if anywhere, does ML genuinely beat a written rule in this system?

**Chosen.** Exactly one required ML component (the deposit-address classifier) plus one optional
advisory one (anomaly detection). Everything else deterministic.

**Why.** The deposit-address boundary is fuzzy, multi-dimensional, and has legitimate
look-alikes — the classic case for a learned model. Tracing, scoring, and pattern detection have
exact definitions, and replacing exact logic with approximation would make the system less
accurate *and* less explainable. Gradient-boosted trees were chosen over a neural network
specifically for SHAP per-prediction attribution, which is what produces the evidence list.

**Trade-offs.** Less impressive on an AI feature list. The classifier's labels are bootstrapped
from our own heuristic, so it refines rather than extends the heuristic's reach — documented in
[LIMITATIONS.md §7](LIMITATIONS.md). The system remains fully functional with `ml/` deleted,
which is the design test.

---

## ADR-008 — LLM restricted to narrative, with structural safeguards

**Status:** Accepted · **Date:** 2026-09-05

**Context.** Reports read better with prose. LLMs hallucinate.

**Options.** Templates only · LLM writes the report · **LLM writes narrative between templated
facts** · LLM as an investigative agent.

**Chosen:** narrative only, with placeholder validation, regex rejection of any model-produced
address or hash, and tier-language checking.

**Why.** A hallucinated wallet address in a document attached to a police case file is a
credibility-ending failure. Prompt instructions are not a control. Making fabrication
*structurally impossible* — the model never sees a blank space it could fill with a fact — is
the only acceptable design. An LLM as an investigative agent would put non-deterministic control
flow inside a legal-evidentiary process, which is not defensible.

**Trade-offs.** Less fluent than free generation. Template mode remains the recommendation for
anything going into a case file, and the report records which mode produced it.

---

## ADR-009 — Fixture cache of real chain data as the demo default

**Status:** Accepted · **Date:** 2026-09-05

**Context.** A live demo depends on venue wifi, free-tier rate limits, and provider uptime,
during a timed presentation.

**Options.** Live only · **frozen real-data fixtures with a live toggle** · synthetic scenarios.

**Chosen:** committed fixtures of real provider responses, `LIVE_MODE=false` by default.

**Why.** It is **real chain data, frozen** — not mock data. It gives a deterministic offline
demo, reproducible tests over real-world messiness, and reproducible bug reports, with no rate
limits. Synthetic scenarios would be more controllable and would be discounted by any
knowledgeable judge. One 429 during a timed presentation ends the demo.

**Trade-offs.** Fixtures age; a scheduled live smoke test detects provider drift
([TESTING_STRATEGY.md §13](TESTING_STRATEGY.md)). A visible "cached snapshot — captured <date>"
banner is mandatory (NFR-15) — presenting cached data as live, even by omission, would be worse
than any technical failure.

---

## ADR-010 — Traces terminate at service boundaries

**Status:** Accepted · **Date:** 2026-09-05

**Context.** What should the tracer do when funds reach an exchange hot wallet?

**Options.** Continue tracing · **stop and report** · continue with a marker · make it
configurable.

**Chosen:** stop, record `SERVICE_BOUNDARY`, and report the entity with recommended next steps.

**Why.** A hot wallet pools every customer's funds. Anything downstream is other customers'
withdrawals — tracing onward would produce a graph implicating hundreds of innocent addresses,
with real consequences if it reached a case file. Stopping is not a limitation: it is the
correct answer, and it is precisely what PS26183 asks for. The output *"funds reached a Binance
deposit address; identifying the account holder requires a KYC request to Binance"* is the
product.

**Trade-offs.** Traces look shorter. That is honesty, not weakness, and the UI frames it as the
finding it is.

---

## ADR-011 — No victim PII stored

**Status:** Accepted · **Date:** 2026-09-05

**Context.** Cases originate from NCRP complaints containing personal data.

**Options.** Store full complaint data · **reference numbers only** · store an encrypted copy.

**Chosen:** NCRP and FIR reference strings only; no names, phone numbers, emails, addresses, or
bank details.

**Why.** The analysis does not need it — only the amount and time of the victim's transfer,
which are not personal identifiers. Identity data belongs in NCRP, where access controls already
exist. Duplicating it here would create a second copy of sensitive personal data with no
analytical benefit, and it materially worsens breach impact.

**Trade-offs.** Cross-referencing victims requires going back to NCRP. Correct: that is where
that data should live ([PRIVACY_AND_COMPLIANCE.md §1](PRIVACY_AND_COMPLIANCE.md)).

---

## ADR-012 — Python FastAPI backend, React/TypeScript frontend

**Status:** Accepted · **Date:** 2026-09-05

**Context.** Language choice affects every subsequent decision.

**Options.** Python + React · Node/TypeScript full-stack · Python + server-rendered UI.

**Chosen:** Python 3.12 + FastAPI, React 18 + TypeScript + Vite.

**Why.** The analytical core is graph algorithms and ML — NetworkX, pandas, scikit-learn,
LightGBM, SHAP, ReportLab — all Python-native with no bridge code. FastAPI gives async I/O
(essential for concurrent provider calls) and Pydantic validation at the boundary. React with
Cytoscape.js is the strongest option for the interactive graph, which is the demo's centrepiece;
a server-rendered UI would be faster to ship and much weaker exactly where it matters most.

**Trade-offs.** Two languages and two toolchains, and no shared types without generation. Each
language is used where it is strongest, which is worth the seam.

---

## ADR-013 — Reads are audited, and forbidden case access returns 404

**Status:** Accepted · **Date:** 2026-09-05

**Context.** The system holds active investigation data. The subject of an investigation
learning they are being traced can move funds within minutes.

**Chosen.** Audit case reads as well as writes; return 404 rather than 403 for cases the user
cannot access.

**Why.** In an investigation system, *who looked at which case* is itself security-relevant, so
reads belong in the audit log. And a 403 confirms the case exists — which leaks that an
investigation into a given address is underway. That leak is the highest-consequence
information disclosure this system can make.

**Trade-offs.** Slightly more audit volume, and a marginally more confusing debugging experience
when a permission is genuinely misconfigured. Both are cheap next to the leak.

---

## ADR-014 — No repository layer over SQLAlchemy

**Status:** Accepted · **Date:** 2026-09-05 · **Supersedes:** the `db/repositories/` module
listed in `IMPLEMENTATION_PLAN.md` Phase 2

**Context.** The Phase 2 file list included `db/repositories/*.py`. Implementing it meant a
class per table wrapping queries that SQLAlchemy already expresses directly.

**Options.** A repository class per aggregate · query directly in the route with shared
helpers for the rules that repeat.

**Chosen:** no repository layer. Routes query through the session; the one rule that repeats
and matters — case isolation — lives in `core/deps.get_accessible_case` and
`api/v1/cases._visible`.

**Why.** A repository over an ORM is an abstraction with one implementation, wrapping an API
that is already a query abstraction. It would add a file per table and a layer to step
through at 3am, and buy a datastore swap we have committed against (ADR-003). Centralising
the *security* rule is worth doing; centralising `session.get` is not.

**Trade-offs.** Query logic sits closer to the routes, so a repeated query could drift. The
mitigation is the isolation test suite, which exercises every case-scoped endpoint against
the actual rule rather than against a shared abstraction.

---

## ADR-015 — Append-only enforced by triggers, not role grants

**Status:** Accepted · **Date:** 2026-09-05 · **Amends:** `DATABASE_DESIGN.md` section 9,
rule 4

**Context.** `audit_log` and `evidence_items` must be append-only. The design specified
database grants: the application role holds INSERT and SELECT and no UPDATE or DELETE.

**Options.** Role grants (a non-owner application role) · `BEFORE UPDATE OR DELETE` triggers
that raise · both.

**Chosen:** triggers now; grants documented as an additional production layer.

**Why.** Grants require a second database role that is not the table owner, created outside
the migration by a superuser — which makes the guarantee depend on deployment steps a
developer can skip, and makes it **untestable in the suite**. A trigger travels with the
schema, applies to every role including the owner, and is asserted directly by
`test_audit_log_is_append_only`. An invariant that is verified on every CI run is worth more
than a stronger one that nobody checks.

**Trade-offs.** A superuser can drop the trigger, where a grant would also have to be
re-granted — but a superuser can do both, so the difference is small. Triggers add a small
per-row cost on tables that are insert-only anyway. Production should still run the
application under a restricted role; that is defence in depth on top of this, not instead
of it.
