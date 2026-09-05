# TraceFall

**Automated blockchain analytics for cryptocurrency fraud investigation.**

Smart India Hackathon 2026 · Problem Statement **SIH26183** · Ministry of Home Affairs ·
Blockchain & Cybersecurity

> ### Status: the product runs, end to end, offline
> `docker compose up` brings up five containers. An investigator signs in, enters a suspect
> address, and the pipeline retrieves, normalizes, traces, builds the graph, detects patterns,
> attributes entities and scores risk — then produces a hash-verified PDF for the case file.
> 506 backend tests, 47 frontend tests and 5 browser end-to-end tests against the running
> stack. Only **Phase 15 — demo hardening** remains; the optional ML classifier (Phase 9) is
> deliberately not built. See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

---

## The problem

**SIH26183 — Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from
Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics.**

When a citizen reports a bank fraud, CFCFRMS knows immediately which institution received the
money — the account number encodes the bank — and a freeze request goes out within minutes.

When the same citizen reports a **cryptocurrency** fraud, the wallet address they provide
encodes nothing. No issuer, no routing, no jurisdiction. The investigator cannot tell whether
`TXn8kL2m…` is a scammer's personal wallet or an exchange deposit address, has no automated way
to follow the money, and therefore **has no one to send a freeze request to.**

Today this is done by hand: paste the address into a block explorer, click through transactions,
give up after two hops. Six to twelve hours per address, usually ending in "unknown" — long
after the funds have been withdrawn.

## The solution

TraceFall takes that address and, in about ninety seconds, produces an evidenced answer.

```
suspect address
   → blockchain data retrieved and hashed as evidence
   → transactions normalized to one chain-agnostic model
   → funds traced across multiple hops with proportional attribution
   → transaction graph constructed
   → laundering patterns detected
   → exchange / VASP attributed, with an explicit confidence tier
   → risk scored, with every signal itemised
   → investigation report generated
```

**Roughly 6–12 hours of manual tracing becomes about 45 minutes of reviewed work** — and the
system follows every branch, not just the two an analyst has patience for.

## Core capabilities

| | |
|---|---|
| **Fund flow tracing** | Multi-hop, proportional (haircut) value attribution, configurable depth and thresholds, terminating honestly at service boundaries |
| **Exchange / VASP identification** | Dataset matching plus a deposit-address funnel heuristic — **the answer to PS26183** |
| **Three-tier attribution** | `CONFIRMED` / `PROBABLE` / `UNATTRIBUTED`, never collapsed, enforced by a database constraint |
| **Pattern detection** | Fan-out, fan-in, rapid layering, peel chains, dormancy bursts, structuring — each disclosing its own false-positive modes |
| **Transparent risk scoring** | 0–100 with every contributing signal, its raw value, weight, and points shown |
| **Interactive graph** | Hierarchical fund-flow visualisation, with a text address list carrying the same information |
| **Investigation reports** | PDF with evidence appendix, content hash, and explicit limitations |
| **Evidence chain** | Every raw API response stored immutably with SHA-256 and retrieval timestamp |

### What it does not do

Identify people · determine that fraud occurred · trace through mixers · follow funds across
bridges automatically · integrate with NCRP · produce court-admissible evidence.

[docs/LIMITATIONS.md](docs/LIMITATIONS.md) is the complete, deliberately blunt list. Knowing
exactly where the system stops is what makes everything before that point trustworthy.

## Architecture

```
React + TypeScript SPA  (Cytoscape.js graph)
          │
      FastAPI  (auth · RBAC · validation · audit)
          │
  Investigation Orchestrator  →  Redis queue  →  async worker
          │
  ┌───────┴──────────────────────────────────────────┐
  ingestion → normalize → intel → tracing → graph
                 → patterns → attribution → risk → reports
  └───────┬──────────────────────────────────────────┘
          │
   PostgreSQL 16  ·  Redis 7  ·  evidence file store
```

A **modular monolith with an async worker** — chosen because the pipeline takes 30–120 seconds
against rate-limited APIs, and because microservices would buy scaling we do not need at the
cost of a demo that fails when any container misbehaves (ADR-002).

## Stack

**Backend** Python 3.12 · FastAPI · SQLAlchemy · Alembic · NetworkX · ReportLab
**Frontend** React 18 · TypeScript · Vite · Tailwind · Cytoscape.js · TanStack Query
**Data** PostgreSQL 16 · Redis 7
**Chains (MVP)** TRON and Ethereum, USDT-first — chosen because USDT-TRC20 is where Indian
crypto fraud money actually goes (ADR-001)
**Deployment** Docker Compose behind nginx
**Not used** No ML model ships. The deposit-address classifier (Phase 9) was optional and cut;
the shipped heuristic is deterministic and inspectable ([AI_ML_STRATEGY](docs/AI_ML_STRATEGY.md))

## Documentation

| | |
|---|---|
| **Start here** | [PROJECT_OVERVIEW](docs/PROJECT_OVERVIEW.md) · [PROBLEM_ANALYSIS](docs/PROBLEM_ANALYSIS.md) · [MVP_SCOPE](docs/MVP_SCOPE.md) · [LIMITATIONS](docs/LIMITATIONS.md) |
| **Product** | [PRODUCT_SPEC](docs/PRODUCT_SPEC.md) · [REQUIREMENTS](docs/REQUIREMENTS.md) · [USER_FLOWS](docs/USER_FLOWS.md) · [INVESTIGATOR_WORKFLOW](docs/INVESTIGATOR_WORKFLOW.md) · [FRONTEND_SPEC](docs/FRONTEND_SPEC.md) |
| **Architecture** | [SYSTEM_ARCHITECTURE](docs/SYSTEM_ARCHITECTURE.md) · [DATA_ARCHITECTURE](docs/DATA_ARCHITECTURE.md) · [DATABASE_DESIGN](docs/DATABASE_DESIGN.md) · [API_SPEC](docs/API_SPEC.md) |
| **Analytics** | [BLOCKCHAIN_ANALYTICS](docs/BLOCKCHAIN_ANALYTICS.md) · [WALLET_TRACING](docs/WALLET_TRACING.md) · [VASP_IDENTIFICATION](docs/VASP_IDENTIFICATION.md) · [GRAPH_ANALYTICS](docs/GRAPH_ANALYTICS.md) · [RISK_ENGINE](docs/RISK_ENGINE.md) · [AI_ML_STRATEGY](docs/AI_ML_STRATEGY.md) |
| **Delivery** | [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md) · [TESTING_STRATEGY](docs/TESTING_STRATEGY.md) · [DEPLOYMENT](docs/DEPLOYMENT.md) · [DATA_SOURCES](docs/DATA_SOURCES.md) |
| **Governance** | [DECISIONS](docs/DECISIONS.md) · [SECURITY](docs/SECURITY.md) · [PRIVACY_AND_COMPLIANCE](docs/PRIVACY_AND_COMPLIANCE.md) · [OPEN_QUESTIONS](docs/OPEN_QUESTIONS.md) · [FUTURE_SCOPE](docs/FUTURE_SCOPE.md) |

Contributors and future Claude Code sessions: start with [CLAUDE.md](CLAUDE.md).

## Running it

```sh
cp .env.example .env
./scripts/generate-secret.sh >> .env                      # writes SECRET_KEY
docker compose up -d                                      # api · worker · web · postgres · redis
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli load-labels
docker compose exec api python -m app.cli create-admin    # interactive; no seeded credentials
open http://localhost
```

Seven commands, one of them interactive, all of them verified. `LIVE_MODE=false` is the
default, so a fresh clone needs no API keys and makes no network calls — it replays the
committed fixture cache, and every screen says so. Detail:
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Backend checks: `cd backend && pip install -e '.[dev]' && ruff check . && mypy app && pytest`
Frontend checks: `cd frontend && npm ci && npm run lint && npm run typecheck && npm test`
Browser end-to-end, against a running stack: `cd frontend && npm run e2e`

## What is measured, not asserted

- **Deposit-address heuristic: precision 0.989, recall 0.186** against Binance's own published
  deposit addresses, with the exchange's hot and cold wallets as deliberately hard negatives
  ([research note](docs/research/OQ-09-deposit-heuristic-precision.md)). The recall figure is
  the honest one: roughly four in five real deposit addresses have too little history to
  classify, and those are reported `UNATTRIBUTED` with a reason. **The precision must never be
  quoted without the recall beside it.**
- **`CONFIRMED` attribution rests on first-party data.** 405 OFAC-designated addresses and 17
  Binance TRON wallets taken from Binance's own proof-of-reserves disclosure — the operator
  naming its own wallets. No third-party explorer scrape is used, and
  [ADR-018](docs/DECISIONS.md) records why one was rejected.
- **Provider rate limits, measured:** TronGrid without a key sustains about 0.5 req/s per RPC
  method ([research note](docs/research/OQ-01-provider-rate-limits.md)). The ninety-second
  target holds against the fixture cache, not a cold live trace.
- **Regression locks:** a golden case pins every number the pipeline produces, and the
  Playwright suite guards what only a real browser reaches.

## A note on honesty

This system deals with criminal investigations. A wrong attribution sends a legal request to the
wrong institution; a hallucinated address in a report ends up in a case file. So the
architecture is built around a single discipline: **observed facts, probabilistic inferences,
and things we simply cannot know are kept visibly separate at every layer** — in the database
constraints, the API shape, the interface, and the printed report.

An address the system cannot identify is reported as unidentified, with an explanation of what
would be needed. That answer is not a gap in the product. It is the product working correctly.
