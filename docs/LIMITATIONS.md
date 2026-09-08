# Limitations

**Read this before writing a presentation slide.**

Every claim in the SIH pitch must be checkable against this document. If a capability is not
supported here, it is not claimed there. This is not defensive hedging — knowing exactly where
your system stops is what makes a knowledgeable evaluator trust everything before that point.

---

## 1. Attribution — the biggest limitation, and the one closest to the problem statement

### Coverage is narrow and always will be with public data

| Address type | Our coverage |
|---|---|
| Major exchange hot/cold wallets | Good — published in public datasets |
| Sanctioned addresses | Good — OFAC publishes them |
| Major mixers and bridges | Good |
| **Exchange deposit addresses** | **Heuristic only, never confirmed** |
| Smaller / regional exchanges | Poor — rarely in public datasets |
| P2P and OTC desks | Very poor |
| Everything else | None |

**The long tail is invisible to us.** Commercial vendors cover it through years of proprietary
clustering, undercover deposits, subpoena returns, and paid data feeds. We have none of that,
and no amount of clever engineering substitutes for it.

### Deposit-address attribution is inference, not identification

The core inference — *"this address sweeps to a confirmed Binance hot wallet, so it is probably
a Binance deposit address"* — is a heuristic. It can be wrong.

**Look-alikes we may misclassify:** payment processors, custodial wallet services, OTC desks,
automated business sweepers, and another exchange's internal rebalancing. All produce a similar
funnel shape.

**Cases we will miss:** fresh addresses with too little history to classify (common, and
consequential — a scammer's new deposit address may be exactly this), exchanges that sweep in
irregular batches, and shared deposit addresses with off-chain memo tags where the customer
identifier never touches the chain at all.

**Consequence:** the system says `PROBABLE` with a confidence value and shows its evidence.
An investigator must verify before acting on it.

### We cannot identify people. Ever.

No KYC data, no means to obtain it, no inference that would produce it. The furthest the system
goes is *"these funds reached an address probably controlled by exchange X"* — after which
identifying the account holder requires a legal request to X. That gap is permanent and by
design.

### Labels go stale

An address labelled "Binance hot wallet" in a 2024 dataset may since have been retired. We
always show the dataset date; we cannot verify current accuracy.

---

## 2. Tracing

### Taint is a convention, not a measurement

On account-model chains, coins are fungible and pooled. "40% of what left this wallet was the
victim's money" is an *attribution convention* (haircut), not a physical fact. FIFO would give a
different number and be equally defensible. Every trace output says so.

### Traces terminate, often early

At exchanges (correct — this is the answer), mixers (the trail genuinely ends), bridges (a
separate chain analysis is needed), depth limits, and value thresholds.

**We prune.** Branches below 1% of the traced value are not followed. A scammer who deliberately
splits into a hundred tiny amounts can push value below the threshold. We report what was
pruned and how much, but we did not follow it.

### Token symbols are not identities

Anyone can deploy a contract calling itself USDT. Our own captured test data contains a
**`USDTT`** token sitting in the same wallet as genuine USDT — routine address poisoning.

Asset identity is always the **contract address**, never the symbol, and an amount that
matches transfers of more than one contract is reported as ambiguous rather than resolved.
The consequence for the interface is a rule, not a preference: **never display a token
symbol without its contract**, or an investigator can be led to trace the wrong asset
entirely.

### A swap ends the trace

A trace follows one asset (ADR-017). If funds are converted — USDT to TRX, or into any other
asset — the trace stops at the conversion rather than following the new asset. We name the swap
and the address, and an investigator can start a second trace from there, but it is manual.

This is a real blind spot and a plausible evasion. It sits alongside mixers and bridges as a
place where on-chain tracing hands off to human work.

### The fan-out cap can miss things

We follow the top 20 outbound branches per node by value. Branch 21 could matter. It is
recorded as pruned, not silently dropped — but it is not traced.

### Internal exchange transfers are invisible

When an exchange moves value between two customers, nothing touches the chain. A trace ending
at an exchange deposit address cannot see what happened next, and that is not a gap in our
implementation — the information does not exist on-chain.

### Time windows can hide movement

The default 180-day window means funds moved on day 181 are missed. Configurable, at the cost of
noise and runtime.

---

## 3. Cross-chain

**Automated bridge tracing is not implemented.** We detect that funds reached a bridge, name the
bridge, name the destination chain where determinable, and stop. Correlating the outbound
deposit with the inbound mint on another chain is manual.

Batching and aggregator contracts make automated correlation genuinely error-prone, which is
why it is future work rather than a shortcut.

**Chains we do not support at all:** Bitcoin, BSC, Polygon, Solana, and everything else. A
scammer moving funds to BSC exits our visibility entirely.

---

## 4. Privacy technology

**Mixers.** Tornado Cash and equivalents break the link cryptographically. We detect entry and
stop. We cannot de-mix, and neither can anyone else without additional information.

**Privacy coins.** Monero and shielded Zcash are not traceable by design. Not supported, not
supportable.

**Privacy protocols on supported chains.** Emerging techniques may defeat our tracing without
our knowing it has happened.

---

## 5. Data quality

### Provider dependence

We see what public APIs report. If a provider is incomplete, wrong, or changes its response
shape, our analysis inherits that. We store raw responses so an error is at least traceable —
but we cannot independently verify a provider's data without running our own node.

### Rate limits shape the analysis

Free tiers constrain how much we retrieve. A high-volume address is truncated at 10,000
transfers. We flag it; we did not see everything.

### Freshness

Data is retrieved at analysis time. Funds may move minutes later. **A completed report is a
snapshot, and it says so.**

### Unconfirmed transactions

Excluded from risk scoring, because a transaction that later fails would otherwise change a
score after the fact.

---

## 6. Risk scoring

**Weights are expert-reasoned, not empirically calibrated.** Proper calibration would need a
large labelled dataset of addresses with adjudicated outcomes. That dataset does not exist
publicly and we do not have it. We can validate determinism, monotonicity, and sanity anchors —
not accuracy.

**A score is not a probability of fraud.** It summarises signals we chose and weighted.

**False positives are certain.** Legitimate behaviour resembling laundering — high-frequency
traders, payment processors, arbitrage bots, market makers — will score high. Every pattern
finding discloses its own false-positive modes.

**False negatives are certain.** Sophisticated laundering designed to look ordinary will score
low.

---

## 7. Machine learning

**Training labels are bootstrapped from our own heuristic**, so the classifier learns to
reproduce that heuristic more finely. It refines a boundary; it cannot discover a class of
deposit address the heuristic never finds. This circularity is real and is not hidden.

**Hard negatives are scarce.** Payment processors and custodial services — exactly the
look-alikes that cost us precision — are few in any dataset we can assemble.

**Synthetic data teaches structure, not calibration.** A model scoring 0.99 on generated
funnels has learned the generator.

**The model is optional.** Everything works without it, at slightly lower confidence.

---

**The deposit-address heuristic finds roughly one in five real deposit addresses.** Measured
2026-09-05 against Binance's own published deposit addresses: precision 0.989, **recall 0.186**
(`docs/research/OQ-09-deposit-heuristic-precision.md`). Four out of five published deposit
addresses had too little transaction history to classify — most had received once and forwarded
once — and the system correctly reports those as `UNATTRIBUTED` with reason
`INSUFFICIENT_ACTIVITY`.

This is the deliberate trade: a missed attribution costs an investigator time, a wrong one sends
a legal request to the wrong institution. **The precision figure must never be quoted without
the recall beside it**, because on its own it implies a coverage the system does not have. A
scammer's brand-new deposit address is very often exactly the case this misses.

The one false positive in that measurement was a Binance *collection* wallet — behaviourally
identical to a deposit address by construction, and an investigator told "probably a deposit
address for Binance" would not have been misled by it.

---

## 8. LLM narrative

Prose only, from structured findings, with placeholder validation and regex rejection of any
address or hash the model produced. Facts are templated.

**We nonetheless recommend the template mode for anything going into a case file.** The
safeguards are structural and tested, but the conservative choice for evidentiary documents is
to not have a language model in the loop at all. The report records which mode was used.

---

## 9. Government data and integration

**We have no access to NCRP, CFCFRMS, SAHYOG, FIU-IND records, or any VASP KYC data.**

The system exposes an integration-*ready* API endpoint. This demonstrates how integration could
work. **It is not an integration, and the demo must not imply otherwise.**

Registered-VASP status is surfaced only where our curated data records it. Coverage is partial.

---

## 10. Legal and evidentiary

**We make no claim that:** reports are admissible in any court; our evidence handling
constitutes legally recognised chain of custody; hashes constitute certification under the IT
Act; findings are forensically certified; or the system meets any regulatory standard.

**What is true:** reproducible, verifiable, documented analysis of public blockchain data with
disclosed sources and methods. Admissibility is determined by courts and by agency procedure.

---

## 11. Operational security

**Querying a public API for an address discloses our interest in it to that provider.** This is
inherent to third-party APIs and is a genuine counter-intelligence consideration for sensitive
investigations. The mitigation is a self-hosted node, which is future work.

**Sign-in is single-factor.** TOTP MFA is specified (Phase 12, `SHOULD`) and is not built. A
stolen or reused investigator password is enough to reach case data, and case data is the
product. This is acceptable for a demonstration and is **not** acceptable for a deployment
holding real case material — MFA belongs in the first hardening pass before any such use.

---

## 12. Demo-specific

**The demo runs on a cached snapshot of real chain data by default**, captured at a known date,
with a visible banner. It is real data, frozen — not mock data, and not live.

**Demo addresses are chosen because they have interesting fund flows.** They are not a random
sample, and performance on them does not represent average-case performance.

**Metrics from a hackathon prototype are not production metrics.**

---

## 13. Claims checklist for the presentation

| ✅ Can say | ❌ Cannot say |
|---|---|
| "Traces fund flows across multiple hops on TRON and Ethereum" | "Traces across all blockchains" |
| "Identifies addresses associated with known exchanges, with confidence levels and evidence" | "Identifies which exchange the criminal used" |
| "Detects patterns consistent with laundering" | "Detects money laundering" |
| "Produces an investigative risk score with a full signal breakdown" | "Calculates fraud probability" |
| "Reduces a multi-hour manual trace to about ninety seconds" | "Solves crypto fraud" |
| "Generates an investigation report for the case file" | "Generates court-admissible evidence" |
| "Every conclusion is deterministic and inspectable — no model ships" | "AI-powered fraud detection platform" |
| "Deposit-address precision 0.989 on Binance's own published addresses — at recall 0.186, so four in five are reported unidentified" | "98.9% accurate" |
| "About ninety seconds against the cached snapshot the demo runs on" | "Ninety seconds for any address, live" |
| "Designed for integration with systems like NCRP" | "Integrated with NCRP" |
| "Shows where on-chain tracing ends and legal process must begin" | "Recovers stolen funds" |

**The right-hand column is not pessimism.** Any judge with domain knowledge will test those
claims, and a system that has already drawn the line itself is far more convincing than one
that has to retreat under questioning.
