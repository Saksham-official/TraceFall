# Project Overview

**TraceFall** — automated blockchain analytics for cryptocurrency fraud investigation.

Smart India Hackathon 2026 · **PS SIH26183** · Ministry of Home Affairs ·
Blockchain & Cybersecurity · Software

---

## The problem in one paragraph

When a citizen reports a bank-transfer fraud, CFCFRMS knows instantly which institution received
the money — the account number encodes the bank — and a freeze request goes out within minutes.
When the same citizen reports a **cryptocurrency** fraud, the wallet address they provide
encodes nothing: no issuer, no routing, no jurisdiction. The investigator has no automated way to
follow the money or to determine which exchange it reached, and therefore **no one to send a
freeze request to.** By the time manual block-explorer work produces an answer — if it ever
does — the funds are gone.

## What TraceFall does

Takes a victim-reported suspect wallet address and, in about ninety seconds, produces:

- **where the money went** — a multi-hop fund flow trace with proportional value attribution,
- **which exchange received it** — entity attribution with an explicit confidence tier and its
  evidence,
- **what it did on the way** — laundering patterns named in plain language,
- **how urgent it is** — a transparent risk score with every contributing signal itemised,
- **an interactive transaction graph**, and
- **an investigation report** suitable for a case file.

It replaces roughly **6–12 hours of manual tracing with about 45 minutes of reviewed work**
([INVESTIGATOR_WORKFLOW.md](INVESTIGATOR_WORKFLOW.md)).

## Who uses it

Cybercrime investigators at state cyber cells and district cyber police stations — competent
with case software, **not** blockchain specialists, time-pressured, and accountable for
everything that reaches a case file. Secondarily, I4C analysts looking across cases, and
supervisors triaging a queue.

## The idea that shapes the whole system

**Separate what we observe from what we infer, visibly, everywhere.**

Every claim carries one of three tiers: `CONFIRMED` (this address is in a named, dated public
dataset), `PROBABLE` (it behaves like one — here is the confidence and the evidence), or
`UNATTRIBUTED` (we do not know, and here is what would be needed). These are enforced by a
database constraint, not by convention, and are never collapsed in the API, the UI, or the PDF.

The failure this prevents is concrete: an investigator sending a legal request to the wrong
institution because our interface presented a heuristic as a fact.

## Scope, honestly

**We can:** trace fund flows across TRON and Ethereum, identify addresses associated with known
exchanges with stated confidence, detect laundering patterns, and show exactly where on-chain
tracing ends and legal process must begin.

**We cannot:** identify people, determine that fraud occurred, trace through mixers, follow
funds across bridges automatically, or produce court-admissible evidence.
[LIMITATIONS.md](LIMITATIONS.md) is the complete list, and §13 of it is the checklist every
presentation claim is measured against.

## Architecture in one line

React SPA → FastAPI → async worker running an eight-stage pipeline over PostgreSQL and Redis,
with chain-specific logic confined to two adapters.
Detail: [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md).

## Documentation map

**Start here** → [PROBLEM_ANALYSIS.md](PROBLEM_ANALYSIS.md) ·
[PRODUCT_SPEC.md](PRODUCT_SPEC.md) · [MVP_SCOPE.md](MVP_SCOPE.md) ·
[LIMITATIONS.md](LIMITATIONS.md)

**Building it** → [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) ·
[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) ·
[DATABASE_DESIGN.md](DATABASE_DESIGN.md) · [API_SPEC.md](API_SPEC.md) ·
[DEPLOYMENT.md](DEPLOYMENT.md)

**The analytics** → [BLOCKCHAIN_ANALYTICS.md](BLOCKCHAIN_ANALYTICS.md) ·
[WALLET_TRACING.md](WALLET_TRACING.md) · [VASP_IDENTIFICATION.md](VASP_IDENTIFICATION.md) ·
[GRAPH_ANALYTICS.md](GRAPH_ANALYTICS.md) · [RISK_ENGINE.md](RISK_ENGINE.md) ·
[AI_ML_STRATEGY.md](AI_ML_STRATEGY.md)

**The product** → [USER_FLOWS.md](USER_FLOWS.md) ·
[INVESTIGATOR_WORKFLOW.md](INVESTIGATOR_WORKFLOW.md) · [FRONTEND_SPEC.md](FRONTEND_SPEC.md)

**Governance** → [DECISIONS.md](DECISIONS.md) · [SECURITY.md](SECURITY.md) ·
[PRIVACY_AND_COMPLIANCE.md](PRIVACY_AND_COMPLIANCE.md) ·
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)

## Current phase

**PHASE 0 — PLANNING / ARCHITECTURE. No implementation has started.**

Next: Phase 1 (repository foundation) in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), after resolving the blocking items in
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md).
