# OQ-09 · Deposit-heuristic precision, measured

*Research note. Resolves the precision gate in FR-71 and TESTING_STRATEGY.md §14, and the
calibration half of OQ-09.*
**Measured:** 2026-09-05, against live Ethereum data through Blockscout.
**Reproduce:** `python scripts/measure_attribution_precision.py --positives 500 --negatives 31`
(seed 20260905, fixed).

---

## Verdict

**Precision 0.989 at the 0.7 threshold — the ≥ 0.95 gate is met.** Recall is 0.186, and that
number matters more than the precision does for how the product should be described.

| | |
|---|---|
| Sample | 531 addresses — 500 positives, 31 negatives |
| True positives | 93 |
| False positives | **1** |
| True negatives | 30 |
| False negatives | 407 |
| **Precision** | **0.989** (gate ≥ 0.95) |
| **Recall** | **0.186** |

---

## 1. Where the ground truth came from

Binance's proof-of-reserves disclosure (`wallet_address_20260801.zip`, audit 01 Aug 2026,
Merkle root `14b8970f…`) publishes two files. Both are first-party: the operator naming its
own addresses.

- **Positives — `PR01AUG26_Deposit.csv`.** 3,255,172 rows, of which **2,289,147 are unique
  Ethereum addresses** Binance publishes as its own deposit addresses. A positive here is an
  address the exchange itself says is a deposit address, which is as good a label as exists.
- **Negatives — `PR01AUG26_HotCold.csv`.** 31 unique Ethereum hot and cold wallets, excluding
  the three under third-party custody (Ceffu), which are not Binance's own wallets.

**The negatives are deliberately hard.** They are the addresses a deposit address sweeps
*into*: exchange-operated, enormous volume, and the single most consequential confusion the
heuristic could make. Easy negatives — a random personal wallet — would have flattered the
number and taught us nothing.

**There are no TRON deposit addresses in the disclosure at all.** Checked, not assumed: the
deposit file contains ETH, WLD, SOL, OPTIMISM, BSC, ARBITRUM, BASE and ZKSYNCERA, and zero TRX.
The measurement is therefore on Ethereum. The heuristic is chain-agnostic — it consumes
`NormalizedTransfer` and knows nothing about which chain produced it — so the result carries
over, but it is an Ethereum measurement and should be described as one.

---

## 2. Score distribution

Deposit addresses that could be scored (120 of 500):

| Score | Count | |
|---|---|---|
| 1.00 | 27 | every signal fired |
| 0.85 | 45 | |
| 0.70 | 21 | at the threshold |
| 0.65 | 2 | below |
| 0.55 | 4 | |
| 0.50 | 3 | |
| 0.40 | 1 | |

Exchange hot and cold wallets (30 scored):

| Score | Count |
|---|---|
| 0.80 | 1 |
| 0.65 | 6 |
| 0.60 | 2 |
| 0.55 | 2 |
| 0.50 | 2 |
| 0.45–0.25 | 3 |
| 0.00 | 14 |

The threshold at 0.70 sits in a real gap: 93 of the 120 scoreable deposit addresses are at or
above it, and 29 of 30 exchange wallets are below. That separation is the reason the number is
what it is, and it was not tuned to produce it — 0.70 is the value OQ-09 reasoned to before any
of this data existed.

---

## 3. The one false positive, and why it is not really wrong

`0xe1940f578743367f38d3f25c2d2d32d6636929b6` scored 0.80. Binance lists it in *HotCold*, so the
ground truth calls it an exchange wallet. Its observed behaviour:

> 44 transfers — **43 inbound from 38 distinct senders, 1 outbound to a single recipient**,
> holding 1.7 billion USDC.

That is a **collection wallet**, and a collection wallet is behaviourally identical to a deposit
address by construction: many unrelated senders in, everything out to one place. The difference
is scale and account ownership, not shape, and no behavioural heuristic can separate them —
which is precisely what VASP_IDENTIFICATION.md §2 says when it distinguishes hot, cold and
deposit roles.

**What an investigator would actually have been told** is "probably a deposit address for
Binance". The address does funnel into Binance. Acting on that — sending a KYC request to
Binance naming it — would have been correct. It is scored as a false positive here because the
ground-truth file puts it in a different column, and it is left scored that way rather than
reclassified to improve the headline number.

---

## 4. Recall 0.186 — the number that should shape how this is described

**411 of 531 addresses could not be scored at all**, and almost every one was
`INSUFFICIENT_ACTIVITY`: a published deposit address that had received once and forwarded once,
or received a handful of times and never sent. The most common shapes were `1 in, 1 out`,
`1 in, 0 out` and `2 in, 0 out`.

This is not a defect that was discovered here. VASP_IDENTIFICATION.md §4 already lists it first
among the false negatives:

> *Fresh addresses with one or two transactions — too little behaviour to classify. Common, and
> the most consequential gap: a scammer's brand-new deposit address may be exactly this.*

What this measurement adds is the size of it. **Roughly four out of five real deposit addresses
have too little history for the heuristic to say anything about them**, and the honest output in
those cases is `UNATTRIBUTED` with reason `INSUFFICIENT_ACTIVITY` — which is what the system
already produces.

The trade is deliberate and correct for this product: a missed attribution costs an investigator
time, a wrong one sends a legal request to the wrong institution. But **"precision 0.989" must
never be quoted without the recall beside it**, or it implies a coverage the system does not
have.

---

## 5. What this measurement cannot tell us

The look-alikes that actually cost precision in the field — **payment processors, custodial
wallet services, OTC desks** — are not in this set, because Binance's disclosure contains
Binance's addresses and nothing else. LIMITATIONS.md §7 already says such hard negatives are
scarce in any dataset we can assemble, and that remains true.

So: this is evidence that the heuristic separates deposit addresses from **exchange wallets**.
It is not evidence that it separates them from a payment processor, and the number must not be
cited as if it were.

---

## 6. Consequences

1. **The FR-71 precision gate is met and can stop being described as unmeasurable.**
2. **OQ-09's thresholds are validated as reasoned, not tuned.** 0.70 was chosen before this data
   existed and lands in a genuine gap in the distribution. No weight was changed as a result of
   this measurement, and none should be without a note here saying why.
3. **Recall belongs in LIMITATIONS.md** as a measured figure rather than a qualitative warning.
4. The measurement needs live network access, so it runs manually or on a schedule alongside the
   live smoke tests (TESTING_STRATEGY.md §13) — never in the offline suite.
