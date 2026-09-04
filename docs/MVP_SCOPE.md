# MVP Scope

**The rule:** the MVP must be buildable by a small team in a hackathon timeframe and must
demonstrate a genuine answer to PS26183. Anything that does not serve both is cut.

**The test to apply to every proposed feature:** *does this make the demo answer "which
exchange received the money" better, or does it just add surface area?*

---

## 1. Must have — the demo does not work without these

### Backend
- ☐ FastAPI application, async job queue, PostgreSQL, Redis, Docker Compose (NFR-11)
- ☐ JWT auth with RBAC and case isolation (NFR-08)
- ☐ Case CRUD and suspect-address intake (FR-01..07, FR-10..14)
- ☐ TRON adapter — native + TRC-20 retrieval, pagination, backoff, evidence capture
- ☐ Ethereum adapter — native + ERC-20 + internal transactions
- ☐ Normalization to the canonical `Transfer` model (FR-30..34)
- ☐ **Fixture cache and `LIVE_MODE` toggle** (FR-24) — the demo depends on this
- ☐ Tracing engine: BFS, haircut taint, depth, thresholds, fan-out cap, edge budget,
  service-boundary stopping, termination reasons (FR-40..48, FR-50)
- ☐ Graph construction with node metadata, paths, render cap (FR-90..93, FR-96)
- ☐ Pattern detectors: fan-out, fan-in, rapid transfer (FR-60..62, FR-66)
- ☐ **Curated label datasets committed to the repo** — OFAC list plus a hand-verified set of
  major TRON and Ethereum exchange hot wallets
- ☐ **Attribution engine with the three-tier model and the deposit-address funnel heuristic**
  (FR-70..76) — *this is the answer to the problem statement*
- ☐ Risk engine: weighted rules, itemised breakdown, bands, separate confidence (FR-80..86)
- ☐ Alerts for sanctioned and mixer contact (FR-100, FR-101)
- ☐ PDF report with evidence appendix and disclaimers (FR-110..113)
- ☐ Audit logging and evidence hashing (NFR-09, NFR-10)

### Frontend
- ☐ Login, dashboard with cases and alerts
- ☐ New case and address intake with live validation
- ☐ Analysis progress with streaming stage detail
- ☐ Investigation workspace: Overview, Graph, Transactions, Patterns, Attribution, Evidence
- ☐ **Interactive Cytoscape graph with tier-distinct node rendering**
- ☐ **Risk breakdown showing every signal**
- ☐ **Attribution cards in all three tier variants**
- ☐ Report generation and download
- ☐ Fixture-mode banner (NFR-15), truncation banner, data-completeness warnings

### Cross-cutting
- ☐ Unit tests on tracing, attribution, and risk (NFR-13)
- ☐ Golden-case end-to-end regression test
- ☐ No secrets in source; no default credentials (NFR-06)

**Together these deliver the full 13-stage pipeline on real data with honest attribution.**

---

## 2. Should have — build if the must-haves are complete and stable

- ☐ Backward tracing for victim enumeration (FR-49) — *high value, moderate cost; the
  strongest "should" on this list, because it turns one complaint into a campaign picture*
- ☐ Cross-case correlation alerts (FR-07, FR-100)
- ☐ Peel chain, dormancy-burst, and structuring detectors (FR-63..65)
- ☐ Betweenness centrality for chokepoint identification (FR-94)
- ☐ Deposit-address ML classifier (FR-73 via `ml/`)
- ☐ Investigator attribution override (FR-78)
- ☐ Timeline scrubber on the graph — *disproportionate demo value for the effort*
- ☐ LLM report narrative with structural safeguards (FR-115, FR-116)
- ☐ JSON and CSV export (FR-114)
- ☐ Provider failover (FR-26)
- ☐ USD valuation (FR-34)
- ☐ Integration-ready submission endpoint (FR-130)
- ☐ Case notes and finding pinning (FR-06)
- ☐ Alert acknowledgement (FR-102)
- ☐ TOTP MFA
- ☐ Playwright E2E suite

---

## 3. Nice to have — only if genuinely ahead of schedule

- ☐ Anomaly detection (Isolation Forest)
- ☐ Community detection on the trace subgraph (FR-95)
- ☐ Bulk address submission (FR-131)
- ☐ Dark mode
- ☐ Graph PNG export
- ☐ Analysis run comparison
- ☐ Saved trace parameter presets

---

## 4. Future / post-SIH — explicitly not now

- Bitcoin support (UTXO model, common-input clustering) — *the highest-value future addition*
- Additional EVM chains (BSC, Polygon, Arbitrum)
- Automated cross-chain bridge correlation
- Continuous address monitoring with alerting
- Self-hosted blockchain nodes
- Live NCRP / CFCFRMS / SAHYOG integration
- Campaign-level multi-case analysis
- Feedback loop from investigator overrides into the classifier
- Multi-tenancy across agencies
- Mobile interface

Full treatment: [FUTURE_SCOPE.md](FUTURE_SCOPE.md).

---

## 5. Explicitly out of scope — permanently

Not "later". These are design boundaries.

| Excluded | Why |
|---|---|
| Identity resolution | Requires KYC data. Tier C. Not obtainable, not attempted |
| Fraud/guilt determination | A judicial function, not a software output |
| Fund recovery or freezing | Requires legal authority and exchange cooperation |
| Privacy coins (Monero, Zcash shielded) | Not traceable by design |
| De-mixing | Mixers break the link cryptographically |
| Automated legal action | Every legal step is a human decision |
| Key custody or transaction signing | TraceFall is read-only against blockchains and holds no keys |
| Continuous surveillance absent a case | Purpose limitation ([PRIVACY_AND_COMPLIANCE.md §5](PRIVACY_AND_COMPLIANCE.md)) |

---

## 6. Is the MVP actually achievable?

An honest assessment, since an unbuildable MVP is worse than a smaller one.

**The genuinely hard parts:**

| Component | Difficulty | Note |
|---|---|---|
| Tracing engine | **High** | The correctness core. Haircut arithmetic, pruning, termination, and the accounting invariant all need care |
| Attribution engine | **High** | The product's central claim. Tier discipline must be right |
| Graph UI | Medium-high | Cytoscape is capable; making it *legible* is the work |
| Chain adapters | Medium | Well-documented APIs, but pagination and edge cases take longer than expected |
| Report generation | Medium | Layout work is always slower than estimated |
| Risk engine | **Low** | Weighted sum over computed features. Deliberately simple, and that is a feature |
| Everything else | Low–medium | Standard CRUD and web work |

**The two risks that could sink it, and their mitigations:**

1. **Label dataset quality.** If attribution returns `UNATTRIBUTED` everywhere, the demo has no
   answer. **Mitigation: hand-curate 50–100 verified major-exchange hot wallets in Phase 7 and
   commit them.** This is the single highest-leverage hour of work in the project.
2. **Demo-day network failure.** **Mitigation: `LIVE_MODE=false` is the default, and the
   offline path is tested with the network physically disconnected**
   ([DEPLOYMENT.md §5](DEPLOYMENT.md)).

**What to cut first if time runs short**, in order:
1. ML classifier — the deterministic heuristic already delivers the attribution
2. LLM narrative — templates produce a complete report
3. Backward tracing
4. Advanced pattern detectors (keep fan-out, fan-in, rapid transfer)
5. Betweenness centrality
6. Ethereum support — **TRON alone still demonstrates the full pipeline on the chain that
   matters most for Indian cases**

Cutting item 6 would be painful for the "multi-chain" story but would not compromise the answer
to PS26183. Knowing that in advance is what keeps the project from panicking in week three.

**What must never be cut:** the three-tier attribution model, the risk breakdown, evidence
capture, and the fixture cache. Each of those is load-bearing for the product's credibility.
