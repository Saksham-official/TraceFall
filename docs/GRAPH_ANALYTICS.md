# Graph Analytics

Implemented by `graph/`. Library: **NetworkX**, in-process, per investigation. Rationale for
not using a graph database: ADR-003.

---

## 1. The graph model

**Directed, weighted, multi-asset, time-aware.**

### Nodes — addresses

| Attribute | Source | Use |
|---|---|---|
| `address`, `chain` | canonical | identity |
| `depth` | trace | layout ordering |
| `taint_share` | trace | node size |
| `tainted_amount` | trace | the headline number |
| `entity_type` | attribution | node icon |
| `entity_name` | attribution | node label |
| `attribution_tier` | attribution | **border style** — solid `CONFIRMED`, dashed `PROBABLE`, none `UNATTRIBUTED` |
| `risk_score`, `risk_band` | risk | node colour |
| `balance`, `first_seen`, `last_seen`, `age_days` | profile | detail panel |
| `in_degree`, `out_degree` | profile | detail panel |
| `is_terminal`, `termination_reason` | trace | terminal marker |
| `is_root` | trace | emphasis |
| `is_contract` | chain | distinct shape |

The attribution tier being encoded as **border style rather than colour** is deliberate: colour
is already carrying risk band, and the tier distinction is too important to lose to
colour-blindness or a projector's colour rendering (NFR-18).

### Edges — aggregated value flows

One edge per `(from, to, asset)` pair, aggregating all transfers between them. Twenty transfers
from A to B become one edge with `transfer_count: 20` — this is what keeps the graph legible.

| Attribute | Use |
|---|---|
| `total_amount`, `tainted_amount` | edge thickness (log-scaled on tainted) |
| `transfer_count` | edge label when > 1 |
| `asset` | edge colour hue |
| `first_transfer_at`, `last_transfer_at` | timeline scrubbing |
| `tx_hashes` | **the drill-down path back to raw evidence** |

**Directionality is not decoration.** Fund flow direction is the entire semantic content of
this graph; arrows are always rendered, and an undirected view is never offered.

### Why aggregate edges

An unaggregated graph of a scam wallet with 3,000 transfers is 3,000 parallel edges between a
few dozen nodes — unreadable and useless. Aggregation converts it into a legible flow diagram
while `tx_hashes` preserves the path to every individual transfer.

---

## 2. Algorithms — and the test each had to pass

Each technique below earns its place by answering a question an investigator actually asks.
Techniques that do not are listed in §4.

### BFS traversal — "where did the money go?"
The tracing engine itself ([WALLET_TRACING.md](WALLET_TRACING.md)). Breadth-first is correct
here because investigative relevance decays with hop distance, so exploring nearer hops first
matches how value dilutes and how attention should be spent.

### Highest-value path — "what is the main flow?"
Modified shortest-path with `weight = -log(tainted_fraction)`, so the "shortest" path
maximises the product of retained taint. This is the path that carried most of the victim's
money, which is the one that goes in the report headline.

**Complexity:** O(E log V), trivial at our scale.

### Shortest path between two addresses — "how are these connected?"
Standard BFS shortest path, used when an investigator selects two nodes and asks for the
connection. Directly useful when a second case surfaces a related address.

### Betweenness centrality — "where is the chokepoint?" (FR-94)

**The highest-value derived measure in the system, and the least obvious.**

Betweenness identifies nodes through which the most traced value must pass. In a laundering
network these are the **consolidation points** — the mule wallets the operation depends on. A
scammer can generate unlimited fresh addresses, but the operation still funnels through a small
number of collection points, and those are the addresses worth naming in a report and
correlating across cases.

Computed on the tainted subgraph only, weighted by attributed value. At ≤ 5,000 edges the exact
computation is fast; approximate betweenness is available if a trace is unusually large.

### Weakly connected components — "is this one operation or several?" (FR-95)
Multiple components in a single trace usually indicate distinct laundering paths that never
reconverge — useful for structuring a report into sections.

### Degree analysis — "which addresses are hubs?"
In-degree and out-degree directly feed the fan-in / fan-out pattern detectors and the
deposit-address heuristic. Cheap and load-bearing.

### Temporal sequencing — "what happened, in what order?"
Not a graph algorithm but a graph *view*: edges ordered by `first_transfer_at`, scrubable in
the UI. Investigators reason in timelines, and watching value propagate hop by hop is both the
most useful analytical view and the most compelling thing to show on stage.

### Cycle detection — "did funds return?"
Simple cycle detection over the trace subgraph. Funds returning to an earlier address indicates
either wash activity or a self-transfer obfuscation attempt. Low cost, occasionally decisive.

---

## 3. Community detection — a qualified yes (FR-95, `NICE TO HAVE`)

Louvain modularity over the trace subgraph, to group addresses into apparent clusters.

**Genuine value:** when a trace fans into 200 addresses, community structure can separate
"these 40 went to one exchange" from "these 60 form a mixing structure", which makes a large
graph comprehensible.

**Serious caveat, and the reason this is `NICE TO HAVE` rather than `SHOULD`:** a graph
community is **not** a set of addresses controlled by one person. Modularity finds
densely-connected regions, which arise from shared services, common counterparties, and
timing coincidence as readily as from common control. If the UI labels a community "Entity
Cluster 3", investigators will read it as common ownership, and that inference is not
supported.

**Therefore:** if built, communities are labelled *"connected flow group"*, are visual grouping
only, never feed attribution, and never feed the risk score.

---

## 4. Techniques considered and rejected

| Technique | Why not |
|---|---|
| PageRank / eigenvector centrality | Optimised for influence in a link graph. On a fund-flow graph it mostly rediscovers high-volume service addresses — which we already identify better, with evidence, via attribution. Impressive-sounding, adds nothing. |
| Graph neural networks | No adequate labelled data; unexplainable output; tends to learn proximity-to-known-bad, which the trace already establishes with evidence attached. See [AI_ML_STRATEGY.md](AI_ML_STRATEGY.md) §2. |
| Maximum flow / min cut | Solves a capacity problem. Our edges carry realised historical value, not capacity. Mathematically inapplicable, not merely unhelpful. |
| Graph embeddings (node2vec etc.) | Produces vectors nobody can interpret, for a downstream task we do not have. |
| Full transitive closure | Combinatorial explosion, no investigative question behind it. |
| Link prediction | Predicting transactions that have not happened is not evidence, and would be read as one. |

Rejecting these is a deliberate position, and being able to explain *why* PageRank is wrong for
this graph is more convincing than shipping it.

---

## 5. Rendering constraints (FR-96)

**Default cap: 500 nodes.** Beyond that, human comprehension fails before the browser does.

**Selection when capped:** highest tainted value first, always including the root, all terminal
nodes, and all attributed service nodes. Capping must never hide the answer.

**`truncated: true` is always returned and always displayed.** Silently showing an investigator
half of a fund flow is unacceptable.

**Progressive expansion.** A capped node renders with a "+N more" affordance that fetches its
subtree on demand — which keeps the initial view readable while making everything reachable.

**Frontend library:** Cytoscape.js. Chosen for mature directed-graph layouts, good performance
at this scale, built-in pan/zoom/select, and reasonable accessibility hooks. Layout is
hierarchical (breadth-first by depth) rather than force-directed by default: fund flow is
inherently layered by hop, force-directed layouts obscure that structure, and hop depth is the
single most important thing to read off the picture.

---

## 6. Performance

| Operation | Scale | Cost |
|---|---|---|
| Build graph from trace | ≤ 5,000 edges | < 100 ms |
| Shortest / highest-value path | ≤ 5,000 edges | < 50 ms |
| Betweenness (exact) | ≤ 5,000 edges | < 2 s |
| Components | ≤ 5,000 edges | < 50 ms |
| Louvain | ≤ 5,000 edges | < 1 s |
| Serialise capped graph | 500 nodes | < 50 ms |

All negligible against the 30–90 second network-bound retrieval stage. **Graph computation is
not a bottleneck and will not become one at MVP scale** — which is the whole argument for
in-memory NetworkX over a graph database (ADR-003).
