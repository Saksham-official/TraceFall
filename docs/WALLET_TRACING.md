# Wallet Tracing — Algorithm Design

The core of TraceFall. Implemented by `tracing/`.

---

## 1. What tracing is, and what it is not

**Tracing is a value-attribution convention, not a physical fact.**

On an account-model chain, balances are pooled fungible numbers. A scam wallet holding 50,000
USDT receives 40,000 from a victim and later sends 60,000 onward. There is no fact of the
matter about how much of the victim's money is in that 60,000. Any answer is a *convention*
someone chose.

This is not a limitation of our implementation. It is a property of the asset. Commercial
forensics tools face it identically; they simply do not always say so.

**TraceFall's convention is proportional attribution ("haircut"), and every trace output,
API response, and report states this in plain language.** An investigator who does not
understand that the number is attributed rather than measured may over-claim in court.

### Why haircut over the alternatives

| Model | Rule | Assessment |
|---|---|---|
| **Poison / taint-all** | Any address touched by tainted funds is fully tainted | Explodes instantly. One deposit to an exchange taints the entire exchange. Unusable. |
| **FIFO** | First coins in are first coins out | Deterministic and used in some legal contexts, but imposes an ordering the chain does not have on account-model assets. Arbitrary precision dressed as rigour. |
| **Haircut / proportional** | Outputs carry tainted value in proportion to the tainted share of the balance at the time | Symmetric, order-independent, conservative, and trivially explainable to a non-technical reader: *"40% of what was in this wallet was traced from the victim, so we attribute 40% of what left it."* **Chosen.** |

The `taint_model` field is recorded on every trace so a future FIFO option remains
distinguishable and old traces stay explicable (ADR-004).

---

## 2. Inputs

**A trace follows one asset.** Raw amounts are integers at each asset's own precision, so
40,000 USDT (6 decimals, 4e10 raw) and 1 ETH (18 decimals, 1e18 raw) are not comparable
numbers; pooling them into a single taint ratio produces a confident, meaningless answer. The
victim sent one asset, and that is the asset we follow. A swap into another asset therefore
ends the trace rather than continuing through it — see ADR-017 and
[LIMITATIONS.md](LIMITATIONS.md).

| Parameter | Default | Max | Purpose |
|---|---|---|---|
| `root_address` | — | — | The victim-reported suspect address |
| `anchor_tx_hash` | derived | — | The victim's specific inbound transaction, if identifiable |
| `direction` | `FORWARD` | — | `FORWARD` follows the money; `BACKWARD` finds other victims |
| `max_depth` | 5 | 10 | Hop limit |
| `taint_threshold` | 0.01 | — | Prune branches carrying <1% of the original value |
| `min_amount_usd` | 10 | — | Ignore dust transfers |
| `time_window_days` | 180 | 365 | Only transfers within the window are eligible |
| `edge_budget` | 5,000 | 20,000 | Global cap on edges explored |
| `fanout_cap` | 20 | 100 | Per-node cap on outbound branches followed, by taint |
| `stop_at_services` | `true` | — | Terminate at exchange / mixer / bridge nodes |

### Anchoring — the single highest-value input

When the victim supplies the amount and approximate time of their transfer, the system finds
the matching inbound transaction to the root address and traces **that value**, rather than
everything the address ever received.

Matching: transfers to the root, within ±24 hours of the reported time, with an amount within
±2%. Exactly one match → anchor set. Several matches → the investigator picks from a list.
None → fall back to tracing all inbound value in the window, clearly flagged as unanchored.

The difference in output quality between an anchored and an unanchored trace is large. This is
why the intake form must press for amount and time (FR-41).

---

## 3. The algorithm

Breadth-first, depth by depth, with a priority queue ordered by tainted value.

```
initialise:
  taint[root] = anchored_amount (or total inbound in window)
  frontier    = [root at depth 0]
  edges_used  = 0

for depth in 0 .. max_depth-1:
    next_frontier = []
    for node in frontier ordered by taint desc:

        if node is terminal:            # see §4
            record termination reason; continue

        outbound = transfers from node, within window,
                   after the node's first tainted inflow,
                   above min_amount_usd
        if outbound is empty:
            terminate(node, NO_OUTFLOW); continue

        total_in  = sum of all inflow to node (tainted + untainted)
        total_out = sum of eligible outflow from node
        taint_ratio = tainted_in[node] / max(total_in, total_out)   # the haircut

        aggregate outbound by (counterparty, asset)
        keep top `fanout_cap` by outbound value

        for each aggregated edge (node → next, asset, amount):
            attributed = amount * taint_ratio
            if attributed / original_amount < taint_threshold:
                record edge as pruned; continue
            if edges_used >= edge_budget:
                terminate(node, EDGE_BUDGET); break out
            record edge with attributed value
            taint[next] += attributed
            edges_used += 1
            if next not already visited at a shallower depth:
                next_frontier.append(next at depth+1)

    frontier = next_frontier

any node still in frontier at max_depth → terminate(node, MAX_DEPTH)
```

### What happens at each hop, in words

1. **Arrive** at an address carrying an attributed tainted amount.
2. **Ask what it is.** Known exchange, mixer, or bridge? Then this is a terminal node and the
   trace has succeeded — it found where the money left the traceable chain. Record and stop.
3. **Compute the haircut.** What fraction of the value leaving this address is
   attributed to the victim?

   The denominator is `max(total_in, total_out)`, **not inflow alone**. An address can send
   out more than the inflow we observe — it may have held a balance before the victim paid,
   or its earlier history may fall outside the analysis window. Dividing by inflow alone
   would then attribute more tainted value than ever arrived, letting the trace create money
   out of nothing. Taking the larger of the two caps total onward attribution at
   `tainted_in` in every case, and reduces to the textbook haircut whenever outflow does not
   exceed inflow. This correction was forced by the accounting invariant during
   implementation.
4. **Look at the outflows** after the tainted money arrived, within the window, above dust.
5. **Aggregate** them per counterparty and asset — twenty transfers to one address is one edge.
6. **Rank and cap.** Follow the top 20 by value. Record the rest as pruned so nothing is
   silently dropped.
7. **Attribute and prune.** Each edge carries `amount × taint_ratio`. Below 1% of the original,
   it is noise; record as pruned and stop.
8. **Enqueue** the survivors for the next depth.

### Ordering rule

Only outbound transfers **after** the tainted funds arrived are followed. Money that left
before the victim's transfer cannot contain it. This one condition removes a large amount of
false trail and is easy to forget.

---

## 4. Termination — where traces end and why that is fine

| Reason | Meaning | What the investigator should do |
|---|---|---|
| `SERVICE_BOUNDARY` | Funds entered an exchange, mixer, or bridge | **This is the win.** Exchange → send a KYC/freeze request. Mixer → trail ends, document it. Bridge → note destination chain. |
| `MAX_DEPTH` | Hop limit reached with value still moving | Increase depth and re-run, or continue from this node as a new root |
| `BELOW_THRESHOLD` | Attributed value fell under 1% | Usually noise; lower the threshold if the case value warrants it |
| `NO_OUTFLOW` | Address has received but not sent | **Good news.** Funds may still be sitting there |
| `EDGE_BUDGET` | Global exploration cap hit | Narrow the window or raise the threshold and re-run |
| `TIME_WINDOW` | Onward movement falls outside the window | Widen the window |

**Service-boundary stopping is the most important design choice in the tracing engine.**

Continuing past an exchange hot wallet is not merely useless — it is actively misleading. A hot
wallet mixes every customer's funds; anything downstream is other customers' withdrawals.
Tracing onward would produce a graph implicating hundreds of innocent addresses, with real
consequences if it reached a case file.

So the trace stops, and the UI says: *"Funds reached a Binance deposit address. On-chain
tracing ends here. Identifying the account holder requires a KYC request to Binance."* That
sentence **is the product**. It is precisely the output PS26183 asks for.

---

## 5. Preventing graph explosion

Without controls, a 5-hop trace touching addresses with 100 counterparties each explores 10^10
nodes. Five independent mechanisms bound it:

| Control | Default | Effect |
|---|---|---|
| Depth limit | 5 | Bounds the exponent |
| Fan-out cap | top 20 by value | Bounds the base |
| Taint threshold | 1% | Kills branches that cannot matter; the most effective control in practice |
| Edge budget | 5,000 | Global hard stop regardless of everything else |
| Service-boundary stopping | on | Prevents expansion into high-degree hub nodes, which are the main explosion source |

Worst case is therefore a known constant (~5,000 edges), not a function of chain size — which
is what makes the "under two minutes" target (NFR-01) achievable at all.

**Everything pruned is recorded**, with the reason and the value not followed. The API and
report show "12 branches pruned below threshold, totalling 3.2% of traced value". An
investigator must be able to see what the algorithm chose not to look at.

---

## 6. Backward tracing (FR-49)

Same algorithm, edges reversed: from the root, find who paid *in*.

Its purpose is different and specific: **identifying other victims**. If 200 addresses paid
similar amounts into a scam wallet over three weeks, that is 200 probable victims — most of
whom have not filed a complaint. For I4C this is arguably the highest-value output of the
whole system, because it turns one complaint into a picture of the whole campaign.

Backward traces terminate faster and shallower (depth 2 default): the point is to enumerate
inbound payers, not to trace their origins.

**Caution, stated in the UI:** an address paying into a scam wallet is a *probable victim*, not
a participant. The system labels these `VICTIM_SOURCE`, never as suspects. Getting this
distinction wrong would cause real harm to real people.

---

## 7. Structural findings the tracer emits

These are computed during traversal and consumed by `patterns/`
([RISK_ENGINE.md](RISK_ENGINE.md) uses them as signals):

**Fund splitting (fan-out).** One address → many recipients in a short window. Classic
layering. *Also produced by:* payroll contracts, airdrops, exchange batch withdrawals.

**Fund consolidation (fan-in).** Many addresses → one recipient. Either a collection point or,
frequently, an exchange deposit address — which is why fan-in feeds attribution as well as
risk. *Also produced by:* legitimate deposit addresses, merchant settlement.

**Rapid transfer (layering).** Median dwell time below 10 minutes across several hops. Funds
that arrive and leave within minutes are being moved, not held. Strong signal.

**Peel chain.** A repeating structure where a large amount moves forward at each hop while a
small amount peels off. Classic Bitcoin laundering; less common but present on account chains.

**Chain hopping / bridging.** Value reaching a known bridge contract. Recorded as terminal with
the destination chain where determinable.

**Intermediary / mule wallet.** A node with high pass-through ratio (out ≈ in), short dwell,
low balance retained, and no independent activity. These are the addresses worth naming in a
report, because they are the operational infrastructure of the laundering network rather than
its endpoints.

---

## 8. Path ranking (FR-48)

The graph shows everything; investigators need the three paths that matter. Paths from root to
each terminal node are ranked by **attributed value, with a modest multiplier for actionable
endpoints** (a service boundary, or funds that have not moved).

As implemented: `score = attributed_value x 1.5 if actionable else attributed_value`, then
fewer hops as a tie-break.

The multiplier is deliberately small. Ranking by terminal quality first — the obvious reading of
the original design — makes a 20,000 peel outrank a 900,000 main flow, which a test caught
immediately. Value has to dominate; actionability lifts a slightly smaller path above a larger
dead end, and no further.

The top three are surfaced as "key findings" and go into the report by default.

---

## 9. Complexity and performance

| Aspect | Bound |
|---|---|
| Time | O(edge_budget) node expansions; dominated by network I/O for uncached addresses |
| Space | O(nodes + edges), bounded by the edge budget |
| Network calls | One per newly discovered address, minus cache hits |
| Realistic wall clock | 30–90 s live (rate-limit bound); 2–10 s from fixture cache |

**The bottleneck is provider rate limits, not computation.** The mitigations that matter are
caching, request coalescing for hot addresses, and — critically — *not* expanding service
nodes, since those are exactly the high-degree addresses that would trigger the most requests.

---

## 10. Correctness properties the tests must hold (see [TESTING_STRATEGY.md](TESTING_STRATEGY.md))

1. **Conservation.** Attributed value out of a node never exceeds attributed value in.
2. **Determinism.** Identical input and parameters produce a bit-identical trace (NFR-14).
3. **Termination.** The algorithm halts on every input, including cyclic graphs.
4. **Cycle safety.** A → B → A does not loop and does not inflate taint.
5. **Completeness of accounting.** Original amount = Σ attributed at terminals + Σ pruned +
   Σ retained at non-terminal nodes. This invariant is the single best test of the engine, and
   it should be asserted after every trace, not only in tests.
