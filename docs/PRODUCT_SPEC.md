# Product Specification — TraceFall

The product as the investigator experiences it. Technical realisation lives in
[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md); this document defines *what each stage
promises*.

---

## 1. Product summary

**TraceFall** takes a victim-reported cryptocurrency wallet address and answers one question
an Indian cybercrime investigator cannot currently answer on their own:

> **"Where did the money go, and which exchange do I send the freeze request to?"**

It does this by automating the manual block-explorer work an analyst would otherwise do by
hand, and by packaging the result as evidence rather than as a dashboard curiosity.

**Positioning:** TraceFall is the crypto-side equivalent of what CFCFRMS does for bank
transfers — identify the receiving institution fast enough to act. It does not attempt to be
Chainalysis. It attempts to be the 20% of Chainalysis that closes 80% of Indian
investment-scam cases, built from public data, and honest about the rest.

---

## 2. Primary user

**Cybercrime / financial investigator** at a state cyber cell or district cyber police
station.

- Comfortable with case management software and web dashboards.
- **Not** a blockchain specialist. Does not know what a nonce, a peel chain, or an EOA is,
  and should not need to.
- Time-pressured; often handling dozens of open complaints.
- Accountable: anything the tool outputs may end up in a case file or in court, so unexplained
  conclusions are worse than useless — they are a liability.

**Design consequences.** Every finding is written in plain language with a "why we think
this" expander. Nothing is stated more confidently than the evidence supports. Every screen
answers "what do I do next?"

---

## 3. Core workflow — the 13 stages

```
 1. Case Creation
        ↓
 2. Suspect Address Intake & Validation
        ↓
 3. Blockchain Data Retrieval
        ↓
 4. Transaction Normalization
        ↓
 5. Address Enrichment & Clustering
        ↓
 6. Fund Flow Tracing
        ↓
 7. Graph Construction
        ↓
 8. Suspicious Pattern Detection
        ↓
 9. VASP / Exchange Attribution
        ↓
10. Risk Scoring
        ↓
11. Alert Generation
        ↓
12. Investigator Review (dashboard)
        ↓
13. Investigation Report
```

Stages 3–11 run automatically as one asynchronous pipeline. Stages 1–2 and 12–13 are human.

---

### Stage 1 — Case Creation

**Purpose.** Establish the investigative container so every downstream artefact is
attributable to a complaint and to an officer.

**Input.** Case title, optional NCRP acknowledgement or FIR number, complaint description,
reported loss in INR, incident date.
**Output.** A `case` record with a generated case ID, owner, status `OPEN`, and the first
entry in the case timeline.
**Human effort saved.** None — this is deliberate. The case is the audit anchor.
**Failure mode.** None material.

---

### Stage 2 — Suspect Address Intake & Validation

**Purpose.** Turn a string a victim typed into a validated, chain-identified address, and
capture the two fields that make the whole trace dramatically better.

**Input.** The address string. Optionally: chain (auto-detected), the amount the victim sent,
the date/time they sent it.
**Output.** A validated `case_address` record with canonical form, detected chain, and
account type (EOA vs contract).

**Why amount and time matter so much.** With them, the trace anchors to *the victim's actual
transaction* and follows that specific value. Without them, the system analyses the address
generically and the trace is far noisier. The form must therefore ask for them prominently
while still accepting an address alone.

**Validation.** TRON base58check with checksum verification; Ethereum hex with EIP-55
checksum verification when mixed-case. Rejection happens before any network call, with an
explanation ("this looks like a Bitcoin address; TraceFall currently supports TRON and
Ethereum").

**Failure mode.** Address valid but has never transacted → the pipeline stops at Stage 3 and
reports "address exists but has no activity", which is itself a useful finding (the victim may
have been given a decoy, or mistyped).

---

### Stage 3 — Blockchain Data Retrieval

**Purpose.** Obtain the complete public transaction record for every address the pipeline
needs to examine.

**Input.** Address + chain + time window.
**Output.** Raw provider responses, persisted verbatim with a SHA-256 hash and retrieval
timestamp, plus a completeness flag.

**Behaviour.** Paginates until the window or page limit is reached. Respects rate limits with
exponential backoff and jitter. Caches by (chain, address, window) with a TTL. In
`LIVE_MODE=false`, reads only from the committed fixture cache.

**Failure modes and handling.**
| Failure | Handling |
|---|---|
| Rate limited (429) | Backoff and retry; on exhaustion, use partial data and mark truncated |
| Provider down | Fail over to secondary provider; else serve cache; else mark stage degraded |
| Address has thousands of transactions | Cap at the configured page limit, mark truncated, and tell the investigator explicitly that this address is high-volume — itself a signal it may be a service |
| Network absent (demo) | Fixture cache serves everything |

**Non-negotiable.** Raw responses are stored *before* transformation. This is what makes the
evidence chain defensible: we can always show what the provider actually returned.

---

### Stage 4 — Transaction Normalization

**Purpose.** Collapse two different chain APIs into one internal model so that nothing
downstream contains chain-specific logic.

**Input.** Raw provider responses.
**Output.** `Transfer` rows — chain, tx hash, block, timestamp, from, to, asset, raw amount,
decimals, normalized amount, approximate USD value, fee, status, transfer index.

**Rules.** Integer arithmetic throughout — token amounts are stored as raw integers with
decimals recorded, and converted only for display. Failed and reverted transactions are kept
and flagged, never dropped. One transaction producing several transfers yields several rows
sharing a hash.

**Failure mode.** Unknown token contract → the transfer is kept with `asset=UNKNOWN` and the
contract address recorded, rather than discarded.

---

### Stage 5 — Address Enrichment & Clustering

**Purpose.** Attach everything already known or cheaply derivable about each address before
the expensive work begins.

**Input.** Normalized transfers, curated label datasets.
**Output.** Per-address: first/last seen, age, in/out degree, total in/out value, balance,
account type, dataset label matches, and behavioural feature vector.

**Clustering caveat.** On TRON and Ethereum there is no common-input heuristic. Clustering
here is behavioural only — deposit-funnel structure, gas/energy funding source, temporal
co-movement — and every cluster claim is Tier B. See
[PROBLEM_ANALYSIS.md §7](PROBLEM_ANALYSIS.md).

---

### Stage 6 — Fund Flow Tracing

**Purpose.** The core of the product: follow the money.

**Input.** Root address, optional anchor transaction, depth, thresholds, time window.
**Output.** A trace: nodes with taint shares, edges with attributed value, and a termination
reason per terminal node.

**Behaviour.** Breadth-first outbound expansion. Proportional (haircut) taint attribution.
Prune below threshold. Cap fan-out per node. Enforce a global edge budget. **Stop expanding at
exchange, mixer, and bridge nodes** — a service boundary is a valid answer, not a dead end.

Full algorithm: [WALLET_TRACING.md](WALLET_TRACING.md).

**Failure mode.** Root has no outbound transfers → trace of one node, terminated
`NO_OUTFLOW`. Reported plainly; the address is a collection point that has not yet moved
funds, which for the investigator is *good news* (money may still be there).

---

### Stage 7 — Graph Construction

**Purpose.** Turn the trace into the object investigators actually reason with.

**Input.** Trace nodes and edges.
**Output.** A directed weighted graph with node and edge metadata, plus derived measures
(paths, centrality, components), capped to a renderable size.

---

### Stage 8 — Suspicious Pattern Detection

**Purpose.** Name the laundering behaviours present, in investigator language.

**Input.** The graph plus the underlying transfers.
**Output.** `pattern_finding` records: type, severity, the exact transactions that triggered
it, a plain-language explanation, and its known false-positive modes.

Detectors: fan-out/splitting, fan-in/consolidation, rapid transfer/layering, peel chain,
dormancy-then-burst, structuring.

**Non-negotiable.** Every detector ships with its own false-positive disclosure. "Fan-out to
50 addresses in 10 minutes" is a laundering signature *and* is what a payroll contract does.
The finding says so.

---

### Stage 9 — VASP / Exchange Attribution

**Purpose.** Answer the question PS26183 actually asks.

**Input.** Every significant node in the trace, with its features and label matches.
**Output.** Per node: entity type, entity name where known, **attribution tier**, confidence
(for `PROBABLE`), and an enumerated evidence list.

**The three tiers, and their exact wording in the UI:**

| Tier | UI wording | Basis |
|---|---|---|
| `CONFIRMED` | *"Known exchange address — Binance (source: <dataset>, as of <date>)"* | Direct match in a curated known-address dataset |
| `PROBABLE` | *"Likely associated with Binance — 0.87 confidence, based on 4 signals"* + expandable evidence | Deposit-funnel heuristic and/or classifier over behavioural features |
| `UNATTRIBUTED` | *"No reliable attribution. This address does not match any known dataset and does not behave like a service. Identifying its controller would require KYC data held by a VASP."* | Neither of the above |

**These three must never be visually or verbally collapsed.** A `PROBABLE` attribution
rendered as a fact is the single worst failure this product can commit, because an
investigator may act on it against the wrong institution.

Full method: [VASP_IDENTIFICATION.md](VASP_IDENTIFICATION.md).

---

### Stage 10 — Risk Scoring

**Purpose.** Prioritise. Not adjudicate.

**Input.** Address features, pattern findings, attributions, trace structure.
**Output.** A 0–100 score, a band, a confidence value, and an itemised breakdown giving every
signal's name, raw value, weight, and point contribution.

**Non-negotiable.** The breakdown is always available, one click from the score. The score is
labelled an investigative prioritisation aid, never a probability of fraud. Weights live in
versioned config; the config version is recorded in every assessment so an old assessment
remains explicable.

Full model: [RISK_ENGINE.md](RISK_ENGINE.md).

---

### Stage 11 — Alert Generation

**Purpose.** Push the things that cannot wait for someone to scroll.

**Triggers.** Trace reaches a sanctioned address; trace reaches a mixer; a node scores
`CRITICAL`; an address already appears in another open case.
**Output.** Alert records with severity, trigger, and a link to the causing finding.

---

### Stage 12 — Investigator Review

**Purpose.** The human does the part machines should not: judgement.

The investigator works the graph, inspects evidence, confirms or overrides attributions
(recorded, never overwriting the machine finding), pins key findings, and adds notes.

**Human-in-the-loop is a feature, not a compromise.** The system's job is to reduce a day of
explorer clicking to five minutes of reviewing a prepared case.

---

### Stage 13 — Investigation Report

**Purpose.** Produce something that can be attached to a case file.

**Contents.** Case metadata · suspect address details · fund flow summary · key transactions ·
graph image · pattern findings · VASP findings with tiers and evidence · risk findings with
signal breakdown · data sources and retrieval timestamps · tracing convention used ·
limitations and disclaimer · evidence appendix of all transaction hashes · report ID and
SHA-256 content hash.

**Narrative may be LLM-written from structured findings. Facts never are** — every address,
amount, hash, and entity name is templated directly from the database. If the LLM is
unavailable, the report generates with templated narrative and loses nothing but prose polish.

---

## 4. What the product deliberately does not do

- Name a suspect.
- Claim fraud.
- Trace through mixers or across bridges automatically.
- Freeze, move, or custody funds. TraceFall holds no keys and is read-only against chains.
- Integrate live with any government system (it exposes an integration-ready API instead).

---

## 5. Success criteria for the SIH demo

1. A real, publicly documented fraud-linked TRON address, entered live.
2. Real on-chain data, retrieved and shown with its provenance.
3. A multi-hop trace terminating at an identifiable exchange deposit address.
4. Attribution presented with its tier and evidence — including at least one node the system
   honestly reports as `UNATTRIBUTED`.
5. An itemised risk score whose every point is explained.
6. A generated PDF report.
7. Under two minutes, end to end.

Criterion 4 is the one that wins credibility with anyone who knows the domain.
