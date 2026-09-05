# Frontend Specification — Investigator Dashboard

Stack: **React 18 + TypeScript + Vite**, TanStack Query for server state, Tailwind CSS,
Cytoscape.js for the graph, Recharts for timelines.

---

## 1. Design principles

1. **The investigator is not a blockchain expert.** Every technical term either goes or comes
   with an inline explanation. "Peel chain" appears as "funds split repeatedly, moving a large
   amount forward while shaving off small amounts".
2. **Evidence is always one click away.** Every number, score, and claim expands to show what
   produced it. There is no assertion in this UI that cannot be interrogated.
3. **Attribution tier is visually unmistakable.** `CONFIRMED`, `PROBABLE`, and `UNATTRIBUTED`
   have distinct, non-colour-dependent treatments everywhere they appear. This is the single
   most important UI rule in the product.
4. **Uncertainty is shown, not hidden.** Partial data, low confidence, pruned branches, and
   truncated graphs are surfaced, not swept under a clean interface.
5. **Every screen answers "what do I do next?"**
6. **Dense but calm.** Investigators want information density; a dashboard with six giant
   gradient cards wastes the screen they need.

---

## 2. Design system

**Palette.** Neutral slate base. Risk bands: `LOW` slate, `MEDIUM` amber, `HIGH` orange,
`CRITICAL` red. **Band text always accompanies the colour** — never colour alone (NFR-18).

**Attribution tier encoding** — consistent across graph, tables, panels, and PDF:

| Tier | Badge | Border | Icon |
|---|---|---|---|
| `CONFIRMED` | solid filled badge, "Confirmed" | solid | shield-check |
| `PROBABLE` | outlined badge, "Likely — 87%" | **dashed** | question-diamond |
| `UNATTRIBUTED` | muted grey, "Unattributed" | none | dash |

**Token display.** A token symbol is never shown alone. Symbols are not identities — real
captured data contains a `USDTT` token beside genuine USDT — so every asset is rendered with
its contract address available, and a token whose symbol resembles a well-known one is marked.

**Typography.** System sans for UI; monospace for addresses and hashes, always with a
one-click copy control. Addresses are truncated middle-out (`TXn8kL…gH5jK2m`) with the full
value on hover and on copy.

**Density.** Compact tables, 8px spacing scale, no decorative whitespace in analytical views.

**Dark mode.** Supported, because investigators work at night and demo projectors vary
wildly. Both themes are defined explicitly; neither inherits from the host.

---

## 3. Screen 1 — Dashboard

The landing screen after login. Answers "what needs my attention?"

```
┌────────────────────────────────────────────────────────────────┐
│ TraceFall            [search address / case ref]      RK ▾     │
├────────────────────────────────────────────────────────────────┤
│  Open cases 24   Analysing 3   Critical 5   Traced ₹4.2 Cr      │
├──────────────────────────────────┬─────────────────────────────┤
│  RECENT CASES                    │  ALERTS                     │
│  ──────────────────────────────  │  ─────────────────────────  │
│  TF-2026-0142  ● CRITICAL  84    │  ⚠ Sanctioned address       │
│  USDT investment fraud           │    reached — TF-2026-0142   │
│  TRON · ₹45,00,000 · 2h ago      │    2h ago                   │
│                                  │                             │
│  TF-2026-0141  ● HIGH      67    │  ⚠ Address also in          │
│  Task scam                       │    TF-2026-0098             │
│  TRON · ₹12,00,000 · 5h ago      │    5h ago                   │
│                                  │                             │
│  TF-2026-0140  ○ analysing  …    │  ⚠ Mixer contact detected   │
│  ETH · running 45s               │    TF-2026-0139 · 1d ago    │
├──────────────────────────────────┴─────────────────────────────┤
│  [ + New Case ]        [ Quick Trace — analyse without a case ] │
└────────────────────────────────────────────────────────────────┘
```

**Quick Trace** is the demo path and the impatient-investigator path: paste an address, get a
result, decide later whether it deserves a case. It creates a provisional case behind the
scenes so nothing escapes the audit trail.

**Global search** accepts a case number, an NCRP reference, or a raw address — pasting an
address that already exists anywhere in the system jumps straight to it.

---

## 4. Screen 2 — Investigation workspace

Where the work happens. Persistent header, tabbed body, persistent detail rail.

```
┌────────────────────────────────────────────────────────────────────┐
│ ← TF-2026-0142 · USDT investment fraud        [Report] [Re-analyse]│
│ TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m  TRON  [copy] [explorer ↗]      │
│ ┌────────────┬────────────┬────────────┬────────────┐              │
│ │ RISK    84 │ TRACED     │ TERMINALS  │ EXCHANGES  │              │
│ │ CRITICAL   │ 40,000     │ 7          │ 2 found    │              │
│ │ conf. 0.78 │ USDT       │ 3 services │ 1 confirmed│              │
│ │ [why?]     │ 62% traced │            │ 1 likely   │              │
│ └────────────┴────────────┴────────────┴────────────┘              │
├────────────────────────────────────────────────────────────────────┤
│ [Overview] [Graph] [Transactions] [Patterns] [Attribution] [Evidence]│
├──────────────────────────────────────────────┬─────────────────────┤
│                                              │  SELECTED NODE      │
│              (tab content)                   │  ─────────────────  │
│                                              │  TQn9…FFbc          │
│                                              │  ▣ Confirmed        │
│                                              │  Binance · Exchange │
│                                              │  ...                │
└──────────────────────────────────────────────┴─────────────────────┘
```

The four header cards are chosen so an investigator gets the whole answer without scrolling:
how bad, how much, where it ended, and — the PS26183 question — which exchanges were found.
`[why?]` opens the risk breakdown.

### Tab: Overview

The narrative answer, in plain language, before any graph:

> **What happened to the money**
> Between 14 and 16 August 2026, 40,000 USDT sent to this address was moved through 4
> intermediary wallets and reached two exchange deposit addresses.
>
> **24,800 USDT (62%)** reached a **confirmed Binance deposit address** on 15 Aug, 11:42 IST.
> **9,200 USDT (23%)** reached an address **likely associated with Bybit** (87% confidence).
> **6,000 USDT (15%)** remains in wallets that have not moved.
>
> **Recommended next step:** a KYC request to Binance naming address `TQn9…FFbc` and
> transaction `a91f…` may identify the receiving account.

Below it: key findings (top 3 paths), pattern summary, and the analysis provenance block —
data sources, retrieval timestamps, and whether this was live or a cached snapshot.

### Tab: Graph

The centrepiece.

- Hierarchical left-to-right layout by hop depth. Root pinned left.
- Node size ∝ tainted value; colour = risk band; **border style = attribution tier**; shape
  distinguishes contracts; terminal nodes carry a stop marker with their termination reason.
- Edge thickness ∝ tainted value (log-scaled); hue by asset; hover shows amount, count, dates.
- **Timeline scrubber** below the graph: dragging replays the flow chronologically, edges
  appearing as they occurred. This is the most compelling thirty seconds of the demo and is
  also genuinely how investigators reason.
- Controls: depth slider (re-queries), asset filter, minimum-value filter, "highlight path to
  selected", fit-to-view, export PNG.
- Capped-graph banner when `truncated` is true, with a count and an expand action.
- Click a node → detail rail. Double-click → expand its subtree.

**Accessibility.** Full keyboard navigation between nodes; a screen-reader-accessible table
view of the same data is available from a toggle — a graph that only works with a mouse
excludes users and fails on a demo laptop with an unfamiliar trackpad.

### Tab: Transactions

Dense, sortable, filterable table: time · from · to · asset · amount · USD · status · hash.
Filters for address, asset, direction, amount range, date range, status. Row expands to full
detail; hash links to the public explorer for independent verification. Failed transfers shown
with a distinct marker, never hidden. CSV export.

### Tab: Patterns

One card per finding:

> **Fund splitting detected** · HIGH
> This wallet distributed funds to **47 different addresses within 6 minutes** on 15 Aug.
> Rapid distribution to many wallets is commonly used to break the trail.
> **Triggering transactions:** `a91f…`, `b23c…`, `c45d…` *(+44)*
> **Note:** this pattern also occurs legitimately — payroll contracts, airdrops, and exchange
> batch withdrawals produce the same shape.

The "Note" line is mandatory on every pattern card (FR-66). It is what makes the other cards
believable.

### Tab: Attribution

The PS26183 answer surface. One card per attributed address, grouped by tier, `CONFIRMED`
first. Card layouts follow [VASP_IDENTIFICATION.md §8](VASP_IDENTIFICATION.md) exactly.

Each card carries an action block: for an exchange, what an investigator would include in a
request to them (address, transaction hashes, timestamps, amounts) with a copy-all control.
This is the feature that turns analysis into action, and it is worth more than another chart.

Investigator override lives here, with a required justification field. The machine finding
remains visible after an override — both are shown, side by side.

### Tab: Evidence

The chain of custody, made visible: every API response retrieved, with provider, endpoint,
HTTP status, retrieval timestamp, SHA-256, byte size, and a live/fixture marker. Downloadable.

Nobody will use this often. Its presence is what makes the rest of the tool credible to anyone
who asks how the data was obtained.

### Detail rail (persistent)

For a selected address: identifier and copy control · attribution card · risk score with
breakdown · profile statistics · label matches with sources and dates · balance and activity ·
`data_completeness` warning if the history was truncated · actions (expand, set as root,
add to case, view on explorer).

---

## 5. Screen 3 — New case / address intake

Two steps, deliberately short.

**Step 1 — case:** title, NCRP reference, FIR reference, description, reported loss (INR),
incident date, priority.

**Step 2 — suspect address:**

```
Address *   [TXn8kL2mQpR4vY7wZ3aB6cD9eF1gH5jK2m          ]  ✓ Valid TRON address

  ⓘ These two fields substantially improve the trace
Amount victim sent   [40000        ] [USDT ▾]
Date and time sent   [14 Aug 2026] [09:32]

▸ Advanced (depth 5, window 90 days, threshold 1%)

                                          [ Start analysis ]
```

Validation is live and specific: a Bitcoin address returns *"This looks like a Bitcoin address.
TraceFall currently supports TRON and Ethereum."* A bad EIP-55 checksum returns *"This
Ethereum address has an invalid checksum — it may have been mistyped."*

If the address already exists in another case, a banner appears **before** analysis starts.

---

## 6. Screen 4 — Analysis progress

Not a spinner. A live stage list with real detail, because 30–120 seconds of an opaque loader
loses an audience and an investigator's trust equally:

```
Analysing TXn8kL2m…                                       elapsed 0:47

✓ Retrieving blockchain data      8.4s   412 transfers · 2 providers
✓ Normalizing transactions        0.2s   412 transfers
✓ Enriching addresses             0.6s   38 addresses profiled
◐ Tracing fund flows                     depth 3 of 5 · 214 nodes
○ Building graph
○ Detecting patterns
○ Attributing entities
○ Scoring risk

                          [ Cancel ]     Partial results available →
```

Partial results are viewable as soon as tracing produces anything.

---

## 7. Screen 5 — Report

Preview of the generated document with the section list, an include/exclude toggle per
section, pinned findings surfaced first, narrative-source selector (template / AI-assisted),
and Generate → download.

After generation: report ID, SHA-256, generation timestamp, and the download link. Previous
reports for the case are listed and remain downloadable — a superseded report is history, not
garbage.

---

## 8. Component inventory

`AddressChip` (truncate + copy + explorer link + tier badge) · `AttributionCard` (the three
tier variants) · `RiskBadge` (score + band + text label) · `RiskBreakdown` (signal table) ·
`AmountDisplay` (raw/display/USD, never a bare number) · `TransactionTable` ·
`FlowGraph` (Cytoscape wrapper) · `TimelineScrubber` · `PatternCard` · `StageProgress` ·
`EvidenceTable` · `DataCompletenessWarning` · `TruncationBanner` · `EmptyState` ·
`ErrorBoundary`.

`AddressChip` and `AttributionCard` are the two components that carry the product's integrity
rules. They are worth building carefully and worth testing.

---

## 9. States that must be designed, not improvised

| State | Treatment |
|---|---|
| No cases yet | Empty state explaining the workflow with a "New case" action |
| Analysis running | Stage progress (§6), partial results reachable |
| Analysis partial | Amber banner naming which stages degraded and why |
| Analysis failed | Plain-language reason, retry action, evidence retained and viewable |
| Address has no activity | Explicit finding: *"This address exists but has never transacted."* — with the note that this may mean a decoy or a mistyped address |
| Trace has one node | *"Funds have not moved from this address."* — framed as good news |
| Graph truncated | Persistent banner with count and expand |
| Data incomplete | Warning on every affected number, not just once at the top |
| No attribution found | Honest empty state, not a blank panel |
| Provider unavailable | Banner naming the provider, with cached-data notice |
| Fixture mode | Persistent, unmissable *"Cached snapshot — captured <date>"* banner (NFR-15) |

**The fixture-mode banner is non-negotiable.** Presenting cached data as live during a demo,
even by omission, is the kind of thing that ends badly under questioning.

---

## 10. Demo considerations

The three moments that carry the presentation:

1. **The timeline scrubber replaying the fund flow.** Visual, immediately legible, and real.
2. **The attribution card resolving to a named exchange with its evidence list.** This is the
   problem statement being answered on screen.
3. **An `UNATTRIBUTED` card sitting honestly next to it.** Counter-intuitive, and the thing
   that persuades a knowledgeable judge that the other claims are trustworthy.

Everything must work at 1366×768 on an unfamiliar projector, in both light and dark mode, with
`LIVE_MODE=false`. That constraint is a design input, not an afterthought.
