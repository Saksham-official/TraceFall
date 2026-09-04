# Data Sources

Every external dependency, what it gives us, what it costs, and where it can break us.

---

## 1. Public blockchain data — primary providers

### TronGrid (TRON) — primary

**Provides:** account info, TRX transfers, TRC-20 transfers, transaction detail, block data.
**Access:** REST, free API key. **Rate limit:** generous free tier; adequate for the MVP.
**Reliability:** high — operated by the TRON Foundation.
**Terms:** standard API terms; transaction data use is permitted.
**MVP suitability:** ✅ **Primary source for the MVP's primary chain.**

**Why it matters most:** TRON carries the USDT-TRC20 flows that dominate Indian crypto fraud
([BLOCKCHAIN_ANALYTICS.md §1](BLOCKCHAIN_ANALYTICS.md)). TronGrid's free tier being workable is
one of the load-bearing assumptions of this project.

### TronScan API (TRON) — failover

**Provides:** similar coverage, plus some address labels for well-known entities.
**Access:** REST, free tier. **Reliability:** high, but documentation is thinner.
**Caution:** label data may carry usage restrictions — **verify before ingesting labels**
(open question OQ-07). Transaction data via the documented API is fine.
**MVP suitability:** ✅ as transaction failover; ⚠️ labels pending licence confirmation.

### Etherscan API (Ethereum) — primary

**Provides:** normal, internal, and ERC-20 token transactions; balances; contract detail;
some address labels via the website.
**Access:** REST, free API key. **Rate limit:** ~5 req/s, 100,000/day free.
**Reliability:** very high; the de-facto standard.
**Terms — important:** the API is usable under its terms, but **scraping the website's label
database is prohibited.** TraceFall uses the API for transaction data and does **not** scrape
labels.
**MVP suitability:** ✅ transactions. ❌ labels.

### Blockscout (Ethereum) — failover

**Provides:** comparable transaction data; open-source and self-hostable.
**Access:** free public instances, or self-hosted.
**Reliability:** medium on public instances; high self-hosted.
**MVP suitability:** ✅ as failover. Strategically valuable as the escape hatch if Etherscan
limits become binding.

### Rate-limit reality check

The Ethereum free tier at ~5 req/s is the tighter constraint. A 5-hop trace touching 200 new
addresses needs ~400 requests (native + token per address) — roughly 80 seconds at the limit,
before any retries. **This is the arithmetic behind NFR-01's 120-second target**, and behind
the mitigations that matter: caching, request coalescing for hot addresses, and not expanding
service nodes ([BLOCKCHAIN_ANALYTICS.md §3](BLOCKCHAIN_ANALYTICS.md)).

---

## 2. Address labels and entity data

The hardest dependency in the project, and the one most likely to disappoint.

### OFAC SDN cryptocurrency addresses

**Provides:** sanctioned addresses across multiple chains, published by the US Treasury.
**Access:** free, published, machine-readable. **Reliability:** authoritative for its purpose.
**Licence:** US government publication; free to use.
**MVP suitability:** ✅ **Ingest first.** Small, authoritative, unambiguous, and directly feeds
the highest-weight risk signal.

### Community label repositories (open-source)

**Provides:** exchange hot wallets, mixers, bridges, and known service addresses, maintained as
open datasets on public repositories.
**Access:** free, typically permissively licensed. **Reliability:** medium — community
maintained, variably current.
**Caution:** licence and freshness vary by repository. Each must be assessed individually
before ingestion, and its `label_source` row records the licence and dataset date
([DATABASE_DESIGN.md §4](DATABASE_DESIGN.md)).
**MVP suitability:** ✅ with per-dataset licence verification (OQ-07).

**This is where the `CONFIRMED` tier's coverage actually comes from**, and it is the single
biggest determinant of how well the system performs. Curating a small, high-quality set of
major-exchange hot wallets for TRON and Ethereum is a **Phase 7 task worth doing carefully by
hand**, not a scripted bulk import. Fifty verified addresses beat five thousand unverified ones,
because one wrong `CONFIRMED` label sends a legal request to the wrong institution.

### Self-derived deposit-address labels

**Provides:** deposit addresses inferred by our own funnel heuristic.
**Reliability:** Tier B by construction — always `PROBABLE`, never `CONFIRMED`.
**MVP suitability:** ✅ this is the product's core inference
([VASP_IDENTIFICATION.md](VASP_IDENTIFICATION.md)).

### Commercial intelligence (Chainalysis, TRM Labs, Elliptic)

**Provides:** comprehensive, current, professionally curated attribution.
**Cost:** enterprise licensing, far outside a hackathon budget.
**MVP suitability:** ❌ **Not used, and their absence is the honest reason our attribution
coverage is narrower than theirs.** Stated plainly in [LIMITATIONS.md](LIMITATIONS.md).

---

## 3. Price data

### CoinGecko (or equivalent) — historical prices

**Provides:** historical USD/INR prices for major assets.
**Access:** free tier with a low rate limit.
**MVP suitability:** ✅ `SHOULD`. Used only for approximate valuation, always marked
approximate, and **never** for anything analytical. A missing price yields `null`, never a
guess (FR-34).

Note that USDT's near-dollar peg makes valuation nearly trivial for the dominant asset in scope
— which is a convenient side effect of the chain choice.

---

## 4. Synthetic and demo data

### Fixture cache — real chain data, frozen

**What:** real provider responses for a curated set of real fraud-linked addresses, captured
once and committed to the repository.
**Purpose:** deterministic offline demo, reproducible tests, no rate limits, no venue-network
dependency.
**Rules:** always displayed with a visible "cached snapshot — captured <date>" banner (NFR-15);
capture is a documented script.
**MVP suitability:** ✅ **Required.** This is the demo path.

**Sourcing the addresses.** Publicly documented fraud-linked addresses are available from OFAC
designations, published incident reports, and open research writeups. Selecting 3–5 with
genuinely interesting fund flows — multi-hop, with an identifiable exchange endpoint — is a
Phase 15 task and materially determines how good the demo is.

### Generated synthetic data

**What:** programmatically generated laundering topologies.
**Purpose:** classifier training augmentation and pattern-detector tests only.
**Rules:** flagged at row level, never in a real case, never in the demo, metrics reported
separately ([AI_ML_STRATEGY.md §6](AI_ML_STRATEGY.md)).
**MVP suitability:** ✅ for tests and training; ❌ for demonstration.

---

## 5. Potential government integrations — clearly hypothetical

| System | What it could provide | Status |
|---|---|---|
| **NCRP** | Complaint data with reported addresses; automated case creation | **No access.** We build an integration-ready API surface (FR-130) and claim nothing more |
| **CFCFRMS** | The freeze-request dispatch mechanism, for a crypto equivalent | **No access.** The conceptual model TraceFall is designed to serve |
| **SAHYOG** | Structured request dispatch to platforms | **No access.** Cited as an architectural precedent only |
| **FIU-IND** | Registered VASP list and contact points | Registration status is public in part; used where available |
| **Indian VASP KYC data** | The identity behind a deposit address | **Requires legal process.** Tier C — permanently outside this system |

**Design consequence:** every one of these is optional. The system is fully functional without
any government data, which is the only responsible way to build it given that we have none.

---

## 6. Dependency risk assessment

| Dependency | Criticality | If it fails | Mitigation |
|---|---|---|---|
| TronGrid | **Critical** | Primary chain unavailable | TronScan failover; fixture cache; self-hosted node (future) |
| Etherscan | High | Ethereum degraded | Blockscout failover; fixture cache |
| Etherscan rate limit | **High** | Slow traces, NFR-01 missed | Caching, coalescing, service-boundary stopping, paid tier |
| Label datasets | **Critical to value** | Attribution collapses to `UNATTRIBUTED` | Curated internal set committed to repo; self-derived deposit labels |
| Label dataset licences | Medium | A dataset must be dropped | Verify before ingestion (OQ-07); design assumes a small curated set |
| Price API | Low | No USD values | `null`, marked; nothing analytical depends on it |
| LLM API | Low | No AI narrative | Template fallback (FR-116) |

### The three that could actually sink the project

1. **Label dataset quality.** Attribution is the product. Poor labels mean `UNATTRIBUTED`
   everywhere, and PS26183 goes unanswered. **Mitigation: hand-curate a small, verified set of
   major TRON and Ethereum exchange hot wallets in Phase 7 and commit it to the repository.**
   This is the highest-leverage hour of work in the whole project.
2. **Rate limits during the live demo.** **Mitigation: the fixture cache. The demo runs with
   `LIVE_MODE=false` by default**, and live mode is shown only if the venue network cooperates.
3. **Provider terms of service on label data.** **Mitigation: use APIs for transactions only;
   source labels solely from datasets with confirmed permissive licences; never scrape.**

---

## 7. What we do not use, and why

| Not used | Why |
|---|---|
| Running our own full node | Days of sync time and hundreds of GB. Correct at scale, wrong for a hackathon. In [FUTURE_SCOPE.md](FUTURE_SCOPE.md) |
| Scraped explorer label data | Prohibited by terms. Non-negotiable |
| Paid intelligence APIs | Cost |
| Social media / OSINT enrichment | Out of scope; we analyse transactions, not people ([PRIVACY_AND_COMPLIANCE.md §3](PRIVACY_AND_COMPLIANCE.md)) |
| Darknet market data | Not accessible, not needed |
| Any dataset with unclear licensing | Not worth the risk |
