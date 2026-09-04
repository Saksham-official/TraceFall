# Risk Engine

Implemented by `risk/`.

---

## 1. What the score is, and what it is not

**It is:** a transparent, weighted summary of observable signals, designed so an investigator
can triage a queue of cases and immediately see *why* something ranked where it did.

**It is not:**
- a probability that fraud occurred,
- a probability that the address holder is a criminal,
- evidence of anything,
- a number anyone should act on without reading its breakdown.

Every surface that displays a score displays this alongside it (FR-84):

> *Investigative prioritisation score. Not a probability of fraud and not evidence of criminal
> conduct. Expand to see every contributing signal.*

**Why a rule engine and not a model.** A gradient-boosted "fraud probability" would score
better on a benchmark and be indefensible in the only setting that matters. An investigator
must be able to answer "why did your system flag this address?" in a courtroom, in one
sentence, without a data scientist present. A weighted rule engine can do that. A model cannot.
This is a deliberate accuracy-for-defensibility trade, and it is the right one for this
product. See ADR-006.

---

## 2. Structure

```
address features + patterns + attributions + trace structure
        ↓
  signal evaluators (independent, each returns points + explanation)
        ↓
  weighted sum, clamped 0–100
        ↓
  band  +  separate confidence  +  full itemised breakdown
```

Every signal evaluator is a pure function: features in, `{name, raw_value, weight, points,
description}` out, or `{name, not_evaluated, reason}` if its inputs are missing. Signals never
interact — no conditional weighting, no multiplicative interactions. This is what keeps the
breakdown readable and the arithmetic checkable by hand.

---

## 3. Signal catalogue

Weights are the **maximum points** a signal can contribute. They live in a versioned config
file (`config/risk_weights.yaml`), not in code (FR-85), and the config version is recorded in
every assessment (FR-86).

### Group A — Direct risk contact (max 45)

| Signal | Weight | Scoring |
|---|---|---|
| `sanctioned_contact` | 25 | Full points if tainted value reached an address on a sanctions list; scaled by hop distance (direct = full, each hop −20%) |
| `mixer_interaction` | 20 | Full if funds entered a known mixer; scaled by hop distance |
| `darknet_contact` | 15 | If a dataset labels a reached address as darknet-associated |
| `high_risk_jurisdiction_vasp` | 8 | Reached VASP is in a jurisdiction with no meaningful AML regime |

These are the strongest signals because they rest on `CONFIRMED` dataset matches — Tier A
facts, not inference.

### Group B — Laundering behaviour (max 40)

| Signal | Weight | Scoring |
|---|---|---|
| `rapid_transfer` | 12 | Scaled on median dwell time: < 1 min = full, > 24 h = 0 |
| `fan_out` | 10 | Scaled on outbound degree within a short window, log-scaled above 5 |
| `fan_in` | 8 | Scaled on inbound degree from unrelated sources |
| `peel_chain` | 10 | Full if a peel structure is detected over ≥ 3 hops |
| `structuring` | 8 | Repeated near-identical or round amounts |
| `chain_hopping` | 8 | Value reached a bridge contract |
| `dormancy_burst` | 6 | Long inactivity followed by concentrated activity |

### Group C — Address characteristics (max 20)

| Signal | Weight | Scoring |
|---|---|---|
| `wallet_age` | 8 | Full for < 7 days old, decaying to 0 at 180 days |
| `pass_through_ratio` | 8 | out/in ≈ 1.0 with near-zero retained balance → mule-like |
| `velocity` | 6 | Transactions per active day, log-scaled |
| `single_use_pattern` | 5 | Receives once, forwards once, never used again |
| `no_legitimate_activity` | 5 | No contract interaction, no DeFi, no diverse assets — pure transfer conduit |

### Group D — Case context (max 15)

| Signal | Weight | Scoring |
|---|---|---|
| `cross_case_match` | 10 | Address already appears in another open case |
| `victim_count` | 8 | Distinct probable-victim inbound payers found by backward tracing |
| `value_magnitude` | 5 | Log-scaled on total traced value |

**Explicitly NOT signals**, and why:

- **`exchange_interaction`.** Reaching an exchange is *expected* in a cash-out and is the
  system's own success condition. Scoring it as risk would mark every successful trace as
  suspicious and punish the legitimate industry. It is reported as a finding, not as risk.
- **Any jurisdiction-of-user or nationality proxy.** Not available, not appropriate.
- **Total balance held.** Wealth is not risk.

---

## 4. Aggregation

```
raw   = Σ points over all evaluated signals
score = min(100, round(raw))
```

Deliberately simple. Group maxima sum to 120, so a score of 100 requires strong signals across
several groups — the ceiling is reached by genuinely extreme cases, not by one loud signal.

**No normalisation by the number of evaluated signals.** If a signal could not be evaluated, it
contributes nothing to the score and appears in `not_evaluated`; confidence drops instead
(§6). Renormalising would inflate scores for addresses with incomplete data, which is precisely
backwards.

**Bands (FR-82):**

| Band | Range | Meaning for the investigator |
|---|---|---|
| `LOW` | 0–24 | Nothing notable found |
| `MEDIUM` | 25–49 | Some suspicious characteristics; worth reviewing |
| `HIGH` | 50–74 | Multiple strong indicators; prioritise |
| `CRITICAL` | 75–100 | Direct risk contact plus laundering behaviour; act now |

---

## 5. Explainability (FR-81)

The breakdown is **always returned, never optional**. A `risk_assessments` row with an empty
`signals` array is invalid at the database level.

```json
{ "score": 84, "band": "CRITICAL", "confidence": 0.78,
  "config_version": "risk-weights-v1.2",
  "signals": [
    { "name": "mixer_interaction", "raw_value": true, "weight": 20, "points": 20,
      "description": "24,800 USDT of traced value entered Tornado Cash at hop 2",
      "evidence_tx": ["a91f…"] },
    { "name": "rapid_transfer", "raw_value": 95, "weight": 12, "points": 11,
      "description": "Funds held for a median of 95 seconds before onward transfer" },
    { "name": "fan_out", "raw_value": 47, "weight": 10, "points": 9,
      "description": "Distributed to 47 addresses within 6 minutes" },
    { "name": "wallet_age", "raw_value": 4, "weight": 8, "points": 8,
      "description": "Address first active 4 days before the reported incident" }
  ],
  "not_evaluated": [
    { "name": "victim_count", "reason": "Backward trace was not run for this analysis" }
  ] }
```

Requirements on this payload:

- Every signal states its **raw value**, not just its points — an investigator must be able to
  check the arithmetic.
- Descriptions are **plain language with concrete numbers**. "Suspicious velocity detected" is
  useless; "distributed to 47 addresses within 6 minutes" is testimony.
- Signals cite the transactions that triggered them wherever applicable, so the UI can link
  straight to the evidence.
- `not_evaluated` is separate from zero-scoring. "We didn't check" and "we checked and found
  nothing" are different facts.

---

## 6. Confidence — reported separately, never folded in (FR-83)

```
confidence = w1·data_completeness + w2·attribution_quality + w3·trace_completeness
```

- `data_completeness` — was the transaction history fully retrieved, or page-limited?
- `attribution_quality` — are the entity claims in this trace `CONFIRMED` or `PROBABLE`?
- `trace_completeness` — did the trace terminate naturally, or hit a budget?

**Why it must not be multiplied into the score.** A score of 84 with 0.4 confidence and a score
of 34 with 1.0 confidence would collapse to the same number, and they mean completely different
things: "probably very bad, but we're working from partial data" versus "we looked thoroughly
and it's fine". Multiplying destroys the distinction the investigator most needs.

The UI renders low confidence prominently — a `CRITICAL` score at 0.4 confidence displays a
"limited data" warning next to the band.

---

## 7. Node-level versus root-level scoring

Every significant node in the trace is scored, not just the root. This is what makes the graph
readable at a glance and what surfaces the intermediary wallets worth naming in a report.

The **root score is computed independently**, not as an aggregate of its downstream nodes — but
it *does* include Group A signals inherited by hop-scaled contact (if traced funds reach a
mixer at hop 2, the root's `mixer_interaction` fires at 80% strength). This models the real
investigative intuition: an address that sends money to a mixer two hops away is implicated by
that, and an address that merely sits three hops downstream of something bad is not.

---

## 8. Configuration and versioning

`config/risk_weights.yaml`:

```yaml
version: risk-weights-v1.2
bands: { low: [0,24], medium: [25,49], high: [50,74], critical: [75,100] }
signals:
  mixer_interaction:
    weight: 20
    hop_decay: 0.2
    enabled: true
  rapid_transfer:
    weight: 12
    full_points_below_seconds: 60
    zero_points_above_seconds: 86400
```

Every assessment records `config_version`, so a score generated months ago remains fully
explicable after weights change. Weights are **not** tuned to make demo cases look dramatic;
they are set from investigative reasoning and adjusted only with a documented rationale in
[DECISIONS.md](DECISIONS.md).

---

## 9. Calibration and honest limits

**We cannot properly validate these weights.** Doing so would require a large labelled dataset
of addresses with adjudicated outcomes, which does not exist publicly and which we will not
have. The weights are **expert-reasoned, not empirically calibrated**, and
[LIMITATIONS.md](LIMITATIONS.md) says so.

What we *can* validate, and do (see [TESTING_STRATEGY.md](TESTING_STRATEGY.md)):

- **Determinism** — same inputs and config give the same score, always (NFR-14).
- **Monotonicity** — adding a risk signal never lowers a score.
- **Sanity anchors** — a known Tornado Cash-adjacent address scores `CRITICAL`; a long-lived
  ordinary wallet with diverse activity scores `LOW`; a confirmed exchange hot wallet does not
  score `HIGH` merely for having high volume. That last case is the important regression test:
  **a risk engine that flags exchanges as risky is broken**, and it is an easy way to be broken.
- **Explanation completeness** — every non-zero score has at least one signal with a populated
  description.

---

## 10. Anti-patterns this design rejects

| Anti-pattern | Why it is rejected |
|---|---|
| A black-box "fraud probability" | Cannot be defended by an investigator to anyone |
| A score with no breakdown | Useless in exactly the moment it is questioned |
| Scoring exchange interaction as risk | Marks the system's own success condition as suspicious |
| Confidence multiplied into the score | Destroys the distinction between "bad" and "unclear" |
| Weights tuned to make demo cases look dramatic | Dishonest; and judges ask how weights were chosen |
| Renormalising for missing signals | Inflates scores exactly where data is weakest |
| Colour as the only risk encoding | Fails accessibility; band text always accompanies colour (NFR-18) |
