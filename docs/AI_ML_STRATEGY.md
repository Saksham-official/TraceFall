# AI / ML Strategy

Implemented by `ml/` (models) and an LLM adapter used only by `reports/`.

---

## 1. The governing decision

**AI is not the product. Evidence is the product.**

SIH problem statements often invite AI/ML, and the reflex is to add a model somewhere visible.
That reflex produces systems that are less accurate, less explainable, and less defensible than
the deterministic version — while looking more impressive for ninety seconds.

TraceFall's position: **use ML in exactly the two places where a fuzzy pattern genuinely beats
a written rule, use an LLM in exactly one place where prose is genuinely needed, and use
deterministic algorithms everywhere else.** We expect to defend this choice to judges, and it
is a stronger answer than a longer model list.

---

## 2. The partition

### Deterministic — no AI, ever

| Component | Why |
|---|---|
| Address validation | Base58check and EIP-55 are exact algorithms. A model would be strictly worse. |
| Transaction retrieval and pagination | API mechanics |
| Normalization | Arithmetic |
| Graph construction | Definitional |
| Path finding, centrality, components | Exact graph algorithms |
| Taint propagation | An arithmetic convention (haircut). A learned taint model would be unexplainable and unauditable. |
| Dataset label matching | A lookup. Exactness is the entire point of `CONFIRMED`. |
| Structural pattern detection (fan-out, fan-in, peel, dormancy, structuring) | These have exact definitions. A detector that says "47 addresses in 6 minutes" is better testimony than one that says "0.81 laundering-likelihood". |
| **Risk scoring** | Must be inspectable and defensible line by line. See [RISK_ENGINE.md](RISK_ENGINE.md) §1. |
| Report facts | Templated from the database. Never generated. |

Using ML for any of these would be replacing a correct answer with an approximate one.

### ML — two components, both optional

1. **Exchange deposit-address classifier** (§3) — the one place where a trained model earns its
   place.
2. **Behavioural anomaly detection** (§4) — advisory only, `SHOULD`-priority.

### LLM — one component

3. **Report narrative generation** (§5) — prose from structured findings, with hard structural
   guarantees against fabrication.

### Deliberately not used

- **Graph neural networks for fraud classification.** Academically attractive, and unusable
  here: no adequate labelled training data, no explainability an investigator could present,
  and a strong tendency to learn "this address is near a known-bad address", which the
  deterministic trace already tells us with evidence attached.
- **LLM agents deciding investigation steps.** Non-deterministic control flow over a
  legal-evidentiary process. No.
- **LLMs reading raw blockchain data.** Slower, more expensive, and less accurate than parsing.
- **Any generative model producing addresses, amounts, hashes, or entity names.**

---

## 3. Component 1 — Exchange deposit-address classifier

**Priority:** `SHOULD` (the deterministic heuristic in
[VASP_IDENTIFICATION.md §4](VASP_IDENTIFICATION.md) is the `MUST`).

**Problem.** Given an address's behavioural profile, is it an exchange deposit address?

**Why ML is genuinely justified here.** The boundary is fuzzy and multi-dimensional. Sweep
consistency, dwell time, counterparty diversity, and balance retention interact in ways a
hand-tuned threshold set captures poorly — an address with 0.93 sweep consistency but a
five-second dwell and forty distinct payers is a deposit address; one with 0.99 consistency, a
three-day dwell, and one payer probably is not. That interaction is what a tree ensemble
learns and what a rule table does badly.

**Input.** The `AddressProfile` feature vector.

**Features** (all deterministic, all computed by `intel/`): `sweep_consistency`, `sweep_ratio`,
`median_dwell_seconds`, `dwell_variance`, `counterparty_diversity_in`,
`counterparty_diversity_out`, `balance_retention`, `contract_interaction_rate`,
`initiates_transfers`, `tx_count_in`, `tx_count_out`, `in_out_ratio`, `age_days`,
`active_days_ratio`, `distinct_assets`, `amount_variance_in`, `round_amount_fraction`.

**Model.** Gradient-boosted trees (LightGBM or XGBoost). Chosen because it handles small
tabular datasets well, needs no scaling, tolerates missing features natively, trains in
seconds, and — decisively — **supports per-prediction feature attribution via SHAP**, which is
what produces the evidence list the UI displays. A neural network would fit similarly and
explain far worse.

**Output.** `{ probability, top_features: [{name, value, contribution}] }`. The top features
become the `evidence` array on the attribution (FR-72).

**Training data.**

| Source | Class | Approx. scale | Reality check |
|---|---|---|---|
| Addresses that demonstrably sweep to confirmed exchange hot wallets | Positive | Thousands, derivable | Strong labels, self-generated from public data |
| Confirmed non-service addresses (long-lived, diverse activity, DeFi use) | Negative | Thousands | Easy to sample |
| Known payment processors and custodial services | Hard negative | Dozens–hundreds | **The scarce class, and the one that matters most** |
| Synthetic funnel and look-alike topologies | Both | Generated | Fills structural gaps only |

**Labelling method.** Positives are bootstrapped from Method 2's chained inference: find
addresses whose sweep destination is a `CONFIRMED` exchange hot wallet. This is honest but
circular in an important way — **the model learns to reproduce the heuristic that generated its
labels.** It can refine the boundary and weigh interactions the heuristic treats
independently; it cannot discover a class of deposit address the heuristic never finds. This
limit is documented in [LIMITATIONS.md](LIMITATIONS.md) and must not be glossed over in the
presentation.

**Evaluation.** Precision, recall, F1, and PR-AUC on a held-out set, with a manually reviewed
sample of hard negatives. **Precision is the optimisation target**, for the reasons in
[VASP_IDENTIFICATION.md §10](VASP_IDENTIFICATION.md): target ≥ 0.95 at the 0.7 operating
threshold.

**Explainability.** SHAP values per prediction, surfaced as the evidence list. A prediction
whose SHAP output cannot be rendered as a human sentence is not shown at all — it is downgraded
to the deterministic heuristic's result.

**Fallback.** Model file missing or failing to load → `attribution/` uses the deterministic
funnel heuristic with a confidence ceiling of 0.8, and records `method=DEPOSIT_HEURISTIC` so
the report shows which path produced the finding. **The system is fully functional with `ml/`
deleted** — that is the design test, and it should be an actual test.

---

## 4. Component 2 — Behavioural anomaly detection

**Priority:** `NICE TO HAVE`. Build only if Phases 1–9 are comfortably complete.

**Problem.** Surface unusual flow structures the hand-written detectors were not designed to
catch.

**Model.** Isolation Forest over the same feature vector. Unsupervised, so it needs no labels —
which is the entire reason it is viable.

**Output.** An anomaly score, presented as *"unusual compared to typical addresses in this
trace"*, and **never as a risk signal**. It does not enter the risk score
([RISK_ENGINE.md](RISK_ENGINE.md) §3 has no anomaly signal, deliberately). It is a hint that
directs an investigator's attention, nothing more.

**Why it stays out of the score.** An unsupervised anomaly score cannot be explained in a
sentence and cannot be defended. Letting it move a number that appears in a report would
violate the risk engine's central property.

**Fallback.** Absent → nothing surfaces. No other component depends on it.

---

## 5. Component 3 — LLM report narrative

**Priority:** `SHOULD`.

**Problem.** The findings are structured data. A report reads better with connective prose that
summarises the fund flow in paragraphs.

**Input.** A structured findings JSON object — and **nothing else**. No raw blockchain data, no
free-text prompt from a user.

**Output.** Narrative paragraphs for defined sections: executive summary, fund-flow narrative,
and findings discussion.

**The hard constraints, and how they are enforced structurally rather than by instruction:**

1. **Every fact is templated from the database.** Addresses, amounts, hashes, entity names,
   dates, scores, and tiers are inserted by the template engine. The LLM writes the sentences
   *between* them.
2. **Placeholder substitution, not free generation.** The model receives text with typed
   placeholders (`{{ROOT_ADDRESS}}`, `{{TRACED_AMOUNT}}`) and must return text preserving them.
   Post-generation validation rejects output that dropped or invented a placeholder.
3. **Regex validation on output.** Any string matching an address or transaction-hash pattern
   that did not come from a placeholder causes rejection and fallback to the template.
4. **No attribution language upgrades.** The model is given tier-appropriate phrasing and the
   output is checked for forbidden constructions — a `PROBABLE` finding whose narrative says
   "belongs to Binance" is rejected. Wording discipline is validated, not merely requested.
5. **Marked in the report.** `narrative_source` is recorded and printed (FR-115).

**Fallback.** LLM unavailable, times out, or fails validation → the templated narrative is used
and the report is otherwise complete (FR-116). This path must be exercised in tests, not
assumed.

**Why the paranoia.** A hallucinated wallet address in a document attached to a police case
file is a catastrophic, credibility-ending failure. Prompt instructions are not a control. The
architecture makes it structurally impossible for the model to introduce a fact, and that is
the only acceptable design.

---

## 6. Synthetic data

**Purpose.** Training augmentation for structural patterns that are rare in sampled real data,
and deterministic fixtures for pattern-detector tests.

**Generation.** A documented script (`ml/synthetic/generate.py`) producing labelled
topologies: deposit-funnel, payment-processor look-alike, peel chain, fan-out layering,
consolidation, and ordinary-wallet baselines. Parameters (hop count, fan-out width, dwell
distribution, amount distribution) are configurable and logged with the dataset.

**Rules.**
- Synthetic records are flagged at the row level and never enter the evidence or canonical
  layers of a real case.
- Anywhere synthetic data surfaces in the UI or an export, it is visibly labelled (NFR-15).
- **Model metrics reported on synthetic data are reported separately from real-data metrics.**
  A classifier scoring 0.99 on generated funnels has learned the generator, not the world.
- No synthetic data appears in the SIH demo. The demo runs on the real-chain fixture snapshot
  ([DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md) §8).

**What synthetic data cannot teach.** Real look-alikes. The genuinely hard negatives — payment
processors, OTC desks, custodial services — have messy real-world behaviour a generator does
not reproduce, and they are exactly the cases where precision is lost. Synthetic data helps
with structure and hurts with calibration if trusted beyond that.

---

## 7. Model operations

**Versioning.** Model artefacts are versioned; the version is recorded on every attribution
that used one, so an old finding stays explicable.

**Storage.** Trained artefacts live outside git (they are binary and large) with a documented
download or training path. Training is reproducible from a script and a seed.

**Inference.** Pure function, in-process, no network. Latency is milliseconds and irrelevant
next to the network-bound retrieval stage.

**Retraining.** Manual and documented. No automated retraining — a model that silently changes
its behaviour between two runs of the same case is unacceptable in an evidentiary context.

**Monitoring.** Prediction distributions logged; a sharp shift indicates data drift and is
investigated by a human.

---

## 8. What we say about AI at the demo

**Accurate:** *"We use machine learning for one thing: classifying exchange deposit addresses
from transaction behaviour, because that boundary is genuinely fuzzy. Every prediction shows
the features that drove it. Everything else — tracing, scoring, pattern detection — is
deterministic and auditable, because an investigator has to defend it."*

**Not said:** "AI-powered fraud detection." "Our AI identifies criminals." "Deep learning
blockchain intelligence." Any claim implying the system determines guilt, or that AI is doing
work that is in fact a database lookup.

The restraint is the differentiator. Most entries will claim more AI than they have; a system
that can explain precisely where AI helps and where it would hurt demonstrates the deeper
understanding.
