# Problem Analysis — SIH26183

> **Status:** Phase 0 (planning). This document establishes the vocabulary and the honesty
> boundaries that every other document in this repository must respect.

---

## 1. The problem statement

**PS ID:** SIH26183
**Organisation:** Ministry of Home Affairs (Government of India)
**Theme:** Blockchain & Cybersecurity · **Category:** Software
**Title:** *Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from
Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics*

Restated in operational terms:

> A victim files a cybercrime complaint and provides the cryptocurrency wallet address they
> sent funds to. Given only that address, automatically determine where the money went, and
> in particular **which exchange or Virtual Asset Service Provider (VASP) the funds reached**,
> fast enough and with enough evidence that an investigator can act on it.

The operative words are **real-time**, **from a wallet address alone**, **automated**, and
**exchange identification**. Everything else in the system exists to serve those four.

---

## 2. Why this problem exists — the Indian enforcement context

Understanding the gap is what separates a credible solution from a generic "blockchain
explorer with a dashboard".

### 2.1 The reporting chain today

| Body / system | Role |
|---|---|
| **NCRP** (National Cybercrime Reporting Portal, cybercrime.gov.in) | Where a citizen files a cybercrime complaint. Financial-fraud complaints capture payment details, including crypto wallet addresses in free-text or attachment form. |
| **CFCFRMS** (Citizen Financial Cyber Fraud Reporting & Management System, helpline 1930) | The "golden hour" mechanism. For **fiat** fraud it routes a freeze request to the receiving bank/wallet within minutes, and money is often recovered. |
| **I4C** (Indian Cyber Crime Coordination Centre, MHA) | Coordinates cybercrime response, operates NCRP/CFCFRMS, runs analytics and capacity building for state police. |
| **SAHYOG** | I4C portal automating notices to intermediaries for removal/disabling of unlawful content. Relevant as the model for *automated, structured request dispatch to a private platform*. |
| **FIU-IND** | Since the 2023 PMLA notification, VASPs operating in India must register as Reporting Entities. This matters: for a registered VASP there is an identifiable, addressable counterparty. |

### 2.2 The gap

**For a bank transfer, CFCFRMS knows exactly which institution received the money.** The
account number encodes the bank. A freeze request goes out in minutes.

**For a crypto transfer, nothing encodes the destination institution.** A TRON address is 34
characters of base58 with no issuer, no routing information, no jurisdiction. An investigator
holding `TXyz...` has:

- no way to know whether it is a scammer's personal wallet or an exchange deposit address,
- no way to know which exchange, if any, controls it,
- no automated way to follow the money after it leaves that address,
- and therefore **no one to send a freeze or KYC request to.**

Today this is done manually: an investigator pastes the address into a block explorer, reads
transactions by eye, clicks through a few hops, and gives up — or escalates to a commercial
tool (Chainalysis, TRM Labs, Elliptic) that most state cyber cells do not have licensed.

**TraceFall targets exactly this gap:** automate the address → fund flow → exchange
attribution path, and produce a report an investigator can attach to a request to that VASP.

### 2.3 Why speed matters

Exchange deposits are swept to hot wallets and, if the account is not frozen, withdrawn or
converted quickly. The window in which a KYC/freeze request can still find the funds is
short. A tool that takes an analyst two days to operate has already lost. Hence *real-time*:
the target is **an actionable first answer in under two minutes** from address submission.

---

## 3. Users and their jobs

| User | What they need | Success looks like |
|---|---|---|
| **Primary: Cybercrime investigator** (state cyber cell / district cyber police station) — moderate technical skill, no blockchain expertise assumed | Paste address → get "where did the money go, which exchange, how confident, and what's my evidence" | Produces a signed PDF report identifying a VASP contact point within minutes |
| **Secondary: I4C / central analyst** | Cross-case patterns; is this address already in another case? Which VASPs recur? | Detects that 40 complaints funnel into 3 deposit addresses |
| **Tertiary: Supervisory officer** | Case triage and prioritisation by risk and recoverability | Sorts a queue of 200 cases by "still recoverable" |
| **Not a user: the victim** | — | Victims interact with NCRP, never with TraceFall |

The primary user's expertise level is the single most important design constraint. **The
system must explain itself in investigator language, not in blockchain jargon**, and must
never require the user to know what a "peel chain" or "nonce" is to understand a finding.

---

## 4. Inputs and outputs

**Input (minimum):** one suspect wallet address, plus optionally the chain, the amount the
victim sent, the approximate date/time of the transfer, and a case/NCRP reference number.
Amount and timestamp are enormously valuable — they let the system pin the *victim's specific
transaction* rather than analysing the address generically. The UI must ask for them but must
work without them.

**Outputs:**

1. **Fund flow trace** — where the money went, hop by hop, with amounts and timestamps.
2. **VASP/exchange attribution** — for each significant endpoint, the entity, the confidence
   tier, and the evidence behind it.
3. **Risk assessment** — a transparent, itemised score with every contributing signal shown.
4. **Detected patterns** — layering, fan-out, consolidation, peel chains, rapid transfer,
   dormancy-then-burst.
5. **Interactive transaction graph** — the visual investigators actually reason with.
6. **Investigation report** — a PDF suitable for attaching to a case file, with an evidence
   appendix of raw transaction hashes and integrity hashes.

---

## 5. The blockchain investigation workflow, honestly described

```
suspect address
  → validate + identify chain
  → fetch native + token transfers
  → normalize to a chain-agnostic transfer model
  → identify the victim's transaction (if amount/time supplied)
  → follow value forward, hop by hop, with proportional taint
  → at each address: is it a known service? does it behave like one?
  → stop at service boundaries, depth limits, or value thresholds
  → assemble a graph, run pattern detectors, score risk
  → attribute endpoints, rank by recoverability
  → report
```

Two things about this that most hackathon projects get wrong:

**(a) Tracing does not "follow the victim's coins".** On an account-model chain, balances
are fungible pooled numbers. When a scam wallet receives 10,000 USDT from a victim and
already held 50,000 USDT, then sends 20,000 USDT out, there is no fact of the matter about
whose coins moved. Tracing is a *value-attribution convention*, not a physical fact.
TraceFall uses **proportional (haircut) taint** and says so explicitly in every report.
See [WALLET_TRACING.md](WALLET_TRACING.md).

**(b) Tracing legitimately ends.** When funds hit an exchange hot wallet, the chain stops
telling you anything — the next movement is an internal database entry the exchange never
publishes. This is not a bug or an incomplete implementation. It is the point at which the
investigation correctly transitions from on-chain analytics to a legal request. The system
must present this as an *achievement* ("we found the exit point, here is who to ask"), not
paper over it.

---

## 6. Capability tiering — the most important section in this repository

Every claim TraceFall makes falls into one of three buckets. This tiering is enforced in the
data model, the API, the UI, and the report. **No document, demo, or presentation may blur
these lines.**

### Tier A — What we can reliably determine (observed on-chain fact)

- That an address is syntactically valid and exists on a given chain.
- The complete list of transactions involving an address, with amounts, timestamps, block
  heights, fees, and confirmation status.
- The direction of every transfer and the exact counterparty address.
- Token contract, symbol, and decimals for a token transfer.
- Whether an address is a contract or an externally-owned account.
- Address age, first-seen and last-seen times, transaction counts, in/out degree.
- Aggregate flow: how much value moved from A to B over a window.
- **Whether an address appears in a specific published dataset** (e.g. the OFAC SDN
  crypto-address list, a published exchange hot-wallet list) — and, critically, *which*
  dataset and as of what date.

These are facts. They are reproducible by anyone with the same public data.

### Tier B — What we can infer probabilistically (intelligence, not fact)

- That an address is a **deposit address belonging to** an exchange, inferred from the
  classic funnel pattern: receives from many unrelated addresses, sweeps ~everything to one
  consistent destination shortly after each receipt, never initiates independent activity.
  Strong heuristic, not proof.
- That two addresses are **controlled by the same actor**, inferred from gas/energy funding
  patterns, synchronised timing, or shared behaviour. On account-model chains this is
  materially weaker than Bitcoin's common-input-ownership heuristic. See §7.
- That a flow pattern constitutes **layering, structuring, or a peel chain**. These are
  behavioural signatures with legitimate look-alikes (market makers, payment processors,
  automated trading).
- **Risk scores of any kind.** A score is a summary of signals we chose and weighted. It is
  an argument, not a measurement.
- That an unlabelled high-volume address is "an exchange" based on behaviour alone.

Everything in Tier B ships with a confidence value and an enumerated evidence list, and is
rendered visually distinct from Tier A.

### Tier C — What requires data we do not and will not have

- **The identity of the person controlling any address.** No KYC data. Ever. Not inferable
  from the chain.
- **Which specific customer account at an exchange received a deposit.** The exchange knows;
  the chain does not.
- Off-chain and internal-ledger transfers (an exchange moving funds between two customers
  never touches the chain).
- Reliable, current, comprehensive attribution of the long tail of addresses. Commercial
  vendors achieve this with years of proprietary clustering, undercover deposits, subpoena
  returns, and paid data — none of which we have.
- Anything inside a mixer (Tornado Cash and similar break the link by construction).
- Privacy-chain activity (Monero, Zcash shielded pools) — not traceable, full stop.
- Whether a transaction was actually fraudulent. **Only a court decides that.** TraceFall
  identifies *suspicion and flow*, never guilt.

**Design rule:** if a feature requires Tier C data, it does not get built, and the
presentation does not claim it. `LIMITATIONS.md` is the canonical public list.

---

## 7. Chain selection and its consequences

The MVP supports **TRON** and **Ethereum**, USDT-first. Rationale in
[DECISIONS.md](DECISIONS.md) (ADR-001); the analytical consequence belongs here:

Both are **account-model** chains. This is a genuine analytical handicap that must be stated
openly, because it is the single biggest technical difference between TraceFall and the
Bitcoin-era forensics literature every judge has read about:

| | Bitcoin (UTXO) | TRON / Ethereum (account) |
|---|---|---|
| Wallet clustering | **Common-input-ownership heuristic** — if two addresses are inputs to one transaction, one party almost certainly controls both. Very strong. | **Does not exist.** No equivalent structural signal. |
| Change-address detection | Available (several heuristics) | Not applicable |
| Available clustering signals | Structural + behavioural | **Behavioural only**: deposit-funnel pattern, gas/energy funding source, temporal correlation, contract-deployer relationships |

**Consequence:** on TRON and Ethereum, entity clustering is weaker and virtually everything
we produce about entity identity that is not a direct dataset match lands in Tier B. We
accept this and design around it, rather than pretending otherwise. The compensating
advantage is that the deposit-address funnel pattern — which is *exactly* what we need for
exchange identification — is highly visible on account-model chains and is precisely the
signal PS26183 asks about.

We chose the corridor where Indian fraud money actually flows over the corridor with the
prettier heuristics. That is the right trade for this problem statement.

---

## 8. Where AI/ML genuinely helps, and where it does not

Summarised here; argued fully in [AI_ML_STRATEGY.md](AI_ML_STRATEGY.md).

**Deterministic algorithms are strictly better for:** address validation, transaction
retrieval, normalization, graph construction, path finding, taint propagation, dataset
matching, and structural pattern detection (fan-out, fan-in, peel chain). These have exact
definitions. Replacing exact logic with a model would make the system less accurate, less
explainable, and slower. **Using ML here would be a downgrade dressed as innovation.**

**ML earns its place in exactly two spots:**
1. **Exchange deposit-address classification** — "does this address behave like an exchange
   deposit address?" is a genuine pattern-recognition problem over behavioural features,
   with fuzzy boundaries and legitimate look-alikes, where a trained classifier beats a
   hand-tuned threshold. This is the core Tier-B inference of the whole product.
2. **Anomaly detection over address behaviour** — surfacing unusual flow structures the
   hand-written detectors were not designed to catch. Optional; advisory only.

**An LLM earns its place in exactly one spot:** turning structured findings into readable
investigator narrative in the report. It receives a JSON findings object and writes prose.
It is **forbidden from producing any address, amount, hash, entity name, or attribution** —
those are templated directly from the data. A hallucinated wallet address in a police report
is a catastrophic failure mode, and the architecture makes it structurally impossible rather
than merely unlikely.

**AI is not used for:** the risk score (must be inspectable and defensible), attribution
decisions (must cite evidence), or anything a judge or a defence lawyer might need to
interrogate.

---

## 9. What is realistically demonstrable at SIH

**Demonstrable:** paste a real fraud-linked TRON address → real transactions retrieved →
multi-hop trace with taint → interactive graph → patterns detected → deposit-address
attribution to a named exchange with evidence → itemised risk score → PDF report. End to end,
under two minutes, on real public blockchain data.

**Not demonstrable, and must not be implied:** identifying a suspect; comprehensive
attribution across all addresses; cross-chain tracing through bridges; de-mixing; real-time
integration with NCRP or any government system (we can demo an *integration-ready interface*,
which is honest); recovering funds.

**The most credible thing we can do on stage is show the system say "I don't know."** An
address it cannot attribute should render as `UNATTRIBUTED` with an explanation of what
would be needed. Judges who understand this domain will trust every other claim more
because of it.

---

## 10. Related documents

- [REQUIREMENTS.md](REQUIREMENTS.md) — the numbered requirements derived from this analysis
- [LIMITATIONS.md](LIMITATIONS.md) — the full honest constraint list
- [VASP_IDENTIFICATION.md](VASP_IDENTIFICATION.md) — how Tier A/B attribution is implemented
- [DECISIONS.md](DECISIONS.md) — ADR-001 (chains), ADR-004 (taint model)
