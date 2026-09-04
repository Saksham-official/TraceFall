# Testing Strategy

**Principle:** the tests that matter are the ones that catch a wrong number in a police report.
Coverage percentage is a proxy; correctness of the tracing, attribution, and risk engines is the
actual goal.

---

## 1. Test pyramid

| Layer | Count (approx.) | Speed | Network |
|---|---|---|---|
| Unit | ~200 | ms | Never |
| Integration | ~60 | s | Fixtures only |
| API contract | ~40 | s | Fixtures only |
| End-to-end | ~10 | min | Fixtures only |
| Live smoke | ~5 | min | **Real APIs**, manual/CI-scheduled |

**Only the live smoke tests touch the network.** Everything else runs from the fixture cache,
which makes the whole suite deterministic, fast, and runnable offline (NFR-12).

**Tooling.** pytest + pytest-asyncio, factory-boy, respx for HTTP mocking, Vitest + React
Testing Library, Playwright for E2E, Testcontainers for a real PostgreSQL in integration tests.

---

## 2. Chain adapters and ingestion

**Unit.**
- TRON base58check: valid addresses accepted; wrong checksum rejected; wrong length rejected;
  wrong prefix rejected.
- Ethereum: lowercase accepted; uppercase accepted; **valid EIP-55 mixed case accepted; invalid
  EIP-55 mixed case rejected** — this one catches real transcription errors from victim
  statements and is worth its own test.
- Chain auto-detection, including the "this looks like Bitcoin" path.
- Canonicalisation: an Ethereum address in three cases resolves to one stored form.
- TRON base58 ↔ hex conversion round-trips.

**Integration (fixtures).**
- Pagination across multiple pages assembles a complete result.
- Rate-limit response triggers backoff and retry, then succeeds.
- Primary failure triggers secondary failover.
- Total failure returns partial data with `complete=false` and a reason — **never raises**.
- Evidence is written with a correct SHA-256 before parsing.
- Page-limit truncation sets the truncation flag.

**Named cases.**
| Case | Expectation |
|---|---|
| Address with zero transactions | Valid empty result, not an error |
| Address with >10,000 transfers | Truncated, flagged, and fed to attribution as a service signal |
| Address with only failed transactions | Transfers retained, marked `FAILED` |
| Provider returns malformed JSON | Typed parse error; raw evidence retained |

---

## 3. Normalization

**Unit.**
- TRC-20 6-decimal amount → correct display value.
- ERC-20 18-decimal amount → correct display value.
- **Unknown token → raw amount retained, decimals never guessed, display suppressed.** The
  single most damaging normalization bug would be a wrong decimal count in a report.
- One transaction with four transfers → four rows sharing a hash, distinct indices.
- Failed transfer retained and flagged.
- TRON millisecond and Ethereum second timestamps both normalise to the same UTC instant.
- Re-ingesting identical data is a no-op (idempotency on `(chain, tx_hash, transfer_index)`).
- **Property test: no float appears anywhere in the amount path.** Assert type invariants on
  large amounts (a 30-digit raw value must survive round-trip exactly).

---

## 4. Tracing engine — the most important suite

Runs entirely on hand-built in-memory transfer sets. No network, no database.

**Correctness properties** ([WALLET_TRACING.md §10](WALLET_TRACING.md)):

| Property | Test |
|---|---|
| Conservation | Attributed value out of a node never exceeds attributed value in |
| **Full accounting** | original = Σ terminals + Σ pruned + Σ retained. Asserted after every trace, in tests *and* in production |
| Determinism | Same input, same params → bit-identical trace (NFR-14) |
| Termination | Halts on every input |
| Cycle safety | A→B→A does not loop and does not inflate taint |

**Haircut arithmetic.**
- Node holds 100 untainted, receives 100 tainted, sends 100 → 50 attributed.
- Node receives only tainted funds, sends all → 100% attributed.
- Node receives 1 tainted into 999 untainted, sends everything → 0.1% attributed, pruned at
  the default 1% threshold.

**Traversal controls.**
- `max_depth=3` produces no node at depth 4.
- Fan-out of 100 with `fanout_cap=20` follows 20 and records 80 as pruned.
- Edge budget exhaustion terminates cleanly with `EDGE_BUDGET`.
- Below-threshold branches are recorded as pruned, with values.

**Termination reasons.** One test per reason, asserting the exact reason is recorded:
`MAX_DEPTH`, `BELOW_THRESHOLD`, `SERVICE_BOUNDARY`, `NO_OUTFLOW`, `EDGE_BUDGET`, `TIME_WINDOW`.

**Ordering rule.** Outbound transfers occurring *before* the tainted inflow are not followed.
Easy to get wrong, and produces a plausible-looking wrong answer when it is.

**Anchoring.** Exact amount+time match anchors correctly; multiple candidates return a list;
no match falls back to unanchored and sets the flag.

**Named scenarios** (fixture graphs committed to the repo):

| Scenario | Shape | Expectation |
|---|---|---|
| `simple_two_hop` | A→B→exchange | Terminates `SERVICE_BOUNDARY` at hop 2, 100% attributed |
| `fan_out_50` | A→50 addresses | 20 followed, 30 pruned, accounting balances |
| `peel_chain_5` | Repeated peel structure | Peel pattern detected, main path ranked first |
| `cycle_a_b_a` | A→B→A | Terminates, no taint inflation |
| `mixer_terminal` | A→B→Tornado | Terminates at mixer, alert raised |
| `no_outflow` | A receives only | Single-node trace, `NO_OUTFLOW` |
| `dust_flood` | 1,000 sub-threshold transfers | All pruned, accounting balances |
| `deep_chain_12` | 12 sequential hops | Terminates at `max_depth`, remaining value reported |

---

## 5. Graph engine

- Trace → graph conversion preserves every node and edge.
- Parallel transfers between the same pair aggregate into one edge with the correct count and
  total.
- Highest-value path selection is correct on a hand-computed example.
- Betweenness identifies the known chokepoint in a fixture graph.
- Node cap returns exactly `max_nodes`, always including root, all terminals, and all attributed
  service nodes; `truncated=true` is set.
- Serialisation round-trips.

---

## 6. Pattern detection

One positive and one **negative (false-positive)** test per detector. The negative tests matter
more:

| Detector | Positive | Must NOT fire on |
|---|---|---|
| `FAN_OUT` | 47 recipients in 6 min | 47 recipients over 6 months |
| `FAN_IN` | 200 payers into one address | An exchange hot wallet already attributed as a service |
| `RAPID_TRANSFER` | 95-second median dwell | A wallet holding funds for days |
| `PEEL_CHAIN` | 5-hop peel structure | A simple linear chain with no peeling |
| `DORMANCY_BURST` | 400 days idle, then 50 txs | A consistently active wallet |
| `STRUCTURING` | Repeated 9,900 USDT transfers | Varied natural amounts |

Every finding must carry a non-empty `false_positive_note` — asserted generically across all
detectors, so a new detector cannot ship without one.

---

## 7. Attribution engine — the integrity suite

**Tier discipline** (the tests that protect the product's core claim):

- Dataset match → `CONFIRMED`, with source name, URL, and dataset date populated.
- **A `CONFIRMED` verdict without a dataset reference is rejected at the database level.**
  Test the constraint, not just the code path.
- **A `PROBABLE` verdict without a confidence value or with an empty evidence array is
  rejected.** Same.
- Insufficient activity → `UNATTRIBUTED` with reason `INSUFFICIENT_ACTIVITY`.
- No signal → `UNATTRIBUTED`, never a low-confidence guess.
- **Confidence propagation:** deposit address whose sweep destination is only `PROBABLE`
  produces a *lower* confidence than one sweeping to a `CONFIRMED` destination. A chain of
  guesses must not launder into a confident answer.
- Conflicting labels from two sources are both returned; neither is silently dropped.
- Classifier unavailable → deterministic fallback runs, confidence capped at 0.8, `method`
  recorded as `DEPOSIT_HEURISTIC`.
- **A test that deletes `ml/` entirely and asserts the full pipeline still completes.**

**Deposit-address heuristic:**

| Fixture | Expectation |
|---|---|
| Classic funnel sweeping to a confirmed hot wallet | `PROBABLE`, confidence > 0.8, exchange named |
| Funnel sweeping to an unattributed address | `PROBABLE`, "deposit address of an unidentified service", entity null |
| Payment-processor look-alike | Low confidence or `UNATTRIBUTED` — **the precision test** |
| Personal wallet with diverse activity | `UNATTRIBUTED` |
| Fresh address, two transactions | `UNATTRIBUTED`, `INSUFFICIENT_ACTIVITY` |

**Metrics.** Precision, recall, and F1 on a held-out labelled set, reported in CI. Precision on
`PROBABLE` at the 0.7 threshold must not regress below 0.95 — a CI gate, not a dashboard.

---

## 8. Risk engine

- Determinism: identical input + config → identical score (NFR-14).
- **Monotonicity: adding a risk signal never lowers a score.** Property-based test over
  generated feature sets.
- Score clamps at 100 when signals exceed it.
- Band boundaries: 24/25, 49/50, 74/75 map correctly.
- Every non-zero score has at least one signal with a populated description.
- `not_evaluated` is populated when inputs are missing, and those signals contribute zero.
- Confidence is returned separately and **never multiplied into the score** — assert both a low
  score with high confidence and a high score with low confidence remain distinguishable.
- Config version is recorded; changing weights changes the score and the recorded version.

**Sanity anchors** (regression tests against real fixture addresses):

| Address type | Expectation |
|---|---|
| Confirmed mixer-adjacent address | `CRITICAL` |
| Fresh pass-through wallet, rapid transfer | `HIGH` |
| Long-lived wallet, diverse activity, no risk contact | `LOW` |
| **Confirmed exchange hot wallet** | **Not `HIGH` merely for volume** — a risk engine that flags exchanges as risky is broken, and this is the easiest way to break it |

---

## 9. ML components

- Feature extraction is deterministic for a fixed profile.
- Model loads and predicts within the latency budget.
- **Missing model file → graceful fallback, no exception.**
- SHAP attribution returns the expected feature count.
- Training script is reproducible from a fixed seed.
- Metrics reported separately for real and synthetic evaluation sets.
- **Synthetic-only metrics are never reported as overall performance** — asserted in the
  reporting code, because this is a claim that would embarrass the project if made loosely.

---

## 10. API

- Every endpoint: happy path, validation failure, unauthenticated, unauthorised, not-found.
- **Case isolation: user A attempting every operation on user B's resources.** Parameterised
  across every case-scoped endpoint. The most important security suite in the system
  ([SECURITY.md §12](SECURITY.md)).
- Not-found and forbidden both return **404** for case resources — no existence leak.
- Rate limits enforced and `Retry-After` returned.
- Async: analysis returns 202 with a job ID; status polls through stages; cancel works;
  duplicate start returns 409.
- Response schema validation against the documented contract for every endpoint.
- **Amounts serialise as strings, never JSON numbers** — a large token amount must survive
  round-trip exactly.
- Error responses contain a request ID and no internal detail.

---

## 11. Frontend

**Unit/component.** `AddressChip` truncation and copy. `AttributionCard` renders all three
tiers with **visually and textually distinct** treatments — asserted, because this is the
product's core UI guarantee. `RiskBadge` never uses colour alone. `AmountDisplay` handles very
large values and null USD. `TruncationBanner` appears whenever `truncated` is true.

**E2E (Playwright, fixture mode).**
1. Login → new case → add address → start analysis → results appear.
2. Graph interaction: select node, expand, scrub timeline.
3. Risk breakdown expands and shows every signal.
4. Attribution override with justification, both findings visible afterwards.
5. Report generation and download.
6. **Degraded path:** provider failure → partial results with the amber banner.
7. **Fixture-mode banner is present** — a demo must never look live when it is not.

**Accessibility.** axe-core on every main screen; keyboard-only navigation of the graph;
contrast verification in both themes.

---

## 12. End-to-end investigation tests

Full pipeline, fixture data, database included:

| Scenario | Asserted outcome |
|---|---|
| **Golden case** — real fraud address, multi-hop, ends at a confirmed exchange | Full pipeline completes; exchange identified `CONFIRMED`; report generates; **every number matches a stored expected value** |
| Mixer case | Terminates at mixer; alert raised; risk `CRITICAL` |
| No-movement case | Single-node trace; framed as "funds have not moved" |
| Unattributable case | Completes with `UNATTRIBUTED` terminals; **report still generates and is useful** |
| Cross-case | Second case with an overlapping address raises the correlation alert |
| Degraded | Provider unavailable → `PARTIAL` status, degradations listed, results usable |

The golden case is a **regression lock**: its expected output is committed, and any change to
tracing, attribution, or risk that alters it must be explained and the expectation
deliberately updated. This is what prevents silent drift in the numbers that go into reports.

---

## 13. Live smoke tests

Five tests against real APIs, run manually and on a CI schedule — never in the main suite:

1. TronGrid reachable, returns transfers for a known active address.
2. Etherscan reachable, same.
3. Failover providers reachable.
4. A short live trace completes within the NFR-01 budget.
5. **Fixture data still matches live data for a stable historical address** — this is how we
   learn a provider changed its response shape before it breaks a demo.

---

## 14. CI gates

Pull requests must pass: full offline suite; ≥ 80% coverage on `tracing/`, `attribution/`,
`risk/` (NFR-13); lint and type checks (ruff, mypy, eslint, tsc); `pip-audit` and `npm audit`;
secret scanning; and the attribution precision gate.

Merges to main additionally run the E2E suite and the golden-case regression.

---

## 15. What is deliberately not tested

- Third-party API correctness — not ours; the smoke tests only verify reachability and shape.
- Blockchain consensus behaviour.
- Exhaustive UI visual regression — high maintenance, low value at this stage.
- Load testing beyond a basic concurrency check — the bottleneck is a third-party rate limit,
  and load-testing our own code would measure the wrong thing.
