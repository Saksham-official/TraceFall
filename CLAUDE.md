# CLAUDE.md — TraceFall

**Read this file first, in every session. It is the operating manual for this repository.**

---

## Current phase

> ## PHASE 8 — RISK ENGINE (next)
> **Phases 0–6 are complete. The pipeline is wired and runs end to end offline.** Phase 7
> (attribution) is built, tested and serving, but stays ◐ for one reason only: the exchange
> label set. Phase 10 (frontend) is partially built.
>
> A run goes RETRIEVAL → NORMALIZATION → TRACING → GRAPH → PATTERNS → ATTRIBUTION and the
> results are reachable at `GET /analyses/{id}/graph`, `/attributions` and `/patterns`.
> Verified through the HTTP API with no network: a suspect address sweeping to a labelled
> exchange returns **`PROBABLE — <exchange>, 0.80`** by `DEPOSIT_HEURISTIC` with ten evidence
> items, while the exchange itself returns `CONFIRMED` carrying no confidence number.
>
> 363 backend tests and 32 frontend tests pass, with no network access. ruff, `ruff format
> --check` and mypy `strict` are clean across 81 source files. The migration chain applies
> cleanly to an empty database.
>
> **Provider reality, measured (`docs/research/OQ-01-provider-rate-limits.md`):** TronGrid
> without a key sustains only 0.5 req/s *per RPC method*; Blockscout is Ethereum's primary
> because Etherscan now rejects keyless requests. NFR-01's 120-second target holds for a warm
> or fixture cache, not a cold live trace. **Retrieval now happens twice** — the root address
> up front, then every address the trace discovers, on demand — so a cold live trace is bounded
> by that rate, and in fixture mode every hop past a fixtured address ends `DATA_UNAVAILABLE`.
>
> **The one thing blocking Phase 7 is not code.** `data/labels/ofac_sanctioned.json` holds 405
> real sanctioned addresses, so `CONFIRMED` currently means sanctions only and a real deposit
> address resolves to "a deposit address for an unidentified service". The engine is ready for
> exchange labels and proven to use them. Curating them needs **ADR-018 signed by a named
> person** (drafted, in DECISIONS.md) and **TronScan's terms read in a browser**. This is the
> single highest-leverage hour of work in the project (MVP_SCOPE.md §6).
>
> Next is **Phase 8 — the risk engine**: transparent weighted rules from versioned config, one
> evaluator per signal, confidence returned separately from the score, and `not_evaluated`
> tracking so a missing input is never a silent zero. Its dependencies (6 and 7) are met.
> Update the phase table in `IMPLEMENTATION_PLAN.md` when a phase completes, and update this
> banner when the phase changes.
>
> Outstanding from Phase 1: `docker compose up` has not been run (Docker is not installed on
> the development machine).

---

## 1. Project identity

| | |
|---|---|
| **Name** | TraceFall |
| **Event** | Smart India Hackathon 2026 |
| **Problem statement** | **SIH26183** |
| **Title** | Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics |
| **Organisation** | Ministry of Home Affairs (I4C context) |
| **Theme / Category** | Blockchain & Cybersecurity / Software |

**Objective.** Given a victim-reported cryptocurrency wallet address, automatically trace the
fund flow, identify the exchange or VASP that received the funds, detect laundering patterns,
assess risk, and produce an investigation report — fast enough and with enough evidence that a
cybercrime investigator can act while the funds are still reachable.

---

## 2. Product definition

**What we are building.** A web application for cybercrime investigators that turns a wallet
address into an evidenced answer to *"where did the money go, and which exchange do I send the
freeze request to?"*

**Who uses it.** Cybercrime investigators at state cyber cells and district cyber police
stations. Competent with case software, **not blockchain specialists**, time-pressured, and
accountable for everything that reaches a case file. Secondarily I4C analysts and supervisors.

**Core user journey.**
```
Case created → suspect address entered (with victim's amount and time)
  → automated pipeline (~90 s):
      retrieve → normalize → enrich → trace → graph
      → detect patterns → attribute entities → score risk → alert
  → investigator reviews graph, evidence, and attributions
  → PDF report generated for the case file
  → investigator sends a KYC/freeze request to the identified VASP
```

Detail: [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md),
[docs/INVESTIGATOR_WORKFLOW.md](docs/INVESTIGATOR_WORKFLOW.md).

---

## 3. Architecture summary

| Layer | Choice |
|---|---|
| **Frontend** | React 18 + TypeScript + Vite + Tailwind; Cytoscape.js for the graph; TanStack Query |
| **Backend** | Python 3.12 + FastAPI; modular monolith with an async worker |
| **Database** | PostgreSQL 16 — single store, no graph database |
| **Cache / queue** | Redis 7 |
| **Blockchain data** | TronGrid (primary) + TronScan; Etherscan + Blockscout. Chain logic confined to `chains/` |
| **Graph analytics** | NetworkX, in memory, per investigation |
| **AI/ML** | LightGBM deposit-address classifier + SHAP. Optional. Everything else deterministic |
| **Risk engine** | Transparent weighted rules from versioned config. **No ML in scoring** |
| **Reports** | ReportLab/WeasyPrint PDF; optional LLM narrative with structural safeguards |
| **External** | Blockchain APIs, public label datasets, optional price and LLM APIs — all optional at runtime |

**Chains supported (MVP): TRON and Ethereum, USDT-first.** Nothing else. Reasoning: ADR-001.

Detail: [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md).

---

## 4. Engineering principles

These are binding. A change that violates one needs an ADR in
[docs/DECISIONS.md](docs/DECISIONS.md) first.

1. **Deterministic evidence beats unsupported AI.** If a rule can compute it exactly, a model
   must not approximate it. ML is confined to deposit-address classification; an LLM to report
   narrative. Nothing else.
2. **Never claim an address belongs to an exchange unless evidence supports it.** Every entity
   claim carries exactly one tier — `CONFIRMED`, `PROBABLE`, `UNATTRIBUTED` — with its evidence.
   **These are never collapsed**, in the database, API, UI, PDF, or a presentation slide. This
   is enforced by a database CHECK constraint, not by convention.
3. **Separate observed fact from inferred intelligence.** Tier A (on-chain fact), Tier B
   (inference, with confidence and evidence), Tier C (requires private law-enforcement data —
   never built, never claimed). See [docs/PROBLEM_ANALYSIS.md §6](docs/PROBLEM_ANALYSIS.md).
4. **Every conclusion traces to transaction hashes.** No finding may dead-end in "trust us".
   Every number expands to its signals, its transactions, and ultimately the stored raw API
   response with its hash and retrieval time.
5. **Design for explainability.** If an investigator cannot explain a finding in one sentence in
   a courtroom, the finding is built wrong.
6. **Keep the architecture modular.** Modules talk through declared interfaces only. A new chain
   must require one new adapter file and **no** changes to tracing, graph, risk, reports, or UI.
7. **Avoid unnecessary complexity.** No microservices, no graph database, no Kubernetes, no
   abstraction with one implementation. The bottleneck is third-party API rate limits; optimise
   that or nothing.
8. **Build the SIH-demo-friendly MVP first.** Consult [docs/MVP_SCOPE.md](docs/MVP_SCOPE.md)
   before adding anything. If it does not improve the answer to "which exchange received the
   money", it waits.
9. **Security and privacy are first-class.** Case isolation, RBAC, append-only audit logging,
   input validation at the boundary. **No victim PII is ever stored** — reference numbers only.
10. **Never expose secrets.** No key in source, logs, responses, or image layers. No default
    credentials in any build, ever. `LIVE_MODE=false` is the default so a fresh clone needs no
    keys at all.
11. **Never fabricate blockchain data.** Synthetic data is for training and tests only, flagged
    at row level, visibly labelled wherever it surfaces, and never in the demo. The demo uses
    **real chain data, frozen** — always with its "cached snapshot" banner.
12. **Degrade honestly.** Partial data, pruned branches, truncated graphs, and unavailable
    stages are surfaced to the user — never silently producing a smaller answer.

---

## 5. Development rules for future sessions

1. **Read this file.** Then read the docs relevant to the task — do not read all 29.
2. **Follow [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).** Pick a phase whose
   dependencies are met. Its section lists tasks, files, acceptance criteria, and definition of
   done.
3. **Do not redesign the architecture without documenting why.** Add an ADR to
   [docs/DECISIONS.md](docs/DECISIONS.md) *before* implementing a deviation, following the
   existing format.
4. **Update documentation when architecture changes.** Stale docs are worse than none. Update
   the phase status table when a phase completes.
5. **Keep modules independently testable.** No module makes a network call inside a pure
   computation — the tracing engine takes a fetch callback rather than calling providers itself.
6. **Prefer real data; mark synthetic data clearly.** Fixtures are real responses, frozen. The
   fixture-mode banner is not optional.
7. **Tests come with the code, not after it.** Every phase's definition of done includes its
   tests passing. `tracing/`, `attribution/`, and `risk/` require ≥ 80% coverage.
8. **Check [docs/LIMITATIONS.md](docs/LIMITATIONS.md) before claiming a capability** — in code
   comments, UI copy, README text, or a slide. §13 is the claims checklist.
9. **Consult [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md)** before starting a phase that
   depends on an unresolved decision. Resolve it, record it as an ADR, then implement.

### Where things live

```
backend/app/
  api/            HTTP routing, auth, validation — no business logic
  core/           config, security, logging, exceptions
  db/             SQLAlchemy models, migrations, repositories
  orchestrator/   pipeline sequencing, job queue, degradation handling
  chains/         ALL chain-specific code — the only place it may exist
  ingestion/      retrieval, caching, rate limiting, evidence capture
  normalize/      raw → canonical Transfer
  intel/          address profiles and behavioural features
  tracing/        the trace engine (pure computation, no network)
  graph/          NetworkX construction and algorithms
  patterns/       pattern detectors
  attribution/    entity attribution — the ONLY place a tier is set
  risk/           weighted rule scoring
  ml/             optional models; the system works without this directory
  reports/        PDF, JSON, CSV generation
  labels/         curated label dataset loading
frontend/src/     React SPA
data/labels/      committed curated label datasets
config/           risk_weights.yaml and other versioned config
docs/             this planning package
```

### Naming that must stay consistent

Attribution tiers `CONFIRMED` / `PROBABLE` / `UNATTRIBUTED` · risk bands `LOW` / `MEDIUM` /
`HIGH` / `CRITICAL` · termination reasons `MAX_DEPTH` / `BELOW_THRESHOLD` / `SERVICE_BOUNDARY` /
`NO_OUTFLOW` / `EDGE_BUDGET` / `TIME_WINDOW` / `DATA_UNAVAILABLE` (ADR-019) · chains `TRON` / `ETHEREUM` · the canonical model
is `Transfer` (one row per value movement) · API prefix `/api/v1`.

---

## 6. Things this system must never do

- Claim to identify a **person** behind an address. Not possible from public chain data.
- Present a `PROBABLE` attribution as a fact.
- Claim a risk score is a probability of fraud, or evidence of guilt.
- Claim reports are court-admissible or forensically certified.
- Claim integration with NCRP, CFCFRMS, SAHYOG, or FIU-IND. We expose an integration-*ready* API
  and nothing more.
- Trace past an exchange hot wallet — downstream addresses are other customers.
- Label an address that paid *into* a scam wallet as a suspect. They are almost certainly
  another victim (`VICTIM_SOURCE`).
- Store victim PII.
- Hold private keys or move funds. TraceFall is read-only against blockchains.
- Guess a token's decimals, or use a float anywhere in an amount path.

---

## 7. Quick reference

| Question | Document |
|---|---|
| What are we building and why? | [docs/PROBLEM_ANALYSIS.md](docs/PROBLEM_ANALYSIS.md) |
| What does the user see? | [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md), [docs/FRONTEND_SPEC.md](docs/FRONTEND_SPEC.md) |
| What do I build next? | [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) |
| How does tracing work? | [docs/WALLET_TRACING.md](docs/WALLET_TRACING.md) |
| How does exchange identification work? | [docs/VASP_IDENTIFICATION.md](docs/VASP_IDENTIFICATION.md) |
| What's the data model? | [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) |
| What's the API? | [docs/API_SPEC.md](docs/API_SPEC.md) |
| Why was X decided? | [docs/DECISIONS.md](docs/DECISIONS.md) |
| Can we claim Y? | [docs/LIMITATIONS.md](docs/LIMITATIONS.md) |
| What's still undecided? | [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) |
