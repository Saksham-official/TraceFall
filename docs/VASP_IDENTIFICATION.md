# VASP / Exchange Identification

**This is the document that answers PS26183.** Everything else in TraceFall exists to feed or
present what happens here. Implemented by `attribution/`.

---

## 1. The question, stated precisely

> Given an address discovered while tracing a victim's funds, can we determine that it belongs
> to a cryptocurrency exchange or VASP — and if so, which one, and how sure are we?

The honest answer has three possible shapes, and the entire design exists to keep them
separate:

| | Claim | Basis | Investigator action |
|---|---|---|---|
| **`CONFIRMED`** | "Known exchange address — Binance" | The address appears in a named, dated, public dataset | Send the request to Binance |
| **`PROBABLE`** | "Likely associated with Binance — 0.87, based on 4 signals" | Behavioural heuristics and/or classifier | Verify before acting; the evidence is shown |
| **`UNATTRIBUTED`** | "No reliable attribution" | Neither of the above | Treat as an unknown wallet; note what would be needed |

**The central integrity rule of this product: these three are never collapsed.** Not in the
database (a CHECK constraint enforces it — [DATABASE_DESIGN.md](DATABASE_DESIGN.md) §4), not in
the API, not in the UI, not in the PDF, not on the presentation slide.

The failure this prevents is concrete and serious: an investigator sends a freeze request to
the wrong exchange, based on a guess our interface presented as a fact.

---

## 2. Entity types

`EXCHANGE` (centralised trading venue / VASP) · `MIXER` (privacy service, e.g. Tornado Cash) ·
`BRIDGE` (cross-chain) · `TOKEN_CONTRACT` · `DEFI` (DEX, lending) · `GAMBLING` ·
`SANCTIONED` (OFAC or equivalent listing) · `MERCHANT` (payment processor) · `UNKNOWN`.

`EXCHANGE` is further divided by **role**, and this distinction is the crux of the whole
problem:

| Role | Behaviour | Attribution difficulty |
|---|---|---|
| **Hot wallet** | Very high volume both directions; the exchange's operational wallet | **Easy** — well known, in every public dataset |
| **Cold wallet** | Huge balance, rare movement | Easy — publicly documented |
| **Deposit address** | Unique per customer. Receives from one or few external addresses, sweeps everything to the hot wallet, never acts independently | **Hard, and this is the one that matters** |

**Why deposit addresses are the whole problem.** When a scammer cashes out, they do not send to
Binance's hot wallet. They send to *their own deposit address at Binance* — a fresh, unlabelled
address that appears in no dataset. That address is the link between the crime and a KYC'd
account. Identifying it, and identifying which exchange it sweeps to, **is what PS26183 is
asking for.**

---

## 3. Method 1 — Dataset match (produces `CONFIRMED`)

Direct lookup against curated known-address datasets ([DATA_SOURCES.md](DATA_SOURCES.md)).

**Requirements for a `CONFIRMED` verdict (FR-71):**
- Exact match on canonical address form.
- The response names the **source**, its **URL**, and its **dataset date**.
- The source's reliability rating is carried through.

**Coverage, honestly:** high for exchange hot and cold wallets, sanctioned addresses (OFAC SDN
publishes these), major mixers and bridges, and major token contracts. **Near-zero for deposit
addresses**, which are generated per customer and never published.

So dataset matching solves the easy half and none of the hard half. Hence Method 2.

**Conflicting labels.** Two sources labelling one address differently are both stored and both
surfaced (FR-75). Silently picking a winner would hide exactly the disagreement an investigator
needs to see.

**Staleness.** Datasets age. An address labelled "Binance hot wallet" in a 2023 dataset may have
been retired. The tier stays `CONFIRMED` — the dataset really does say that — but the dataset
date is always shown so the investigator can weigh it.

---

## 4. Method 2 — The deposit-address funnel heuristic (produces `PROBABLE`)

The core inference of the product.

### The pattern

An exchange deposit address has an unmistakable behavioural shape:

1. **Many-in, from unrelated sources.** Receives from multiple external addresses with no
   relationship to each other.
2. **Sweeps out.** Shortly after each receipt, ~the entire balance moves onward.
3. **To one consistent destination.** Every sweep goes to the same address — the exchange's
   collection or hot wallet.
4. **Never acts independently.** No outbound activity except sweeps. Rarely interacts with
   contracts. Retains almost no balance.
5. **Often single-purpose.** Many deposit addresses see only a handful of receipts.

### Computable signals

| Signal | Definition | Deposit address looks like |
|---|---|---|
| `sweep_consistency` | Fraction of outbound value going to the single most common destination | > 0.95 |
| `sweep_ratio` | Median (outbound amount / balance at that time) | > 0.98 |
| `dwell_time` | Median seconds between receipt and sweep | < 1 hour |
| `counterparty_diversity_in` | Distinct inbound counterparties | ≥ 3, often high |
| `counterparty_diversity_out` | Distinct outbound counterparties | 1, occasionally 2 |
| `balance_retention` | Current balance / total received | ≈ 0 |
| `contract_interaction_rate` | Fraction of txs interacting with contracts | ≈ 0 |
| `initiates_transfers` | Ever sends without a preceding receipt | false |

### The chained inference — and its weak link

Establishing "this is *a* deposit address" is the strong part. Establishing **which exchange**
requires a second step:

```
address X sweeps consistently to address Y
Y is CONFIRMED as Binance hot wallet   (dataset match)
∴ X is PROBABLY a Binance deposit address
```

**The confidence of the conclusion is bounded by the confidence of the weakest link.** If Y is
itself only `PROBABLE`, then X can be at best `PROBABLE` with a *lower* confidence — the
system must propagate this, never launder a chain of guesses into a confident answer. If Y is
`UNATTRIBUTED`, then X is "probably a deposit address for an unidentified service", which is
still a genuinely useful finding and is reported as exactly that.

### Confidence

Weighted combination of the signals above, calibrated against a labelled validation set, capped
at 0.95. **Never 1.0** — behavioural inference does not produce certainty, and a UI showing
100% confidence on a heuristic is lying.

### False positives — services that look identical

| Look-alike | Why it fires | Distinguisher |
|---|---|---|
| **Payment processor** | Also funnels many-to-one | Usually has merchant-facing outbound patterns and a public label |
| **Custodial wallet service** | Structurally identical | Genuinely hard to distinguish; both are VASPs, so the investigative action is similar |
| **OTC desk** | Funnel-like | Larger, less regular amounts |
| **Automated sweeper for a legitimate business** | Same shape | Consistent, predictable timing |
| **Another exchange's internal rebalancing** | Sweeps to one destination | Very high volume, bidirectional |

This is disclosed in the finding text. **The system does not pretend this heuristic is clean.**

### False negatives — deposit addresses we will miss

- Fresh addresses with one or two transactions — too little behaviour to classify. Common, and
  the most consequential gap: a scammer's brand-new deposit address may be exactly this.
- Exchanges that sweep infrequently or in batches.
- Direct-to-hot-wallet deposits with a memo tag (some venues), where the deposit address is
  shared and the customer identifier is off-chain entirely.
- Non-custodial destinations that are simply not exchanges.

**Reported as `UNATTRIBUTED`, never as "not an exchange".** Absence of evidence is stated as
absence of evidence.

---

## 5. Method 3 — Behavioural classifier (produces `PROBABLE`)

An ML refinement of Method 2, not a replacement. Details in
[AI_ML_STRATEGY.md](AI_ML_STRATEGY.md).

**Why ML is genuinely justified here** (and almost nowhere else in this system): the boundary
between "deposit address" and "look-alike" is fuzzy, multi-dimensional, and interacts — no
hand-tuned threshold set captures it as well as a model trained on labelled examples.

**Constraints.** Gradient-boosted trees over the §4 feature set, so per-prediction feature
attribution is available. Every prediction returns its top contributing features as the
evidence list. **If the model is unavailable, Method 2's deterministic heuristic runs instead**
with a lower confidence ceiling, and the attribution records that it fell back. The product
works with `ml/` deleted.

---

## 6. Method 4 — Behavioural clustering (produces weak `PROBABLE`)

Grouping addresses under one controlling actor. On TRON and Ethereum this is materially weaker
than on Bitcoin — no common-input heuristic exists
([PROBLEM_ANALYSIS.md §7](PROBLEM_ANALYSIS.md)).

Available signals: **gas/energy funding** (on Ethereum, addresses funded for gas by a common
source are often co-controlled — a reasonable signal); **temporal correlation** (synchronised
activity); **behavioural fingerprints** (identical round amounts, same-second timing, identical
contract-call patterns); **contract deployment** (deployer relationships are structural and
reliable).

**Used only as supporting evidence, never as a primary attribution basis.** Confidence capped
at 0.6. A cluster claim on an account-model chain is a hint, and is labelled as one.

---

## 7. Decision procedure

```
1. Dataset match?
      yes → CONFIRMED, cite source + date. Stop.
2. Is it a contract?
      yes → classify by contract type (token / DEX / bridge / mixer);
            CONFIRMED if the contract is in a dataset, else PROBABLE by behaviour. Stop.
3. Enough activity to profile? (≥3 inbound transfers and ≥1 outbound)
      no  → UNATTRIBUTED, reason INSUFFICIENT_ACTIVITY. Stop.
4. Deposit-funnel heuristic and/or classifier:
      score ≥ 0.7 → identify the sweep destination
                      destination CONFIRMED   → PROBABLE, entity = that exchange,
                                                confidence = score
                      destination PROBABLE    → PROBABLE, confidence = score × dest_confidence
                      destination UNATTRIBUTED→ PROBABLE "deposit address of an
                                                unidentified service", entity = null
      score 0.4–0.7 → PROBABLE "service-like behaviour", entity = null, low confidence
      score < 0.4  → continue
5. High-volume hub? (very high degree, high volume, bidirectional)
      → PROBABLE "service, type unidentified", low confidence
6. Otherwise → UNATTRIBUTED
```

Note steps 3 and 6. **A system that reaches `UNATTRIBUTED` often is working correctly.** Most
addresses on a chain are not services and cannot be attributed from public data. A tool that
labels everything is a tool that is guessing.

---

## 8. What is presented to the investigator

### `CONFIRMED`
> **Binance — Exchange (Confirmed)**
> This address appears in the *<source name>* known-address dataset (as of 2026-07-01).
> `[View source]`
> **Action:** funds reaching this address entered Binance's custody. A KYC request to Binance
> naming this address and the transaction hash may identify the receiving account.

### `PROBABLE`
> **Likely a Binance deposit address — 87% confidence**
> *This is a probabilistic assessment based on transaction behaviour, not a confirmed
> identification.*
> **Evidence:**
> - 31 of 32 inbound receipts were swept to `TQn9…FFbc` within a median of 12 minutes
> - `TQn9…FFbc` is a confirmed Binance hot wallet (*<source>*, 2026-07-01)
> - Received from 32 distinct addresses with no prior relationship to each other
> - Retains 0.02% of total received value; never initiates independent transfers
>
> **Also consistent with:** a payment processor or custodial wallet service with a similar
> sweep pattern.
> **Action:** verify before acting. The transaction hashes above can be checked independently.

### `UNATTRIBUTED`
> **No reliable attribution**
> This address does not appear in any known-address dataset and does not exhibit service-like
> behaviour. It is most likely a personal or intermediary wallet.
> **What would be needed:** identifying the controller requires KYC records held by a VASP, or
> data sources beyond public blockchain analytics.

That third box is the one that earns the other two their credibility.

---

## 9. Investigator override (FR-78)

An investigator may confirm or correct any attribution, with a required justification. The
override is stored in `attribution_overrides` and **never modifies the machine finding** —
both are retained and both appear in the report, so the record shows what the system said and
what the human concluded.

Overrides accumulate into a valuable labelled dataset. Feeding them back into the classifier is
noted in [FUTURE_SCOPE.md](FUTURE_SCOPE.md); it requires careful handling of confirmation bias
and is not an MVP feature.

---

## 10. Evaluation

Measured against a hold-out set of addresses with known ground truth from public datasets, and
reported honestly in [TESTING_STRATEGY.md](TESTING_STRATEGY.md).

**Precision is prioritised over recall, deliberately.** A missed attribution costs an
investigator time. A wrong attribution sends a legal request to the wrong institution, wastes
that institution's time, damages the credibility of the requesting agency, and may appear in a
case file. Target: **precision ≥ 0.95 on `PROBABLE` at the 0.7 confidence threshold**, recall
whatever that permits.

The threshold is configurable, versioned, and recorded in every assessment.
