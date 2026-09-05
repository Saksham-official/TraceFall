# Open Questions

Decisions that must be made **before or during** the phase that depends on them, and that
Phase 0 deliberately did not settle — because settling them requires information we do not have
yet (a measurement, a licence check, a team-size answer), and locking them prematurely would be
guessing dressed as planning.

**Process:** resolve → record as an ADR in [DECISIONS.md](DECISIONS.md) → then implement.
Do not implement a resolution that has not been written down.

**Do not resolve these now.** They are listed here so nobody starts a phase unaware of them.

---

## Blocking Phase 3 — Ingestion

### OQ-01 · What are the actual free-tier rate limits, measured?
**Answered 2026-09-05 by measurement** —
[research/OQ-01-provider-rate-limits.md](research/OQ-01-provider-rate-limits.md).

**NFR-01 is not achievable as originally specified.** TronGrid without a key sustains
**0.5 req/s per RPC method** with no burst tolerance; a 200-address cold trace takes ~400 s.
120 s buys about 60 uncached addresses. Acted on: rates corrected, rate-limiting rebucketed
per method, backoff given a throttle floor (TronGrid sends no `Retry-After`), trace depth
5 to 3 and fan-out 20 to 8, a new `trace_address_budget` of 60, and cache TTL 1h to 24h —
the highest-leverage change, since a closed block range never changes.

**The remaining lever is unquantified:** TronGrid publishes no numbers for authenticated
access. Getting a free API key and re-measuring is the one thing that could restore the
original target.
**Why it matters.** NFR-01 (under 120 s) is derived from *published* limits. Published limits
and enforced limits differ, and the whole performance target rests on this arithmetic
([DATA_SOURCES.md §1](DATA_SOURCES.md)).
**Resolve by:** writing a throwaway script that hammers each provider and records the real
sustained rate, before building anything on top of it.
**If the answer is bad:** raise the cache TTL, lower the default depth, or make TRON-only the
default demo path.

### OQ-02 · Does Etherscan's free tier expose internal transactions adequately?
**Answered 2026-09-05: the question turned out to be the wrong one.** Etherscan's free tier
*documents* `txlistinternal` as available, but it now rejects keyless requests entirely, so it
could not be measured. **Blockscout is primary instead** — no key, no throttling observed,
identical coverage.

The finding that matters is why internal transactions are non-negotiable: at the Ronin
exploiter address, **173,600 ETH arrived in a single internal transaction** while `txlist`
shows only 8,667.91 ETH inbound. The same hash appears in `txlist` with the direction reversed
and `value: "0"`. Normal-transaction-only tracing misses **95.2% of inbound value and gets the
largest edge backwards** — a confident, wrong answer.

**Original framing:**
**Why it matters.** Internal transactions are where contract-mediated value actually moves.
Missing them produces a trace that looks complete and is not — the worst kind of wrong.
**Resolve by:** testing against a known address with internal transfers.
**Fallback:** Blockscout, which exposes them differently.

### OQ-03 · Fixture cache in git, or Git LFS?
**Answered 2026-09-05: plain git, no LFS.** Measured 546 TRC-20 transfers = 194,614 B raw,
51,270 B gzipped (3.8:1, ~356 B/record). Native transactions cost 1,614 B/record — 4.5x worse
for the asset class that usually is not the fraud, so capture token transfers preferentially.
Projected 10-50 MB raw for 3-5 demo cases.

Fixtures stay **readable indented JSON** for now: they are evidence, and being able to diff them
is worth more than the 66% gzip saving at today's 64 KB. Revisit in Phase 15 if the captured set
lands above ~20 MB.

**Original framing:**
**Why it matters.** Real provider responses for 3–5 addresses across several hops could be tens
of megabytes. Committing that directly bloats every clone; LFS adds a setup step that can fail
on an unfamiliar machine — on demo day.
**Options.** Direct commit (simple, heavy) · Git LFS (clean, fragile) · commit compressed
fixtures and decompress at startup (probably the right answer).
**Resolve by:** capturing one address's fixtures and measuring.

### OQ-04 · Evidence storage: filesystem or object storage, and what retention default?
**Why it matters.** [DATA_ARCHITECTURE.md §2](DATA_ARCHITECTURE.md) specifies files on disk with
metadata rows. Fine for a demo. The retention default in
[PRIVACY_AND_COMPLIANCE.md §4](PRIVACY_AND_COMPLIANCE.md) (case + 3 years) is a **placeholder**,
not a researched figure.
**Resolve by:** filesystem for the MVP is almost certainly correct; the retention default needs
someone to check what Indian investigation record-retention practice actually requires, and to
say so rather than inventing a number.

---

## Blocking Phase 5 — Tracing

### OQ-05 · Anchor-matching tolerances
**Why it matters.** [WALLET_TRACING.md §2](WALLET_TRACING.md) proposes matching the victim's
transaction within **±24 hours and ±2%**. Both numbers are reasoned guesses. Too tight and real
victims' transactions are missed (they misremember times, and fees change amounts); too loose
and we anchor to the wrong transaction, which silently corrupts the entire trace.
**Resolve by:** testing against real fixture data with known victim transfers. Consider
returning ranked candidates whenever more than one matches, rather than tuning toward a single
answer.

### OQ-06 · Are the default thresholds right for real Indian case sizes?
Depth 5, taint threshold 1%, fan-out cap 20, 90-day window. Chosen for a sensible balance of
completeness and runtime. **Unvalidated against real cases.**
**Resolve by:** running traces on the demo addresses in Phase 15 and checking whether the
defaults reach the exchange endpoints or stop short. Adjust once, with the reasoning recorded.

---

## Blocking Phase 7 — Attribution *(highest-risk cluster)*

### OQ-07 · Which label datasets have licences that actually permit our use? — **ANSWERED**
**Fully answered 2026-09-05.** TronScan's terms were finally read (a real browser cleared the
Cloudflare challenge that had returned 403 to every automated attempt): **§6.1 and §8 rule
TronScan out entirely** — its label data is proprietary Company Materials licensed for internal
use only, with distribution, public display and derivative use all excluded. Details and the
quoted clauses are in [research/OQ-08-tron-label-coverage.md §3](research/OQ-08-tron-label-coverage.md).
The remaining permitted sources are OFAC (ingested), exchanges' own published disclosures, and
our own TronGrid observation. **ADR-018 still needs a signature** before curation begins.
**Partially answered 2026-09-05** — see
[research/OQ-08-tron-label-coverage.md](research/OQ-08-tron-label-coverage.md). OFAC via the
`0xB10C` repository is MIT and usable. Several candidates are ruled out. **One answer is still
missing: TronScan's terms of service could not be retrieved** (the page is a client-side route
and the host returns 403 to automated fetches). Someone must open it in a browser before we
rely on TronScan labels.
**Why it matters.** [DATA_SOURCES.md §2](DATA_SOURCES.md) names candidate sources but explicitly
does **not** confirm their licences. Several block explorers prohibit bulk use of their label
data. Ingesting a dataset we are not permitted to use is both a legal problem and an
embarrassment in a Ministry of Home Affairs problem statement.
**Resolve by:** reading each dataset's licence individually and recording it in its
`label_sources` row. **No dataset is ingested until its licence is confirmed and written down.**
*Enforced in code 2026-09-05:* a label dataset with no `licence` field fails to parse, so an
unlicensed dataset cannot reach the database. OFAC is ingested (405 addresses). **ADR-018 is
drafted and awaiting a named signer**, and TronScan's terms still need reading in a browser;
both gate the exchange label set.

### OQ-08 · Is there adequate public label coverage for **TRON** exchange hot wallets?
**Answered 2026-09-05: yes, by curation.** Full findings in
[research/OQ-08-tron-label-coverage.md](research/OQ-08-tron-label-coverage.md). Coverage is
thin relative to Ethereum but sufficient, and **ADR-001 stands**. Three things carry forward
into Phase 7: base58check validation on ingest is mandatory (a leading public dataset contains
invalid addresses); hot and cold wallets must be separated by observed behaviour rather than
trusted from a label; and the compiled dataset that has the best coverage is licensed in a way
that blocks ingestion, so labels must be re-derived from independent observation. That last
point is a legal judgement that needs a named signer in an ADR.

**Original framing, retained for context:** Public labelling for Ethereum is good. For TRON —
our primary chain, chosen deliberately in ADR-001 — it is materially thinner, and attribution is
the product.
**Why it matters.** If TRON hot-wallet coverage is poor, `CONFIRMED` attribution mostly fails on
the chain that matters most, and the deposit-address heuristic has nothing confirmed to sweep
*to* — collapsing the chained inference in
[VASP_IDENTIFICATION.md §4](VASP_IDENTIFICATION.md).
**Resolve by:** doing the curation work **early in Phase 7, before building the engine around
it**. Major exchange TRON hot wallets are identifiable by inspection — very high volume,
consistent sweep patterns, publicly discussed. Fifty verified addresses would be sufficient.
**If coverage genuinely cannot be assembled:** this is the one finding that would justify
revisiting ADR-001 and leading the demo with Ethereum instead. Better to discover it in week one
than in week four.

### OQ-18 · How does a trace report an address it could not fetch? — **ANSWERED**
**Answered 2026-09-05 by ADR-019:** a seventh termination reason, `DATA_UNAVAILABLE`. The
cheaper JSONB-degradation option was rejected for making the model less honest in the one place
it cannot afford to be. Original framing follows.
**Raised 2026-09-05, while wiring Phase 6.** Retrieval fetches only the root address, so a
multi-hop trace must fetch each address it discovers. When that fetch fails — a missing fixture,
a provider outage, a rate limit — the tracing engine currently sees no outflow and terminates the
node as `NO_OUTFLOW`.
**Why it matters.** `NO_OUTFLOW` asserts "nothing left this address", which is a finding. "We
could not look" is the opposite of a finding, and presenting one as the other is precisely the
silent degradation principle 12 forbids. On a fixture demo this is the *common* case, not an
edge case.
**Options.** Add a `DATA_UNAVAILABLE` termination reason (needs a migration, and all migrations
are front-loaded per Phase 2) · carry it as a per-node degradation flag alongside the existing
reason · fail the whole run when any discovered address cannot be fetched (safe, but a single
rate limit then costs the entire trace).
**Resolve by:** an ADR, before the TRACING stage is wired into `worker.py`. This blocks the
pipeline, not the engines — every stage it would call is built and tested.

### OQ-09 · Deposit-heuristic thresholds
`sweep_consistency > 0.95`, `dwell < 1 h`, `balance_retention ≈ 0`, decision cut-offs at 0.7 and
0.4. All reasoned, none calibrated.
**Resolve by:** measuring against known deposit addresses and known look-alikes once the label
set exists. **Prioritise precision over recall** — this is the number that decides whether a
legal request goes to the right institution.
*Status 2026-09-05:* implemented as six weighted signals in `attribution/decision.py` at exactly
these defaults, versioned as engine `1.0.0` and marked in code as uncalibrated. Still unmeasured
— it needs the label set from OQ-07.

---

## Blocking Phase 9 — ML *(only if ML is built)*

### OQ-10 · Where do hard negatives come from?
**Why it matters.** Payment processors, OTC desks, and custodial services are the look-alikes
that cost us precision, and they are scarce in any dataset we can assemble
([LIMITATIONS.md §7](LIMITATIONS.md)). A classifier trained without them will be confidently
wrong on exactly the cases that matter.
**Resolve by:** manual identification of a modest set, or accept the limitation explicitly, cap
the model's confidence, and say so.

### OQ-11 · Is the classifier worth building at all?
**Why it matters.** The deterministic heuristic already delivers the attribution. The classifier
adds precision at the boundary — and the labels are bootstrapped from the heuristic itself, so
the gain may be small.
**Resolve by:** measuring the heuristic's precision at the end of Phase 7. **If it is already
above 0.95, skip Phase 9** and spend the time on the frontend or the demo. That would be a
better project, and a more interesting answer to give a judge who asks why there is no model.

---

## Blocking Phase 11 — Reports

### OQ-12 · ReportLab or WeasyPrint? — **ANSWERED**
**Answered 2026-09-05 by ADR-020: ReportLab.** A fresh clone must be able to generate a report
with no system packages installed. Original framing follows.
**Trade-off.** ReportLab gives precise programmatic layout and no system dependencies, but PDF
layout in code is slow to write. WeasyPrint renders HTML/CSS — far faster to iterate, and the
report template could share styling with the frontend — but adds native system dependencies to
the Docker image.
**Recommendation to validate:** WeasyPrint, for iteration speed, unless the container
dependencies prove painful.

### OQ-13 · Use an LLM for report narrative at all? — **ANSWERED**
**Answered 2026-09-05 by ADR-021: no.** Templates only; `NarrativeSource.LLM` stays in the
schema and nothing writes it. Original framing follows.
**Why it matters.** [LIMITATIONS.md §8](LIMITATIONS.md) already recommends template mode for
anything entering a case file. If the recommendation is always "use templates", the LLM path is
a demo feature carrying real risk and real implementation cost (placeholder validation, regex
rejection, tier-language checking, fallback — all of which must be tested).
**Resolve by:** deciding whether the narrative quality justifies it. **A defensible answer is
"no, and here is why"** — which is itself a strong position to present.

---

## Blocking Phase 2 — Backend / Phase 12 — Security

### OQ-14 · Local accounts only, or is SSO expected?
Current design assumes local accounts with Argon2 and JWT. A real police deployment would likely
need integration with an existing directory.
**Resolve by:** local accounts for the MVP is almost certainly right; confirm that no judge-
facing claim implies otherwise, and note the integration path in
[FUTURE_SCOPE.md](FUTURE_SCOPE.md).

---

## Blocking Phase 15 — Demo

### OQ-15 · Which real addresses does the demo use?
**Requirements.** Publicly documented as fraud-linked (OFAC designations, published incident
reports, open research). Multi-hop fund flow. At least one terminating at an identifiable
exchange. **At least one honestly unattributable** — the example that earns credibility. Ideally
on TRON, with USDT.
**Why it matters.** This choice determines how good the demo is more than any code written
after Phase 10. Do not leave it to the last week.
**Resolve by:** researching candidates during Phase 7, while curating labels — the two tasks
share the same source material.

---

## Project-level

### OQ-16 · Team size and available time
Every estimate in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) assumes four people working
in parallel tracks. With fewer, the cut list in [MVP_SCOPE.md §6](MVP_SCOPE.md) applies in
order, and **Ethereum support is the sixth thing to go** — TRON alone still answers PS26183.
**Resolve by:** deciding now, honestly, and choosing the scope that fits rather than discovering
it in week four.

### OQ-17 · Should the MVP ship Ethereum at all?
Reopened deliberately, because it is the largest optional scope in the project. Ethereum earns
its place by proving the adapter abstraction and by having better label coverage; it costs a
second provider integration, a second label curation effort, and the tighter of the two rate
limits.
**Resolve by:** a checkpoint at the end of Phase 3. If TRON alone is not fully working by then,
drop Ethereum without hesitation. **A complete, honest, single-chain system demonstrates the
problem statement better than two half-finished ones**, and the adapter interface means adding
Ethereum later costs one file.

---

## Deliberately not open

For the avoidance of doubt, these are **settled** and should not be reopened without a
superseding ADR: the three-tier attribution model (ADR-005) · haircut taint (ADR-004) ·
deterministic risk scoring (ADR-006) · service-boundary termination (ADR-010) · no victim PII
(ADR-011) · PostgreSQL only (ADR-003) · fixture-first demo (ADR-009).

These are the product's integrity guarantees. Everything above is a detail; these are the
design.
